import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from node_definitions.instance import (  # noqa: E402
    definition_data_from_properties,
    definition_properties_from_data,
    normalize_definition_properties,
)


class NodeDefinitionInstanceTest(unittest.TestCase):
    def test_round_trips_definition_data_through_neo4j_properties(self):
        data = {
            "definition_id": "semt.reconciliation",
            "definition_version": 1,
            "configuration_status": "unconfigured",
            "implementation": {
                "kind": "semt",
                "operation": "reconciliation",
                "service_id": "",
                "parameters": {"deduplicate": False},
            },
        }

        properties = definition_properties_from_data(data)
        restored = definition_data_from_properties(properties)

        self.assertEqual(data, restored)
        self.assertIsInstance(properties["implementation_json"], str)
        self.assertEqual(
            data["implementation"],
            json.loads(properties["implementation_json"]),
        )

    def test_normalizer_removes_nested_map_before_neo4j_write(self):
        properties = {
            "definition_id": "semt.extension",
            "definition_version": "2",
            "configuration_status": "not-a-status",
            "implementation": {"kind": "semt"},
        }

        normalize_definition_properties(properties)

        self.assertNotIn("implementation", properties)
        self.assertNotIn("configuration_status", properties)
        self.assertEqual(2, properties["definition_version"])
        self.assertEqual({"kind": "semt"}, json.loads(properties["implementation_json"]))

    def test_round_trips_moose_configuration_without_storing_secrets(self):
        data = {
            "definition_id": "moose.analysis",
            "definition_version": 1,
            "configuration_status": "valid",
            "implementation": {
                "kind": "moose",
                "operation": "text_ner",
                "schema": "dpv_pd",
                "parameters": {},
                "llm": {"provider": "openrouter", "model": "test/model"},
                "connection_ref": "default-moose",
            },
        }

        restored = definition_data_from_properties(
            definition_properties_from_data(data)
        )

        self.assertEqual(data, restored)

    def test_legacy_node_has_no_definition_properties(self):
        properties = {"label": "Legacy", "implementation": {"ignored": True}}

        normalize_definition_properties(properties)

        self.assertEqual({"label": "Legacy"}, properties)
        self.assertEqual({}, definition_data_from_properties(properties))


if __name__ == "__main__":
    unittest.main()
