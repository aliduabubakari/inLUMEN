"""Authenticated internal API routes for Moose catalog and validation."""

from __future__ import annotations

from collections.abc import Callable

from flask import Blueprint, jsonify, make_response, request

from auth_middleware import require_auth

from .catalog import get_moose_catalog
from .schemas import MooseCatalog
from .validation import validate_moose_implementation


def create_moose_blueprint(
    catalog_provider: Callable[[], MooseCatalog] | None = None,
) -> Blueprint:
    moose = Blueprint("moose", __name__)
    active_catalog = catalog_provider or get_moose_catalog

    @moose.route("/api/moose/catalog", methods=["GET", "OPTIONS"])
    @require_auth
    def get_catalog():
        if request.method == "OPTIONS":
            return make_response("", 200)
        force_refresh = str(request.args.get("refresh") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        catalog = (
            get_moose_catalog(force_refresh=force_refresh)
            if catalog_provider is None
            else active_catalog()
        )
        return jsonify(catalog.to_dict()), 200

    @moose.route("/api/moose/validate", methods=["POST", "OPTIONS"])
    @require_auth
    def validate_implementation():
        if request.method == "OPTIONS":
            return make_response("", 200)
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            payload = {}
        implementation = payload.get("implementation", payload)
        return jsonify(
            validate_moose_implementation(implementation, active_catalog())
        ), 200

    return moose
