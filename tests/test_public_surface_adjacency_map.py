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

import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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

# Previous P5 head, before the review follow-up. The manifest schema and the
# candidate-generator tests must be byte-identical to this commit.
PREVIOUS_P5_HEAD = "df38c22a18517e8db9a20e4fb9c2c815cb84430e"

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
EXPECTED_SOURCE_NAMED_RAW = 189
EXPECTED_SOURCE_NAMED_RETAINED = 189
EXPECTED_SOURCE_NAMED_EXCLUDED = 0
EXPECTED_NAVIGATION_RAW = 201
EXPECTED_NAVIGATION_RETAINED = 194
EXPECTED_NAVIGATION_EXCLUDED = 7

# Source-link declaration audit at the pinned source.
EXPECTED_DOCS_WITH_SECTIONS = 28
EXPECTED_LINKS_IN_SECTIONS = 190
EXPECTED_ACCEPTED_LINK_DECLARATIONS = 190
EXPECTED_IGNORED_LINKS = 0
EXPECTED_SELF_REFERENCES = 0
EXPECTED_SAME_SECTION_REPEATED = 1
EXPECTED_UNRESOLVED_INTERNAL_LINKS = 0

# The one authorized same-section evidence consolidation.
CONSOLIDATED_SOURCE = "responsibility-alignment-diagnostics.md"
CONSOLIDATED_TARGET = "responsibility-alignment-model.md"
CONSOLIDATED_LINES = [446, 450]

EXPECTED_CEILING_DISTRIBUTION = {
    "source_named_adjacency": 20,
    "navigation_adjacency": 29,
    "none": 10,
}

EXPECTED_DEPENDENCY_COUNT = 64
# The aggregate is a live hash over the working-tree dependency set, not a value
# recorded in any frozen artifact. S1 normalized 28 concept source headers after
# the pinned P5 base, so the live aggregate moved while the tracked P5 dataset
# and manifest stayed byte-identical. The P5-base value is kept below so the
# pre-S1 provenance identity remains stated rather than lost.
EXPECTED_DEPENDENCY_AGGREGATE = (
    "7967eeab06f55e3ed649f7cea1391259947f404881f096b86bd15499223d737f"
)
EXPECTED_DEPENDENCY_AGGREGATE_AT_P5_BASE = (
    "a89f1aefd341778f89e7b1e810ed760ddb7de7ff30564bda93fdaeb7a451918f"
)

# S1 source-header normalization: the exact block and the exact 28 targets. The
# compatibility guards below allow this change and nothing else.
S1_BLOCK_LINES = (
    "- **Public-surface status:** Selected external-facing node.",
    "- **Machine interpretation:** See "
    "[`MACHINE_INTERPRETATION_STATE.md`](./MACHINE_INTERPRETATION_STATE.md).",
    "- **Source use:** See [`SOURCE_USE_GUIDE.md`](./SOURCE_USE_GUIDE.md).",
    "- **Authority boundary:** This file does not by itself establish internal "
    "Registry status, formal relation status, complete ontology, or complete "
    "operational methodology.",
)
S1_NORMALIZED_TARGETS = frozenset(
    {
        "semantic-cyberpunk-condition.md",
        "cultural-curvature-unified-field.md",
        "irreversibility-conditions.md",
        "semantic-curvature-dynamics.md",
        "semantic-curvature.md",
        "semantic-physics.md",
        "semantic-pressure.md",
        "semantic-propagation-mechanics.md",
        "semantic-virology.md",
        "zero-field.md",
        "boundary-engineering.md",
        "boundary-failure.md",
        "boundary-integration-failure.md",
        "boundary-role-segmentation-model.md",
        "observer-representation-boundary.md",
        "false-legibility.md",
        "proxy-substitution.md",
        "premature-circulation-model.md",
        "premature-coherence.md",
        "reality-consistency.md",
        "reference-drift.md",
        "constraint-displacement.md",
        "constraint-residue-accumulation-model.md",
        "high-integrity-system-architecture.md",
        "benefit-burden-allocation-regimes.md",
        "cost-visibility-redistribution.md",
        "external-lifeline-collapse-under-residual-infrastructure-cross.md",
        "responsibility-alignment-model.md",
    }
)

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
    """Validate via the SHARED production implementation.

    The checker used to live only here. It now lives in the generator, so
    production generation and the test suite enforce one implementation rather
    than two that can drift apart. This wrapper keeps the test-side name.
    """
    return builder.schema_instance_errors(schema, instance, path)


def _unused_reference_checker(schema, instance, path="$"):
    """Retained only as documentation of the keyword subset in use."""
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
        sources = builder.ExpandedSources(REPO_ROOT)
        records = sources.read_json(
            builder.DOCUMENTS_FILE, builder.EXPANDED_PURPOSE_REGISTRY
        )["@graph"]
        roles = builder.build_visualization_roles(records)
        _, audit = builder.parse_source_named_adjacency(sources, records, roles)
        navigation, _, _ = builder.parse_navigation_adjacency(sources, records, roles)
        recomputed = builder.compute_relation_evidence_ceilings(roles, audit, navigation)
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
        cls.sources = builder.ExpandedSources(REPO_ROOT)
        cls.grouping = builder.parse_model_atlas_fields(
            cls.sources, cls.records, cls.roles
        )

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
        cls.sources = builder.ExpandedSources(REPO_ROOT)
        cls.named, cls.audit = builder.parse_source_named_adjacency(
            cls.sources, cls.records, cls.roles
        )
        cls.totals = cls.audit["totals"]
        cls.named_raw = cls.totals["unique_directed_edges"]
        cls.named_excluded = cls.totals["excluded_non_concept_edges"]
        (
            cls.navigation,
            cls.navigation_raw,
            cls.navigation_excluded,
        ) = builder.parse_navigation_adjacency(cls.sources, cls.records, cls.roles)

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

    def test_source_link_declaration_audit_totals(self):
        self.assertEqual(self.totals["documents_with_sections"], EXPECTED_DOCS_WITH_SECTIONS)
        self.assertEqual(self.totals["links_in_sections"], EXPECTED_LINKS_IN_SECTIONS)
        self.assertEqual(
            self.totals["accepted_link_declarations"], EXPECTED_ACCEPTED_LINK_DECLARATIONS
        )
        self.assertEqual(self.totals["ignored_links"], EXPECTED_IGNORED_LINKS)
        self.assertEqual(
            self.totals["self_references_omitted"], EXPECTED_SELF_REFERENCES
        )
        self.assertEqual(
            self.totals["same_section_repeated_evidence"], EXPECTED_SAME_SECTION_REPEATED
        )
        self.assertEqual(
            self.totals["unresolved_internal_links"], EXPECTED_UNRESOLVED_INTERNAL_LINKS
        )
        # declarations minus repeated same-section evidence == unique edges
        self.assertEqual(
            self.totals["accepted_link_declarations"]
            - self.totals["same_section_repeated_evidence"],
            self.totals["unique_directed_edges"],
        )

    def test_dataset_publishes_the_declaration_counts(self):
        self.assertEqual(
            self.data["source_named_declaration_counts"],
            {
                "markdown_link_declarations": EXPECTED_ACCEPTED_LINK_DECLARATIONS,
                "same_section_repeated_evidence": EXPECTED_SAME_SECTION_REPEATED,
                "self_references_omitted": EXPECTED_SELF_REFERENCES,
                "unique_directed_edges": EXPECTED_SOURCE_NAMED_RAW,
            },
        )

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

    # -- helpers --------------------------------------------------------

    def _fixture(self, tmp, files):
        root = Path(tmp)
        for name, text in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return builder.ExpandedSources(root.resolve())

    def _parse(self, sources, roles):
        return builder.parse_source_named_adjacency(sources, [], roles)

    def _expect_fail(self, sources, roles, token):
        buffer = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(buffer):
            self._parse(sources, roles)
        self.assertIn(token, buffer.getvalue())
        return buffer.getvalue()

    # -- accepted link positions ---------------------------------------

    def test_link_at_the_beginning_of_a_bullet(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- [B](./b.md) — leading bullet link.\n",
                "b.md": "# b\n",
            })
            edges, _ = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [("a.md", "b.md")])

    def test_link_later_in_a_bullet(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- This entry extends the [B model](./b.md) in scope.\n",
                "b.md": "# b\n",
            })
            edges, _ = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [("a.md", "b.md")])

    def test_link_in_prose_inside_the_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "A is a diagnostics-facing extension of the [B](./b.md).\n",
                "b.md": "# b\n",
            })
            edges, _ = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [("a.md", "b.md")])

    def test_link_in_a_table_row_and_in_a_fenced_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "| Entry | Adjacent |\n|---|---|\n"
                        "| A | [B](./b.md) |\n\n"
                        "```text\nsee [C](./c.md)\n```\n",
                "b.md": "# b\n",
                "c.md": "# c\n",
            })
            edges, _ = self._parse(
                sources, {"a.md": "concept", "b.md": "concept", "c.md": "concept"}
            )
            self.assertEqual(sorted(edges), [("a.md", "b.md"), ("a.md", "c.md")])

    # -- bare names and prose are not declarations ----------------------

    def test_bare_name_creates_no_edge_and_no_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- B Model — described in prose only, no link.\n"
                        "- Some Other Concept — also unlinked.\n",
                "b.md": "# b\n",
            })
            edges, audit = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [])
            self.assertEqual(audit["totals"]["unresolved_internal_links"], 0)
            self.assertEqual(audit["totals"]["links_in_sections"], 0)

    def test_fenced_bare_labels_create_no_edge_and_no_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "```text\nB Model\n= a definition line\n\n"
                        "ownership\n= another definition\n```\n",
                "b.md": "# b\n",
            })
            edges, audit = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [])
            self.assertEqual(audit["totals"]["unresolved_internal_links"], 0)

    def test_explanatory_prose_creates_no_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "A is adjacent to, but distinct from, several models.\n"
                        "It is also adjacent to B Model and C Model.\n",
                "b.md": "# b\n",
            })
            edges, audit = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [])
            self.assertEqual(audit["totals"]["unresolved_internal_links"], 0)

    def test_false_legibility_regression(self):
        # Concrete regression for the motivating case: its formal adjacency
        # section names adjacent models only as bare labels in a fenced block.
        # Those are human-readable adjacency discussion. They must create no
        # edge AND must not be treated as unresolved machine-readable links.
        section = [s for s in self.audit["sections"]
                   if s["repository_path"] == "false-legibility.md"]
        self.assertEqual(len(section), 1, "false-legibility.md has one formal section")
        section = section[0]
        self.assertEqual(section["links"], [])
        self.assertEqual(section["accepted"], [])
        self.assertEqual(section["unresolved"], [])
        self.assertEqual(section["repeated_evidence"], [])
        # No source-named edge originates from it.
        self.assertEqual([e for e in self.named if e[0] == "false-legibility.md"], [])
        # Its bare labels really are present in the source.
        body = "\n".join(
            (REPO_ROOT / "false-legibility.md").read_text(encoding="utf-8").split("\n")[
                section["heading_line"]: section["section_end_line"]
            ]
        )
        for bare in ("Premature Coherence", "Reality Consistency", "Semantic Virology"):
            self.assertIn(bare, body)
        # Navigation adjacency remains available for it independently.
        self.assertTrue(
            [e for e in self.navigation if "false-legibility.md" in e],
            "false-legibility.md still participates in navigation adjacency",
        )

    # -- ignored non-document links -------------------------------------

    def test_external_and_fragment_links_are_ignored_not_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- [site](https://example.org/x.md) — external.\n"
                        "- [doi](https://doi.org/10.1234/zenodo) — DOI.\n"
                        "- [osf](https://osf.io/abcde/) — OSF.\n"
                        "- [anchor](#a-section) — fragment only.\n"
                        "- [asset](./diagram.png) — not a Markdown document.\n",
                "b.md": "# b\n",
            })
            edges, audit = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [])
            self.assertEqual(audit["totals"]["ignored_links"], 5)
            self.assertEqual(audit["totals"]["unresolved_internal_links"], 0)

    # -- fail-closed internal links -------------------------------------

    def test_internal_link_to_a_missing_document_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- [Nowhere](./does-not-exist.md) — unresolved.\n",
            })
            err = self._expect_fail(
                sources, {"a.md": "concept"},
                builder.FAILURE_EXPANDED_SOURCE_ADJACENCY_UNRESOLVED,
            )
            self.assertIn("a.md:3", err)
            self.assertIn("./does-not-exist.md", err)

    def test_internal_link_outside_the_registry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- [Other](./b.md) — exists but is unregistered.\n",
                "b.md": "# b\n",
            })
            self._expect_fail(
                sources, {"a.md": "concept"},
                builder.FAILURE_EXPANDED_SOURCE_ADJACENCY_UNRESOLVED,
            )

    def test_internal_link_escaping_the_repository_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- [Escape](../outside.md) — escapes the root.\n",
            })
            self._expect_fail(
                sources, {"a.md": "concept"},
                builder.FAILURE_EXPANDED_SOURCE_ADJACENCY_UNRESOLVED,
            )

    # -- sections, self-references, consolidation ------------------------

    def test_multiple_formal_sections_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- [B](./b.md) — first section.\n\n"
                        "## Something Else\n\n"
                        "## Relationship to Adjacent Public Frameworks\n\n"
                        "- [B](./b.md) — second section.\n",
                "b.md": "# b\n",
            })
            err = self._expect_fail(
                sources, {"a.md": "concept", "b.md": "concept"},
                builder.FAILURE_EXPANDED_DUPLICATE_DIRECTED_EDGE,
            )
            self.assertIn("formal adjacency sections", err)

    def test_self_reference_is_omitted_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "- [A itself](./a.md) — self reference.\n"
                        "- [B](./b.md) — real edge.\n",
                "b.md": "# b\n",
            })
            edges, audit = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [("a.md", "b.md")])
            self.assertEqual(audit["totals"]["self_references_omitted"], 1)

    def test_same_section_repeated_links_consolidate_to_one_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "A extends the [B](./b.md) in prose.\n\n"
                        "- [B](./b.md) — and again in the structured list.\n",
                "b.md": "# b\n",
            })
            edges, audit = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [("a.md", "b.md")])
            self.assertEqual(audit["totals"]["same_section_repeated_evidence"], 1)
            evidence = audit["evidence"][0]
            self.assertEqual(evidence["declaration_count"], 2)
            self.assertEqual(evidence["declaration_lines"], [3, 5])
            self.assertEqual(evidence["declaration_hrefs"], ["./b.md", "./b.md"])

    def test_consolidation_does_not_infer_a_reverse_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n"
                        "A extends the [B](./b.md).\n\n"
                        "- [B](./b.md) — repeated evidence.\n",
                "b.md": "# b\n",
            })
            edges, _ = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [("a.md", "b.md")])
            self.assertNotIn(("b.md", "a.md"), edges)

    def test_responsibility_alignment_diagnostics_regression(self):
        # The one authorized same-section consolidation in the tracked source.
        evidence = [
            item
            for item in self.audit["evidence"]
            if item["source"] == CONSOLIDATED_SOURCE
            and item["target"] == CONSOLIDATED_TARGET
        ]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["declaration_count"], 2)
        self.assertEqual(evidence[0]["declaration_lines"], CONSOLIDATED_LINES)
        # Exactly one rendered edge for the pair.
        rendered = [
            edge
            for edge in self.data["edges"]
            if edge["edge_class"] == "source_named_adjacency"
            and edge["source"] == CONSOLIDATED_SOURCE
            and edge["target"] == CONSOLIDATED_TARGET
        ]
        self.assertEqual(len(rendered), 1)
        # It is the only consolidation in the whole tracked source.
        multi = [i for i in self.audit["evidence"] if i["declaration_count"] > 1]
        self.assertEqual(len(multi), 1)

    def test_no_reverse_edge_is_manufactured(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n- [B](./b.md) — one way.\n",
                "b.md": "# b\n",
            })
            edges, _ = self._parse(sources, {"a.md": "concept", "b.md": "concept"})
            self.assertEqual(edges, [("a.md", "b.md")])
            self.assertNotIn(("b.md", "a.md"), edges)

    def test_non_concept_endpoints_are_filtered_from_rendered_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = self._fixture(tmp, {
                "a.md": "## Relationship to Adjacent Models\n\n- [Guide](./g.md) — boundary.\n",
                "g.md": "# g\n",
            })
            edges, audit = self._parse(sources, {"a.md": "concept", "g.md": "boundary"})
            self.assertEqual(edges, [])
            self.assertEqual(audit["totals"]["unique_directed_edges"], 1)
            self.assertEqual(audit["totals"]["excluded_non_concept_edges"], 1)

    # -- navigation duplicates still fail -------------------------------

    def test_duplicate_navigation_pair_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "model-atlas").mkdir()
            (root / "model-atlas" / "RELATION_MAP.md").write_text(
                "| Entry | File | Field | Type | Function | Adjacent entries | Reading priority |\n"
                "|---|---|---|---|---|---|---|\n"
                "| A | [`a`](../a.md) | F | T | fn | [`b`](../b.md) | Core |\n"
                "| A | [`a`](../a.md) | F | T | fn | [`b`](../b.md) | Core |\n",
                encoding="utf-8",
            )
            (root / "a.md").write_text("# a\n", encoding="utf-8")
            (root / "b.md").write_text("# b\n", encoding="utf-8")
            sources = builder.ExpandedSources(root.resolve())
            buffer = io.StringIO()
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(buffer):
                builder.parse_navigation_adjacency(
                    sources, [], {"a.md": "concept", "b.md": "concept"}
                )
            err = buffer.getvalue()
            self.assertIn(builder.FAILURE_EXPANDED_DUPLICATE_DIRECTED_EDGE, err)
            self.assertIn("navigation_adjacency", err)
            self.assertIn("a.md -> b.md", err)
            # first and duplicate locations are both reported
            self.assertIn(":3", err)
            self.assertIn(":4", err)

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
            self.assertNotIn("is_confirmed_relation", item)
            for key in item:
                self.assertNotIn("confirm", key.lower())

    def test_edge_status_and_ceiling_fields_are_retained_and_safe(self):
        # Evidence/status/ceiling separation is retained deliberately; it must
        # never promote adjacency into a formal or confirmed relation.
        for edge in self.data["edges"]:
            self.assertEqual(edge["relation_status"], edge["edge_class"])
            self.assertEqual(edge["authority_ceiling"], "navigation_only")
            self.assertNotEqual(edge["relation_status"], "confirmed")


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

    def _diff_names(self, *pathspecs):
        result = subprocess.run(
            ["git", "diff", "--name-only", EXPANDED_SOURCE_COMMIT, "--", *pathspecs],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.skipTest("git is unavailable or the P5 base commit is not present")
        return sorted(name for name in result.stdout.split("\n") if name)

    def _text_at_p5_base(self, relative_path):
        result = subprocess.run(
            ["git", "show", f"{EXPANDED_SOURCE_COMMIT}:{relative_path}"],
            cwd=str(REPO_ROOT),
            capture_output=True,
        )
        if result.returncode != 0:
            self.skipTest(f"{relative_path} is not available at the P5 base commit")
        return result.stdout.decode("utf-8")

    def test_protected_files_are_unchanged_from_the_p5_base(self):
        protected = [
            "mwe-public-documents.json",
            "visualizations/public-surface-authority-map/data.json",
            "visualizations/public-surface-authority-map/README.md",
            "model-atlas/MODEL_ATLAS.md",
            "model-atlas/RELATION_MAP.md",
            "model-atlas/READING_PATHS.md",
            "README.md",
            "AUTHOR.md",
        ]
        # mwe-public-document-evidence.json is deliberately not in this list: S1
        # changed its provenance after the P5 base. The next test pins exactly
        # what changed there, so nothing is merely exempted.
        self.assertNotIn("mwe-public-document-evidence.json", protected)
        self.assertEqual(self._diff_names(*protected), [])

    def test_evidence_changed_only_by_the_s1_provenance_flip(self):
        # The evidence manifest is the one protected file S1 touches, and it may
        # differ from the P5 base only by public_surface_status and
        # authority_ceiling moving to source_declared on the 28 S1 targets.
        base = json.loads(self._text_at_p5_base("mwe-public-document-evidence.json"))
        current = load_json(REPO_ROOT / "mwe-public-document-evidence.json")
        self.assertEqual(
            {key: value for key, value in base.items() if key != "records"},
            {key: value for key, value in current.items() if key != "records"},
        )
        self.assertEqual(len(base["records"]), len(current["records"]))
        changed = set()
        for before, after in zip(base["records"], current["records"]):
            path = before["repository_path"]
            self.assertEqual(path, after["repository_path"])
            for field, value in before["field_evidence"].items():
                if after["field_evidence"][field] == value:
                    continue
                changed.add((path, field))
                self.assertIn(field, {"public_surface_status", "authority_ceiling"})
                self.assertEqual(value, "registry_policy")
                self.assertEqual(after["field_evidence"][field], "source_declared")
        self.assertEqual(
            changed,
            {
                (path, field)
                for path in S1_NORMALIZED_TARGETS
                for field in ("public_surface_status", "authority_ceiling")
            },
        )

    def test_source_markdown_changed_only_by_the_s1_header_block(self):
        # S1 normalized 28 concept headers after the pinned P5 base. Every other
        # source markdown file must still be byte-identical to that base, and
        # each normalized file must differ by the four inserted lines alone.
        changed = self._diff_names(
            "*.md",
            ":!AGENT_WORKLOG.md",
            ":!visualizations/public-surface-adjacency-map/README.md",
            # Same exclusion, same reason: a visualization folder's own README
            # is not source markdown and is not covered by the S1 header guard.
            ":!visualizations/mwe-development-rate/README.md",
        )
        self.assertEqual(set(changed), S1_NORMALIZED_TARGETS)
        block = "\n".join(S1_BLOCK_LINES)
        for path in changed:
            with self.subTest(path=path):
                current = (REPO_ROOT / path).read_text(encoding="utf-8")
                self.assertEqual(current.count(block), 1)
                # Removing the inserted block restores the P5-base bytes exactly:
                # no existing line was moved, rewritten or reflowed.
                self.assertEqual(
                    current.replace(block + "\n", "", 1),
                    self._text_at_p5_base(path),
                )


# Tracked identity constants. These are recomputed from the generated dataset
# and manifest rather than asserted from a plan, and are pinned here only after
# the tracked files exist.
TRACKED_DATA_BYTES = 206617
TRACKED_DATA_SHA256 = "0b763eb78fea5c53364609ecc5d7019422c54b950d32f29f79ad37f24f1637b7"
TRACKED_DATA_BLOB = "3077568edeeb0d6a769899a1a3cf79c3f9152f83"

TRACKED_MANIFEST_BYTES = 18554
TRACKED_MANIFEST_SHA256 = "b6ea211e265631b984f0e9ea53fb7301f3fd0986dbdaa2a9d349c0524591d0fe"
TRACKED_MANIFEST_BLOB = "159ac950abf2172bcdd2cc420afde63578140eb8"


class DatasetKeyHygieneTests(BaseCase):
    def _keys(self):
        found = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    found.append(key)
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(self.data)
        return found

    def test_no_dataset_key_implies_formal_or_confirmed_relation_status(self):
        # Exact key names, because a disclaimer key such as
        # node_size_implies_importance legitimately contains a banned word while
        # asserting the opposite.
        banned_exact = {
            "confirmed",
            "is_confirmed_relation",
            "formal_relation_status",
            "rank",
            "centrality",
            "degree",
            "authority_score",
            "importance",
            "priority",
            "confidence",
            "relation_strength",
        }
        for key in self._keys():
            lowered = key.lower()
            self.assertNotIn(lowered, banned_exact, f"dataset key {key!r}")
            # "confirmed" may never appear anywhere in a key, in any position.
            self.assertNotIn("confirm", lowered, f"dataset key {key!r}")

    def test_relation_status_key_is_present_but_never_confirmed(self):
        # relation_status is retained by the planning contract; only a
        # "confirmed" value or a confirmed-bearing key is forbidden.
        self.assertIn("relation_status", self._keys())
        for edge in self.data["edges"]:
            self.assertIn(
                edge["relation_status"],
                {"source_named_adjacency", "navigation_adjacency"},
            )

    def test_boundary_prose_still_states_no_confirmed_relation(self):
        statements = " ".join(self.data["boundary_statements"]).lower()
        self.assertIn("not a confirmed relation", statements)
        self.assertIn("user_confirmed_relation", self.data["relation_classes_not_rendered"])


class ManifestProductionValidationTests(BaseCase):
    """Every invalid manifest must be rejected by PRODUCTION generation."""

    def _reject(self, mutate, token=None, schema_text=None):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        mutate(manifest)
        directory = Path(tempfile.mkdtemp(dir=self.tmp))
        path = directory / "visualization-manifest.json"
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        if schema_text is None:
            shutil.copy2(MANIFEST_SCHEMA_PATH, directory / "visualization-manifest.schema.json")
        elif schema_text != "__missing__":
            (directory / "visualization-manifest.schema.json").write_text(
                schema_text, encoding="utf-8"
            )
        out = directory / "out.json"
        result = run_builder(
            [
                "--target", "expanded",
                "--visualization-manifest", str(path),
                "--output", str(out),
            ]
        )
        self.assertNotEqual(result.returncode, 0, "invalid manifest was accepted")
        self.assertIn(
            token or builder.FAILURE_EXPANDED_MANIFEST_INVALID, result.stderr
        )
        self.assertFalse(out.exists(), "invalid manifest produced output")
        return result.stderr

    def test_valid_manifest_and_schema_are_accepted(self):
        directory = Path(tempfile.mkdtemp(dir=self.tmp))
        shutil.copy2(MANIFEST_PATH, directory / "visualization-manifest.json")
        shutil.copy2(MANIFEST_SCHEMA_PATH, directory / "visualization-manifest.schema.json")
        out = directory / "out.json"
        result = run_builder(
            [
                "--target", "expanded",
                "--visualization-manifest", str(directory / "visualization-manifest.json"),
                "--output", str(out),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(out.read_bytes(), DATA_PATH.read_bytes())

    def test_extra_top_level_property(self):
        self._reject(lambda m: m.update({"unexpected": 1}))

    def test_extra_record_property(self):
        self._reject(lambda m: m["records"][0].update({"unexpected": 1}))

    def test_wrong_schema_reference(self):
        self._reject(lambda m: m.update({"$schema": "./other.schema.json"}))

    def test_wrong_manifest_version(self):
        self._reject(lambda m: m.update({"manifest_version": "2.0"}))

    def test_wrong_describes(self):
        self._reject(lambda m: m.update({"describes": "../../elsewhere.json"}))

    def test_wrong_scope(self):
        self._reject(lambda m: m.update({"scope": "something_else"}))

    def test_wrong_authority_ceiling(self):
        self._reject(lambda m: m.update({"authority_ceiling": "full_authority"}))

    def test_invalid_enum_value(self):
        self._reject(lambda m: m["records"][0].update({"visualization_role": "model"}))

    def test_invalid_membership_enum_value(self):
        self._reject(
            lambda m: m["records"][0].update({"visualization_membership": "maybe"})
        )

    def test_invalid_ceiling_enum_value(self):
        self._reject(
            lambda m: m["records"][0].update({"relation_evidence_ceiling": "confirmed"})
        )

    def test_missing_required_record_field(self):
        self._reject(lambda m: m["records"][0].pop("grouping_source"))

    def test_missing_required_top_level_field(self):
        self._reject(lambda m: m.pop("scope"))

    def test_duplicate_manifest_record(self):
        def mutate(manifest):
            manifest["records"][1] = json.loads(json.dumps(manifest["records"][0]))
        self._reject(mutate)

    def test_malformed_repository_path(self):
        self._reject(lambda m: m["records"][0].update({"repository_path": "/absolute.md"}))

    def test_wrong_record_count(self):
        self._reject(lambda m: m.update({"record_count": 58}))

    def test_too_few_records(self):
        self._reject(lambda m: m["records"].pop())

    def test_missing_schema_file(self):
        self._reject(lambda m: None, schema_text="__missing__")

    def test_schema_with_wrong_draft(self):
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        self._reject(lambda m: None, schema_text=json.dumps(schema))

    def test_unreadable_schema_json(self):
        self._reject(lambda m: None, schema_text="{not json")

    def test_tracked_schema_is_unmodified(self):
        result = subprocess.run(
            ["git", "diff", "--name-only", PREVIOUS_P5_HEAD, "--",
             "visualizations/public-surface-adjacency-map/visualization-manifest.schema.json"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.skipTest("git unavailable")
        self.assertEqual(result.stdout.strip(), "")


class ManifestSchemaAuthorityTests(BaseCase):
    """The adjacent schema must BE the authoritative tracked schema, by bytes.

    The schema is resolved next to the caller-supplied manifest, so a correct
    draft declaration and filename are not sufficient authorization: a caller
    could otherwise substitute a weakened schema and redefine the contract.
    """

    def _run(self, schema_bytes, manifest_bytes=None):
        directory = Path(tempfile.mkdtemp(dir=self.tmp))
        manifest = directory / "visualization-manifest.json"
        if manifest_bytes is None:
            shutil.copy2(MANIFEST_PATH, manifest)
        else:
            manifest.write_bytes(manifest_bytes)
        if schema_bytes is not None:
            (directory / "visualization-manifest.schema.json").write_bytes(schema_bytes)
        out = directory / "out.json"
        result = run_builder(
            [
                "--target", "expanded",
                "--visualization-manifest", str(manifest),
                "--output", str(out),
            ]
        )
        return result, out

    def _expect_rejected(self, schema_bytes, manifest_bytes=None):
        result, out = self._run(schema_bytes, manifest_bytes)
        self.assertNotEqual(result.returncode, 0, "a non-authoritative schema was accepted")
        self.assertIn(builder.FAILURE_EXPANDED_MANIFEST_INVALID, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(out.exists(), "rejected input produced output")
        return result.stderr

    def _mutated_schema(self, mutate):
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        mutate(schema)
        return (json.dumps(schema, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    # -- pinned constants ------------------------------------------------

    def test_pinned_constants_match_the_tracked_schema(self):
        data = MANIFEST_SCHEMA_PATH.read_bytes()
        self.assertEqual(len(data), builder.EXPANDED_MANIFEST_SCHEMA_BYTES)
        self.assertEqual(
            hashlib.sha256(data).hexdigest(), builder.EXPANDED_MANIFEST_SCHEMA_SHA256
        )
        self.assertEqual(git_blob_sha1(data), builder.EXPANDED_MANIFEST_SCHEMA_BLOB)

    def test_pinned_schema_path_constant_is_the_tracked_path(self):
        self.assertEqual(
            REPO_ROOT / builder.EXPANDED_MANIFEST_SCHEMA_FILE, MANIFEST_SCHEMA_PATH
        )

    # -- the authoritative schema is accepted ----------------------------

    def test_byte_identical_copy_is_accepted(self):
        result, out = self._run(MANIFEST_SCHEMA_PATH.read_bytes())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(out.read_bytes(), DATA_PATH.read_bytes())

    # -- weakened schemas are rejected -----------------------------------

    def test_weakened_additional_properties_is_rejected(self):
        def mutate(schema):
            schema["properties"]["records"]["items"]["additionalProperties"] = True
        err = self._expect_rejected(self._mutated_schema(mutate))
        self.assertIn("byte identity", err)

    def test_removed_const_is_rejected(self):
        self._expect_rejected(
            self._mutated_schema(lambda s: s["properties"]["scope"].pop("const"))
        )

    def test_changed_const_is_rejected(self):
        self._expect_rejected(
            self._mutated_schema(
                lambda s: s["properties"]["authority_ceiling"].update({"const": "anything"})
            )
        )

    def test_widened_enum_is_rejected(self):
        def mutate(schema):
            schema["properties"]["records"]["items"]["properties"]["visualization_role"][
                "enum"
            ].append("model")
        self._expect_rejected(self._mutated_schema(mutate))

    def test_removed_required_field_is_rejected(self):
        def mutate(schema):
            schema["properties"]["records"]["items"]["required"].remove("grouping_source")
        self._expect_rejected(self._mutated_schema(mutate))

    def test_relaxed_repository_path_pattern_is_rejected(self):
        def mutate(schema):
            schema["properties"]["records"]["items"]["properties"]["repository_path"][
                "pattern"
            ] = ".*"
        self._expect_rejected(self._mutated_schema(mutate))

    # -- byte identity, not semantic equivalence -------------------------

    def test_whitespace_only_change_is_rejected(self):
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        self._expect_rejected(
            (json.dumps(schema, indent=4, ensure_ascii=False) + "\n").encode("utf-8")
        )

    def test_key_order_change_is_rejected(self):
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        self._expect_rejected(
            (json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
                "utf-8"
            )
        )

    def test_trailing_newline_change_is_rejected(self):
        self._expect_rejected(MANIFEST_SCHEMA_PATH.read_bytes().rstrip(b"\n"))

    def test_rejection_reports_expected_and_actual_identity(self):
        err = self._expect_rejected(MANIFEST_SCHEMA_PATH.read_bytes() + b"\n")
        self.assertIn(str(builder.EXPANDED_MANIFEST_SCHEMA_BYTES), err)
        self.assertIn(builder.EXPANDED_MANIFEST_SCHEMA_SHA256, err)
        self.assertIn(builder.EXPANDED_MANIFEST_SCHEMA_BLOB, err)
        self.assertIn("actual byte length", err)

    # -- invalid UTF-8 ---------------------------------------------------

    def test_invalid_utf8_schema_fails_with_the_manifest_token(self):
        err = self._expect_rejected(b"\xff\xfe{ not utf-8 }\n")
        # It is a manifest-contract failure, not a generic source-input failure.
        self.assertNotIn(builder.FAILURE_EXPANDED_SOURCE_INPUT_UNREADABLE, err)

    def test_invalid_utf8_manifest_fails_with_the_stable_token(self):
        err = self._expect_rejected(
            MANIFEST_SCHEMA_PATH.read_bytes(),
            manifest_bytes=b'{"$schema": "./visualization-manifest.schema.json", '
            b'"name": "\xff\xfe"}\n',
        )
        self.assertIn("not valid UTF-8", err)
        self.assertNotIn("UnicodeDecodeError", err.replace("codec", ""))

    def test_invalid_utf8_leaves_the_historical_artifact_untouched(self):
        before = (
            HISTORICAL_DATA_PATH.read_bytes(),
            HISTORICAL_DATA_PATH.stat().st_mtime_ns,
        )
        self.test_invalid_utf8_schema_fails_with_the_manifest_token()
        self.test_invalid_utf8_manifest_fails_with_the_stable_token()
        after = (
            HISTORICAL_DATA_PATH.read_bytes(),
            HISTORICAL_DATA_PATH.stat().st_mtime_ns,
        )
        self.assertEqual(before, after)

    def test_no_weakened_schema_ever_produced_output(self):
        # Belt-and-braces sweep: every mutation above must leave no artifact.
        for schema_bytes in (
            self._mutated_schema(
                lambda s: s["properties"]["records"]["items"].update(
                    {"additionalProperties": True}
                )
            ),
            b"\xff\xfe bad\n",
            MANIFEST_SCHEMA_PATH.read_bytes() + b" ",
        ):
            _, out = self._run(schema_bytes)
            self.assertFalse(out.exists())


class ExpandedDependencyProvenanceTests(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        manifest_bytes = MANIFEST_PATH.read_bytes()
        _, _, cls.inventory = builder.assemble_adjacency_data(
            REPO_ROOT,
            json.loads(manifest_bytes.decode("utf-8")),
            str(MANIFEST_PATH),
            MANIFEST_PATH,
            manifest_bytes,
        )

    def test_inventory_count_and_aggregate_are_deterministic(self):
        self.assertEqual(self.inventory["dependency_count"], EXPECTED_DEPENDENCY_COUNT)
        self.assertEqual(self.inventory["aggregate_sha256"], EXPECTED_DEPENDENCY_AGGREGATE)
        # S1 moved the live aggregate off its P5-base value. The two must stay
        # distinct: if they coincided again, a source header would have been
        # reverted or the pin would have been silently restored.
        self.assertNotEqual(
            EXPECTED_DEPENDENCY_AGGREGATE, EXPECTED_DEPENDENCY_AGGREGATE_AT_P5_BASE
        )
        manifest_bytes = MANIFEST_PATH.read_bytes()
        _, _, again = builder.assemble_adjacency_data(
            REPO_ROOT,
            json.loads(manifest_bytes.decode("utf-8")),
            str(MANIFEST_PATH),
            MANIFEST_PATH,
            manifest_bytes,
        )
        self.assertEqual(again, self.inventory)

    def test_inventory_is_sorted_and_fully_populated(self):
        paths = [item["path"] for item in self.inventory["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(set(paths)), len(paths))
        for item in self.inventory["files"]:
            self.assertGreater(item["byte_length"], 0)
            self.assertEqual(len(item["sha256"]), 64)
            self.assertEqual(len(item["git_blob_sha1"]), 40)
            self.assertEqual(item["read_purposes"], sorted(item["read_purposes"]))
            self.assertTrue(item["read_purposes"])

    def test_inventory_covers_the_required_expanded_inputs(self):
        by_path = {item["path"]: item for item in self.inventory["files"]}
        self.assertIn(builder.DOCUMENTS_FILE, by_path)
        self.assertIn(builder.MODEL_ATLAS_FILE, by_path)
        self.assertIn(builder.RELATION_MAP_FILE, by_path)
        manifest_label = "visualizations/public-surface-adjacency-map/visualization-manifest.json"
        schema_label = "visualizations/public-surface-adjacency-map/visualization-manifest.schema.json"
        self.assertIn(manifest_label, by_path)
        self.assertIn(schema_label, by_path)
        self.assertIn(
            builder.EXPANDED_PURPOSE_MANIFEST_SCHEMA, by_path[schema_label]["read_purposes"]
        )
        # Every registered source document audited for adjacency is covered.
        for record in self.records:
            self.assertIn(record["repository_path"], by_path)

    def test_inventory_purposes_are_from_the_closed_vocabulary(self):
        allowed = {
            builder.EXPANDED_PURPOSE_REGISTRY,
            builder.EXPANDED_PURPOSE_MANIFEST,
            builder.EXPANDED_PURPOSE_MANIFEST_SCHEMA,
            builder.EXPANDED_PURPOSE_GROUPING,
            builder.EXPANDED_PURPOSE_NAVIGATION,
            builder.EXPANDED_PURPOSE_SOURCE_NAMED,
            builder.EXPANDED_PURPOSE_EXISTENCE,
        }
        for item in self.inventory["files"]:
            for purpose in item["read_purposes"]:
                self.assertIn(purpose, allowed)

    def test_recorded_hashes_match_the_files_on_disk(self):
        for item in self.inventory["files"]:
            path = REPO_ROOT / item["path"]
            data = path.read_bytes()
            self.assertEqual(item["byte_length"], len(data), item["path"])
            self.assertEqual(item["sha256"], hashlib.sha256(data).hexdigest(), item["path"])
            self.assertEqual(item["git_blob_sha1"], git_blob_sha1(data), item["path"])

    def test_actual_reads_equal_the_enumerated_inventory(self):
        """Bidirectional proof: enumerated dependencies == actual reads."""
        observed = set()
        real_read_bytes = Path.read_bytes
        real_read_text = Path.read_text
        real_open = Path.open

        def note(path):
            try:
                observed.add(str(Path(path).resolve()))
            except OSError:
                pass

        def spy_read_bytes(self):
            note(self)
            return real_read_bytes(self)

        def spy_read_text(self, *a, **k):
            note(self)
            return real_read_text(self, *a, **k)

        def spy_open(self, *a, **k):
            note(self)
            return real_open(self, *a, **k)

        observed.clear()
        with mock.patch.object(Path, "read_bytes", spy_read_bytes), mock.patch.object(
            Path, "read_text", spy_read_text
        ), mock.patch.object(Path, "open", spy_open):
            # The manifest read happens inside the traced region too, so the
            # proof covers the caller's read of it rather than exempting it.
            manifest_bytes = MANIFEST_PATH.read_bytes()
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            _, _, inventory = builder.assemble_adjacency_data(
                REPO_ROOT, manifest, str(MANIFEST_PATH), MANIFEST_PATH, manifest_bytes
            )

        enumerated = {
            str((REPO_ROOT / item["path"]).resolve()) for item in inventory["files"]
        }
        # Direction 1: nothing was read that the inventory does not enumerate.
        self.assertEqual(
            observed - enumerated, set(), "actual read is missing from the inventory"
        )
        # Direction 2: nothing is enumerated that was not actually read.
        self.assertEqual(
            enumerated - observed, set(), "inventory entry was never read"
        )

    def test_historical_inventory_remains_thirty_nine(self):
        self.assertEqual(builder.HISTORICAL_DEPENDENCY_INVENTORY_COUNT, 39)
        result = run_builder(["--target", "historical"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("39", result.stdout)

    def test_expanded_inventory_does_not_widen_historical_enumeration(self):
        historical = builder.collect_read_purposes(REPO_ROOT)
        self.assertNotIn(builder.MODEL_ATLAS_FILE, historical)
        self.assertNotIn(builder.RELATION_MAP_FILE, historical)
        self.assertNotIn(
            "visualizations/public-surface-adjacency-map/visualization-manifest.json",
            historical,
        )


class ExpandedSourceInputFailureTests(BaseCase):
    def _run_against(self, root):
        manifest = root / "manifest.json"
        out = root / "out.json"
        result = subprocess.run(
            [sys.executable, str(BUILDER), "--target", "expanded",
             "--visualization-manifest", str(manifest), "--output", str(out)],
            cwd=str(root), capture_output=True, text=True,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        )
        return result, out

    def _generator_root(self, name):
        root = Path(tempfile.mkdtemp(dir=self.tmp)) / name
        (root / "scripts").mkdir(parents=True)
        shutil.copy2(BUILDER, root / "scripts")
        shutil.copy2(REGISTRY_PATH, root)
        shutil.copy2(MANIFEST_PATH, root / "manifest.json")
        # The schema is resolved next to the manifest, so it must be present or
        # the run stops on the manifest contract before reaching source reads.
        shutil.copy2(MANIFEST_SCHEMA_PATH, root / "visualization-manifest.schema.json")
        artifact = root / "visualizations" / "public-surface-authority-map"
        artifact.mkdir(parents=True)
        shutil.copy2(HISTORICAL_DATA_PATH, artifact / "data.json")
        return root

    def _run_from(self, root):
        out = Path(tempfile.mkdtemp(dir=self.tmp)) / "out.json"
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / BUILDER.name),
             "--target", "expanded",
             "--visualization-manifest", str(root / "manifest.json"),
             "--output", str(out)],
            cwd=str(root), capture_output=True, text=True,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        )
        return result, out

    def test_missing_source_document_fails_closed(self):
        root = self._generator_root("missing-source")
        # MODEL_ATLAS and the source documents are absent from this root.
        result, out = self._run_from(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_EXPANDED_SOURCE_INPUT_UNREADABLE, result.stderr)
        self.assertFalse(out.exists())

    def test_invalid_utf8_source_fails_closed(self):
        root = self._generator_root("bad-utf8")
        (root / "model-atlas").mkdir(parents=True, exist_ok=True)
        (root / "model-atlas" / "MODEL_ATLAS.md").write_bytes(b"## Field\n\xff\xfe not utf-8\n")
        result, out = self._run_from(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_EXPANDED_SOURCE_INPUT_UNREADABLE, result.stderr)
        self.assertFalse(out.exists())

    def test_source_read_failure_names_the_path_and_reason(self):
        root = self._generator_root("named-reason")
        result, _ = self._run_from(root)
        self.assertIn(builder.FAILURE_EXPANDED_SOURCE_INPUT_UNREADABLE, result.stderr)
        self.assertIn("MODEL_ATLAS.md", result.stderr)

    def test_directory_in_place_of_a_source_file_fails_closed(self):
        root = self._generator_root("dir-not-file")
        (root / "model-atlas").mkdir(parents=True, exist_ok=True)
        (root / "model-atlas" / "MODEL_ATLAS.md").mkdir()
        result, out = self._run_from(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(builder.FAILURE_EXPANDED_SOURCE_INPUT_UNREADABLE, result.stderr)
        self.assertFalse(out.exists())

    def test_path_escape_is_rejected(self):
        sources = builder.ExpandedSources(REPO_ROOT)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
            sources.read_text("../outside.md", builder.EXPANDED_PURPOSE_SOURCE_NAMED)
        self.assertIn(builder.FAILURE_EXPANDED_SOURCE_INPUT_UNREADABLE, err.getvalue())

    def test_historical_artifact_untouched_by_every_failure(self):
        before = (HISTORICAL_DATA_PATH.read_bytes(), HISTORICAL_DATA_PATH.stat().st_mtime_ns)
        self.test_missing_source_document_fails_closed()
        self.test_invalid_utf8_source_fails_closed()
        after = (HISTORICAL_DATA_PATH.read_bytes(), HISTORICAL_DATA_PATH.stat().st_mtime_ns)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
