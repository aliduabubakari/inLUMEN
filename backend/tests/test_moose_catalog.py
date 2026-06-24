import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moose.catalog import (  # noqa: E402
    LOCAL_POLICY_PACKS,
    LOCAL_PROFILES,
    LOCAL_SCHEMAS,
    get_moose_catalog,
)
from moose.client import MooseClientError, MooseMetadataClient  # noqa: E402
from moose.routes import create_moose_blueprint  # noqa: E402
from moose.validation import validate_moose_implementation  # noqa: E402


class StubClient:
    configured = True

    def __init__(self, payloads=None, errors=None):
        self.payloads = payloads or {}
        self.errors = errors or {}
        self.calls = []

    def get_json(self, path, *, force=False):
        self.calls.append((path, force))
        if path in self.errors:
            raise self.errors[path]
        return self.payloads[path]


def configured(operation, *, schema="", parameters=None):
    return {
        "kind": "moose",
        "operation": operation,
        "schema": schema,
        "parameters": parameters or {},
        "llm": {"provider": "openrouter", "model": "test/model"},
        "connection_ref": "default-moose",
    }


class MooseCatalogTest(unittest.TestCase):
    def setUp(self):
        self.previous_auth_enabled = os.environ.get("AUTH_ENABLED")
        os.environ["AUTH_ENABLED"] = "false"

    def tearDown(self):
        if self.previous_auth_enabled is None:
            os.environ.pop("AUTH_ENABLED", None)
        else:
            os.environ["AUTH_ENABLED"] = self.previous_auth_enabled

    def test_local_catalog_contains_one_node_family_and_five_operations(self):
        client = StubClient()
        client.configured = False
        catalog = get_moose_catalog(client)

        self.assertEqual("local-baseline", catalog.source)
        self.assertEqual(
            {
                "text_ner",
                "table_annotation",
                "table_cpa",
                "privacy_text",
                "privacy_table",
            },
            {operation.id for operation in catalog.operations},
        )
        cpa = next(
            operation for operation in catalog.operations if operation.id == "table_cpa"
        )
        self.assertEqual("supports_cpa", cpa.schema_capability)
        self.assertIn(
            "subject_column", {parameter.name for parameter in cpa.parameters}
        )

    def test_remote_metadata_drives_capabilities_and_profile_options(self):
        client = StubClient(
            {
                "/schemas": {
                    "schemas": [
                        {
                            "name": "remote_text",
                            "label": "Remote Text",
                            "supports_text": True,
                            "supports_table": False,
                            "supports_cpa": False,
                            "prefilter_types": True,
                            "score_mode": "sparse",
                        }
                    ]
                },
                "/privacy/profiles": {
                    "profiles": [
                        {
                            "id": "remote_profile",
                            "label": "Remote Profile",
                            "description": "Remote",
                            "defaults": {},
                        }
                    ]
                },
                "/policy-packs": {"policy_packs": ["remote_pack"]},
            }
        )

        catalog = get_moose_catalog(client)

        self.assertEqual("moose-api", catalog.source)
        self.assertEqual(["remote_text"], [schema.value for schema in catalog.schemas])
        privacy = next(
            operation
            for operation in catalog.operations
            if operation.id == "privacy_text"
        )
        profile = next(
            parameter
            for parameter in privacy.parameters
            if parameter.name == "profile"
        )
        self.assertEqual(["remote_profile"], [option.value for option in profile.options])

    def test_metadata_client_caches_success_and_supports_forced_refresh(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.payload

        client = MooseMetadataClient(
            base_url="http://moose.test",
            api_key="test",
            cache_ttl_seconds=300,
        )
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                Response(b'{"schemas": [{"name": "one"}]}'),
                Response(b'{"schemas": [{"name": "two"}]}'),
            ],
        ) as urlopen:
            first = client.get_json("/schemas")
            cached = client.get_json("/schemas")
            refreshed = client.get_json("/schemas", force=True)

        self.assertEqual(first, cached)
        self.assertEqual("two", refreshed["schemas"][0]["name"])
        self.assertEqual(2, urlopen.call_count)

    def test_remote_failure_uses_stale_then_local_metadata(self):
        stale_schemas = {"schemas": [LOCAL_SCHEMAS[0].to_dict()]}
        client = StubClient(
            payloads={
                "/privacy/profiles": {
                    "profiles": [profile.to_dict() for profile in LOCAL_PROFILES]
                },
                "/policy-packs": {
                    "policy_packs": [option.value for option in LOCAL_POLICY_PACKS]
                },
            },
            errors={
                "/schemas": MooseClientError(
                    "offline", stale_value=stale_schemas
                ),
            },
        )

        catalog = get_moose_catalog(client)

        self.assertIn("stale-cache", catalog.source)
        self.assertTrue(any("stale Moose schemas" in warning for warning in catalog.warnings))

    def test_all_operations_validate_and_incompatible_schema_is_rejected(self):
        client = StubClient()
        client.configured = False
        catalog = get_moose_catalog(client)
        cases = [
            configured("text_ner", schema="dpv_pd"),
            configured(
                "table_annotation",
                schema="sti",
                parameters={"sample_size": 50, "sample_strategy": "head"},
            ),
            configured(
                "table_cpa",
                schema="cpa",
                parameters={
                    "sample_size": 50,
                    "sample_strategy": "head",
                    "subject_column": "Person",
                    "target_columns": ["Country"],
                    "use_sti_signature_cache": True,
                    "debug": False,
                    "debug_preview_limit": 20,
                },
            ),
            configured(
                "privacy_text",
                parameters={
                    "profile": "balanced",
                    "policy_pack": "gdpr_basic",
                    "analysis_mode": "hybrid",
                    "include_extraction": True,
                    "text_schema": "dpv_pd",
                },
            ),
            configured(
                "privacy_table",
                parameters={
                    "sample_size": 50,
                    "sample_strategy": "head",
                    "profile": "balanced",
                    "policy_pack": "gdpr_basic",
                    "analysis_mode": "hybrid",
                    "include_extraction": True,
                    "table_schema": "dpv_pd",
                    "scan_schema": "dpv_pd",
                },
            ),
        ]

        for implementation in cases:
            with self.subTest(operation=implementation["operation"]):
                result = validate_moose_implementation(implementation, catalog)
                self.assertEqual("valid", result["status"], result["errors"])

        invalid = validate_moose_implementation(
            configured("table_cpa", schema="dpv_pd", parameters={
                "sample_size": 50,
                "sample_strategy": "head",
                "subject_column": "Person",
                "target_columns": ["Country"],
            }),
            catalog,
        )
        self.assertEqual("invalid", invalid["status"])
        self.assertTrue(any("does not support" in error for error in invalid["errors"]))

    def test_secret_values_are_rejected(self):
        client = StubClient()
        client.configured = False
        catalog = get_moose_catalog(client)
        implementation = configured("text_ner", schema="dpv_pd")
        implementation["llm"]["api_key"] = "should-not-persist"

        result = validate_moose_implementation(implementation, catalog)

        self.assertEqual("invalid", result["status"])
        self.assertTrue(any("Secrets cannot be stored" in error for error in result["errors"]))

    def test_catalog_and_validation_routes_return_normalized_contracts(self):
        client = StubClient()
        client.configured = False
        catalog = get_moose_catalog(client)
        app = Flask(__name__)
        app.register_blueprint(create_moose_blueprint(lambda: catalog))
        http = app.test_client()

        catalog_response = http.get("/api/moose/catalog")
        validation_response = http.post(
            "/api/moose/validate",
            json={"implementation": configured("text_ner", schema="dpv_pd")},
        )

        self.assertEqual(200, catalog_response.status_code)
        self.assertEqual("moose", catalog_response.get_json()["family"])
        self.assertEqual(200, validation_response.status_code)
        self.assertEqual("valid", validation_response.get_json()["status"])


if __name__ == "__main__":
    unittest.main()
