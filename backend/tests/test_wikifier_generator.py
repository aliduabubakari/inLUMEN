import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generators import generate_runtime_artifacts  # noqa: E402
from wikifier.validation import validate_wikifier_implementation  # noqa: E402


def wikifier_step():
    return {
        "flow_id": "wikify",
        "definition_id": "wikifier.annotation",
        "definition_version": 1,
        "configuration_status": "valid",
        "implementation": {
            "kind": "wikifier",
            "operation": "annotation",
            "parameters": {
                "source_column": "Text",
                "language": "en",
                "threshold": 0.8,
                "output_mode": "compact_and_raw",
            },
            "connection_ref": "default-wikifier",
        },
    }


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "annotations": [
                {
                    "title": "Oslo",
                    "url": "https://en.wikipedia.org/wiki/Oslo",
                    "dbPediaIri": "http://dbpedia.org/resource/Oslo",
                    "wikiDataClassIds": ["Q515"],
                }
            ],
        }


class FakeRequests(types.ModuleType):
    def __init__(self):
        super().__init__("requests")
        self.calls = []

    def post(self, url, data, timeout):
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        return FakeResponse()


class WikifierGeneratorTest(unittest.TestCase):
    def test_validation_requires_source_column_and_connection(self):
        result = validate_wikifier_implementation(
            {
                "kind": "wikifier",
                "operation": "annotation",
                "parameters": {
                    "source_column": "",
                    "language": "en",
                    "threshold": 0.8,
                    "output_mode": "compact_and_raw",
                },
                "connection_ref": "",
            }
        )

        self.assertEqual("unconfigured", result["status"])
        self.assertIn("Source column is required.", result["errors"])
        self.assertIn("Connection profile is required.", result["errors"])

    def test_generation_is_deterministic_and_contains_no_user_key_secret(self):
        first = generate_runtime_artifacts(wikifier_step(), {})
        second = generate_runtime_artifacts(wikifier_step(), {})

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
                "Dockerfile.wikify",
                "node-manifest.json",
                "image-build-manifest.json",
            },
            set(files),
        )
        compile(files["main.py"], "main.py", "exec")
        self.assertIn("requests==2.32.5", files["requirements.txt"])
        self.assertIn("FROM python:3.11-slim", files["Dockerfile.wikify"])
        self.assertIn("WIKIFIER_USER_KEY", files["main.py"])
        self.assertNotIn("insert your user key here", files["main.py"])
        self.assertNotIn("secret-user-key", files["main.py"])
        self.assertNotIn("secret-user-key", files["node-manifest.json"])

        manifest = json.loads(files["node-manifest.json"])
        self.assertEqual("wikifier.annotation", manifest["definition_id"])
        self.assertEqual(first.image_reference, manifest["image"]["reference"])
        self.assertIn("/inlumen/wikifier-wikify:", first.image_reference)
        self.assertEqual(["json"], manifest["data_contract"]["output_encodings"])

    def test_generated_runtime_posts_to_wikifier_and_adds_annotation_columns(self):
        bundle = generate_runtime_artifacts(wikifier_step(), {})
        source = next(item.content for item in bundle.files if item.filename == "main.py")

        fake_requests = FakeRequests()
        previous_requests = sys.modules.get("requests")
        sys.modules["requests"] = fake_requests
        previous_key = os.environ.get("WIKIFIER_USER_KEY")
        os.environ["WIKIFIER_USER_KEY"] = "secret-user-key"
        try:
            namespace = {"__name__": "generated_wikifier_runtime"}
            exec(compile(source, "main.py", "exec"), namespace)

            with tempfile.TemporaryDirectory() as temp_dir:
                input_path = Path(temp_dir) / "input.csv"
                output_path = Path(temp_dir) / "output.json"
                pd.DataFrame([{"Text": "Oslo is the capital of Norway."}]).to_csv(
                    input_path,
                    index=False,
                )

                records = namespace["load_records"](input_path)
                result = namespace["execute_operation"](records)
                namespace["write_records"](result, output_path)
                payload = json.loads(output_path.read_text(encoding="utf-8"))
        finally:
            if previous_requests is None:
                sys.modules.pop("requests", None)
            else:
                sys.modules["requests"] = previous_requests
            if previous_key is None:
                os.environ.pop("WIKIFIER_USER_KEY", None)
            else:
                os.environ["WIKIFIER_USER_KEY"] = previous_key

        self.assertEqual(1, len(fake_requests.calls))
        self.assertEqual(
            "https://www.wikifier.org/annotate-article",
            fake_requests.calls[0]["url"],
        )
        self.assertEqual("secret-user-key", fake_requests.calls[0]["data"]["userKey"])
        record = payload["records"][0]
        self.assertEqual(["Oslo"], record["wikifier_titles"])
        self.assertEqual(["Q515"], record["wikifier_wikidata_ids"])
        self.assertEqual("Oslo", record["wikifier_raw_json"]["annotations"][0]["title"])


if __name__ == "__main__":
    unittest.main()
