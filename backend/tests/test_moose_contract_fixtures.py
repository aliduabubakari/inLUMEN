import json
import re
import unittest
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "moose"
EXPECTED_OPERATIONS = {
    "text_ner",
    "table_annotation",
    "table_cpa",
    "privacy_text",
    "privacy_table",
}
FORBIDDEN_SECRET_KEYS = {
    "api_key",
    "authorization",
    "deepinfra_api_key",
    "deepseek_api_key",
    "llm_api_key",
    "ollama_token",
    "openrouter_api_key",
    "x-api-key",
    "x-llm-api-key",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must contain a JSON object")
    return payload


def collect_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {
            str(key).lower()
            for key in value
        } | set().union(*(collect_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(collect_keys(item) for item in value))
    return set()


class MooseContractFixtureTest(unittest.TestCase):
    def test_records_clean_mainline_baseline_and_pinned_runtime(self):
        baseline = load_json(FIXTURE_ROOT / "baseline.json")

        self.assertEqual(
            "22efaf0d8cb15352147d6c43c5dfa5541360b8c5",
            baseline["moose"]["commit"],
        )
        self.assertEqual("origin/main", baseline["moose"]["ref"])
        self.assertRegex(
            baseline["generated_runtime"]["python_image"],
            r"^python:3\.12\.13-slim-bookworm@sha256:[0-9a-f]{64}$",
        )
        self.assertEqual("0.28.1", baseline["generated_runtime"]["httpx"])

    def test_operation_fixtures_cover_all_five_modes_without_secrets(self):
        fixtures = [
            load_json(path)
            for path in sorted((FIXTURE_ROOT / "operations").glob("*.json"))
        ]

        self.assertEqual(
            EXPECTED_OPERATIONS,
            {fixture["operation"] for fixture in fixtures},
        )
        for fixture in fixtures:
            with self.subTest(operation=fixture["operation"]):
                self.assertTrue(str(fixture["endpoint"]).startswith("/"))
                self.assertEqual("queued", fixture["queued_response"]["status"])
                self.assertEqual("completed", fixture["completed_job"]["status"])
                self.assertRegex(
                    fixture["queued_response"]["job_id"],
                    r"^[0-9a-f]{32}$",
                )
                self.assertEqual(
                    fixture["queued_response"]["job_id"],
                    fixture["completed_job"]["job_id"],
                )
                self.assertIsInstance(fixture["request"]["llm"]["provider"], str)
                self.assertIsInstance(fixture["request"]["llm"]["model"], str)
                self.assertFalse(
                    collect_keys(fixture) & FORBIDDEN_SECRET_KEYS,
                    f"{fixture['operation']} fixture contains a secret-shaped key",
                )

    def test_operation_specific_request_and_result_shapes(self):
        fixtures = {
            path.stem: load_json(path)
            for path in (FIXTURE_ROOT / "operations").glob("*.json")
        }

        text_ner = fixtures["text_ner"]
        self.assertEqual("/ner", text_ner["endpoint"])
        self.assertTrue(text_ner["request"]["text"])
        self.assertTrue(text_ner["request"]["schema"])
        self.assertIsInstance(
            text_ner["completed_job"]["result"]["entities"],
            list,
        )

        table_annotation = fixtures["table_annotation"]
        self.assertEqual("/tabular/annotate", table_annotation["endpoint"])
        self.assertTrue(table_annotation["request"]["sampled_rows"])
        self.assertIsInstance(
            table_annotation["completed_job"]["result"]["columns"],
            list,
        )

        table_cpa = fixtures["table_cpa"]
        self.assertEqual("/tabular/cpa", table_cpa["endpoint"])
        self.assertTrue(table_cpa["request"]["subject_column"])
        self.assertTrue(table_cpa["request"]["target_columns"])
        self.assertIsInstance(
            table_cpa["completed_job"]["result"]["relationships"],
            list,
        )

        for operation in ("privacy_text", "privacy_table"):
            fixture = fixtures[operation]
            result = fixture["completed_job"]["result"]
            task_kind = operation.removeprefix("privacy_")
            self.assertEqual("/privacy/analyze", fixture["endpoint"])
            self.assertEqual(task_kind, fixture["request"]["tasks"][0]["kind"])
            self.assertEqual(
                "moose.privacy.machine_report.v1",
                result["reports"]["machine_readable"]["schema_id"],
            )
            self.assertTrue(
                result["reports"]["human_readable"]["content"].startswith(
                    "# Privacy Analysis Report"
                )
            )

    def test_text_and_table_contract_examples_preserve_extensions(self):
        text_contract = load_json(
            FIXTURE_ROOT / "contracts" / "inlumen-text-v1.json"
        )
        table_contract = load_json(
            FIXTURE_ROOT / "contracts" / "inlumen-table-v1.json"
        )

        self.assertEqual("inlumen.text", text_contract["kind"])
        self.assertEqual("1", text_contract["contract_version"])
        self.assertTrue(text_contract["text"])
        self.assertTrue(text_contract["extensions"]["moose"])

        self.assertEqual("inlumen.table", table_contract["kind"])
        self.assertEqual("1", table_contract["contract_version"])
        self.assertTrue(table_contract["records"])
        self.assertTrue(table_contract["semt_table"]["rows"])
        self.assertTrue(table_contract["extensions"]["moose"])

        for contract in (text_contract, table_contract):
            entry = contract["extensions"]["moose"][0]
            self.assertEqual(1, entry["schema_version"])
            self.assertTrue(entry["flow_id"])
            self.assertIn(entry["operation"], EXPECTED_OPERATIONS)
            self.assertIsInstance(entry["result"], dict)


if __name__ == "__main__":
    unittest.main()
