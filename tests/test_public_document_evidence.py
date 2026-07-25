#!/usr/bin/env python3
"""Phase 3A P1 tests: public-document registry policy and evidence contract.

Standard-library unittest only (no third-party dependency). These tests cover the
per-field evidence manifest that accompanies the selected public-document
registry:

- exact one-to-one coverage between the registry and the evidence manifest
  (no missing registry path, no evidence entry for a non-registry path, no
  duplicate path, registry order preserved);
- the declared record_count agrees with the number of entries;
- all eleven tracked fields are present on every entry;
- every recorded value belongs to the closed nine-value evidence vocabulary;
- every source-derived claim is supported by the source file on disk, and every
  registry-policy claim corresponds to the absence of that declaration, in both
  directions, for public-surface status and for classification;
- inclusion evidence agrees with the MODEL_ATLAS File inventory;
- the registry envelope and record set are unchanged by this phase;
- the frozen historical dataset remains byte-identical.

The manifest records provenance only. Nothing here confirms or changes
classification, relation status, internal Registry status, ontology membership,
conceptual priority, or authoritative-copy identity.

Byte-level proof that mwe-public-documents.json is unchanged against a specific
base commit is a repository-diff check, not a unit test; these tests pin the
registry's envelope, count and exact path set instead, which is what a phase that
must not touch the registry can assert without pinning bytes a later authorized
phase is expected to change.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

REGISTRY_FILE = ROOT / "mwe-public-documents.json"
EVIDENCE_FILE = ROOT / "mwe-public-document-evidence.json"
EVIDENCE_SCHEMA_FILE = ROOT / "mwe-public-document-evidence.schema.json"
POLICY_FILE = ROOT / "PUBLIC_DOCUMENT_REGISTRY_POLICY.md"
MODEL_ATLAS_FILE = ROOT / "model-atlas" / "MODEL_ATLAS.md"
HISTORICAL_DATA_FILE = ROOT / "visualizations" / "public-surface-authority-map" / "data.json"

# Registry state this phase must not change.
EXPECTED_REGISTRY_RECORD_COUNT = 30
EXPECTED_EVIDENCE_RECORD_COUNT = 30

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
    def test_record_count_is_thirty_and_matches_entries(self):
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
        self.assertEqual(checked, 21)

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
        self.assertEqual(checked, 9)

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
        self.assertEqual(checked, 15)

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
        self.assertEqual(checked, 15)

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
        self.assertEqual(h1_count, 27)
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
        self.assertEqual(inventory_declared, 23)
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


class RegistryUnchangedTests(EvidenceManifestBaseCase):
    def test_registry_count_and_path_set_unchanged(self):
        self.assertEqual(self.registry["record_count"], EXPECTED_REGISTRY_RECORD_COUNT)
        self.assertEqual(len(self.registry_records), EXPECTED_REGISTRY_RECORD_COUNT)
        self.assertEqual(
            set(self.registry_paths), set(validator.EXPECTED_REGISTRY_PATHS)
        )
        self.assertEqual(self.registry_paths, list(validator.EXPECTED_REGISTRY_PATHS))

    def test_registry_envelope_unchanged(self):
        self.assertEqual(self.registry["scope"], "selected_public_documents_only")
        self.assertEqual(self.registry["authority_ceiling"], "metadata_only")
        self.assertEqual(self.registry["completeness"], "not_a_complete_archive_or_registry")
        self.assertEqual(self.registry["schema_version"], "1.0")
        self.assertEqual(
            self.registry["scope_note"],
            "This is a selected public-document registry. It is not the full MWE "
            "archive, not the internal Registry, and not a complete corpus listing.",
        )

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
