#!/usr/bin/env python3
"""Phase 3A P1/P3/S1 tests: public-document registry contract and evidence contract.

Standard-library unittest only (no third-party dependency). These tests cover the
selected public-document registry at its P3 size of 59 records and the per-field
evidence manifest that accompanies it:

- exact one-to-one coverage between the registry and the evidence manifest
  (no missing registry path, no evidence entry for a non-registry path, no
  duplicate path, registry order preserved);
- the declared record_count agrees with the number of entries, on both files;
- all eleven tracked fields are present on every entry;
- every recorded value belongs to the closed nine-value evidence vocabulary;
- every source-derived claim is supported by the source file on disk, and every
  registry-policy claim corresponds to the absence of that declaration, in both
  directions, for public-surface status and for classification;
- inclusion evidence agrees with the MODEL_ATLAS File inventory;
- the exact candidate set: the registry is the union of the pre-expansion
  registry and the MODEL_ATLAS File inventory, and the 29 appended records are
  exactly the pre-expansion difference, in MODEL_ATLAS declaration order;
- the original 30 registry records and the original 30 evidence entries are
  byte-identical to their form at the P3 base commit;
- mechanical field construction and role/status cluster consistency across all 59;
- classification remains fail-closed, 16 explicit_in_file and 43 not_asserted;
- the JSON-LD context and the document schema already cover every term used;
- the frozen historical dataset remains byte-identical;
- the S1 source-header normalization: the 28 P3 concept additions now carry the
  exact four-line public-surface block, AUTHOR.md does not, and the resulting
  evidence distribution is 49 source_declared and 10 registry_policy for both
  public_surface_status and authority_ceiling.

The manifest records provenance only. Nothing here confirms or changes
classification, relation status, internal Registry status, ontology membership,
conceptual priority, or authoritative-copy identity.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

REGISTRY_FILE = ROOT / "mwe-public-documents.json"
EVIDENCE_FILE = ROOT / "mwe-public-document-evidence.json"
EVIDENCE_SCHEMA_FILE = ROOT / "mwe-public-document-evidence.schema.json"
POLICY_FILE = ROOT / "PUBLIC_DOCUMENT_REGISTRY_POLICY.md"
MODEL_ATLAS_FILE = ROOT / "model-atlas" / "MODEL_ATLAS.md"
HISTORICAL_DATA_FILE = ROOT / "visualizations" / "public-surface-authority-map" / "data.json"

# Registry state after the P3 expansion.
EXPECTED_REGISTRY_RECORD_COUNT = 59
EXPECTED_EVIDENCE_RECORD_COUNT = 59

# The pre-expansion registry: the first 30 records and the first 30 evidence
# entries must survive P3 unchanged, in their original order and positions.
ORIGINAL_RECORD_COUNT = 30
ADDITION_COUNT = 29

# The commit P3 was based on (the merge commit of the P2 pull request). The
# original-30 proof reads the two files at this commit through Git rather than
# comparing the working tree with itself.
P3_BASE_COMMIT = "7a5e5fe59203cc7de6e70c3d4080bbf3b92c9008"

# Post-expansion distributions, all recomputed from the sources by the tests
# below rather than assumed. Stated as constants so a silent drift fails loudly.
EXPECTED_EXPLICIT_IN_FILE = 16
EXPECTED_NOT_ASSERTED = 43
EXPECTED_CLASSIFICATION_LINE_SEARCH_LINES = 80

# S1 state. The optional, terminal source-header normalization inserted the exact
# four-line public-surface block into the 28 P3 concept additions. It changed the
# provenance of two evidence fields only; every registry value stayed as it was.
EXPECTED_SOURCE_DECLARED_STATUS = 49
EXPECTED_REGISTRY_POLICY_STATUS = 10

# The exact block, in order. Any drift in punctuation, capitalization, link
# target or wording fails the normalized-source assertion below.
SOURCE_PUBLIC_SURFACE_BLOCK = (
    "- **Public-surface status:** Selected external-facing node.",
    "- **Machine interpretation:** See "
    "[`MACHINE_INTERPRETATION_STATE.md`](./MACHINE_INTERPRETATION_STATE.md).",
    "- **Source use:** See [`SOURCE_USE_GUIDE.md`](./SOURCE_USE_GUIDE.md).",
    "- **Authority boundary:** This file does not by itself establish internal "
    "Registry status, formal relation status, complete ontology, or complete "
    "operational methodology.",
)

# The exact S1 target set: the 28 files normalized by S1, stated literally so the
# target set is proved rather than recomputed from the same data it should match.
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

# The commit S1 was based on: the state after P3/P5/P6, before any header was
# normalized. The S1 proofs read the registry and the evidence manifest at this
# commit through Git rather than comparing the working tree with itself.
S1_BASE_COMMIT = "814997119e543c8d39f312687f2b4b2ffc45da67"

# Three concept files declared the same four-line block before S1 in the attested
# indented `*` header style, each with its own established Authority boundary
# wording. They were already source_declared, they are not S1 targets, and S1
# rewrote no existing header, so they keep their own form.
PRE_S1_VARIANT_STYLE_CONCEPT_FILES = frozenset(
    {
        "delegated-execution-retained-answerability.md",
        "structural-fidelity-use-validity-boundary.md",
        "llm-condition-research-result-boundary.md",
    }
)

# The sole classified addition. Its literal is already present in the registry
# via generation-condition-disclosure-reproducibility-cross.md, so the expansion
# introduces no new classification literal.
SOLE_CLASSIFIED_ADDITION = (
    "external-lifeline-collapse-under-residual-infrastructure-cross.md"
)
SOLE_CLASSIFIED_ADDITION_LITERAL = "Cross / Structural Account / Domain Declaration"

# AUTHOR.md is registered as repository orientation. It is not a concept node and
# must not enter the semantic concept layer merely because it is registered.
ORIENTATION_ADDITION = "AUTHOR.md"

# The two set corrections that must survive into the executed expansion.
REQUIRED_ADDITION = "cultural-curvature-unified-field.md"
NOT_AN_ADDITION = "constraint-residue-governance.md"

# The two attested boundary-reference clusters.
CONCEPT_BOUNDARY_REFERENCES = [
    "SUMMARY_BOUNDARIES.md",
    "MACHINE_INTERPRETATION_STATE.md",
    "SOURCE_USE_GUIDE.md",
    "RELATION_STATUS_GUIDE.md",
]
ORIENTATION_BOUNDARY_REFERENCES = [
    "SUMMARY_BOUNDARIES.md",
    "SUMMARY_CONTRACT.md",
    "MACHINE_INTERPRETATION_STATE.md",
    "SOURCE_USE_GUIDE.md",
    "MACHINE_READING_PRECEDENCE.md",
    "RELATION_STATUS_GUIDE.md",
]

# The attested status clusters: the triple is a strict function of surface_role.
# No crossover exists in the registry, and P3 introduces no new cluster.
STATUS_CLUSTERS = {
    "concept_node": (
        "schema:CreativeWork",
        "selected_external_node",
        "public_file_claim_only",
        "adjacency_only",
    ),
    "repository_orientation": (
        "schema:DigitalDocument",
        "public_navigation_surface",
        "navigation_only",
        "navigation_only",
    ),
    "boundary_document": (
        "schema:DigitalDocument",
        "public_boundary_document",
        "repository_boundary_only",
        "not_applicable",
    ),
    "interpretation_guide": (
        "schema:DigitalDocument",
        "public_boundary_document",
        "repository_boundary_only",
        "not_applicable",
    ),
    "source_use_guide": (
        "schema:DigitalDocument",
        "public_boundary_document",
        "repository_boundary_only",
        "not_applicable",
    ),
    "public_anchor": (
        "schema:DigitalDocument",
        "public_boundary_document",
        "repository_boundary_only",
        "not_applicable",
    ),
}

EXPECTED_SCOPE_NOTE = (
    "This is a selected public-document registry. It is not the full MWE archive, "
    "not the internal Registry, and not a complete corpus listing. Inclusion records "
    "public-document selection only; it does not establish internal Registry status, "
    "formal classification, conceptual priority, confirmed relation status, ontology "
    "membership, or authoritative-copy identity. Some metadata values, including "
    "surface role, public-surface status, authority ceiling, relation default, and "
    "boundary references, are assigned by registry policy rather than copied from the "
    "source document; per-field provenance is recorded in "
    "mwe-public-document-evidence.json. This registry is not a visualization-node "
    "manifest."
)

# The seven registry-only paths (R - A): MODEL_ATLAS is a model atlas and does not
# list boundary, interpretation or anchor surfaces.
REGISTRY_ONLY_PATHS = {
    "SUMMARY_BOUNDARIES.md",
    "SUMMARY_CONTRACT.md",
    "MACHINE_INTERPRETATION_STATE.md",
    "SOURCE_USE_GUIDE.md",
    "MACHINE_READING_PRECEDENCE.md",
    "RELATION_STATUS_GUIDE.md",
    "public-anchors/ai-training-boundary-statement.md",
}

MODEL_ATLAS_FILE_DECLARATION_RE = re.compile(r"^- \*\*File:\*\* `([^`]+)`", re.M)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_module("evidence_validator_under_test", SCRIPTS / "validate_public_metadata.py")

# Reuse the pinned historical-snapshot identity from the phase 3B-1 module rather
# than restating it, so the two suites cannot drift to different pinned values.
snapshot_identity = load_module(
    "phase3a_snapshot_identity",
    Path(__file__).resolve().parent / "test_public_surface_candidate_generator.py",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha1_bytes(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


class EvidenceManifestBaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = read_json(REGISTRY_FILE)
        cls.evidence = read_json(EVIDENCE_FILE)
        cls.evidence_schema = read_json(EVIDENCE_SCHEMA_FILE)
        cls.registry_records = cls.registry["@graph"]
        cls.evidence_records = cls.evidence["records"]
        cls.registry_paths = [record["repository_path"] for record in cls.registry_records]
        cls.evidence_paths = [entry["repository_path"] for entry in cls.evidence_records]

    def source_text(self, repository_path: str) -> str:
        return (ROOT / repository_path).read_text(encoding="utf-8")

    def field_evidence(self, repository_path: str) -> dict:
        for entry in self.evidence_records:
            if entry["repository_path"] == repository_path:
                return entry["field_evidence"]
        raise AssertionError(f"no evidence entry for {repository_path}")


class ManifestStructureTests(EvidenceManifestBaseCase):
    def test_record_count_is_fifty_nine_and_matches_entries(self):
        self.assertEqual(self.evidence["record_count"], EXPECTED_EVIDENCE_RECORD_COUNT)
        self.assertEqual(len(self.evidence_records), EXPECTED_EVIDENCE_RECORD_COUNT)
        self.assertEqual(self.evidence["record_count"], len(self.evidence_records))

    def test_manifest_envelope_constants(self):
        self.assertEqual(self.evidence["$schema"], "./mwe-public-document-evidence.schema.json")
        self.assertEqual(self.evidence["evidence_schema_version"], "1.0")
        self.assertEqual(
            self.evidence["evidence_schema_version"],
            validator.EXPECTED_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(self.evidence["describes"], "./mwe-public-documents.json")
        self.assertEqual(self.evidence["scope"], "field_level_evidence_provenance_only")
        self.assertEqual(self.evidence["authority_ceiling"], "metadata_only")
        self.assertTrue(self.evidence["scope_note"])
        self.assertEqual(set(self.evidence), validator.EVIDENCE_TOP_LEVEL_KEYS)

    def test_registry_and_evidence_path_sets_are_identical(self):
        self.assertEqual(set(self.evidence_paths), set(self.registry_paths))
        self.assertEqual(sorted(set(self.registry_paths) - set(self.evidence_paths)), [])
        self.assertEqual(sorted(set(self.evidence_paths) - set(self.registry_paths)), [])

    def test_evidence_paths_are_unique(self):
        self.assertEqual(len(self.evidence_paths), len(set(self.evidence_paths)))

    def test_evidence_follows_registry_order(self):
        self.assertEqual(self.evidence_paths, self.registry_paths)

    def test_all_eleven_tracked_fields_present_per_entry(self):
        expected = set(validator.EVIDENCE_TRACKED_FIELDS)
        self.assertEqual(len(expected), 11)
        for entry in self.evidence_records:
            with self.subTest(path=entry["repository_path"]):
                self.assertEqual(set(entry), {"repository_path", "field_evidence"})
                self.assertEqual(set(entry["field_evidence"]), expected)

    def test_every_value_is_in_the_closed_vocabulary(self):
        self.assertEqual(len(validator.EVIDENCE_VALUES), 9)
        for entry in self.evidence_records:
            for field, value in entry["field_evidence"].items():
                with self.subTest(path=entry["repository_path"], field=field):
                    self.assertIn(value, validator.EVIDENCE_VALUES)

    def test_manifest_carries_no_classification_or_relation_value(self):
        # The records must carry evidence values only. Classification literals,
        # relation-status literals and the registry's own fail-closed enum must
        # not appear anywhere in the records. The envelope's scope_note is
        # excluded deliberately: it is a disclaimer naming what the manifest does
        # not establish, not a value.
        records_text = json.dumps(self.evidence_records, ensure_ascii=False)
        for prohibited in (
            "publicly_declared_classification",
            "classification_evidence",
            "explicit_in_file",
            "adjacency_only",
            "navigation_only",
            "not_applicable",
            "confirmed",
        ):
            self.assertNotIn(prohibited, records_text)

        # Every recorded value names a derivation kind, never a metadata value.
        # `not_asserted` is deliberately shared with the registry's own
        # classification_evidence enum: in both places it records absence.
        for entry in self.evidence_records:
            for field, value in entry["field_evidence"].items():
                with self.subTest(path=entry["repository_path"], field=field):
                    self.assertIn(value, validator.EVIDENCE_VALUES)


class EvidenceSchemaTests(EvidenceManifestBaseCase):
    def test_schema_is_draft_2020_12_and_strict(self):
        self.assertEqual(
            self.evidence_schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertIs(self.evidence_schema["additionalProperties"], False)
        self.assertEqual(self.evidence_schema["type"], "object")

    def test_schema_declares_required_top_level_keys_and_constants(self):
        self.assertEqual(
            set(self.evidence_schema["required"]), validator.EVIDENCE_TOP_LEVEL_KEYS
        )
        properties = self.evidence_schema["properties"]
        self.assertEqual(properties["evidence_schema_version"]["const"], "1.0")
        self.assertEqual(properties["describes"]["const"], "./mwe-public-documents.json")
        self.assertEqual(properties["scope"]["const"], "field_level_evidence_provenance_only")
        self.assertEqual(properties["authority_ceiling"]["const"], "metadata_only")

    def test_schema_record_and_field_definitions_are_closed(self):
        defs = self.evidence_schema["$defs"]
        self.assertEqual(set(defs["evidenceValue"]["enum"]), validator.EVIDENCE_VALUES)
        self.assertIs(defs["evidenceRecord"]["additionalProperties"], False)
        self.assertEqual(
            set(defs["evidenceRecord"]["required"]), {"repository_path", "field_evidence"}
        )
        self.assertIs(defs["fieldEvidence"]["additionalProperties"], False)
        self.assertEqual(
            set(defs["fieldEvidence"]["required"]), set(validator.EVIDENCE_TRACKED_FIELDS)
        )

    def test_document_schema_gains_no_evidence_fields(self):
        document_schema = read_json(ROOT / "mwe-document.schema.json")
        for field in ("field_evidence", "evidence", "inclusion"):
            self.assertNotIn(field, document_schema["properties"])
        self.assertNotIn("field_evidence", set(document_schema["required"]))


class SourceAgreementTests(EvidenceManifestBaseCase):
    def test_public_surface_status_source_declared_is_supported_by_the_file(self):
        checked = 0
        for entry in self.evidence_records:
            path = entry["repository_path"]
            if entry["field_evidence"]["public_surface_status"] != "source_declared":
                continue
            with self.subTest(path=path):
                self.assertRegex(
                    self.source_text(path),
                    validator.PUBLIC_SURFACE_STATUS_DECLARATION_RE,
                )
            checked += 1
        # After S1 this is every concept node: the 21 already normalized before
        # S1 plus the 28 files S1 normalized.
        self.assertEqual(checked, EXPECTED_SOURCE_DECLARED_STATUS)

    def test_public_surface_status_registry_policy_means_absent_in_the_file(self):
        checked = 0
        for entry in self.evidence_records:
            path = entry["repository_path"]
            if entry["field_evidence"]["public_surface_status"] != "registry_policy":
                continue
            with self.subTest(path=path):
                self.assertIsNone(
                    validator.PUBLIC_SURFACE_STATUS_DECLARATION_RE.search(self.source_text(path))
                )
            checked += 1
        # After S1 the remainder is exactly the 10 non-concept records: the 9
        # pre-expansion non-concept records plus AUTHOR.md, which is repository
        # orientation rather than a concept node and was excluded from S1.
        self.assertEqual(checked, EXPECTED_REGISTRY_POLICY_STATUS)

    def test_authority_ceiling_tracks_the_same_source_block(self):
        for entry in self.evidence_records:
            with self.subTest(path=entry["repository_path"]):
                self.assertEqual(
                    entry["field_evidence"]["authority_ceiling"],
                    entry["field_evidence"]["public_surface_status"],
                )

    def test_classification_source_declared_is_supported_by_a_literal_declaration(self):
        checked = 0
        for entry in self.evidence_records:
            path = entry["repository_path"]
            if entry["field_evidence"]["classification"] != "source_declared":
                continue
            with self.subTest(path=path):
                self.assertRegex(
                    self.source_text(path), validator.CLASSIFICATION_DECLARATION_RE
                )
            checked += 1
        self.assertEqual(checked, EXPECTED_EXPLICIT_IN_FILE)

    def test_classification_not_asserted_means_no_literal_declaration(self):
        checked = 0
        for entry in self.evidence_records:
            path = entry["repository_path"]
            if entry["field_evidence"]["classification"] != "not_asserted":
                continue
            with self.subTest(path=path):
                self.assertIsNone(
                    validator.CLASSIFICATION_DECLARATION_RE.search(self.source_text(path))
                )
            checked += 1
        self.assertEqual(checked, EXPECTED_NOT_ASSERTED)

    def test_classification_evidence_agrees_with_the_registry_fail_closed_field(self):
        for record in self.registry_records:
            path = record["repository_path"]
            recorded = self.field_evidence(path)["classification"]
            with self.subTest(path=path):
                if record["classification_evidence"] == "explicit_in_file":
                    self.assertEqual(recorded, "source_declared")
                    self.assertIn("publicly_declared_classification", record)
                else:
                    self.assertEqual(recorded, "not_asserted")
                    self.assertNotIn("publicly_declared_classification", record)

    def test_name_evidence_matches_the_declared_naming_basis(self):
        h1_count = 0
        display_title_count = 0
        for record in self.registry_records:
            path = record["repository_path"]
            text = self.source_text(path)
            recorded = self.field_evidence(path)["name"]
            h1_match = validator.H1_RE.search(text)
            titles = [m.group(1) for m in validator.DISPLAY_TITLE_DECLARATION_RE.finditer(text)]
            with self.subTest(path=path):
                if recorded == "source_h1":
                    self.assertIsNotNone(h1_match)
                    self.assertEqual(record["name"], h1_match.group(1))
                    h1_count += 1
                elif recorded == "source_declared_display_title":
                    # The shortened-title exception must be confirmed from the
                    # file itself, never inferred from MODEL_ATLAS.
                    self.assertIn(record["name"], titles)
                    self.assertNotEqual(record["name"], h1_match.group(1))
                    display_title_count += 1
                else:
                    self.fail(f"{path}: unexpected name evidence {recorded!r}")
        # 27 pre-expansion H1 names plus all 29 additions. The shortened-title
        # exception describes three existing records only; no addition uses it.
        self.assertEqual(h1_count, 56)
        self.assertEqual(display_title_count, 3)

    def test_inclusion_evidence_agrees_with_the_model_atlas_inventory(self):
        atlas = MODEL_ATLAS_FILE.read_text(encoding="utf-8")
        inventory = set(MODEL_ATLAS_FILE_DECLARATION_RE.findall(atlas))
        inventory_declared = 0
        registry_policy = 0
        for entry in self.evidence_records:
            path = entry["repository_path"]
            recorded = entry["field_evidence"]["inclusion"]
            with self.subTest(path=path):
                if recorded == "inventory_declared":
                    self.assertIn(path, inventory)
                    inventory_declared += 1
                elif recorded == "registry_policy":
                    self.assertNotIn(path, inventory)
                    self.assertIn(path, REGISTRY_ONLY_PATHS)
                    registry_policy += 1
                else:
                    self.fail(f"{path}: unexpected inclusion evidence {recorded!r}")
        # 23 pre-expansion intersection records plus the 29 additions, all of
        # which are MODEL_ATLAS-declared by construction (they are A - R).
        self.assertEqual(inventory_declared, 52)
        self.assertEqual(registry_policy, 7)
        self.assertEqual(set(self.registry_paths) - inventory, REGISTRY_ONLY_PATHS)

    def test_mechanical_and_constant_fields_are_actually_derived(self):
        for record in self.registry_records:
            path = record["repository_path"]
            evidence = self.field_evidence(path)
            with self.subTest(path=path):
                self.assertEqual(evidence["repository_path"], "mechanical")
                self.assertEqual(evidence["canonical_public_url"], "mechanical")
                self.assertEqual(evidence["source_use_reference"], "schema_const")
                expected_url = validator.CANONICAL_URL_PREFIX + path
                self.assertEqual(record["canonical_public_url"], expected_url)
                self.assertEqual(record["@id"], expected_url + "#public-document-metadata")
                self.assertEqual(record["source_use_reference"], "SOURCE_USE_GUIDE.md")

    def test_policy_assigned_fields_are_recorded_as_registry_policy(self):
        for entry in self.evidence_records:
            with self.subTest(path=entry["repository_path"]):
                self.assertEqual(entry["field_evidence"]["surface_role"], "registry_policy")
                self.assertEqual(entry["field_evidence"]["relation_default"], "registry_policy")
                self.assertEqual(
                    entry["field_evidence"]["boundary_references"], "registry_policy"
                )

    def test_declaration_pattern_does_not_match_running_prose(self):
        # A declaration is a header line, not a mention. Two registered boundary
        # surfaces contain the phrase "Authority boundary:" in running text while
        # carrying no public-surface block; the pattern used for evidence must not
        # treat a prose mention as a declaration.
        pattern = validator.source_declaration_pattern("Classification")
        self.assertIsNone(pattern.search("Text that discusses Classification: loosely.\n"))
        self.assertIsNotNone(pattern.search("- **Classification:** Model / Domain Declaration\n"))
        self.assertIsNotNone(pattern.search("  * Classification: Cross-Supporting Boundary Note\n"))
        self.assertIsNotNone(pattern.search("Classification: Training-facing Public Surface Anchor\n"))


class S1SourceNormalizationTests(EvidenceManifestBaseCase):
    """The optional, terminal S1 source-header normalization.

    S1 inserted the exact four-line public-surface block into the 28 P3 concept
    additions and flipped two evidence fields from registry_policy to
    source_declared. It changed no registry value, no classification, no
    relation status and no ordering.
    """

    def concept_paths(self):
        return [
            record["repository_path"]
            for record in self.registry_records
            if record["surface_role"] == "concept_node"
        ]

    def non_concept_paths(self):
        return [
            record["repository_path"]
            for record in self.registry_records
            if record["surface_role"] != "concept_node"
        ]

    def test_the_s1_target_set_is_exactly_the_p3_concept_additions(self):
        additions = set(self.registry_paths[ORIGINAL_RECORD_COUNT:])
        self.assertEqual(len(additions), ADDITION_COUNT)
        self.assertEqual(S1_NORMALIZED_TARGETS, additions - {ORIENTATION_ADDITION})
        self.assertEqual(len(S1_NORMALIZED_TARGETS), ADDITION_COUNT - 1)
        self.assertEqual(len(S1_NORMALIZED_TARGETS), 28)

    def test_author_md_is_registered_but_excluded_from_s1(self):
        self.assertIn(ORIENTATION_ADDITION, self.registry_paths)
        self.assertNotIn(ORIENTATION_ADDITION, S1_NORMALIZED_TARGETS)
        self.assertNotIn(ORIENTATION_ADDITION, self.concept_paths())
        # It is repository orientation, so its source carries no block and its
        # evidence stays registry_policy.
        self.assertIsNone(
            validator.PUBLIC_SURFACE_STATUS_DECLARATION_RE.search(
                self.source_text(ORIENTATION_ADDITION)
            )
        )
        evidence = self.field_evidence(ORIENTATION_ADDITION)
        self.assertEqual(evidence["public_surface_status"], "registry_policy")
        self.assertEqual(evidence["authority_ceiling"], "registry_policy")

    def test_every_s1_target_carries_the_exact_block_exactly_once(self):
        block = "\n".join(SOURCE_PUBLIC_SURFACE_BLOCK)
        for path in sorted(S1_NORMALIZED_TARGETS):
            with self.subTest(path=path):
                self.assertEqual(self.source_text(path).count(block), 1)

    def test_every_concept_node_declares_the_full_four_line_block(self):
        # All 49 concept nodes declare the block. The 46 files in the bold list
        # style carry it byte-for-byte; the three pre-S1 files in the attested
        # indented style carry the same four declarations contiguously, in the
        # same order, with their own established wording. S1 normalized its 28
        # targets only and rewrote no pre-existing header.
        block = "\n".join(SOURCE_PUBLIC_SURFACE_BLOCK)
        keys = (
            "Public-surface status",
            "Machine interpretation",
            "Source use",
            "Authority boundary",
        )
        exact = 0
        variant = 0
        concept_paths = self.concept_paths()
        self.assertEqual(len(concept_paths), EXPECTED_SOURCE_DECLARED_STATUS)
        for path in concept_paths:
            text = self.source_text(path)
            with self.subTest(path=path):
                lines = text.split("\n")
                positions = []
                for key in keys:
                    pattern = validator.source_declaration_pattern(key)
                    matched = [i for i, line in enumerate(lines) if pattern.match(line)]
                    self.assertEqual(len(matched), 1, f"{key} must be declared once")
                    positions.append(matched[0])
                # Contiguous and in the canonical order.
                self.assertEqual(
                    positions, list(range(positions[0], positions[0] + len(keys)))
                )
                if text.count(block) == 1:
                    exact += 1
                else:
                    self.assertIn(path, PRE_S1_VARIANT_STYLE_CONCEPT_FILES)
                    variant += 1
        self.assertEqual(variant, len(PRE_S1_VARIANT_STYLE_CONCEPT_FILES))
        self.assertEqual(exact, EXPECTED_SOURCE_DECLARED_STATUS - variant)
        self.assertEqual(exact, 46)

    def test_every_concept_node_is_source_declared_on_both_fields(self):
        for path in self.concept_paths():
            with self.subTest(path=path):
                evidence = self.field_evidence(path)
                self.assertEqual(evidence["public_surface_status"], "source_declared")
                self.assertEqual(evidence["authority_ceiling"], "source_declared")

    def test_the_ten_non_concept_records_remain_registry_policy(self):
        non_concept = self.non_concept_paths()
        self.assertEqual(len(non_concept), EXPECTED_REGISTRY_POLICY_STATUS)
        for path in non_concept:
            with self.subTest(path=path):
                evidence = self.field_evidence(path)
                self.assertEqual(evidence["public_surface_status"], "registry_policy")
                self.assertEqual(evidence["authority_ceiling"], "registry_policy")
                self.assertIsNone(
                    validator.PUBLIC_SURFACE_STATUS_DECLARATION_RE.search(
                        self.source_text(path)
                    )
                )

    def test_the_final_distribution_is_forty_nine_over_ten(self):
        for field in ("public_surface_status", "authority_ceiling"):
            values = [entry["field_evidence"][field] for entry in self.evidence_records]
            with self.subTest(field=field):
                self.assertEqual(
                    values.count("source_declared"), EXPECTED_SOURCE_DECLARED_STATUS
                )
                self.assertEqual(
                    values.count("registry_policy"), EXPECTED_REGISTRY_POLICY_STATUS
                )
                self.assertEqual(len(values), EXPECTED_EVIDENCE_RECORD_COUNT)

    def test_s1_changed_the_registry_not_at_all(self):
        base = read_json_at_commit(S1_BASE_COMMIT, "mwe-public-documents.json")
        self.assertEqual(canonical(self.registry), canonical(base))

    def test_s1_changed_only_two_evidence_fields_on_the_twenty_eight_targets(self):
        base_records = read_json_at_commit(
            S1_BASE_COMMIT, "mwe-public-document-evidence.json"
        )["records"]
        self.assertEqual(len(base_records), len(self.evidence_records))
        changed = set()
        for before, after in zip(base_records, self.evidence_records):
            path = before["repository_path"]
            with self.subTest(path=path):
                # Order is unchanged, record for record.
                self.assertEqual(path, after["repository_path"])
                for field in validator.EVIDENCE_TRACKED_FIELDS:
                    if before["field_evidence"][field] == after["field_evidence"][field]:
                        continue
                    changed.add((path, field))
                    self.assertIn(
                        field, {"public_surface_status", "authority_ceiling"}
                    )
                    self.assertEqual(before["field_evidence"][field], "registry_policy")
                    self.assertEqual(after["field_evidence"][field], "source_declared")
        self.assertEqual(
            changed,
            {
                (path, field)
                for path in S1_NORMALIZED_TARGETS
                for field in ("public_surface_status", "authority_ceiling")
            },
        )

    def test_s1_changed_no_classification_evidence(self):
        base_records = read_json_at_commit(
            S1_BASE_COMMIT, "mwe-public-document-evidence.json"
        )["records"]
        for before, after in zip(base_records, self.evidence_records):
            with self.subTest(path=before["repository_path"]):
                self.assertEqual(
                    before["field_evidence"]["classification"],
                    after["field_evidence"]["classification"],
                )

    def test_s1_left_the_concept_registry_triple_untouched(self):
        for record in self.registry_records:
            if record["surface_role"] != "concept_node":
                continue
            with self.subTest(path=record["repository_path"]):
                self.assertEqual(record["public_surface_status"], "selected_external_node")
                self.assertEqual(record["authority_ceiling"], "public_file_claim_only")
                self.assertEqual(record["relation_default"], "adjacency_only")


class RegistryContractTests(EvidenceManifestBaseCase):
    def test_registry_count_and_path_set(self):
        self.assertEqual(self.registry["record_count"], EXPECTED_REGISTRY_RECORD_COUNT)
        self.assertEqual(len(self.registry_records), EXPECTED_REGISTRY_RECORD_COUNT)
        self.assertEqual(self.registry["record_count"], len(self.registry_records))
        self.assertEqual(
            set(self.registry_paths), set(validator.EXPECTED_REGISTRY_PATHS)
        )
        self.assertEqual(self.registry_paths, list(validator.EXPECTED_REGISTRY_PATHS))

    def test_registry_paths_and_ids_are_distinct(self):
        ids = [record["@id"] for record in self.registry_records]
        self.assertEqual(len(self.registry_paths), len(set(self.registry_paths)))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(set(ids)), EXPECTED_REGISTRY_RECORD_COUNT)

    def test_every_registered_source_file_exists(self):
        for path in self.registry_paths:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), f"{path} is not a regular file")

    def test_registry_envelope_apart_from_count_and_scope_note_is_unchanged(self):
        self.assertEqual(self.registry["scope"], "selected_public_documents_only")
        self.assertEqual(self.registry["authority_ceiling"], "metadata_only")
        self.assertEqual(self.registry["completeness"], "not_a_complete_archive_or_registry")
        self.assertEqual(self.registry["schema_version"], "1.0")
        self.assertEqual(self.registry["@context"], "./mwe-public-context.jsonld")
        self.assertEqual(self.registry["document_schema"], "./mwe-document.schema.json")
        self.assertEqual(self.registry["@type"], "schema:DataCatalog")
        self.assertEqual(self.registry["omission_meaning"], "Omission does not imply nonexistence.")
        self.assertEqual(self.registry["inclusion_meaning"], "Inclusion does not imply priority.")
        self.assertEqual(self.registry["order_meaning"], "Record order does not imply hierarchy.")
        self.assertEqual(
            self.registry["density_meaning"],
            "Record density does not imply conceptual importance.",
        )

    def test_revised_scope_note_states_every_required_boundary(self):
        note = self.registry["scope_note"]
        self.assertEqual(note, EXPECTED_SCOPE_NOTE)
        # It opens with the previous note verbatim and adds the required
        # boundaries. No ASCII not-equal marker may appear in this prose.
        self.assertTrue(
            note.startswith(
                "This is a selected public-document registry. It is not the full MWE "
                "archive, not the internal Registry, and not a complete corpus listing."
            )
        )
        self.assertNotIn("!=", note)
        for required in (
            "does not establish internal Registry status",
            "formal classification",
            "conceptual priority",
            "confirmed relation status",
            "ontology membership",
            "authoritative-copy identity",
            "assigned by registry policy",
            "mwe-public-document-evidence.json",
            "not a visualization-node manifest",
        ):
            self.assertIn(required, note)

    def test_registry_records_carry_no_evidence_fields(self):
        for record in self.registry_records:
            with self.subTest(path=record["repository_path"]):
                self.assertNotIn("field_evidence", record)
                self.assertNotIn("inclusion", record)

    def test_evidence_files_are_not_registered_as_public_documents(self):
        for path in (
            "mwe-public-document-evidence.json",
            "mwe-public-document-evidence.schema.json",
            "PUBLIC_DOCUMENT_REGISTRY_POLICY.md",
        ):
            self.assertNotIn(path, self.registry_paths)

    def test_historical_dataset_remains_byte_identical(self):
        data = HISTORICAL_DATA_FILE.read_bytes()
        self.assertEqual(len(data), snapshot_identity.EXPECTED_DATA_BYTES)
        self.assertEqual(
            hashlib.sha256(data).hexdigest(), snapshot_identity.EXPECTED_DATA_SHA256
        )
        self.assertEqual(git_blob_sha1_bytes(data), snapshot_identity.EXPECTED_DATA_BLOB)
        parsed = json.loads(data)
        self.assertEqual(len(parsed["nodes"]), snapshot_identity.EXPECTED_NODES)
        self.assertEqual(len(parsed["edges"]), snapshot_identity.EXPECTED_EDGES)


def read_json_at_commit(commit: str, relative_path: str):
    """Read a tracked file as it stood at a commit, through Git.

    This is deliberately not a working-tree read: the original-30 proof must
    compare HEAD against a different source, never against itself.
    """
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative_path}"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise unittest.SkipTest(
            f"{commit}:{relative_path} is not available locally: "
            + result.stderr.decode("utf-8", "replace")
        )
    return json.loads(result.stdout.decode("utf-8"))


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


class CandidateSetTests(EvidenceManifestBaseCase):
    """The registry is exactly R union A, and the additions are exactly A - R.

    R is the pre-expansion registry read at the P3 base commit; A is the set of
    files MODEL_ATLAS declares with a literal `- **File:**` line. This is an
    inventory identity only. It confirms no classification and no relation.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base_registry = read_json_at_commit(P3_BASE_COMMIT, "mwe-public-documents.json")
        cls.base_paths = [record["repository_path"] for record in base_registry["@graph"]]
        atlas = MODEL_ATLAS_FILE.read_text(encoding="utf-8")
        cls.inventory = list(dict.fromkeys(MODEL_ATLAS_FILE_DECLARATION_RE.findall(atlas)))

    def test_pre_expansion_registry_is_the_thirty_record_state(self):
        self.assertEqual(len(self.base_paths), ORIGINAL_RECORD_COUNT)

    def test_set_identity_reproduces(self):
        r = set(self.base_paths)
        a = set(self.inventory)
        self.assertEqual(len(r), 30)
        self.assertEqual(len(a), 52)
        self.assertEqual(len(r & a), 23)
        self.assertEqual(len(r | a), 59)
        self.assertEqual(len(a - r), ADDITION_COUNT)
        self.assertEqual(len(r - a), 7)
        self.assertEqual(r - a, REGISTRY_ONLY_PATHS)

    def test_registry_is_exactly_the_union(self):
        self.assertEqual(set(self.registry_paths), set(self.base_paths) | set(self.inventory))

    def test_appended_paths_are_exactly_the_pre_expansion_difference(self):
        appended = self.registry_paths[ORIGINAL_RECORD_COUNT:]
        expected = [p for p in self.inventory if p not in set(self.base_paths)]
        self.assertEqual(len(appended), ADDITION_COUNT)
        # Order matters: the additions follow MODEL_ATLAS declaration order.
        self.assertEqual(appended, expected)

    def test_both_required_set_corrections_hold(self):
        appended = self.registry_paths[ORIGINAL_RECORD_COUNT:]
        self.assertIn(REQUIRED_ADDITION, appended)
        # Already registry record #23 before the expansion, so it is in R and A
        # and cannot be an addition.
        self.assertIn(NOT_AN_ADDITION, self.base_paths)
        self.assertNotIn(NOT_AN_ADDITION, appended)

    def test_expected_registry_paths_equals_inventory_plus_registry_only(self):
        self.assertEqual(
            set(validator.EXPECTED_REGISTRY_PATHS),
            set(self.inventory) | REGISTRY_ONLY_PATHS,
        )
        self.assertEqual(
            len(validator.EXPECTED_REGISTRY_PATHS), EXPECTED_REGISTRY_RECORD_COUNT
        )
        self.assertEqual(set(validator.REGISTRY_ONLY_PATHS), REGISTRY_ONLY_PATHS)

    def test_validator_reports_no_inventory_drift(self):
        # The inventory-union proof, invoked directly. This is the only place
        # MODEL_ATLAS.md is read for this purpose: the helper is test-facing and
        # validate_public_metadata() does not call it.
        errors: list[str] = []
        validator.validate_expected_paths_match_inventory(errors)
        self.assertEqual(errors, [])

    def test_default_validator_does_not_read_model_atlas(self):
        # Production validation must not acquire a source dependency the P2
        # dependency inventory does not enumerate. MODEL_ATLAS.md is outside the
        # validator's production read set, and this proves it by construction
        # rather than by inspection: any read of that path during an ordinary
        # validation run fails the test.
        original = validator.read_repo_text

        def guarded(relative_path, errors):
            if relative_path == validator.MODEL_ATLAS_FILE:
                raise AssertionError("production validator must not read MODEL_ATLAS.md")
            return original(relative_path, errors)

        with mock.patch.object(validator, "read_repo_text", side_effect=guarded), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(validator.validate_public_metadata(), 0)

    def test_production_validation_still_enforces_the_explicit_path_contract(self):
        # Removing the MODEL_ATLAS call must not weaken the production contract:
        # the explicit list is still compared by set equality in both directions.
        registry = copy.deepcopy(self.registry)
        document_schema = read_json(ROOT / "mwe-document.schema.json")

        missing = copy.deepcopy(registry)
        dropped = missing["@graph"].pop()
        missing["record_count"] = len(missing["@graph"])
        errors: list[str] = []
        validator.validate_document_registry(missing, document_schema, errors)
        self.assertTrue(
            any("missing expected paths" in error for error in errors),
            f"dropping {dropped['repository_path']} was not caught: {errors}",
        )

        added = copy.deepcopy(registry)
        extra = copy.deepcopy(added["@graph"][-1])
        extra["repository_path"] = "AGENTS.md"
        extra["canonical_public_url"] = validator.CANONICAL_URL_PREFIX + "AGENTS.md"
        extra["@id"] = extra["canonical_public_url"] + "#public-document-metadata"
        added["@graph"].append(extra)
        added["record_count"] = len(added["@graph"])
        errors = []
        validator.validate_document_registry(added, document_schema, errors)
        self.assertTrue(
            any("unexpected registry paths" in error for error in errors),
            f"an unapproved path was not caught: {errors}",
        )


class OriginalThirtyUnchangedTests(EvidenceManifestBaseCase):
    """The pre-expansion records and evidence entries survive P3 untouched."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_registry = read_json_at_commit(P3_BASE_COMMIT, "mwe-public-documents.json")
        cls.base_evidence = read_json_at_commit(
            P3_BASE_COMMIT, "mwe-public-document-evidence.json"
        )

    def test_base_commit_really_is_the_pre_expansion_state(self):
        # Without this the comparisons below could pass by comparing HEAD with
        # itself if the base reference ever pointed at an expanded commit.
        self.assertEqual(self.base_registry["record_count"], ORIGINAL_RECORD_COUNT)
        self.assertEqual(len(self.base_registry["@graph"]), ORIGINAL_RECORD_COUNT)
        self.assertEqual(self.base_evidence["record_count"], ORIGINAL_RECORD_COUNT)
        self.assertEqual(len(self.base_evidence["records"]), ORIGINAL_RECORD_COUNT)
        self.assertNotEqual(len(self.registry_records), ORIGINAL_RECORD_COUNT)

    def test_first_thirty_registry_records_are_byte_identical(self):
        self.assertEqual(
            canonical(self.registry_records[:ORIGINAL_RECORD_COUNT]),
            canonical(self.base_registry["@graph"]),
        )

    def test_first_thirty_evidence_entries_are_byte_identical(self):
        self.assertEqual(
            canonical(self.evidence_records[:ORIGINAL_RECORD_COUNT]),
            canonical(self.base_evidence["records"]),
        )

    def test_original_records_keep_their_positions(self):
        base_paths = [r["repository_path"] for r in self.base_registry["@graph"]]
        self.assertEqual(self.registry_paths[:ORIGINAL_RECORD_COUNT], base_paths)
        for index, path in enumerate(base_paths):
            with self.subTest(position=index + 1, path=path):
                self.assertEqual(self.registry_records[index]["repository_path"], path)

    def test_additions_occupy_positions_thirty_one_to_fifty_nine(self):
        self.assertEqual(
            len(self.registry_records) - ORIGINAL_RECORD_COUNT, ADDITION_COUNT
        )
        self.assertEqual(
            self.evidence_paths[ORIGINAL_RECORD_COUNT:],
            self.registry_paths[ORIGINAL_RECORD_COUNT:],
        )


class AdditionConstructionTests(EvidenceManifestBaseCase):
    """Field construction across all 59, and the approved shape of the 29."""

    def additions(self):
        return self.registry_records[ORIGINAL_RECORD_COUNT:]

    def test_ids_and_urls_are_mechanically_derived(self):
        for record in self.registry_records:
            path = record["repository_path"]
            with self.subTest(path=path):
                url = validator.CANONICAL_URL_PREFIX + path
                self.assertEqual(record["canonical_public_url"], url)
                self.assertEqual(record["@id"], url + "#public-document-metadata")
                self.assertEqual(record["source_use_reference"], "SOURCE_USE_GUIDE.md")

    def test_role_status_clusters_are_internally_valid(self):
        for record in self.registry_records:
            role = record["surface_role"]
            with self.subTest(path=record["repository_path"], role=role):
                self.assertIn(role, STATUS_CLUSTERS)
                self.assertEqual(
                    (
                        record["@type"],
                        record["public_surface_status"],
                        record["authority_ceiling"],
                        record["relation_default"],
                    ),
                    STATUS_CLUSTERS[role],
                )

    def test_boundary_reference_clusters_match_policy(self):
        for record in self.registry_records:
            expected = (
                CONCEPT_BOUNDARY_REFERENCES
                if record["surface_role"] == "concept_node"
                else ORIENTATION_BOUNDARY_REFERENCES
            )
            with self.subTest(path=record["repository_path"]):
                self.assertEqual(record["boundary_references"], expected)

    def test_no_new_surface_role_or_classification_literal_is_introduced(self):
        base = read_json_at_commit(P3_BASE_COMMIT, "mwe-public-documents.json")["@graph"]
        base_roles = {record["surface_role"] for record in base}
        base_literals = {
            record["publicly_declared_classification"]
            for record in base
            if "publicly_declared_classification" in record
        }
        roles = {record["surface_role"] for record in self.registry_records}
        literals = {
            record["publicly_declared_classification"]
            for record in self.registry_records
            if "publicly_declared_classification" in record
        }
        self.assertEqual(roles, base_roles)
        self.assertEqual(literals, base_literals)
        self.assertEqual(len(literals), 12)

    def test_author_md_uses_the_approved_orientation_treatment(self):
        record = next(
            r for r in self.additions() if r["repository_path"] == ORIENTATION_ADDITION
        )
        self.assertEqual(self.registry_paths[ORIGINAL_RECORD_COUNT], ORIENTATION_ADDITION)
        self.assertEqual(record["@type"], "schema:DigitalDocument")
        self.assertEqual(record["name"], "Author")
        self.assertEqual(record["surface_role"], "repository_orientation")
        self.assertEqual(record["public_surface_status"], "public_navigation_surface")
        self.assertEqual(record["authority_ceiling"], "navigation_only")
        self.assertEqual(record["relation_default"], "navigation_only")
        self.assertEqual(record["classification_evidence"], "not_asserted")
        self.assertEqual(record["boundary_references"], ORIENTATION_BOUNDARY_REFERENCES)
        self.assertNotIn("publicly_declared_classification", record)
        # It is registered, but it is not a concept node.
        self.assertNotEqual(record["surface_role"], "concept_node")

    def test_the_other_twenty_eight_additions_use_the_concept_treatment(self):
        concepts = [
            r for r in self.additions() if r["repository_path"] != ORIENTATION_ADDITION
        ]
        self.assertEqual(len(concepts), 28)
        for record in concepts:
            with self.subTest(path=record["repository_path"]):
                self.assertEqual(record["surface_role"], "concept_node")
                self.assertEqual(record["@type"], "schema:CreativeWork")
                self.assertEqual(record["public_surface_status"], "selected_external_node")
                self.assertEqual(record["authority_ceiling"], "public_file_claim_only")
                self.assertEqual(record["relation_default"], "adjacency_only")
                self.assertEqual(record["boundary_references"], CONCEPT_BOUNDARY_REFERENCES)

    def test_additions_carry_no_optional_metadata(self):
        # P3 adds no DOI, version, license, date, OSF URL, abstract, source
        # commit or notes. Historical incompleteness is not repaired here.
        prohibited = {
            "doi",
            "version",
            "license",
            "date",
            "datePublished",
            "publication_date",
            "osf_url",
            "abstract",
            "source_commit",
            "notes",
        }
        for record in self.additions():
            with self.subTest(path=record["repository_path"]):
                self.assertEqual(set(record) & prohibited, set())

    def test_additions_use_only_the_attested_field_set(self):
        allowed = {
            "@id",
            "@type",
            "name",
            "repository_path",
            "surface_role",
            "public_surface_status",
            "authority_ceiling",
            "relation_default",
            "classification_evidence",
            "publicly_declared_classification",
            "boundary_references",
            "source_use_reference",
            "canonical_public_url",
        }
        for record in self.additions():
            with self.subTest(path=record["repository_path"]):
                self.assertTrue(set(record) <= allowed, f"unexpected fields {set(record) - allowed}")

    def test_addition_names_are_the_verbatim_source_h1(self):
        for record in self.additions():
            path = record["repository_path"]
            with self.subTest(path=path):
                h1 = validator.H1_RE.search(self.source_text(path))
                self.assertIsNotNone(h1)
                self.assertEqual(record["name"], h1.group(1))
                self.assertEqual(self.field_evidence(path)["name"], "source_h1")


class ClassificationFailClosedTests(EvidenceManifestBaseCase):
    def test_split_is_sixteen_and_forty_three(self):
        explicit = [
            r for r in self.registry_records if r["classification_evidence"] == "explicit_in_file"
        ]
        not_asserted = [
            r for r in self.registry_records if r["classification_evidence"] == "not_asserted"
        ]
        self.assertEqual(len(explicit), EXPECTED_EXPLICIT_IN_FILE)
        self.assertEqual(len(not_asserted), EXPECTED_NOT_ASSERTED)
        self.assertEqual(len(explicit) + len(not_asserted), EXPECTED_REGISTRY_RECORD_COUNT)

    def test_every_explicit_literal_appears_within_the_first_eighty_lines(self):
        for record in self.registry_records:
            if record["classification_evidence"] != "explicit_in_file":
                continue
            path = record["repository_path"]
            with self.subTest(path=path):
                head = "\n".join(
                    self.source_text(path).splitlines()[
                        :EXPECTED_CLASSIFICATION_LINE_SEARCH_LINES
                    ]
                )
                self.assertIn(record["publicly_declared_classification"], head)

    def test_not_asserted_records_declare_no_classification(self):
        for record in self.registry_records:
            if record["classification_evidence"] != "not_asserted":
                continue
            path = record["repository_path"]
            with self.subTest(path=path):
                self.assertNotIn("publicly_declared_classification", record)
                self.assertIsNone(
                    validator.CLASSIFICATION_DECLARATION_RE.search(self.source_text(path))
                )

    def test_only_one_addition_is_classified(self):
        classified = [
            r["repository_path"]
            for r in self.registry_records[ORIGINAL_RECORD_COUNT:]
            if r["classification_evidence"] == "explicit_in_file"
        ]
        self.assertEqual(classified, [SOLE_CLASSIFIED_ADDITION])

    def test_the_classified_addition_matches_its_source_byte_for_byte(self):
        record = next(
            r
            for r in self.registry_records
            if r["repository_path"] == SOLE_CLASSIFIED_ADDITION
        )
        self.assertEqual(
            record["publicly_declared_classification"], SOLE_CLASSIFIED_ADDITION_LITERAL
        )
        lines = self.source_text(SOLE_CLASSIFIED_ADDITION).splitlines()
        self.assertEqual(
            lines[7], f"- **Classification:** {SOLE_CLASSIFIED_ADDITION_LITERAL}"
        )
        self.assertEqual(
            self.field_evidence(SOLE_CLASSIFIED_ADDITION)["classification"],
            "source_declared",
        )


class ContextAndSchemaCoverageTests(EvidenceManifestBaseCase):
    """The existing context and schema already cover the 59 records.

    P3 changes neither. If a new term were required the phase would stop rather
    than widen either file.
    """

    def test_jsonld_context_defines_every_term_used(self):
        context = read_json(ROOT / "mwe-public-context.jsonld")["@context"]
        used = set()
        for record in self.registry_records:
            used |= set(record)
        undefined = sorted(t for t in used if not t.startswith("@") and t not in context)
        self.assertEqual(undefined, [])

    def test_document_schema_allows_every_field_used(self):
        document_schema = read_json(ROOT / "mwe-document.schema.json")
        properties = set(document_schema["properties"])
        self.assertIs(document_schema.get("additionalProperties"), False)
        for record in self.registry_records:
            with self.subTest(path=record["repository_path"]):
                self.assertTrue(set(record) <= properties)
                self.assertTrue(set(document_schema["required"]) <= set(record))

    def test_document_schema_enums_cover_the_expanded_values(self):
        properties = read_json(ROOT / "mwe-document.schema.json")["properties"]
        for field in (
            "surface_role",
            "public_surface_status",
            "authority_ceiling",
            "relation_default",
            "classification_evidence",
        ):
            allowed = set(properties[field]["enum"])
            used = {record[field] for record in self.registry_records}
            with self.subTest(field=field):
                self.assertTrue(used <= allowed, f"{field}: {sorted(used - allowed)}")


class PolicyDocumentTests(EvidenceManifestBaseCase):
    def test_policy_document_exists_and_documents_the_contract(self):
        text = POLICY_FILE.read_text(encoding="utf-8")
        for value in sorted(validator.EVIDENCE_VALUES):
            self.assertIn(value, text, f"policy does not document evidence value {value}")
        for field in validator.EVIDENCE_TRACKED_FIELDS:
            self.assertIn(field, text, f"policy does not document tracked field {field}")

    def test_policy_document_uses_the_proper_not_equal_symbol(self):
        # Prose must not carry the ASCII not-equal marker.
        self.assertNotIn("!=", POLICY_FILE.read_text(encoding="utf-8"))


class ValidatorRejectionTests(EvidenceManifestBaseCase):
    """The evidence contract must fail closed. Each mutation below must be
    rejected, so a later phase cannot quietly downgrade or misstate provenance."""

    def _errors_for(self, mutate) -> list[str]:
        evidence = copy.deepcopy(self.evidence)
        registry = copy.deepcopy(self.registry)
        mutate(evidence, registry)
        errors: list[str] = []
        validator.validate_evidence_manifest(
            evidence, copy.deepcopy(self.evidence_schema), registry, errors
        )
        return errors

    def _assert_rejected(self, mutate, fragment: str):
        errors = self._errors_for(mutate)
        self.assertTrue(
            any(fragment in error for error in errors),
            f"expected an error containing {fragment!r}, got {errors}",
        )

    def test_unmutated_manifest_passes(self):
        self.assertEqual(self._errors_for(lambda e, r: None), [])

    def test_rejects_count_mismatch(self):
        def mutate(evidence, registry):
            evidence["record_count"] += 1

        self._assert_rejected(mutate, "record_count")

    def test_rejects_missing_registry_path(self):
        def mutate(evidence, registry):
            evidence["records"] = evidence["records"][1:]
            evidence["record_count"] = len(evidence["records"])

        self._assert_rejected(mutate, "missing evidence for registry paths")

    def test_rejects_non_registry_path(self):
        def mutate(evidence, registry):
            extra = copy.deepcopy(evidence["records"][0])
            extra["repository_path"] = "AGENTS.md"
            evidence["records"].append(extra)
            evidence["record_count"] = len(evidence["records"])

        self._assert_rejected(mutate, "evidence for non-registry paths")

    def test_rejects_duplicate_path(self):
        def mutate(evidence, registry):
            evidence["records"].append(copy.deepcopy(evidence["records"][0]))
            evidence["record_count"] = len(evidence["records"])

        self._assert_rejected(mutate, "duplicate repository_path")

    def test_rejects_value_outside_the_vocabulary(self):
        def mutate(evidence, registry):
            evidence["records"][0]["field_evidence"]["surface_role"] = "source_of_truth"

        self._assert_rejected(mutate, "outside the closed vocabulary")

    def test_rejects_missing_tracked_field(self):
        def mutate(evidence, registry):
            del evidence["records"][0]["field_evidence"]["relation_default"]

        self._assert_rejected(mutate, "missing tracked fields")

    def test_rejects_untracked_field(self):
        def mutate(evidence, registry):
            evidence["records"][0]["field_evidence"]["doi"] = "mechanical"

        self._assert_rejected(mutate, "untracked fields")

    def test_rejects_unsupported_source_declared_public_surface_status(self):
        # README.md declares no public-surface block.
        def mutate(evidence, registry):
            for entry in evidence["records"]:
                if entry["repository_path"] == "README.md":
                    entry["field_evidence"]["public_surface_status"] = "source_declared"
                    entry["field_evidence"]["authority_ceiling"] = "source_declared"

        self._assert_rejected(mutate, "declares no 'Public-surface status:' line")

    def test_rejects_registry_policy_where_the_file_does_declare_the_block(self):
        def mutate(evidence, registry):
            for entry in evidence["records"]:
                if entry["repository_path"] == "ai-induced-semantic-deviation.md":
                    entry["field_evidence"]["public_surface_status"] = "registry_policy"
                    entry["field_evidence"]["authority_ceiling"] = "registry_policy"

        self._assert_rejected(mutate, "declares a 'Public-surface status:' line")

    def test_rejects_mismatched_authority_ceiling_evidence(self):
        def mutate(evidence, registry):
            evidence["records"][0]["field_evidence"]["authority_ceiling"] = "source_declared"

        self._assert_rejected(mutate, "does not match")

    def test_rejects_unsupported_source_declared_classification(self):
        # README.md declares no literal Classification: line.
        def mutate(evidence, registry):
            for entry in evidence["records"]:
                if entry["repository_path"] == "README.md":
                    entry["field_evidence"]["classification"] = "source_declared"

        self._assert_rejected(mutate, "declares no literal 'Classification:' line")

    def test_rejects_not_asserted_where_the_file_declares_a_classification(self):
        def mutate(evidence, registry):
            for entry in evidence["records"]:
                if entry["repository_path"] == "surface-bounded-semantic-rendering.md":
                    entry["field_evidence"]["classification"] = "not_asserted"

        self._assert_rejected(mutate, "literal 'Classification:' line")

    def test_rejects_name_evidence_that_the_source_does_not_support(self):
        def mutate(evidence, registry):
            for entry in evidence["records"]:
                if entry["repository_path"] == "llm-condition-research-result-boundary.md":
                    entry["field_evidence"]["name"] = "source_h1"

        self._assert_rejected(mutate, "does not match the source H1")

    def test_rejects_display_title_claim_without_a_declared_title(self):
        def mutate(evidence, registry):
            for entry in evidence["records"]:
                if entry["repository_path"] == "README.md":
                    entry["field_evidence"]["name"] = "source_declared_display_title"

        self._assert_rejected(mutate, "matches no declared display title")

    def test_rejects_wrong_evidence_schema_version(self):
        def mutate(evidence, registry):
            evidence["evidence_schema_version"] = "1.1"

        self._assert_rejected(mutate, "evidence_schema_version must be")

    def test_rejects_wrong_describes_target(self):
        def mutate(evidence, registry):
            evidence["describes"] = "./mwe-public-surface.json"

        self._assert_rejected(mutate, "describes must be")

    def test_rejects_wrong_authority_ceiling(self):
        def mutate(evidence, registry):
            evidence["authority_ceiling"] = "public_file_claim_only"

        self._assert_rejected(mutate, "authority_ceiling must be")

    def test_rejects_wrong_scope(self):
        def mutate(evidence, registry):
            evidence["scope"] = "selected_public_documents_only"

        self._assert_rejected(mutate, "scope must be")

    def test_rejects_unknown_top_level_field(self):
        def mutate(evidence, registry):
            evidence["confirmed_relations"] = []

        self._assert_rejected(mutate, "unknown top-level fields")

    def test_rejects_missing_top_level_field(self):
        def mutate(evidence, registry):
            del evidence["scope_note"]

        self._assert_rejected(mutate, "missing top-level fields")

    def test_rejects_order_divergence_from_the_registry(self):
        def mutate(evidence, registry):
            evidence["records"].reverse()

        self._assert_rejected(mutate, "must follow registry order")

    def test_rejects_evidence_disagreeing_with_registry_classification_field(self):
        def mutate(evidence, registry):
            # Drop the registry's declared classification without updating the
            # manifest: the two must not be allowed to disagree.
            for record in registry["@graph"]:
                if record["repository_path"] == "surface-bounded-semantic-rendering.md":
                    record["classification_evidence"] = "not_asserted"
                    record.pop("publicly_declared_classification", None)

        self._assert_rejected(mutate, "disagrees with")


class EvidenceSchemaContractDriftTests(EvidenceManifestBaseCase):
    """The schema file and the validator constants must not drift apart."""

    def _errors_for(self, mutate) -> list[str]:
        schema = copy.deepcopy(self.evidence_schema)
        mutate(schema)
        errors: list[str] = []
        validator.validate_evidence_schema_file(schema, errors)
        return errors

    def test_unmutated_schema_passes(self):
        self.assertEqual(self._errors_for(lambda s: None), [])

    def test_rejects_widened_vocabulary(self):
        def mutate(schema):
            schema["$defs"]["evidenceValue"]["enum"].append("assumed")

        self.assertTrue(
            any("closed vocabulary" in error for error in self._errors_for(mutate))
        )

    def test_rejects_open_field_evidence_object(self):
        def mutate(schema):
            schema["$defs"]["fieldEvidence"]["additionalProperties"] = True

        self.assertTrue(
            any("additionalProperties false" in error for error in self._errors_for(mutate))
        )

    def test_rejects_classification_value_field_in_the_manifest_schema(self):
        def mutate(schema):
            schema["$defs"]["fieldEvidence"]["properties"][
                "publicly_declared_classification"
            ] = {"type": "string"}

        self.assertTrue(
            any("must not declare" in error for error in self._errors_for(mutate))
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
