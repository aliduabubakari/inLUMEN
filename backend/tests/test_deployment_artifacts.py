import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deployment_artifacts import (  # noqa: E402
    DeploymentArtifactValidationError,
    build_argo_workflow_object,
    build_argo_workflow_yaml,
    build_dockerfile_artifacts,
    extract_pipeline_steps,
    validate_argo_workflow_object,
    validate_dockerfile_artifacts,
)


class DeploymentArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.graph = {
            "nodes": [
                {
                    "id": "1",
                    "data": {
                        "label": "Retrieve data",
                        "type": "input",
                        "files": ["retrieve.sh", "requirements.txt"],
                    },
                },
                {
                    "id": "2",
                    "data": {
                        "label": "Process data",
                        "type": "action",
                        "files": ["process.py"],
                    },
                },
                {
                    "id": "3",
                    "data": {
                        "label": "Notify",
                        "type": "output",
                    },
                },
            ],
            "edges": [
                {"source": "1", "target": "2"},
                {"source": "2", "target": "3"},
            ],
        }

    def semt_reference_graph(self):
        return {
            "nodes": [
                {
                    "id": "reconcile",
                    "data": {
                        "label": "Reconcile City",
                        "type": "action",
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
                    },
                },
                {
                    "id": "extend",
                    "data": {
                        "label": "Extend City",
                        "type": "action",
                        "definition_id": "semt.extension",
                        "definition_version": 1,
                        "configuration_status": "valid",
                        "implementation": {
                            "kind": "semt",
                            "operation": "extension",
                            "service_id": "wikidataPropertySPARQL",
                            "parameters": {
                                "column_name": "City",
                                "properties": ["P17", "P1082"],
                                "other_params": {},
                                "deduplicate": False,
                                "extra_key_columns": [],
                            },
                            "connection_ref": "default-semt",
                        },
                    },
                },
            ],
            "edges": [{"source": "reconcile", "target": "extend"}],
        }

    def semt_input_graph(self):
        graph = self.semt_reference_graph()
        graph["nodes"] = [
            {
                "id": "input",
                "data": {
                    "label": "Input Data",
                    "type": "input",
                    "definition_id": "core.input-data",
                    "definition_version": 1,
                    "file_buckets": [
                        {
                            "filename": "cities.csv",
                            "bucket": "files-step-id-input",
                        }
                    ],
                },
            },
            {
                "id": "modify",
                "data": {
                    "label": "Normalize City",
                    "type": "action",
                    "definition_id": "semt.modification",
                    "definition_version": 1,
                    "configuration_status": "valid",
                    "implementation": {
                        "kind": "semt",
                        "operation": "modification",
                        "service_id": "dataCleaning",
                        "parameters": {"column_name": "City", "operationType": "toLowercase"},
                        "connection_ref": "default-semt",
                    },
                },
            },
            *graph["nodes"],
        ]
        graph["edges"] = [
            {"source": "input", "target": "modify"},
            {"source": "modify", "target": "reconcile"},
            {"source": "reconcile", "target": "extend"},
        ]
        return graph

    def test_builds_one_valid_dockerfile_per_pipeline_step(self):
        artifacts = build_dockerfile_artifacts(self.graph)

        dockerfiles = artifacts["dockerfiles"]
        self.assertEqual(["1", "2", "3"], [item["flow_id"] for item in dockerfiles])
        self.assertEqual(
            ["Dockerfile.1", "Dockerfile.2", "Dockerfile.3"],
            [item["dockerfile_filename"] for item in dockerfiles],
        )
        validate_dockerfile_artifacts(
            dockerfiles,
            expected_step_ids=["1", "2", "3"],
            steps=[
                {"flow_id": "1", "files": [{"filename": "retrieve.sh"}, {"filename": "requirements.txt"}]},
                {"flow_id": "2", "files": [{"filename": "process.py"}]},
                {"flow_id": "3", "files": []},
            ],
        )
        self.assertIn("RUN pip install --no-cache-dir -r requirements.txt", dockerfiles[0]["content"])
        self.assertIn('RUN find /app -type f -name "*.sh"', dockerfiles[0]["content"])

    def test_preserves_node_definition_metadata(self):
        graph = {
            "nodes": [
                {
                    "id": "1",
                    "data": {
                        "type": "action",
                        "label": "Reconcile",
                        "definition_id": "semt.reconciliation",
                        "definition_version": 1,
                        "configuration_status": "unconfigured",
                        "implementation": {
                            "kind": "semt",
                            "operation": "reconciliation",
                            "service_id": "",
                            "parameters": {},
                        },
                    },
                }
            ],
            "edges": [],
        }

        steps = extract_pipeline_steps(graph)

        self.assertEqual("semt.reconciliation", steps[0]["definition_id"])
        self.assertEqual(1, steps[0]["definition_version"])
        self.assertEqual("semt", steps[0]["implementation"]["kind"])
        self.assertEqual("unconfigured", steps[0]["configuration_status"])

    def test_semt_step_uses_deterministic_runtime_artifacts(self):
        graph = {
            "nodes": [
                {
                    "id": "12",
                    "data": {
                        "type": "action",
                        "label": "Lower names",
                        "definition_id": "semt.modification",
                        "definition_version": 1,
                        "configuration_status": "valid",
                        "implementation": {
                            "kind": "semt",
                            "operation": "modification",
                            "service_id": "dataCleaning",
                            "parameters": {"column_name": "Name", "operationType": "toLowercase"},
                            "connection_ref": "default-semt",
                        },
                    },
                }
            ],
            "edges": [],
        }

        artifacts = build_dockerfile_artifacts(graph)

        self.assertEqual(1, len(artifacts["runtime_artifacts"]))
        dockerfile = artifacts["dockerfiles"][0]
        self.assertEqual("Dockerfile.12", dockerfile["dockerfile_filename"])
        self.assertEqual(["python", "/app/main.py"], dockerfile["command"])
        self.assertIn("FROM python:3.11-slim", dockerfile["content"])
        generated_files = {
            item["filename"]
            for item in artifacts["runtime_artifacts"][0]["files"]
        }
        self.assertEqual(
            {
                "main.py",
                "requirements.txt",
                "Dockerfile.12",
                "node-manifest.json",
                "image-build-manifest.json",
            },
            generated_files,
        )
        self.assertNotIn(":latest", dockerfile["image"])
        self.assertEqual(
            artifacts["runtime_artifacts"][0]["configuration_hash"],
            dockerfile["configuration_hash"],
        )

    def test_wikifier_step_uses_deterministic_runtime_artifacts(self):
        graph = {
            "nodes": [
                {
                    "id": "wikify",
                    "data": {
                        "type": "action",
                        "label": "Wikify text",
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
                    },
                }
            ],
            "edges": [],
        }

        artifacts = build_dockerfile_artifacts(graph)

        self.assertEqual(1, len(artifacts["runtime_artifacts"]))
        dockerfile = artifacts["dockerfiles"][0]
        self.assertEqual("Dockerfile.wikify", dockerfile["dockerfile_filename"])
        self.assertEqual(["python", "/app/main.py"], dockerfile["command"])
        self.assertIn("FROM python:3.11-slim", dockerfile["content"])
        self.assertIn("/inlumen/wikifier-wikify:", dockerfile["image"])
        self.assertNotIn(":latest", dockerfile["image"])
        generated_files = {
            item["filename"]
            for item in artifacts["runtime_artifacts"][0]["files"]
        }
        self.assertEqual(
            {
                "main.py",
                "requirements.txt",
                "Dockerfile.wikify",
                "node-manifest.json",
                "image-build-manifest.json",
            },
            generated_files,
        )
        self.assertEqual(
            artifacts["runtime_artifacts"][0]["configuration_hash"],
            dockerfile["configuration_hash"],
        )

    def test_dockerfile_guardrail_rejects_bad_format(self):
        with self.assertRaises(DeploymentArtifactValidationError) as ctx:
            validate_dockerfile_artifacts(
                [{"dockerfile_filename": "Dockerfile.1", "content": "WORKDIR /app\nCMD [\"true\"]\n"}],
                expected_step_ids=["1"],
            )

        self.assertIn("must start with a FROM instruction", str(ctx.exception))

    def test_builds_valid_argo_workflow_dag_from_graph_edges(self):
        dockerfiles = build_dockerfile_artifacts(self.graph)
        workflow = build_argo_workflow_object(self.graph, dockerfiles)

        validate_argo_workflow_object(workflow, expected_step_ids=["1", "2", "3"])
        tasks = workflow["spec"]["templates"][0]["dag"]["tasks"]
        self.assertEqual("step-1", tasks[0]["name"])
        self.assertEqual(["step-1"], tasks[1]["dependencies"])
        self.assertEqual(["step-2"], tasks[2]["dependencies"])
        self.assertEqual("inlumen/step-2:latest", workflow["spec"]["templates"][2]["container"]["image"])

    def test_argo_yaml_output_is_plain_yaml_not_markdown(self):
        dockerfiles = build_dockerfile_artifacts(self.graph)
        yaml_text = build_argo_workflow_yaml(self.graph, dockerfiles)

        self.assertIn('apiVersion: "argoproj.io/v1alpha1"', yaml_text)
        self.assertIn('kind: "Workflow"', yaml_text)
        self.assertIn('template: "step-3"', yaml_text)
        self.assertNotIn("```", yaml_text)

    def test_codegen_runtime_workflow_uses_manifest_handoff_contract(self):
        configuration_hash = "sha256:" + ("b" * 64)
        graph = {
            "nodes": [
                {
                    "id": "1",
                    "data": {
                        "label": "Data Ingestion",
                        "type": "input",
                        "generated_artifact": {
                            "status": "current",
                            "generator": "inlumen-codegen-service",
                            "configuration_hash": configuration_hash,
                            "data_contract": {
                                "input_manifest_env": "INLUMEN_INPUT_MANIFEST",
                                "output_dir_env": "INLUMEN_OUTPUT_DIR",
                                "output_manifest_env": "INLUMEN_OUTPUT_MANIFEST",
                                "context_path_env": "INLUMEN_CONTEXT_PATH",
                            },
                        },
                    },
                },
                {
                    "id": "2",
                    "data": {
                        "label": "Preprocessing",
                        "type": "action",
                        "generated_artifact": {
                            "status": "current",
                            "generator": "inlumen-codegen-service",
                            "configuration_hash": configuration_hash,
                            "data_contract": {
                                "input_manifest_env": "INLUMEN_INPUT_MANIFEST",
                                "output_dir_env": "INLUMEN_OUTPUT_DIR",
                                "output_manifest_env": "INLUMEN_OUTPUT_MANIFEST",
                                "context_path_env": "INLUMEN_CONTEXT_PATH",
                            },
                        },
                    },
                },
            ],
            "edges": [{"source": "1", "target": "2"}],
        }
        dockerfile_content = "\n".join(
            [
                "FROM python:3.11-slim",
                "WORKDIR /app",
                'COPY ["requirements.txt", "/app/requirements.txt"]',
                "RUN pip install --no-cache-dir -r requirements.txt",
                'COPY ["main.py", "/app/main.py"]',
                'COPY ["node-manifest.json", "/app/node-manifest.json"]',
                'CMD ["python", "/app/main.py"]',
                "",
            ]
        )
        dockerfiles = {
            "dockerfiles": [
                {
                    "dockerfile_filename": "Dockerfile.1",
                    "content": dockerfile_content,
                    "flow_id": "1",
                    "image": "ghcr.io/inlumen/codegen-1:bbbbbbbbbbbb",
                    "command": ["python", "/app/main.py"],
                    "files": ["requirements.txt", "main.py", "node-manifest.json"],
                    "generator": "inlumen-codegen-service",
                    "configuration_hash": configuration_hash,
                    "build_manifest": "node-manifest.json",
                },
                {
                    "dockerfile_filename": "Dockerfile.2",
                    "content": dockerfile_content,
                    "flow_id": "2",
                    "image": "ghcr.io/inlumen/codegen-2:bbbbbbbbbbbb",
                    "command": ["python", "/app/main.py"],
                    "files": ["requirements.txt", "main.py", "node-manifest.json"],
                    "generator": "inlumen-codegen-service",
                    "configuration_hash": configuration_hash,
                    "build_manifest": "node-manifest.json",
                },
            ]
        }

        workflow = build_argo_workflow_object(graph, dockerfiles)
        validate_argo_workflow_object(workflow, expected_step_ids=["1", "2"])

        spec = workflow["spec"]
        self.assertEqual(
            {
                "configMap": "inlumen-artifact-repositories",
                "key": "minio",
            },
            spec["artifactRepositoryRef"],
        )
        tasks = spec["templates"][0]["dag"]["tasks"]
        self.assertEqual(
            "{{workflow.parameters.input-artifact-key}}",
            tasks[0]["arguments"]["artifacts"][0]["s3"]["key"],
        )
        self.assertEqual(
            "{{tasks.step-1.outputs.artifacts.outputs}}",
            tasks[1]["arguments"]["artifacts"][0]["from"],
        )
        self.assertEqual(["step-1"], tasks[1]["dependencies"])

        first_template = spec["templates"][1]
        second_template = spec["templates"][2]
        self.assertEqual(
            "/inlumen/inputs",
            first_template["inputs"]["artifacts"][0]["path"],
        )
        self.assertEqual(
            "/inlumen/outputs",
            first_template["outputs"]["artifacts"][0]["path"],
        )
        self.assertEqual(
            "{{workflow.parameters.output-artifact-prefix}}/step-2",
            second_template["outputs"]["artifacts"][0]["s3"]["key"],
        )
        env_by_name = {item["name"]: item["value"] for item in first_template["container"]["env"]}
        self.assertEqual("/inlumen/inputs/input_manifest.json", env_by_name["INLUMEN_INPUT_MANIFEST"])
        self.assertEqual("/inlumen/outputs", env_by_name["INLUMEN_OUTPUT_DIR"])
        self.assertEqual("/inlumen/outputs/output_manifest.json", env_by_name["INLUMEN_OUTPUT_MANIFEST"])
        self.assertEqual("/app/node-manifest.json", env_by_name["INLUMEN_CONTEXT_PATH"])

        yaml_text = build_argo_workflow_yaml(graph, dockerfiles)
        self.assertIn('generateName: "inlumen-codegen-"', yaml_text)
        self.assertIn('artifactRepositoryRef:', yaml_text)

    def test_codegen_dockerfile_payload_selects_manifest_handoff_without_node_metadata(self):
        graph = {
            "nodes": [
                {"id": "1", "data": {"label": "Ingestion", "type": "input"}},
                {"id": "2", "data": {"label": "Preprocessing", "type": "action"}},
            ],
            "edges": [{"source": "1", "target": "2"}],
        }
        dockerfile_content = "\n".join(
            [
                "FROM python:3.11-slim",
                "WORKDIR /app",
                'COPY ["requirements.txt", "/app/requirements.txt"]',
                "RUN pip install --no-cache-dir -r requirements.txt",
                'COPY ["main.py", "/app/main.py"]',
                'COPY ["node-manifest.json", "/app/node-manifest.json"]',
                'CMD ["python", "/app/main.py"]',
                "",
            ]
        )
        dockerfiles = {
            "dockerfiles": [
                {
                    "dockerfile_filename": "Dockerfile.1",
                    "content": dockerfile_content,
                    "flow_id": "1",
                    "image": "inlumen/step-1:latest",
                    "command": ["python", "/app/main.py"],
                    "files": ["requirements.txt", "main.py", "node-manifest.json"],
                    "generator": "inlumen-codegen-service",
                },
                {
                    "dockerfile_filename": "Dockerfile.2",
                    "content": dockerfile_content,
                    "flow_id": "2",
                    "image": "inlumen/step-2:latest",
                    "command": ["python", "/app/main.py"],
                    "files": ["requirements.txt", "main.py", "node-manifest.json"],
                    "generator": "inlumen-codegen-service",
                },
            ]
        }

        workflow = build_argo_workflow_object(graph, dockerfiles)

        self.assertEqual("inlumen-codegen-", workflow["metadata"]["generateName"])
        self.assertEqual(
            "/inlumen/inputs/input_manifest.json",
            next(
                item["value"]
                for item in workflow["spec"]["templates"][1]["container"]["env"]
                if item["name"] == "INLUMEN_INPUT_MANIFEST"
            ),
        )

    def test_argo_guardrail_requires_dockerfile_for_each_step(self):
        dockerfiles = build_dockerfile_artifacts(self.graph)
        dockerfiles["dockerfiles"] = dockerfiles["dockerfiles"][:2]

        with self.assertRaises(DeploymentArtifactValidationError) as ctx:
            build_argo_workflow_object(self.graph, dockerfiles)

        self.assertIn("missing Dockerfile for step id '3'", str(ctx.exception))

    def test_argo_guardrail_rejects_cyclic_pipeline(self):
        graph = {
            "nodes": self.graph["nodes"][:2],
            "edges": [
                {"source": "1", "target": "2"},
                {"source": "2", "target": "1"},
            ],
        }
        dockerfiles = build_dockerfile_artifacts(graph)

        with self.assertRaises(DeploymentArtifactValidationError) as ctx:
            build_argo_workflow_object(graph, dockerfiles)

        self.assertIn("pipeline graph contains a cycle", str(ctx.exception))

    def test_builds_artifact_aware_semt_workflow(self):
        graph = self.semt_reference_graph()
        dockerfiles = build_dockerfile_artifacts(graph)

        workflow = build_argo_workflow_object(graph, dockerfiles)
        validate_argo_workflow_object(
            workflow,
            expected_step_ids=["reconcile", "extend"],
        )

        spec = workflow["spec"]
        self.assertEqual(
            {
                "configMap": "inlumen-artifact-repositories",
                "key": "minio",
            },
            spec["artifactRepositoryRef"],
        )
        tasks = spec["templates"][0]["dag"]["tasks"]
        self.assertEqual(
            "{{workflow.parameters.input-artifact-key}}",
            tasks[0]["arguments"]["artifacts"][0]["s3"]["key"],
        )
        self.assertEqual(
            "{{tasks.reconcile.outputs.artifacts.table}}",
            tasks[1]["arguments"]["artifacts"][0]["from"],
        )

        reconciliation = spec["templates"][1]
        extension = spec["templates"][2]
        self.assertEqual(
            "/data/input.csv",
            reconciliation["inputs"]["artifacts"][0]["path"],
        )
        self.assertEqual(
            "/data/reconciled.json",
            reconciliation["outputs"]["artifacts"][0]["path"],
        )
        self.assertEqual(
            "/data/input.json",
            extension["inputs"]["artifacts"][0]["path"],
        )
        self.assertEqual(
            "{{workflow.parameters.output-artifact-key}}",
            extension["outputs"]["artifacts"][0]["s3"]["key"],
        )
        self.assertEqual(
            "http://semt-backend:3003",
            next(
                env["value"]
                for env in extension["container"]["env"]
                if env["name"] == "SEMT_API_BASE_URL"
            ),
        )

        yaml_text = build_argo_workflow_yaml(graph, dockerfiles)
        self.assertNotIn(":latest", yaml_text)
        self.assertNotIn("localhost", yaml_text)
        self.assertNotIn('"test"', yaml_text)

    def test_input_data_file_feeds_the_complete_semt_chain(self):
        graph = self.semt_input_graph()
        artifacts = build_dockerfile_artifacts(graph)

        self.assertCountEqual(
            ["modify", "reconcile", "extend"],
            [item["flow_id"] for item in artifacts["dockerfiles"]],
        )
        workflow = build_argo_workflow_object(graph, artifacts)
        validate_argo_workflow_object(
            workflow,
            expected_step_ids=["modify", "reconcile", "extend"],
        )

        spec = workflow["spec"]
        tasks = spec["templates"][0]["dag"]["tasks"]
        self.assertEqual(
            {
                "bucket": "files-step-id-input",
                "key": "cities.csv",
            },
            tasks[0]["arguments"]["artifacts"][0]["s3"],
        )
        self.assertEqual(["modify"], tasks[1]["dependencies"])
        self.assertEqual(["reconcile"], tasks[2]["dependencies"])

        modification = spec["templates"][1]
        reconciliation = spec["templates"][2]
        extension = spec["templates"][3]
        self.assertEqual(
            "/data/input.csv",
            modification["inputs"]["artifacts"][0]["path"],
        )
        self.assertEqual(
            "/data/input.json",
            reconciliation["inputs"]["artifacts"][0]["path"],
        )
        self.assertEqual(
            "/data/input.json",
            extension["inputs"]["artifacts"][0]["path"],
        )

        yaml_text = build_argo_workflow_yaml(graph, artifacts)
        self.assertIn('bucket: "files-step-id-input"', yaml_text)
        self.assertIn('key: "cities.csv"', yaml_text)
        self.assertNotIn('template: "input"', yaml_text)

    def test_input_data_semt_boundary_requires_one_csv_file(self):
        graph = self.semt_input_graph()
        graph["nodes"][0]["data"]["file_buckets"] = []
        artifacts = build_dockerfile_artifacts(graph)

        with self.assertRaises(DeploymentArtifactValidationError) as ctx:
            build_argo_workflow_object(graph, artifacts)

        self.assertIn(
            "Input Data node must contain exactly one uploaded CSV file",
            str(ctx.exception),
        )

    def test_semt_workflow_rejects_mismatched_extension_column(self):
        graph = self.semt_reference_graph()
        graph["nodes"][1]["data"]["implementation"]["parameters"][
            "column_name"
        ] = "Country"
        dockerfiles = build_dockerfile_artifacts(graph)

        with self.assertRaises(DeploymentArtifactValidationError) as ctx:
            build_argo_workflow_object(graph, dockerfiles)

        self.assertIn("must target a column reconciled earlier", str(ctx.exception))

    def test_semt_extension_can_follow_intervening_operation_for_reconciled_column(self):
        graph = self._full_semt_pipeline_graph()
        weather_extension = {
            "id": "weather",
            "data": {
                "label": "Weather Properties",
                "type": "action",
                "definition_id": "semt.extension",
                "definition_version": 1,
                "configuration_status": "valid",
                "implementation": {
                    "kind": "semt",
                    "operation": "extension",
                    "service_id": "meteoPropertiesOpenMeteo",
                    "parameters": {
                        "column_name": "City",
                        "granularity": "daily",
                        "dateColumnName": "ObservationDate",
                        "decimalFormat": ".",
                        "properties": [
                            "light_hours",
                            "apparent_temperature_max",
                        ],
                    },
                    "connection_ref": "default-semt",
                },
            },
        }
        date_formatter = {
            "id": "format-date",
            "data": {
                "label": "Format Date",
                "type": "action",
                "definition_id": "semt.modification",
                "definition_version": 1,
                "configuration_status": "valid",
                "implementation": {
                    "kind": "semt",
                    "operation": "modification",
                    "service_id": "dateFormatter",
                    "parameters": {
                        "column_name": "ObservationDate",
                        "formatType": "iso",
                        "detailLevel": "hourMinutes",
                        "outputMode": "update",
                        "selectedColumns": ["ObservationDate"],
                    },
                    "connection_ref": "default-semt",
                },
            },
        }
        graph["nodes"].insert(4, date_formatter)
        graph["nodes"].insert(5, weather_extension)
        graph["edges"] = [
            {"source": "input", "target": "modify"},
            {"source": "modify", "target": "reconcile"},
            {"source": "reconcile", "target": "extend"},
            {"source": "extend", "target": "format-date"},
            {"source": "format-date", "target": "weather"},
            {"source": "weather", "target": "export"},
        ]

        dockerfiles = build_dockerfile_artifacts(graph)
        workflow = build_argo_workflow_object(graph, dockerfiles)

        task_names = [task["name"] for task in workflow["spec"]["templates"][0]["dag"]["tasks"]]
        self.assertEqual(
            ["modify", "reconcile", "extend", "format-date", "weather", "export"],
            task_names,
        )

    def test_semt_workflow_rejects_stale_runtime_metadata(self):
        graph = self.semt_reference_graph()
        dockerfiles = build_dockerfile_artifacts(graph)
        dockerfiles["dockerfiles"][0]["configuration_hash"] = "sha256:" + ("0" * 64)

        with self.assertRaises(DeploymentArtifactValidationError) as ctx:
            build_argo_workflow_object(graph, dockerfiles)

        self.assertIn("runtime is stale", str(ctx.exception))

    # ------------------------------------------------------------------
    # Full-pipeline integration test
    # ------------------------------------------------------------------

    def _full_semt_pipeline_graph(self):
        """SemT pipeline: Input table-load boundary → Mod → Recon → Extend → Export."""
        return {
            "settings": {
                "semt": {
                    "api_base_url": "http://semt-backend:3003",
                    "username": "test",
                    "password": "test",
                }
            },
            "nodes": [
                {
                    "id": "input",
                    "data": {
                        "label": "Input Data",
                        "type": "input",
                        "definition_id": "core.input-data",
                        "definition_version": 1,
                        "file_buckets": [
                            {
                                "filename": "cities.csv",
                                "bucket": "files-step-id-input",
                                "snapshot_bucket": "inlumen-bucket",
                                "snapshot_object": "cities.csv",
                            }
                        ],
                        "implementation": {
                            "kind": "semt-input",
                            "mode": "table-load",
                            "parameters": {
                                "semt_table_load": True,
                                "dataset_id": "114",
                                "table_name": "my_table",
                                "csv_file": "cities.csv",
                            },
                            "connection_ref": "default-semt",
                        },
                    },
                },
                {
                    "id": "modify",
                    "data": {
                        "label": "Clean Cities",
                        "type": "action",
                        "definition_id": "semt.modification",
                        "definition_version": 1,
                        "configuration_status": "valid",
                        "implementation": {
                            "kind": "semt",
                            "operation": "modification",
                            "service_id": "dataCleaning",
                            "parameters": {
                                "column_name": "City",
                                "operationType": "toTitlecase",
                            },
                            "connection_ref": "default-semt",
                        },
                    },
                },
                {
                    "id": "reconcile",
                    "data": {
                        "label": "Reconcile Cities",
                        "type": "action",
                        "definition_id": "semt.reconciliation",
                        "definition_version": 1,
                        "configuration_status": "valid",
                        "implementation": {
                            "kind": "semt",
                            "operation": "reconciliation",
                            "service_id": "geonames",
                            "parameters": {
                                "column_name": "City",
                            },
                            "connection_ref": "default-semt",
                        },
                    },
                },
                {
                    "id": "extend",
                    "data": {
                        "label": "Extend Cities",
                        "type": "action",
                        "definition_id": "semt.extension",
                        "definition_version": 1,
                        "configuration_status": "valid",
                        "implementation": {
                            "kind": "semt",
                            "operation": "extension",
                            "service_id": "reconciledColumnExt",
                            "parameters": {
                                "column_name": "City",
                                "properties": ["id", "name"],
                            },
                            "connection_ref": "default-semt",
                        },
                    },
                },
                {
                    "id": "export",
                    "data": {
                        "label": "Export Results",
                        "type": "output",
                        "definition_id": "semt.export",
                        "definition_version": 1,
                        "configuration_status": "valid",
                        "implementation": {
                            "kind": "semt",
                            "operation": "export",
                            "service_id": "export_table",
                            "parameters": {
                                "output_format": "json",
                                "output_filename": "results",
                            },
                            "connection_ref": "default-semt",
                        },
                    },
                },
            ],
            "edges": [
                {"source": "input", "target": "modify"},
                {"source": "modify", "target": "reconcile"},
                {"source": "reconcile", "target": "extend"},
                {"source": "extend", "target": "export"},
            ],
        }

    def test_full_semt_pipeline_integration(self):
        """End-to-end: Input → Setup → Mod → Recon → Extend → Export."""
        graph = self._full_semt_pipeline_graph()

        # 1. Generate all Dockerfiles and runtime artifacts
        dockerfiles_payload = build_dockerfile_artifacts(graph)
        self.assertTrue(dockerfiles_payload["guardrails"]["valid"])

        dockerfiles = dockerfiles_payload["dockerfiles"]
        runtime_artifacts = dockerfiles_payload["runtime_artifacts"]

        # 2. Expect Dockerfiles for SemT operation steps; input remains a boundary.
        runtime_step_ids = {"modify", "reconcile", "extend", "export"}
        generated_ids = {df["flow_id"] for df in dockerfiles}
        self.assertEqual(runtime_step_ids, generated_ids)

        # 3. Verify each step's runtime artifacts
        for artifact in runtime_artifacts:
            fid = artifact["flow_id"]
            definition_id = artifact["definition_id"]

            # Every step has main.py, requirements.txt, and manifests
            filenames = {f["filename"] for f in artifact["files"]}
            for required in ("main.py", "requirements.txt", "node-manifest.json"):
                self.assertIn(required, filenames, f"{fid} missing {required}")

            # Export is standalone; operation nodes use the shared SemT base runtime.
            main_py = next(
                f["content"] for f in artifact["files"] if f["filename"] == "main.py"
            )
            if definition_id == "semt.export":
                self.assertNotIn(
                    "execute_operation", main_py,
                    f"{definition_id} should be standalone",
                )
            else:
                self.assertIn(
                    "execute_operation", main_py,
                    f"{definition_id} should use base.py.j2",
                )
                if fid == "modify":
                    self.assertIn('"semt_table_load":true', main_py)
                    self.assertIn('"dataset_id":"114"', main_py)
                    self.assertIn('"table_name":"my_table"', main_py)

            # No generated script should contain the placeholder URL
            self.assertNotIn(
                "YOUR-SEMT-API-BASE-URL", main_py,
                f"{fid} contains placeholder URL",
            )

        # 4. Build and validate the Argo workflow
        workflow = build_argo_workflow_object(graph, dockerfiles_payload)
        validate_argo_workflow_object(
            workflow,
            expected_step_ids=sorted(runtime_step_ids),
        )

        spec = workflow["spec"]
        templates = spec["templates"]
        dag_tasks = templates[0]["dag"]["tasks"]

        # 5. Verify DAG task ordering — flow_ids become Argo task names
        task_names = [t["name"] for t in dag_tasks]
        self.assertEqual(
            ["modify", "reconcile", "extend", "export"],
            task_names,
        )

        # 6. First task reads from the ingress CSV (snapshot object from Input Data)
        first_artifact = dag_tasks[0]["arguments"]["artifacts"][0]
        self.assertEqual("table", first_artifact["name"])
        self.assertIn("cities.csv", first_artifact["s3"]["key"])
        for i in range(1, len(dag_tasks)):
            prev_name = task_names[i - 1]
            self.assertEqual(
                f"{{{{tasks.{prev_name}.outputs.artifacts.table}}}}",
                dag_tasks[i]["arguments"]["artifacts"][0]["from"],
            )

        # 7. All dependencies are sequential
        for i in range(1, len(dag_tasks)):
            self.assertEqual([task_names[i - 1]], dag_tasks[i].get("dependencies", []))

        # 8. Container checks for each template
        template_by_name = {t["name"]: t for t in templates if t["name"] != "inlumen-pipeline"}
        for step_id in ("modify", "reconcile", "extend", "export"):
            step_name = step_id  # flow_id IS the Argo task name
            template = template_by_name[step_name]
            container = template["container"]

            # Each step uses a workflow image parameter
            self.assertTrue(
                container["image"].startswith("{{workflow.parameters.image-"),
                f"{step_id} missing image parameter",
            )

            # Each step has the required env vars
            env_by_name = {e["name"]: e for e in container["env"]}
            self.assertIn("INLUMEN_FLOW_ID", env_by_name)
            self.assertIn("SEMT_API_BASE_URL", env_by_name)
            self.assertEqual(
                "http://semt-backend:3003",
                env_by_name["SEMT_API_BASE_URL"]["value"],
            )

            # Credential env vars come from secrets
            for env_name, secret_key in (
                ("SEMT_API_USERNAME", "username"),
                ("SEMT_API_PASSWORD", "password"),
            ):
                self.assertIn(env_name, env_by_name)
                self.assertEqual(
                    {"name": "semt-runtime-credentials", "key": secret_key},
                    env_by_name[env_name]["valueFrom"]["secretKeyRef"],
                )

        # 9. Leaf output is persisted via output-artifact-key
        export_template = template_by_name["export"]
        export_output = export_template["outputs"]["artifacts"][0]
        self.assertEqual("table", export_output["name"])
        self.assertEqual("{{workflow.parameters.output-artifact-key}}", export_output["s3"]["key"])
        self.assertEqual({"none": {}}, export_output["archive"])

        # 10. Workflow-level output references the export task
        self.assertEqual(
            "{{tasks.export.outputs.artifacts.table}}",
            templates[0]["outputs"]["artifacts"][0]["from"],
        )

        # 11. YAML output is valid (no markdown, no localhost)
        yaml_text = build_argo_workflow_yaml(graph, dockerfiles_payload)
        self.assertNotIn("```", yaml_text)
        self.assertNotIn("localhost", yaml_text)
        self.assertNotIn(":latest", yaml_text)

        # 12. All image parameters are present
        image_params = {
            p["name"]: p["value"]
            for p in spec["arguments"]["parameters"]
            if p["name"].startswith("image-")
        }
        self.assertEqual(4, len(image_params))
        for value in image_params.values():
            self.assertTrue(value.startswith("ghcr.io/inlumen/semt-"))
            self.assertNotIn(":latest", value)
