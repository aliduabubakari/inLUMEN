from __future__ import annotations

from flask import Blueprint, jsonify, make_response, request

from auth_middleware import require_auth

from .catalog import SemTCatalogService, get_semt_catalog_service


def create_semt_blueprint(
    catalog_service: SemTCatalogService | None = None,
) -> Blueprint:
    semt = Blueprint("semt", __name__)

    def active_service() -> SemTCatalogService:
        return catalog_service or get_semt_catalog_service()

    @semt.route(
        "/api/semt/catalog/<catalog_name>",
        methods=["GET", "OPTIONS"],
    )
    @require_auth
    def get_catalog(catalog_name: str):
        if request.method == "OPTIONS":
            return make_response("", 200)
        if catalog_name not in {"setup", "modifications", "reconciliators", "extenders", "export"}:
            return jsonify({"error": f"Unknown SemT catalog: {catalog_name}"}), 404
        force_refresh = str(request.args.get("refresh") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        catalog = active_service().get_catalog(
            catalog_name,
            force_refresh=force_refresh,
        )
        return jsonify(catalog.to_dict()), 200

    @semt.route("/api/semt/validate", methods=["POST", "OPTIONS"])
    @require_auth
    def validate_configuration():
        if request.method == "OPTIONS":
            return make_response("", 200)
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            payload = {}
        result = active_service().validate_implementation(
            str(payload.get("definition_id") or "").strip(),
            payload.get("implementation"),
        )
        return jsonify(result), 200

    return semt
