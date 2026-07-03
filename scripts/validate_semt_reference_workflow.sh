#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
I2T_BACKEND_DIR="${I2T_BACKEND_DIR:-${ROOT_DIR}/../../New_Semtui_pipeline_2025/I2T-backend}"
I2T_PORT="${I2T_PORT:-3003}"
STUB_PORT="${STUB_PORT:-4010}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/inlumen-semt-validation.XXXXXX")"
STUB_PID=""
I2T_PID=""
if [[ -x "/opt/homebrew/bin/argo" ]]; then
  ARGO_BIN="${ARGO_BIN:-/opt/homebrew/bin/argo}"
else
  ARGO_BIN="${ARGO_BIN:-$(command -v argo)}"
fi
KUBECTL_BIN="${KUBECTL_BIN:-$(command -v kubectl)}"
KUBECONFORM_BIN="${KUBECONFORM_BIN:-$(command -v kubeconform || true)}"

cleanup() {
  if [[ -n "${I2T_PID}" ]]; then
    kill "${I2T_PID}" 2>/dev/null || true
    wait "${I2T_PID}" 2>/dev/null || true
  fi
  if [[ -n "${STUB_PID}" ]]; then
    kill "${STUB_PID}" 2>/dev/null || true
    wait "${STUB_PID}" 2>/dev/null || true
  fi
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

wait_for_url() {
  local url="$1"
  local attempts="${2:-60}"
  local index
  for ((index = 0; index < attempts; index += 1)); do
    if curl --fail --silent --show-error "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for ${url}" >&2
  return 1
}

require_available_port() {
  local port="$1"
  local label="$2"
  if ! python - "${port}" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", port))
PY
  then
    echo "${label} port ${port} is already in use. Set a different port and retry." >&2
    return 1
  fi
}

if [[ ! -d "${I2T_BACKEND_DIR}" ]]; then
  echo "I2T backend not found at ${I2T_BACKEND_DIR}" >&2
  exit 1
fi

require_available_port "${I2T_PORT}" "I2T"
require_available_port "${STUB_PORT}" "Wikidata stub"

(
  cd "${I2T_BACKEND_DIR}"
  STUB_PORT="${STUB_PORT}" npm run start-stub-services
) >"${WORK_DIR}/wikidata-stubs.log" 2>&1 &
STUB_PID=$!
wait_for_url "http://127.0.0.1:${STUB_PORT}/health"

(
  cd "${I2T_BACKEND_DIR}"
  ENV=PROD \
  PORT="${I2T_PORT}" \
  JWT_SECRET="offline-validation-secret" \
  JWT_EXPIRES_IN="300 days" \
  FRONTEND_URL="http://inlumen-frontend:8080" \
  WIKIDATA="http://127.0.0.1:${STUB_PORT}/reconcile" \
  WD_SPARQL="http://127.0.0.1:${STUB_PORT}/sparql?query=" \
  npm run start-prod
) >"${WORK_DIR}/i2t-backend.log" 2>&1 &
I2T_PID=$!
wait_for_url "http://127.0.0.1:${I2T_PORT}/health"
wait_for_url "http://127.0.0.1:${I2T_PORT}/ready"

python "${ROOT_DIR}/scripts/generate_semt_reference_artifacts.py" \
  --output "${WORK_DIR}/generated" \
  >"${WORK_DIR}/generation.json"

RECON_IMAGE="$(
  python -c 'import json,sys; print(json.load(open(sys.argv[1]))["reconcile"]["image"])' \
    "${WORK_DIR}/generated/images.json"
)"
EXTEND_IMAGE="$(
  python -c 'import json,sys; print(json.load(open(sys.argv[1]))["extend"]["image"])' \
    "${WORK_DIR}/generated/images.json"
)"

docker build \
  --file "${WORK_DIR}/generated/reconcile/Dockerfile.reconcile" \
  --tag "${RECON_IMAGE}" \
  "${WORK_DIR}/generated/reconcile"
docker build \
  --file "${WORK_DIR}/generated/extend/Dockerfile.extend" \
  --tag "${EXTEND_IMAGE}" \
  "${WORK_DIR}/generated/extend"

mkdir -p "${WORK_DIR}/data"
cp "${ROOT_DIR}/backend/tests/fixtures/semt-cities.csv" "${WORK_DIR}/data/input.csv"

docker run --rm \
  --volume "${WORK_DIR}/data:/data" \
  --env INLUMEN_INPUT_PATH=/data/input.csv \
  --env INLUMEN_OUTPUT_PATH=/data/reconciled.json \
  --env SEMT_API_BASE_URL="http://host.docker.internal:${I2T_PORT}" \
  --env SEMT_API_USERNAME=test \
  --env SEMT_API_PASSWORD=test \
  "${RECON_IMAGE}"

cp "${WORK_DIR}/data/reconciled.json" "${WORK_DIR}/data/input.json"
docker run --rm \
  --volume "${WORK_DIR}/data:/data" \
  --env INLUMEN_INPUT_PATH=/data/input.json \
  --env INLUMEN_OUTPUT_PATH=/data/output.json \
  --env SEMT_API_BASE_URL="http://host.docker.internal:${I2T_PORT}" \
  --env SEMT_API_USERNAME=test \
  --env SEMT_API_PASSWORD=test \
  "${EXTEND_IMAGE}"

python - "${WORK_DIR}/data/output.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["kind"] == "inlumen.table"
assert payload["contract_version"] == "1"
assert [row["City"] for row in payload["records"]] == ["Oslo", "Accra"]
assert [row["country (P17)"] for row in payload["records"]] == ["Norway", "Ghana"]
assert [row["population (P1082)"] for row in payload["records"]] == ["709037", "2388000"]
for row in payload["semt_table"]["rows"].values():
    assert row["cells"]["City"]["metadata"][0]["id"].startswith("wd:Q")
print("Reference CSV produced reconciled and extended inlumen.table@1 JSON.")
PY

"${ARGO_BIN}" lint --offline "${WORK_DIR}/generated/workflow.yaml"
if [[ -n "${KUBECONFORM_BIN}" ]]; then
  "${KUBECTL_BIN}" kustomize "${I2T_BACKEND_DIR}/deploy/k8s/base" \
    | "${KUBECONFORM_BIN}" -strict -summary
  "${KUBECTL_BIN}" kustomize "${ROOT_DIR}/deploy/argo" \
    | "${KUBECONFORM_BIN}" -strict -summary
else
  echo "kubeconform is required for cluster-independent Kubernetes validation." >&2
  exit 1
fi

if rg -n 'localhost|127\.0\.0\.1|host\.docker\.internal|:latest|test/test' \
  "${WORK_DIR}/generated/workflow.yaml"; then
  echo "Generated Workflow contains a forbidden deployment value." >&2
  exit 1
fi

echo "SemT reference workflow validation completed successfully."
