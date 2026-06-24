import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generators import generate_runtime_artifacts  # noqa: E402
from node_definitions.instance import (  # noqa: E402
    definition_data_from_properties,
    definition_properties_from_data,
)


def modification_step():
    return {
        "flow_id": "12",
        "definition_id": "semt.modification",
        "definition_version": 1,
        "configuration_status": "valid",
        "implementation": {
            "kind": "semt",
            "operation": "modification",
            "service_id": "dataCleaning",
            "parameters": {
                "column_name": "Name",
                "operationType": "toLowercase",
            },
            "connection_ref": "default-semt",
        },
    }


def reconciliation_step():
    return {
        "flow_id": "reconcile",
        "definition_id": "semt.reconciliation",
        "definition_version": 1,
        "configuration_status": "valid",
        "implementation": {
            "kind": "semt",
            "operation": "reconciliation",
            "service_id": "wikidataOpenRefine",
            "parameters": {
                "column_name": "City",
                "optional_columns": [],
                "deduplicate": False,
            },
            "connection_ref": "default-semt",
        },
    }


class FakeModificationManager:
    def __init__(self, base_url=None, token=None):
        pass

    def modify(self, table, column_name, modifier_name, props, debug=False):
        return table, {}


class SemTGeneratorTest(unittest.TestCase):
    def test_generation_is_deterministic_and_uses_python_runtime(self):
        first = generate_runtime_artifacts(modification_step(), {})
        second = generate_runtime_artifacts(modification_step(), {})

        self.assertEqual(first.configuration_hash, second.configuration_hash)
        self.assertEqual(
            [(item.filename, item.content) for item in first.files],
            [(item.filename, item.content) for item in second.files],
        )
        files = {item.filename: item.content for item in first.files}
        self.assertEqual(
            {
                "main.py",
                "requirements.txt",
                "Dockerfile.12",
                "node-manifest.json",
                "image-build-manifest.json",
            },
            set(files),
        )
        compile(files["main.py"], "main.py", "exec")
        self.assertIn("FROM python:3.11-slim", files["Dockerfile.12"])
        self.assertIn(
            "I2T-library.git",
            files["requirements.txt"],
        )
        self.assertIn("ipython==9.14.1", files["requirements.txt"])

        manifest = json.loads(files["node-manifest.json"])
        self.assertEqual(first.configuration_hash, manifest["configuration_hash"])
        self.assertEqual(["python", "/app/main.py"], manifest["entrypoint"])
        self.assertEqual(["csv", "json"], manifest["data_contract"]["input_encodings"])
        self.assertEqual(first.image_reference, manifest["image"]["reference"])
        self.assertNotIn(":latest", first.image_reference)
        self.assertTrue(
            first.image_reference.endswith(
                first.configuration_hash.removeprefix("sha256:")[:12]
            )
        )

        build_manifest = json.loads(files["image-build-manifest.json"])
        self.assertEqual(first.image_reference, build_manifest["image"])
        self.assertEqual(
            ["main.py", "requirements.txt", "node-manifest.json"],
            build_manifest["context_files"],
        )

        dockerfile_artifact = first.dockerfile_artifact()
        self.assertEqual(first.image_reference, dockerfile_artifact["image"])
        self.assertEqual(
            build_manifest["context_files"],
            dockerfile_artifact["files"],
        )

    def test_invalid_configuration_is_rejected(self):
        step = modification_step()
        step["implementation"]["parameters"] = {}

        with self.assertRaisesRegex(ValueError, "Target column is required"):
            generate_runtime_artifacts(step, {})

    def test_reconciliation_runtime_normalizes_column_metadata_for_extension(self):
        bundle = generate_runtime_artifacts(reconciliation_step(), {})
        source = next(item.content for item in bundle.files if item.filename == "main.py")

        self.assertIn('"id": "None:"', source)
        self.assertIn('column["metadata"]', source)
        self.assertIn("deduplicate=True", source)
        self.assertIn("_resolve_api_base_url", source)

    def test_generated_modification_executes_csv_contract(self):
        bundle = generate_runtime_artifacts(modification_step(), {})
        source = next(item.content for item in bundle.files if item.filename == "main.py")

        fake_package = types.ModuleType("semt_py")
        fake_auth = types.ModuleType("semt_py.auth_manager")
        fake_auth.AuthManager = object
        fake_extension = types.ModuleType("semt_py.extension_manager")
        fake_extension.ExtensionManager = object
        fake_modification = types.ModuleType("semt_py.modification_manager")
        fake_modification.ModificationManager = FakeModificationManager
        fake_reconciliation = types.ModuleType("semt_py.reconciliation_manager")
        fake_reconciliation.ReconciliationManager = object
        fake_table = types.ModuleType("semt_py.table_manager")
        fake_table.TableManager = object
        fake_utils = types.ModuleType("semt_py.utils")
        fake_utils.Utility = object
        replacements = {
            "semt_py": fake_package,
            "semt_py.auth_manager": fake_auth,
            "semt_py.extension_manager": fake_extension,
            "semt_py.modification_manager": fake_modification,
            "semt_py.reconciliation_manager": fake_reconciliation,
            "semt_py.table_manager": fake_table,
            "semt_py.utils": fake_utils,
        }
        previous = {name: sys.modules.get(name) for name in replacements}
        sys.modules.update(replacements)
        try:
            namespace = {"__name__": "generated_semt_runtime"}
            exec(compile(source, "main.py", "exec"), namespace)
        finally:
            for name, original in previous.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.csv"
            output_path = Path(temp_dir) / "output.csv"
            pd.DataFrame(
                [{"Name": "ALICE", "Country": "NO"}, {"Name": "BOB", "Country": "GH"}]
            ).to_csv(input_path, index=False)

            table = namespace["load_table"](input_path)
            result = namespace["execute_operation"](table)
            namespace["write_table"](result, output_path)
            output = pd.read_csv(output_path)

        self.assertEqual(["alice", "bob"], output["Name"].tolist())
        self.assertIn("__inlumen_table_metadata", output.columns)

    def test_csv_contract_preserves_cell_metadata(self):
        bundle = generate_runtime_artifacts(modification_step(), {})
        source = next(item.content for item in bundle.files if item.filename == "main.py")

        modules = {
            "semt_py": types.ModuleType("semt_py"),
            "semt_py.auth_manager": types.ModuleType("semt_py.auth_manager"),
            "semt_py.extension_manager": types.ModuleType("semt_py.extension_manager"),
            "semt_py.modification_manager": types.ModuleType("semt_py.modification_manager"),
            "semt_py.reconciliation_manager": types.ModuleType("semt_py.reconciliation_manager"),
            "semt_py.table_manager": types.ModuleType("semt_py.table_manager"),
            "semt_py.utils": types.ModuleType("semt_py.utils"),
        }
        modules["semt_py.auth_manager"].AuthManager = object
        modules["semt_py.extension_manager"].ExtensionManager = object
        modules["semt_py.modification_manager"].ModificationManager = FakeModificationManager
        modules["semt_py.reconciliation_manager"].ReconciliationManager = object
        modules["semt_py.table_manager"].TableManager = object
        modules["semt_py.utils"].Utility = object
        previous = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        try:
            namespace = {"__name__": "generated_semt_runtime"}
            exec(compile(source, "main.py", "exec"), namespace)
        finally:
            for name, original in previous.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        table = namespace["dataframe_to_table"](pd.DataFrame([{"Name": "Alice"}]))
        table["rows"]["r0"]["cells"]["Name"]["metadata"] = [
            {"id": "wd:Q1", "score": 1, "match": True}
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "handoff.csv"
            namespace["write_table"](table, path)
            restored = namespace["load_table"](path)

        self.assertEqual(
            "wd:Q1",
            restored["rows"]["r0"]["cells"]["Name"]["metadata"][0]["id"],
        )

    def test_artifact_status_becomes_stale_after_configuration_change(self):
        bundle = generate_runtime_artifacts(modification_step(), {})
        data = {
            **modification_step(),
            "generated_artifact": {
                **bundle.to_dict(include_content=False),
                "status": "current",
            },
        }
        properties = definition_properties_from_data(data)
        restored = definition_data_from_properties(properties)
        self.assertEqual("current", restored["generated_artifact"]["status"])

        changed = dict(properties)
        changed["implementation_json"] = json.dumps(
            {
                **modification_step()["implementation"],
                "parameters": {"column": "Other"},
            },
            sort_keys=True,
        )
        stale = definition_data_from_properties(changed)
        self.assertEqual("stale", stale["generated_artifact"]["status"])


if __name__ == "__main__":
    unittest.main()
