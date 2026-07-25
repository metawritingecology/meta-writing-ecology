#!/usr/bin/env python3
"""Phase 3A P5 tests: expanded public-surface adjacency dataset and its manifest.

Standard-library unittest only (no third-party dependency), matching the rest of
this repository's test suite. The JSON Schema instance check below is a
deliberately small hand-rolled validator covering exactly the keyword subset the
manifest schema uses (type, const, enum, required, additionalProperties,
minItems/maxItems, uniqueItems, minLength, pattern); it exists because no
JSON Schema library is available here, and the repository's own validator
performs structural checks the same way.

Coverage:

- manifest schema identity: Draft 2020-12, closed objects, required fields,
  closed enums;
- manifest identity: 59 records, registry order, unique paths, exact 1:1
  registry coverage, all included, role distribution 49/2/7/1, labels equal
  registry names, grouping-source and relation-evidence-ceiling assignment,
  pinned source commit;
- MODEL_ATLAS navigation grouping: every concept resolves to exactly one field,
  no non-concept receives a field, and grouping alters no registry value;
- edge extraction: raw and retained counts by class, concept-only endpoints,
  direction preserved, no inferred reverse edges, duplicate handling within a
  class, no cross-class deduplication, no governance/source-use/user-confirmed
  edge, no unresolved or out-of-registry endpoint;
- dataset identity: 59 nodes, role distribution, concept-only semantic
  participation, no rank/centrality field, pinned source commit, consumer
  ceiling, deterministic rebuild to separate temporary paths, and equality with
  the tracked data.json;
- expanded/historical isolation: historical verification reads none of the
  expanded-only inputs, and collision checking precedes generation.

Nothing here writes into the repository. Every generated artifact goes to a
temporary directory outside the repository root.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
BUILDER = SCRIPTS / "build_public_surface_authority_map.py"

ADJACENCY_DIR = REPO_ROOT / "visualizations" / "public-surface-adjacency-map"
MANIFEST_PATH = ADJACENCY_DIR / "visualization-manifest.json"
MANIFEST_SCHEMA_PATH = ADJACENCY_DIR / "visualization-manifest.schema.json"
DATA_PATH = ADJACENCY_DIR / "data.json"

REGISTRY_PATH = REPO_ROOT / "mwe-public-documents.json"
MODEL_ATLAS_PATH = REPO_ROOT / "model-atlas" / "MODEL_ATLAS.md"
RELATION_MAP_PATH = REPO_ROOT / "model-atlas" / "RELATION_MAP.md"
HISTORICAL_DATA_PATH = (
    REPO_ROOT / "visualizations" / "public-surface-authority-map" / "data.json"
)

# Pinned generation source commit for the expanded product (Phase 3A P5 base).
EXPANDED_SOURCE_COMMIT = "933274af9693d6d1d9fac36819aafdf56f9ab81d"

EXPECTED_RECORD_COUNT = 59
EXPECTED_ROLE_DISTRIBUTION = {
    "concept": 49,
    "orientation": 2,
    "boundary": 7,
    "anchor": 1,
}
EXPECTED_CONCEPTS = 49
EXPECTED_FIXED_BAND = 10

# Recomputed from the pinned source at P5 generation time and asserted here so a
# silent parser drift becomes a test failure.
EXPECTED_SOURCE_NAMED_RAW = 180
EXPECTED_SOURCE_NAMED_RETAINED = 180
EXPECTED_SOURCE_NAMED_EXCLUDED = 0
EXPECTED_NAVIGATION_RAW = 201
EXPECTED_NAVIGATION_RETAINED = 194
EXPECTED_NAVIGATION_EXCLUDED = 7

EXPECTED_CEILING_DISTRIBUTION = {
    "source_named_adjacency": 18,
    "navigation_adjacency": 31,
    "none": 10,
}

EXPECTED_FIELD_DISTRIBUTION = {
    "AI-Readable Interface / Externalization": 6,
    "Boundary / Representation": 10,
    "Coherence / Circulation / Collapse Risk": 6,
    "Constraint / Residue / Capability Shift": 4,
    "Proxy / Legibility / Provenance": 6,
    "Responsibility / Benefit-Burden / Cost": 7,
    "Semantic Field Foundations": 10,
}

CONSUMER_CEILING_BYTES = 262144

# Field names that would promote a navigation surface into a ranked or
# confirmed one. None may appear anywhere in the tracked dataset.
PROHIBITED_FIELD_NAMES = {
    "rank",
    "centrality",
    "authority_score",
    "importance",
    "priority",
    "canonicality",
    "confidence",
    "relation_strength",
    "confirmed",
}

sys.path.insert(0, str(SCRIPTS))
import build_public_surface_authority_map as builder  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\x00" + data).hexdigest()


def run_builder(args, cwd=REPO_ROOT):
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
    )


# ---------------------------------------------------------------------------
# Minimal JSON Schema instance checker (only the keywords the schema uses).
# ---------------------------------------------------------------------------


def check_instance(schema, instance, path="$"):
    """Return a list of validation error strings for instance against schema."""
    errors = []

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: {instance!r} != const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']!r}")

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(instance, dict):
            return errors + [f"{path}: expected object"]
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required key {key!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: additional property {key!r} not allowed")
        for key, value in instance.items():
            if key in properties:
                errors.extend(check_instance(properties[key], value, f"{path}.{key}"))
    elif expected_type == "array":
        if not isinstance(instance, list):
            return errors + [f"{path}: expected array"]
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            seen = [json.dumps(item, sort_keys=True) for item in instance]
            if len(set(seen)) != len(seen):
                errors.append(f"{path}: items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                errors.extend(check_instance(item_schema, item, f"{path}[{index}]"))
    elif expected_type == "string":
        if not isinstance(instance, str):
            return errors + [f"{path}: expected string"]
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']!r}")
    elif expected_type == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            return errors + [f"{path}: expected integer"]

    return errors


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_ctx = tempfile.TemporaryDirectory(prefix="mwe-p5-")
        cls.tmp = Path(cls._tmp_ctx.name)
        cls.registry = load_json(REGISTRY_PATH)
        cls.records = cls.registry["@graph"]
        cls.manifest = load_json(MANIFEST_PATH)
        cls.schema = load_json(MANIFEST_SCHEMA_PATH)
        cls.data = load_json(DATA_PATH)

    @classmethod
    def tearDownClass(cls):
        cls._tmp_ctx.cleanup()


# ---------------------------------------------------------------------------
# 16.1 Manifest schema and identity
# ---------------------------------------------------------------------------


class ManifestSchemaTests(BaseCase):
    def test_schema_is_draft_2020_12(self):
        self.assertEqual(
            self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )

    def test_every_object_level_is_closed(self):
        def walk(node, path="$"):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(
                        node.get("additionalProperties"),
                        False,
                        f"{path}: object level is not closed",
                    )
                    self.assertIn("required", node, f"{path}: no required list")
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        walk(self.schema)

    def test_all_top_level_keys_required(self):
        self.assertEqual(
            sorted(self.schema["required"]), sorted(self.schema["properties"])
        )

    def test_all_record_fields_required(self):
        items = self.schema["properties"]["records"]["items"]
        self.assertEqual(sorted(items["required"]), sorted(items["properties"]))

    def test_record_count_is_pinned_to_fifty_nine(self):
        self.assertEqual(self.schema["properties"]["record_count"]["const"], 59)
        records = self.schema["properties"]["records"]
        self.assertEqual(records["minItems"], 59)
        self.assertEqual(records["maxItems"], 59)
        self.assertTrue(records["uniqueItems"])

    def test_enums_are_closed_and_exact(self):
        properties = self.schema["properties"]["records"]["items"]["properties"]
        self.assertEqual(
            properties["visualization_membership"]["enum"],
            ["included", "excluded", "pending"],
        )
        self.assertEqual(
            properties["visualization_role"]["enum"],
            ["concept", "orientation", "boundary", "anchor"],
        )
        self.assertEqual(properties["display_label_source"]["enum"], ["registry_name"])
        self.assertEqual(
            properties["grouping_source"]["enum"],
            ["model_atlas_field", "visualization_role"],
        )
        self.assertEqual(
            properties["relation_evidence_ceiling"]["enum"],
            ["source_named_adjacency", "navigation_adjacency", "none"],
        )

    def test_no_record_field_asserts_status_or_ontology(self):
        properties = self.schema["properties"]["records"]["items"]["properties"]
        for name in properties:
            self.assertNotIn(name, PROHIBITED_FIELD_NAMES)
        for banned in (
            "publicly_declared_classification",
            "surface_role",
            "public_surface_status",
            "registry_status",
            "ontology_membership",
            "relation_status",
        ):
            self.assertNotIn(banned, properties)

    def test_manifest_validates_against_its_schema(self):
        self.assertEqual(check_instance(self.schema, self.manifest), [])

    def test_manifest_is_independent_of_the_registry_contract(self):
        # The manifest may reference the registry, but must not be embedded in
        # it or extend its contract.
        self.assertEqual(self.manifest["describes"], "../../mwe-public-documents.json")
        self.assertNotIn("records", self.registry)
        self.assertNotIn("visualization_membership", json.dumps(self.registry))
        for record in self.records:
            self.assertNotIn("visualization_role", record)


class ManifestIdentityTests(BaseCase):
    def test_record_count_and_length_agree(self):
        self.assertEqual(self.manifest["record_count"], EXPECTED_RECORD_COUNT)
        self.assertEqual(len(self.manifest["records"]), EXPECTED_RECORD_COUNT)

    def test_source_commit_is_the_pinned_generation_commit(self):
        self.assertEqual(self.manifest["source_commit"], EXPANDED_SOURCE_COMMIT)

    def test_one_to_one_registry_coverage_in_registry_order(self):
        registry_order = [record["repository_path"] for record in self.records]
        manifest_order = [entry["repository_path"] for entry in self.manifest["records"]]
        self.assertEqual(manifest_order, registry_order)
        self.assertEqual(len(set(manifest_order)), EXPECTED_RECORD_COUNT)

    def test_no_manifest_record_lies_outside_the_registry(self):
        registry_paths = {record["repository_path"] for record in self.records}
        for entry in self.manifest["records"]:
            self.assertIn(entry["repository_path"], registry_paths)

    def test_every_record_is_included(self):
        memberships = {entry["visualization_membership"] for entry in self.manifest["records"]}
        self.assertEqual(memberships, {"included"})

    def test_role_distribution(self):
        counts = {}
        for entry in self.manifest["records"]:
            counts[entry["visualization_role"]] = counts.get(entry["visualization_role"], 0) + 1
        self.assertEqual(counts, EXPECTED_ROLE_DISTRIBUTION)

    def test_roles_are_mechanical_from_registry_surface_role(self):
        by_path = {record["repository_path"]: record for record in self.records}
        for entry in self.manifest["records"]:
            expected = builder.VISUALIZATION_ROLE_BY_SURFACE_ROLE[
                by_path[entry["repository_path"]]["surface_role"]
            ]
            self.assertEqual(entry["visualization_role"], expected)

    def test_expected_orientation_and_anchor_records(self):
        roles = {
            entry["repository_path"]: entry["visualization_role"]
            for entry in self.manifest["records"]
        }
        self.assertEqual(roles["README.md"], "orientation")
        self.assertEqual(roles["AUTHOR.md"], "orientation")
        self.assertEqual(
            roles["public-anchors/ai-training-boundary-statement.md"], "anchor"
        )

    def test_display_label_source_is_uniform(self):
        sources = {entry["display_label_source"] for entry in self.manifest["records"]}
        self.assertEqual(sources, {"registry_name"})

    def test_grouping_source_assignment(self):
        for entry in self.manifest["records"]:
            expected = (
                "model_atlas_field"
                if entry["visualization_role"] == "concept"
                else "visualization_role"
            )
            self.assertEqual(entry["grouping_source"], expected, entry["repository_path"])

    def test_relation_evidence_ceiling_assignment(self):
        counts = {}
        for entry in self.manifest["records"]:
            counts[entry["relation_evidence_ceiling"]] = (
                counts.get(entry["relation_evidence_ceiling"], 0) + 1
            )
        self.assertEqual(counts, EXPECTED_CEILING_DISTRIBUTION)

    def test_non_concept_records_have_no_relation_evidence(self):
        for entry in self.manifest["records"]:
            if entry["visualization_role"] != "concept":
                self.assertEqual(entry["relation_evidence_ceiling"], "none")

    def test_ceilings_match_recomputed_evidence(self):
        roles = builder.build_visualization_roles(self.records)
        named, _, _ = builder.parse_source_named_adjacency(REPO_ROOT, self.records, roles)
        navigation, _, _ = builder.parse_navigation_adjacency(REPO_ROOT, self.records, roles)
        recomputed = builder.compute_relation_evidence_ceilings(
            self.records, roles, named, navigation
        )
        for entry in self.manifest["records"]:
            self.assertEqual(
                entry["relation_evidence_ceiling"],
                recomputed[entry["repository_path"]],
                entry["repository_path"],
            )


# ---------------------------------------------------------------------------
# 16.2 Grouping
# ---------------------------------------------------------------------------


class GroupingTests(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.roles = builder.build_visualization_roles(cls.records)
        cls.grouping = builder.parse_model_atlas_fields(REPO_ROOT, cls.records, cls.roles)

    def test_every_concept_has_exactly_one_field(self):
        concepts = [p for p, role in self.roles.items() if role == "concept"]
        self.assertEqual(len(concepts), EXPECTED_CONCEPTS)
        for path in concepts:
            self.assertIn(path, self.grouping)
            self.assertIsInstance(self.grouping[path], str)
            self.assertTrue(self.grouping[path])

    def test_no_concept_resolves_to_zero_or_multiple_fields(self):
        # Parsed independently of the builder's own selection, so a duplicate
        # MODEL_ATLAS entry would surface here rather than being silently
        # collapsed to one field.
        assignments = {}
        field = None
        for line in MODEL_ATLAS_PATH.read_text(encoding="utf-8").split("\n"):
            heading = builder.ATLAS_FIELD_HEADING.match(line)
            if heading:
                field = heading.group(1)
                continue
            entry = builder.ATLAS_ENTRY_FILE.match(line)
            if entry:
                assignments.setdefault(entry.group(1), []).append(field)
        for path, role in self.roles.items():
            if role == "concept":
                self.assertEqual(len(assignments.get(path, [])), 1, path)

    def test_no_non_concept_receives_a_model_atlas_field(self):
        for path, role in self.roles.items():
            if role != "concept":
                self.assertNotIn(path, self.grouping)

    def test_field_distribution_is_fixed_by_source(self):
        counts = {}
        for path, role in self.roles.items():
            if role == "concept":
                counts[self.grouping[path]] = counts.get(self.grouping[path], 0) + 1
        self.assertEqual(counts, EXPECTED_FIELD_DISTRIBUTION)
        self.assertEqual(sum(counts.values()), EXPECTED_CONCEPTS)

    def test_grouping_does_not_alter_registry_classification(self):
        by_path = {record["repository_path"]: record for record in self.records}
        for path in self.grouping:
            record = by_path[path]
            self.assertEqual(record["surface_role"], "concept_node")
            # Grouping adds no classification and rewrites none.
            self.assertNotIn("grouping", record)
            self.assertNotIn("model_atlas_field", record)

    def test_dataset_grouping_matches_the_parsed_field(self):
        for node in self.data["nodes"]:
            if node["visualization_role"] == "concept":
                self.assertEqual(node["grouping"], self.grouping[node["repository_path"]])
                self.assertEqual(node["grouping_source"], "model_atlas_field")
            else:
                self.assertEqual(node["grouping"], node["visualization_role"])
                self.assertEqual(node["grouping_source"], "visualization_role")


# ---------------------------------------------------------------------------
# 16.3 Edge extraction
# ---------------------------------------------------------------------------


class EdgeExtractionTests(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.roles = builder.build_visualization_roles(cls.records)
        (
            cls.named,
            cls.named_raw,
            cls.named_excluded,
        ) = builder.parse_source_named_adjacency(REPO_ROOT, cls.records, cls.roles)
        (
            cls.navigation,
            cls.navigation_raw,
            cls.navigation_excluded,
        ) = builder.parse_navigation_adjacency(REPO_ROOT, cls.records, cls.roles)

    def test_reported_raw_and_retained_counts_by_class(self):
        self.assertEqual(self.named_raw, EXPECTED_SOURCE_NAMED_RAW)
        self.assertEqual(len(self.named), EXPECTED_SOURCE_NAMED_RETAINED)
        self.assertEqual(self.named_excluded, EXPECTED_SOURCE_NAMED_EXCLUDED)
        self.assertEqual(self.navigation_raw, EXPECTED_NAVIGATION_RAW)
        self.assertEqual(len(self.navigation), EXPECTED_NAVIGATION_RETAINED)
        self.assertEqual(self.navigation_excluded, EXPECTED_NAVIGATION_EXCLUDED)
        self.assertEqual(
            self.navigation_raw - len(self.navigation), self.navigation_excluded
        )
        self.assertEqual(self.named_raw - len(self.named), self.named_excluded)

    def test_dataset_reports_the_same_counts(self):
        self.assertEqual(
            self.data["raw_edge_counts"],
            {
                "navigation_adjacency": EXPECTED_NAVIGATION_RAW,
                "source_named_adjacency": EXPECTED_SOURCE_NAMED_RAW,
            },
        )
        self.assertEqual(
            self.data["edge_counts"],
            {
                "navigation_adjacency": EXPECTED_NAVIGATION_RETAINED,
                "source_named_adjacency": EXPECTED_SOURCE_NAMED_RETAINED,
            },
        )
        self.assertEqual(
            self.data["excluded_non_concept_endpoint_counts"],
            {
                "navigation_adjacency": EXPECTED_NAVIGATION_EXCLUDED,
                "source_named_adjacency": EXPECTED_SOURCE_NAMED_EXCLUDED,
            },
        )

    def test_all_retained_endpoints_are_concept_records(self):
        concepts = {p for p, role in self.roles.items() if role == "concept"}
        for edge in self.data["edges"]:
            self.assertIn(edge["source"], concepts, edge["id"])
            self.assertIn(edge["target"], concepts, edge["id"])

    def test_no_endpoint_outside_the_registry(self):
        registry_paths = {record["repository_path"] for record in self.records}
        for edge in self.data["edges"]:
            self.assertIn(edge["source"], registry_paths)
            self.assertIn(edge["target"], registry_paths)

    def test_source_named_is_default_on_and_navigation_default_off(self):
        for edge in self.data["edges"]:
            expected = edge["edge_class"] == "source_named_adjacency"
            self.assertIs(edge["default_visible"], expected, edge["id"])
        classes = {item["edge_class"]: item for item in self.data["edge_classes"]}
        self.assertIs(classes["source_named_adjacency"]["default_visible"], True)
        self.assertIs(classes["navigation_adjacency"]["default_visible"], False)

    def test_every_edge_is_directed(self):
        for edge in self.data["edges"]:
            self.assertIs(edge["directed"], True, edge["id"])

    def test_no_inferred_reverse_edges(self):
        # A reverse edge may exist only when it is independently written in the
        # source. Every extracted pair must be traceable to a written entry.
        written = self._written_source_named_pairs()
        for edge in self.data["edges"]:
            if edge["edge_class"] == "source_named_adjacency":
                self.assertIn((edge["source"], edge["target"]), written, edge["id"])

    def _written_source_named_pairs(self):
        pairs = set()
        for path in self.roles:
            lines = (REPO_ROOT / path).read_text(encoding="utf-8").split("\n")
            starts = [
                i
                for i, line in enumerate(lines)
                if builder.SOURCE_ADJACENCY_HEADING.match(line)
            ]
            if not starts:
                continue
            start = starts[0]
            end = len(lines)
            for index in range(start + 1, len(lines)):
                if lines[index].startswith("## "):
                    end = index
                    break
            for line in lines[start + 1 : end]:
                entry = builder.SOURCE_ADJACENCY_ENTRY.match(line)
                if entry:
                    target = builder.resolve_reference_path(entry.group(1), path)
                    if target is not None:
                        pairs.add((path, target))
        return pairs

    def test_extraction_only_reads_the_declared_adjacency_section(self):
        # Links that appear in a source document but outside its adjacency
        # section must never become edges.
        sample = "ai-readable-knowledge-architecture.md"
        lines = (REPO_ROOT / sample).read_text(encoding="utf-8").split("\n")
        starts = [
            i for i, line in enumerate(lines) if builder.SOURCE_ADJACENCY_HEADING.match(line)
        ]
        self.assertTrue(starts)
        start = starts[0]
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if lines[index].startswith("## "):
                end = index
                break
        outside = set()
        for index, line in enumerate(lines):
            if start < index < end:
                continue
            for reference in builder.MARKDOWN_LINK.findall(line):
                target = builder.resolve_reference_path(reference, sample)
                if target and target in self.roles:
                    outside.add(target)
        inside = {t for s, t in self.named if s == sample}
        self.assertTrue(outside - inside or not outside)
        for target in outside - inside:
            self.assertNotIn((sample, target), self.named)

    def test_file_with_multiple_directed_entries(self):
        counts = {}
        for source, _ in self.named:
            counts[source] = counts.get(source, 0) + 1
        self.assertTrue(any(value > 1 for value in counts.values()))
        self.assertEqual(
            counts.get("ai-readable-knowledge-architecture.md", 0),
            len(
                {
                    target
                    for source, target in self.named
                    if source == "ai-readable-knowledge-architecture.md"
                }
            ),
        )

    def test_file_with_no_adjacency_section_contributes_no_edge(self):
        sources = {source for source, _ in self.named}
        without = [
            path
            for path in self.roles
            if not any(
                builder.SOURCE_ADJACENCY_HEADING.match(line)
                for line in (REPO_ROOT / path).read_text(encoding="utf-8").split("\n")
            )
        ]
        self.assertTrue(without)
        for path in without:
            self.assertNotIn(path, sources)

    def test_unresolved_target_is_rejected(self):
        roles = dict(self.roles)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text(
                "## Relationship to Adjacent Models\n\n"
                "- [Nowhere](./does-not-exist.md) — unresolved.\n",
                encoding="utf-8",
            )
            roles = {"a.md": "concept"}
            with self.assertRaises(SystemExit):
                builder.parse_source_named_adjacency(root.resolve(), [], roles)

    def test_target_outside_the_registry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text(
                "## Relationship to Adjacent Models\n\n"
                "- [Other](./b.md) — outside the registry.\n",
                encoding="utf-8",
            )
            (root / "b.md").write_text("# b\n", encoding="utf-8")
            # b.md exists on disk but is not a registered record.
            with self.assertRaises(SystemExit):
                builder.parse_source_named_adjacency(root.resolve(), [], {"a.md": "concept"})

    def test_duplicate_identical_directed_entries_collapse_within_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text(
                "## Relationship to Adjacent Models\n\n"
                "- [B](./b.md) — first.\n"
                "- [B again](./b.md) — duplicate identical directed entry.\n",
                encoding="utf-8",
            )
            (root / "b.md").write_text("# b\n", encoding="utf-8")
            roles = {"a.md": "concept", "b.md": "concept"}
            edges, raw, excluded = builder.parse_source_named_adjacency(
                root.resolve(), [], roles
            )
            self.assertEqual(raw, 1)
            self.assertEqual(edges, [("a.md", "b.md")])
            self.assertEqual(excluded, 0)

    def test_no_reverse_edge_is_manufactured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text(
                "## Relationship to Adjacent Models\n\n- [B](./b.md) — one way.\n",
                encoding="utf-8",
            )
            (root / "b.md").write_text("# b\n", encoding="utf-8")
            edges, _, _ = builder.parse_source_named_adjacency(
                root.resolve(), [], {"a.md": "concept", "b.md": "concept"}
            )
            self.assertEqual(edges, [("a.md", "b.md")])
            self.assertNotIn(("b.md", "a.md"), edges)

    def test_non_concept_endpoints_are_filtered_from_rendered_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text(
                "## Relationship to Adjacent Models\n\n- [Guide](./g.md) — boundary.\n",
                encoding="utf-8",
            )
            (root / "g.md").write_text("# g\n", encoding="utf-8")
            edges, raw, excluded = builder.parse_source_named_adjacency(
                root.resolve(), [], {"a.md": "concept", "g.md": "boundary"}
            )
            self.assertEqual(raw, 1)
            self.assertEqual(edges, [])
            self.assertEqual(excluded, 1)

    def test_reciprocal_navigation_pairs_stay_two_directed_edges(self):
        navigation = {
            (edge["source"], edge["target"])
            for edge in self.data["edges"]
            if edge["edge_class"] == "navigation_adjacency"
        }
        reciprocal = {pair for pair in navigation if (pair[1], pair[0]) in navigation}
        self.assertTrue(reciprocal)
        for source, target in reciprocal:
            self.assertIn((source, target), navigation)
            self.assertIn((target, source), navigation)

    def test_identical_pairs_across_classes_are_not_deduplicated(self):
        named = {
            (edge["source"], edge["target"])
            for edge in self.data["edges"]
            if edge["edge_class"] == "source_named_adjacency"
        }
        navigation = {
            (edge["source"], edge["target"])
            for edge in self.data["edges"]
            if edge["edge_class"] == "navigation_adjacency"
        }
        overlap = named & navigation
        self.assertTrue(overlap, "expected at least one pair present in both classes")
        for pair in overlap:
            matches = [
                edge
                for edge in self.data["edges"]
                if (edge["source"], edge["target"]) == pair
            ]
            self.assertEqual(len(matches), 2)
            self.assertEqual(
                {edge["edge_class"] for edge in matches},
                {"source_named_adjacency", "navigation_adjacency"},
            )

    def test_no_duplicate_edge_within_a_class(self):
        keys = [
            (edge["edge_class"], edge["source"], edge["target"])
            for edge in self.data["edges"]
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_only_the_two_approved_edge_classes_exist(self):
        classes = {edge["edge_class"] for edge in self.data["edges"]}
        self.assertEqual(classes, {"source_named_adjacency", "navigation_adjacency"})

    def test_no_governance_source_use_or_user_confirmed_edge(self):
        for edge in self.data["edges"]:
            self.assertNotIn(
                edge["edge_class"],
                {
                    "governance_reference",
                    "source_use_reference",
                    "visual_layout_adjacency",
                    "user_confirmed_relation",
                    "relation",
                },
            )
        serialized = json.dumps(self.data["edges"])
        for banned in (
            "governance_reference",
            "source_use_reference",
            "user_confirmed_relation",
            "visual_layout_adjacency",
        ):
            self.assertNotIn(banned, serialized)

    def test_governance_and_source_use_are_stated_at_product_level_only(self):
        self.assertEqual(
            self.data["relation_classes_not_rendered"],
            [
                "governance_reference",
                "source_use_reference",
                "visual_layout_adjacency",
                "user_confirmed_relation",
            ],
        )
        self.assertFalse(self.data["transform_notes"]["governance_or_source_use_edges_rendered"])

    def test_registry_boundary_references_are_not_weakened(self):
        # The registry still carries its boundary_references; P5 renders none of
        # them as semantic edges but removes nothing.
        with_boundary = [r for r in self.records if r.get("boundary_references")]
        self.assertTrue(with_boundary)
        self.assertEqual(len(with_boundary), EXPECTED_RECORD_COUNT)

    def test_no_edge_is_labelled_confirmed(self):
        # No edge may carry a confirmed status in any field name or value. The
        # product-level boundary statements may say "is not a confirmed
        # relation", so prose is deliberately not scanned here.
        for edge in self.data["edges"]:
            for key, value in edge.items():
                self.assertNotIn("confirm", key.lower(), edge["id"])
                if isinstance(value, str):
                    self.assertNotIn("confirm", value.lower(), edge["id"])
            self.assertIn(
                edge["relation_status"],
                {"source_named_adjacency", "navigation_adjacency"},
            )
        for item in self.data["edge_classes"]:
            self.assertIs(item["is_confirmed_relation"], False)


# ---------------------------------------------------------------------------
# 16.4 Dataset identity
# ---------------------------------------------------------------------------


class DatasetIdentityTests(BaseCase):
    def test_node_count_and_role_distribution(self):
        self.assertEqual(len(self.data["nodes"]), EXPECTED_RECORD_COUNT)
        self.assertEqual(self.data["record_count"], EXPECTED_RECORD_COUNT)
        counts = {}
        for node in self.data["nodes"]:
            counts[node["visualization_role"]] = counts.get(node["visualization_role"], 0) + 1
        self.assertEqual(counts, EXPECTED_ROLE_DISTRIBUTION)
        self.assertEqual(self.data["role_distribution"], EXPECTED_ROLE_DISTRIBUTION)

    def test_all_fifty_nine_records_are_present_in_registry_order(self):
        registry_order = [record["repository_path"] for record in self.records]
        self.assertEqual([node["repository_path"] for node in self.data["nodes"]], registry_order)

    def test_only_concepts_participate_in_semantic_layout(self):
        for node in self.data["nodes"]:
            self.assertIs(
                node["semantic_layout_participation"],
                node["visualization_role"] == "concept",
                node["repository_path"],
            )
        self.assertEqual(self.data["semantic_layout_participant_count"], EXPECTED_CONCEPTS)
        self.assertEqual(self.data["fixed_band_record_count"], EXPECTED_FIXED_BAND)

    def test_labels_equal_registry_names_byte_for_byte(self):
        by_path = {record["repository_path"]: record for record in self.records}
        for node in self.data["nodes"]:
            expected = by_path[node["repository_path"]]["name"]
            self.assertEqual(node["display_label"], expected)
            self.assertEqual(
                node["display_label"].encode("utf-8"), expected.encode("utf-8")
            )
            self.assertEqual(node["display_label_source"], "registry_name")

    def test_nodes_carry_detail_link_provenance(self):
        by_path = {record["repository_path"]: record for record in self.records}
        for node in self.data["nodes"]:
            self.assertEqual(
                node["canonical_public_url"],
                by_path[node["repository_path"]].get("canonical_public_url"),
            )
            self.assertTrue(node["repository_path"])

    def test_source_commit_is_exact(self):
        self.assertEqual(self.data["source_commit"], EXPANDED_SOURCE_COMMIT)

    def test_no_prohibited_rank_or_centrality_field(self):
        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertNotIn(key, PROHIBITED_FIELD_NAMES, f"prohibited key {key!r}")
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(self.data)

    def test_no_degree_or_timestamp_is_published(self):
        # Checked against field NAMES, not prose: a boundary statement may
        # legitimately mention degree in order to disclaim it.
        banned_substrings = ("generated_at", "timestamp", "degree", "score", "rank")

        def walk(node, path="$"):
            if isinstance(node, dict):
                for key, value in node.items():
                    lowered = key.lower()
                    for banned in banned_substrings:
                        self.assertNotIn(banned, lowered, f"{path}.{key}")
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        walk(self.data)

    def test_dataset_is_below_the_consumer_ceiling(self):
        self.assertLess(len(DATA_PATH.read_bytes()), CONSUMER_CEILING_BYTES)

    def test_boundary_statements_are_present_and_explicit(self):
        statements = " ".join(self.data["boundary_statements"])
        self.assertIn("navigation grouping", statements)
        self.assertIn("not a formal classification", statements)
        self.assertIn("Omission does not imply nonexistence.", self.data["boundary_statements"])
        self.assertIn("not rendered as semantic edges", statements)

    def _rebuild(self, name):
        out = self.tmp / name / "data.json"
        result = run_builder(
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(MANIFEST_PATH),
                "--output",
                str(out),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return out

    def test_deterministic_rebuild_to_two_temporary_paths(self):
        first = self._rebuild("rebuild-a")
        second = self._rebuild("rebuild-b")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(
            hashlib.sha256(first.read_bytes()).hexdigest(),
            hashlib.sha256(second.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            git_blob_sha1(first.read_bytes()), git_blob_sha1(second.read_bytes())
        )

    def test_deterministic_rebuild_equals_the_tracked_dataset(self):
        rebuilt = self._rebuild("rebuild-tracked")
        self.assertEqual(rebuilt.read_bytes(), DATA_PATH.read_bytes())

    def test_tracked_dataset_identity_is_self_consistent(self):
        data = DATA_PATH.read_bytes()
        self.assertEqual(len(data), TRACKED_DATA_BYTES)
        self.assertEqual(hashlib.sha256(data).hexdigest(), TRACKED_DATA_SHA256)
        self.assertEqual(git_blob_sha1(data), TRACKED_DATA_BLOB)

    def test_tracked_manifest_identity_is_self_consistent(self):
        data = MANIFEST_PATH.read_bytes()
        self.assertEqual(len(data), TRACKED_MANIFEST_BYTES)
        self.assertEqual(hashlib.sha256(data).hexdigest(), TRACKED_MANIFEST_SHA256)
        self.assertEqual(git_blob_sha1(data), TRACKED_MANIFEST_BLOB)


# ---------------------------------------------------------------------------
# 16.5 Expanded / historical isolation
# ---------------------------------------------------------------------------


class ExpandedIsolationTests(BaseCase):
    def _historical_snapshot(self):
        stat = HISTORICAL_DATA_PATH.stat()
        return HISTORICAL_DATA_PATH.read_bytes(), stat.st_mtime_ns

    def test_expanded_requires_a_visualization_manifest(self):
        before = self._historical_snapshot()
        out = self.tmp / "no-manifest.json"
        result = run_builder(["--target", "expanded", "--output", str(out)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_EXPANDED_TARGET_REQUIRES_MANIFEST, result.stderr)
        self.assertFalse(out.exists())
        self.assertEqual(before, self._historical_snapshot())

    def test_collision_is_rejected_before_the_manifest_requirement(self):
        # Proof that collision checking runs first: the historical path is
        # refused with the collision token even though no manifest was supplied.
        before = self._historical_snapshot()
        result = run_builder(
            [
                "--target",
                "expanded",
                "--output",
                "visualizations/public-surface-authority-map/data.json",
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION, result.stderr)
        self.assertNotIn(builder.FAILURE_EXPANDED_TARGET_REQUIRES_MANIFEST, result.stderr)
        self.assertEqual(before, self._historical_snapshot())

    def test_expanded_output_cannot_resolve_into_the_historical_directory(self):
        before = self._historical_snapshot()
        result = run_builder(
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(MANIFEST_PATH),
                "--output",
                str(HISTORICAL_DATA_PATH.resolve()),
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION, result.stderr)
        self.assertEqual(before, self._historical_snapshot())

    def test_missing_manifest_file_fails_closed(self):
        out = self.tmp / "missing-manifest.json"
        result = run_builder(
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(self.tmp / "nope.json"),
                "--output",
                str(out),
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_EXPANDED_MANIFEST_INVALID, result.stderr)
        self.assertFalse(out.exists())

    def test_manifest_with_wrong_source_commit_is_rejected(self):
        broken = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        broken["source_commit"] = "0" * 40
        path = self.tmp / "wrong-commit.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        out = self.tmp / "wrong-commit-out.json"
        result = run_builder(
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(path),
                "--output",
                str(out),
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_EXPANDED_MANIFEST_INVALID, result.stderr)
        self.assertFalse(out.exists())

    def test_manifest_with_a_pending_record_is_rejected(self):
        broken = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        broken["records"][0]["visualization_membership"] = "pending"
        path = self.tmp / "pending.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        out = self.tmp / "pending-out.json"
        result = run_builder(
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(path),
                "--output",
                str(out),
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_EXPANDED_MANIFEST_INVALID, result.stderr)

    def test_manifest_out_of_registry_order_is_rejected(self):
        broken = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        broken["records"][0], broken["records"][1] = (
            broken["records"][1],
            broken["records"][0],
        )
        path = self.tmp / "reordered.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        out = self.tmp / "reordered-out.json"
        result = run_builder(
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(path),
                "--output",
                str(out),
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_EXPANDED_MANIFEST_INVALID, result.stderr)

    def test_historical_verification_does_not_read_expanded_only_inputs(self):
        # Production historical verification must not touch MODEL_ATLAS,
        # RELATION_MAP, or the visualization manifest. Proved by tracing every
        # path opened during the verify-only run.
        opened = []
        real_open = Path.open
        real_read_bytes = Path.read_bytes
        real_read_text = Path.read_text

        def spy_open(self, *args, **kwargs):
            opened.append(str(self.resolve()))
            return real_open(self, *args, **kwargs)

        def spy_read_bytes(self):
            opened.append(str(self.resolve()))
            return real_read_bytes(self)

        def spy_read_text(self, *args, **kwargs):
            opened.append(str(self.resolve()))
            return real_read_text(self, *args, **kwargs)

        from unittest import mock

        with mock.patch.object(Path, "open", spy_open), mock.patch.object(
            Path, "read_bytes", spy_read_bytes
        ), mock.patch.object(Path, "read_text", spy_read_text):
            self.assertEqual(builder.main([]), 0)
            self.assertEqual(builder.main(["--target", "historical"]), 0)

        forbidden = {
            str(MODEL_ATLAS_PATH.resolve()),
            str(RELATION_MAP_PATH.resolve()),
            str(MANIFEST_PATH.resolve()),
            str(MANIFEST_SCHEMA_PATH.resolve()),
            str(DATA_PATH.resolve()),
        }
        self.assertTrue(opened, "no reads were traced")
        self.assertEqual(forbidden & set(opened), set())
        self.assertIn(str(HISTORICAL_DATA_PATH.resolve()), opened)

    def test_historical_verification_leaves_the_artifact_untouched(self):
        before = self._historical_snapshot()
        result = run_builder([])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_builder(["--target", "historical"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self._historical_snapshot())

    def test_expanded_generation_leaves_the_historical_artifact_untouched(self):
        before = self._historical_snapshot()
        out = self.tmp / "isolation" / "data.json"
        result = run_builder(
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(MANIFEST_PATH),
                "--output",
                str(out),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(out.exists())
        self.assertEqual(before, self._historical_snapshot())

    def test_no_expanded_file_is_written_under_the_historical_directory(self):
        directory = HISTORICAL_DATA_PATH.parent
        self.assertEqual(
            sorted(p.name for p in directory.iterdir()),
            ["README.md", "app.js", "data.json", "index.html", "styles.css"],
        )

    def test_visualization_manifest_flag_is_expanded_only(self):
        result = run_builder(
            ["--target", "historical", "--visualization-manifest", str(MANIFEST_PATH)]
        )
        self.assertNotEqual(result.returncode, 0)


# ---------------------------------------------------------------------------
# 16.6 Protected source state and compatibility guard
# ---------------------------------------------------------------------------


class CompatibilityGuardTests(BaseCase):
    def test_registry_and_evidence_remain_fifty_nine(self):
        self.assertEqual(self.registry["record_count"], EXPECTED_RECORD_COUNT)
        self.assertEqual(len(self.records), EXPECTED_RECORD_COUNT)
        evidence = load_json(REPO_ROOT / "mwe-public-document-evidence.json")
        self.assertEqual(evidence["record_count"], EXPECTED_RECORD_COUNT)
        self.assertEqual(len(evidence["records"]), EXPECTED_RECORD_COUNT)

    def test_no_new_registry_surface_role_literal(self):
        roles = {record["surface_role"] for record in self.records}
        self.assertEqual(roles, set(builder.VISUALIZATION_ROLE_BY_SURFACE_ROLE))

    def test_classification_split_remains_sixteen_and_forty_three(self):
        explicit = sum(
            1 for r in self.records if r.get("classification_evidence") == "explicit_in_file"
        )
        not_asserted = sum(
            1 for r in self.records if r.get("classification_evidence") == "not_asserted"
        )
        self.assertEqual(explicit, 16)
        self.assertEqual(not_asserted, 43)

    def test_manifest_roles_do_not_alter_registry_roles(self):
        by_path = {record["repository_path"]: record for record in self.records}
        for entry in self.manifest["records"]:
            record = by_path[entry["repository_path"]]
            self.assertIn(record["surface_role"], builder.VISUALIZATION_ROLE_BY_SURFACE_ROLE)
            self.assertNotEqual(entry["visualization_role"], record["surface_role"])

    def test_protected_files_are_unchanged_from_the_p5_base(self):
        protected = [
            "mwe-public-documents.json",
            "mwe-public-document-evidence.json",
            "visualizations/public-surface-authority-map/data.json",
            "visualizations/public-surface-authority-map/README.md",
            "model-atlas/MODEL_ATLAS.md",
            "model-atlas/RELATION_MAP.md",
            "model-atlas/READING_PATHS.md",
            "README.md",
            "AUTHOR.md",
        ]
        result = subprocess.run(
            ["git", "diff", "--name-only", EXPANDED_SOURCE_COMMIT, "--", *protected],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.skipTest("git is unavailable or the P5 base commit is not present")
        self.assertEqual(result.stdout.strip(), "")

    def test_no_source_markdown_changed_from_the_p5_base(self):
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                EXPANDED_SOURCE_COMMIT,
                "--",
                "*.md",
                ":!AGENT_WORKLOG.md",
                ":!visualizations/public-surface-adjacency-map/README.md",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.skipTest("git is unavailable or the P5 base commit is not present")
        self.assertEqual(result.stdout.strip(), "")


# Tracked identity constants. These are recomputed from the generated dataset
# and manifest rather than asserted from a plan, and are pinned here only after
# the tracked files exist.
TRACKED_DATA_BYTES = 202303
TRACKED_DATA_SHA256 = "370cde8431641a4d5118e72379564deea0012cef42e49cf6542d319c8f46da69"
TRACKED_DATA_BLOB = "161501533c2378a24aac666252577974fdee9acc"

TRACKED_MANIFEST_BYTES = 18550
TRACKED_MANIFEST_SHA256 = "b1db120e3bbaef0d35ff95fa79de3231f9b4f8f183b2a60b7f8729c459112d12"
TRACKED_MANIFEST_BLOB = "1ce71b0abd2e8485cf807db0a9ba0898b1f23e55"


if __name__ == "__main__":
    unittest.main()
