# SemT Runtime Data Contract

Phase 3 introduced the file-based boundary for generated SemT nodes. Phase 4
binds that contract to Argo artifacts backed by the configured MinIO artifact
repository.

## Runtime Paths

Generated containers read `INLUMEN_INPUT_PATH` and write
`INLUMEN_OUTPUT_PATH`. The defaults are `/data/input.json` and
`/data/output.json`. The generated entrypoint also accepts `--input` and
`--output`.

## Logical Contract

Every SemT node consumes and produces one logical `inlumen.table` value.
Version 1 supports CSV and JSON encodings. The deployment contract accepts CSV
at workflow ingress, uses JSON for internal SemT handoffs, and emits JSON at
workflow egress.

The canvas `Input Data` node is the supported ingress boundary. When it is
connected directly to the first SemT node, it must contain exactly one CSV
file. The Input Data node does not produce a container image; generated Argo
workflows mount that uploaded MinIO object directly into the first SemT
container at `/data/input.csv`.

JSON is the preferred internal handoff because it preserves records and the
complete SemT table representation:

```json
{
  "schema_version": 1,
  "kind": "inlumen.table",
  "contract_version": "1",
  "records": [
    {
      "City": "Oslo",
      "Country": "Norway"
    }
  ],
  "semt_table": {
    "table": {},
    "columns": {},
    "rows": {}
  }
}
```

For ingress compatibility, JSON may also be a records array, an object with an
`items` or `records` array, or a native SemT table object.

## CSV Encoding

CSV is accepted as a normal table. SemT metadata is preserved using reserved
columns:

- `__inlumen_table_metadata` stores table and column metadata in the first row.
- `<column>__semt_metadata` stores cell metadata as JSON.

These reserved columns let a reconciliation node emit CSV that a later
extension node can consume without losing entity identifiers. Applications
should avoid source columns that use these reserved names.

## Credentials

Generated source stores only `connection_ref`. Remote reconciliation and
extension operations resolve credentials at runtime from:

```text
SEMT_API_BASE_URL
SEMT_API_USERNAME
SEMT_API_PASSWORD
```

Credentials are not written to the graph, generated source, requirements, or
node manifest.

## Generated Files

Each valid SemT node generates:

```text
main.py
requirements.txt
Dockerfile.<flow_id>
node-manifest.json
image-build-manifest.json
```

The manifest contains the generator version, data-contract version,
entrypoint, immutable runtime image reference, and a canonical configuration
hash. The build manifest records the Dockerfile and exact build-context files.
Editing the node after generation marks the stored artifact metadata as stale.

Generated sources and manifests are stored in the node's MinIO bucket. Images
are identified in an OCI registry namespace configured by
`INLUMEN_IMAGE_REGISTRY`; MinIO is not used as an image registry.

## Argo Transport

Generated SemT Workflows:

- reference `inlumen-artifact-repositories/minio`;
- bind a connected Input Data upload by its MinIO bucket and object key;
- retain the input object-key parameter for SemT-only graphs without a canvas
  Input Data boundary;
- parameterize the output object key;
- mount reconciliation ingress at `/data/input.csv`;
- publish reconciliation output from `/data/reconciled.json`;
- mount downstream JSON at `/data/input.json`;
- publish final JSON from `/data/output.json` without archive wrapping;
- resolve I2T through `http://semt-backend:3003`;
- resolve credentials from `semt-runtime-credentials`.

The current transport validator supports one linear SemT table chain. Fan-in,
fan-out, mixed non-SemT transport, and multiple table inputs are deferred.
