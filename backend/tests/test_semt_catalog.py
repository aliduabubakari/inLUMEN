import os
import sys
import unittest
from pathlib import Path

from flask import Flask


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semt.catalog import SemTCatalogService  # noqa: E402
from semt.client import SemTClientError  # noqa: E402
from semt.routes import create_semt_blueprint  # noqa: E402


class StubClient:
    configured = True

    def __init__(self, services=None, error=None):
        self.services = services or {}
        self.error = error
        self.calls = []

    def list_services(self, family, *, force_refresh=False):
        self.calls.append((family, force_refresh))
        if self.error:
            raise self.error
        return self.services.get(family, [])


class SemTCatalogTest(unittest.TestCase):
    def setUp(self):
        self.previous_auth_enabled = os.environ.get("AUTH_ENABLED")
        os.environ["AUTH_ENABLED"] = "false"

    def tearDown(self):
        if self.previous_auth_enabled is None:
            os.environ.pop("AUTH_ENABLED", None)
        else:
            os.environ["AUTH_ENABLED"] = self.previous_auth_enabled

    def test_modification_catalog_contains_eight_structured_operations(self):
        catalog = SemTCatalogService(StubClient()).get_catalog("modifications")

        self.assertEqual("modification", catalog.family)
        self.assertEqual(8, len(catalog.items))
        data_clean = next(item for item in catalog.items if item.id == "dataCleaning")
        self.assertEqual("select", data_clean.parameters[1].type)
        self.assertTrue(data_clean.parameters[1].required)

    def test_remote_catalogs_include_eight_reconcilers_with_context_columns(self):
        service = SemTCatalogService(StubClient(error=SemTClientError("offline")))
        reconciliators = service.get_catalog("reconciliators")
        extenders = service.get_catalog("extenders")

        self.assertEqual(8, len(reconciliators.items))
        alligator = next(item for item in reconciliators.items if item.id == "wikidataAlligator")
        context_columns = next(
            parameter for parameter in alligator.parameters if parameter.name == "additionalColumns"
        )
        self.assertEqual("column-list", context_columns.type)
        self.assertFalse(context_columns.required)
        self.assertFalse(
            any(
                parameter.name == "deduplicate"
                for catalog in (reconciliators, extenders)
                for item in catalog.items
                for parameter in item.parameters
            )
        )

    def test_unconfigured_remote_discovery_uses_local_adapters_without_warning(self):
        class UnconfiguredClient(StubClient):
            configured = False

        catalog = SemTCatalogService(UnconfiguredClient()).get_catalog("reconciliators")

        self.assertEqual("local-adapters", catalog.source)
        self.assertEqual((), catalog.warnings)

    def test_remote_catalog_is_intersected_with_supported_adapters(self):
        client = StubClient(
            {
                "reconciliators": [
                    {"id": "wikidataOpenRefine", "name": "Remote Wikidata"},
                    {"id": "unsupportedRemote", "name": "Unsupported"},
                ]
            }
        )
        catalog = SemTCatalogService(client).get_catalog("reconciliators")

        self.assertEqual("remote-intersection", catalog.source)
        self.assertEqual(["wikidataOpenRefine"], [item.id for item in catalog.items])
        self.assertEqual("Remote Wikidata", catalog.items[0].label)

    def test_remote_failure_falls_back_to_local_supported_adapters(self):
        client = StubClient(error=SemTClientError("SemT unavailable"))
        catalog = SemTCatalogService(client).get_catalog("extenders")

        self.assertEqual("local-fallback", catalog.source)
        self.assertEqual(11, len(catalog.items))
        self.assertIn("SemT unavailable", catalog.warnings)

    def test_configuration_validation_applies_service_constraints(self):
        service = SemTCatalogService(StubClient(error=SemTClientError("offline")))
        invalid = service.validate_implementation(
            "semt.reconciliation",
            {
                "service_id": "inTableLinker",
                "connection_ref": "default-semt",
                "parameters": {
                    "column_name": "City",
                },
            },
        )
        valid = service.validate_implementation(
            "semt.reconciliation",
            {
                "service_id": "inTableLinker",
                "connection_ref": "default-semt",
                "parameters": {
                    "column_name": "City",
                    "prefix": "wd",
                    "columnToReconcile": "ID",
                },
            },
        )

        self.assertEqual("invalid", invalid["status"])
        self.assertTrue(any("required" in error.lower() for error in invalid["errors"]))
        self.assertEqual({"status": "valid", "errors": []}, valid)

    def test_configuration_validation_does_not_require_connection_profile(self):
        service = SemTCatalogService(StubClient(error=SemTClientError("offline")))
        result = service.validate_implementation(
            "semt.modification",
            {
                "service_id": "textRows",
                "parameters": {"column_name": "col", "separator": ";"},
            },
        )

        self.assertEqual({"status": "valid", "errors": []}, result)

    def test_catalog_and_validation_routes_return_normalized_contracts(self):
        app = Flask(__name__)
        app.register_blueprint(
            create_semt_blueprint(
                SemTCatalogService(StubClient(error=SemTClientError("offline")))
            )
        )
        client = app.test_client()

        catalog_response = client.get("/api/semt/catalog/modifications")
        validation_response = client.post(
            "/api/semt/validate",
            json={
                "definition_id": "semt.modification",
                "implementation": {
                    "service_id": "textRows",
                    "connection_ref": "default-semt",
                    "parameters": {"column_name": "col", "separator": ";"},
                },
            },
        )

        self.assertEqual(200, catalog_response.status_code)
        self.assertEqual("modification", catalog_response.get_json()["family"])
        self.assertEqual(200, validation_response.status_code)
        self.assertEqual("valid", validation_response.get_json()["status"])


if __name__ == "__main__":
    unittest.main()
