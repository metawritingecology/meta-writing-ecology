#!/usr/bin/env python3
"""Validate public metadata structure for the MWE public repository.

This validator checks JSON shape, references, enum use, selected registry
coverage, per-field evidence provenance, and public correction-register
constraints. It is not conceptual, empirical, Registry, relation, ontology, or
corpus-completeness authority.

The evidence checks confirm that mwe-public-document-evidence.json covers the
public-document registry one-to-one and that every recorded evidence value is
drawn from the closed vocabulary in PUBLIC_DOCUMENT_REGISTRY_POLICY.md. They
confirm source-derived claims where they can be mechanically verified. For
declaration-sensitive fields, including public_surface_status,
authority_ceiling, and classification, they also confirm that registry_policy or
not_asserted corresponds to the absence of the relevant source declaration. The
manifest records provenance only; it establishes no classification and no
relation.

Three invocation modes:

1. Default (backward-compatible) mode
       python scripts/validate_public_metadata.py
   Validates the public metadata in the generator/repository root. Behavior is
   unchanged from prior releases.

2. Isolated preflight mode
       python <generator-root>/scripts/validate_public_metadata.py \
         --source-root <detached-source-checkout> --mode preflight
   Runs the existing public-metadata and source-boundary validation directly
   against an explicit source root. No inventory is required (generation has
   not occurred). Performs no writes and generates/repairs nothing.

3. Isolated inventory-verification mode
       python <generator-root>/scripts/validate_public_metadata.py \
         --source-root <detached-source-checkout> --mode verify-inventory \
         --inventory <isolated-inventory-file>
   Performs all applicable existing metadata validation against the source
   root, then validates the supplied dependency-inventory schema, recomputes
   every listed source-file identity against the source root, and confirms the
   inventory paths and read purposes agree with the source root. Rejects
   missing, extra, duplicated, escaped, or identity-mismatched entries.
   Performs no writes.

Source-tree Python files are treated only as data. This validator never
imports or executes any module discovered under the source root; the only
generator-local module it loads is the companion builder from the generator
root, used to enumerate the expected dependency set.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROOT_RESOLVED = ROOT.resolve()

GENERATOR_ROOT_RESOLVED = ROOT_RESOLVED

# Root that source-relative paths resolve against. Default mode uses the
# generator/repository root; isolated modes point it at the explicit
# --source-root. It is only ever set to an explicitly resolved directory.
_ACTIVE_ROOT: Path = ROOT_RESOLVED

VALID_MODES = ("preflight", "verify-inventory")

INVENTORY_SCHEMA_FILE = "mwe-public-surface-dependency-inventory.schema.json"
EXPECTED_INVENTORY_SCHEMA_VERSION = "1.0"
EXPECTED_SOURCE_REPOSITORY = "metawritingecology/meta-writing-ecology"
INVENTORY_TOP_LEVEL_KEYS = {
    "inventory_schema_version",
    "source_repository",
    "interface_version",
    "dependency_count",
    "aggregate_sha256",
    "files",
}
INVENTORY_ITEM_KEYS = {
    "path",
    "byte_length",
    "sha256",
    "git_blob_sha1",
    "read_purposes",
}
INVENTORY_READ_PURPOSES = {
    "direct_input",
    "scope_context",
    "registry_referenced_document",
    "classification_evidence",
    "reference_existence_check",
    "schema",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_BLOB_RE = re.compile(r"^[0-9a-f]{40}$")


def source_declaration_pattern(key: str) -> "re.Pattern[str]":
    """Match a literal `Key:` header declaration in any attested header style.

    Three styles carry the same declaration in this repository: a bare
    `Key: value` line, a bold list item `- **Key:** value`, and an indented list
    item `* Key: value`. All three are literal declarations. Running prose that
    merely mentions the phrase is not a declaration and must not match.
    """
    return re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?" + re.escape(key) + r":(?:\*\*)?\s", re.M)


CLASSIFICATION_DECLARATION_RE = source_declaration_pattern("Classification")
PUBLIC_SURFACE_STATUS_DECLARATION_RE = source_declaration_pattern("Public-surface status")
DISPLAY_TITLE_DECLARATION_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?OSF (?:Project|Registration):(?:\*\*)?\s+(.+?)\s*$", re.M
)
H1_RE = re.compile(r"^# (.+?)\s*$", re.M)

JSON_FILES = [
    "mwe-public-surface.json",
    "mwe-public-documents.json",
    "mwe-public-context.jsonld",
    "public-misreading-register.json",
    "mwe-document.schema.json",
    "mwe-public-surface.schema.json",
    "public-misreading-register.schema.json",
    "mwe-public-document-evidence.json",
    "mwe-public-document-evidence.schema.json",
]

SCHEMA_FILES = [
    "mwe-document.schema.json",
    "mwe-public-surface.schema.json",
    "public-misreading-register.schema.json",
    "mwe-public-document-evidence.schema.json",
]

CANONICAL_URL_PREFIX = "https://github.com/metawritingecology/meta-writing-ecology/blob/main/"

EVIDENCE_FILE = "mwe-public-document-evidence.json"
EVIDENCE_SCHEMA_FILE = "mwe-public-document-evidence.schema.json"
EXPECTED_EVIDENCE_SCHEMA_VERSION = "1.0"
EXPECTED_EVIDENCE_DESCRIBES = "./mwe-public-documents.json"
EXPECTED_EVIDENCE_SCOPE = "field_level_evidence_provenance_only"
EXPECTED_EVIDENCE_AUTHORITY_CEILING = "metadata_only"

EVIDENCE_TOP_LEVEL_KEYS = {
    "$schema",
    "evidence_schema_version",
    "describes",
    "scope",
    "authority_ceiling",
    "scope_note",
    "record_count",
    "records",
}

# The eleven tracked fields, in manifest order.
EVIDENCE_TRACKED_FIELDS = [
    "inclusion",
    "name",
    "repository_path",
    "canonical_public_url",
    "surface_role",
    "public_surface_status",
    "authority_ceiling",
    "relation_default",
    "classification",
    "boundary_references",
    "source_use_reference",
]

# Closed evidence vocabulary (see PUBLIC_DOCUMENT_REGISTRY_POLICY.md).
EVIDENCE_VALUES = {
    "source_declared",
    "source_h1",
    "source_declared_display_title",
    "inventory_declared",
    "mechanical",
    "registry_policy",
    "schema_const",
    "not_asserted",
    "user_decision",
}

# The exact approved registry membership, in registry order. This stays an
# explicit list rather than a set derived from the registry itself: it is
# compared by set equality in both directions, so it catches an accidental
# deletion and an accidental addition alike. A derived set would silently accept
# whatever the registry happened to contain.
#
# This list is the whole of the production registry-membership contract. That
# the list itself still agrees with the declared inventory is proved separately
# by the test suite, which calls validate_expected_paths_match_inventory
# directly; production validation never reads MODEL_ATLAS.md.
EXPECTED_REGISTRY_PATHS = [
    "README.md",
    "SUMMARY_BOUNDARIES.md",
    "SUMMARY_CONTRACT.md",
    "MACHINE_INTERPRETATION_STATE.md",
    "SOURCE_USE_GUIDE.md",
    "MACHINE_READING_PRECEDENCE.md",
    "AI-READING-GUIDE.md",
    "RELATION_STATUS_GUIDE.md",
    "public-anchors/ai-training-boundary-statement.md",
    "ai-induced-semantic-deviation.md",
    "ai-readable-knowledge-architecture.md",
    "model-induced-coherence-pressure.md",
    "generation-condition-disclosure-reproducibility-cross.md",
    "verification-labor-compression.md",
    "surface-bounded-semantic-rendering.md",
    "text-conditioned-semantic-rendering.md",
    "model-use-reporting-boundary-protocol.md",
    "policy-continuity-evidence-mapping.md",
    "boundary-failure-diagnostics.md",
    "premature-circulation-diagnostics.md",
    "responsibility-alignment-diagnostics.md",
    "semantic-field-diagnostics.md",
    "constraint-residue-governance.md",
    "source-summary-citation-boundary-packet.md",
    "provenance-validity-separation-model.md",
    "origin-control-validity-burden-accelerated-submission-systems.md",
    "evaluation-boundary-failure-permitted-surface-variation.md",
    "delegated-execution-retained-answerability.md",
    "structural-fidelity-use-validity-boundary.md",
    "llm-condition-research-result-boundary.md",
    "AUTHOR.md",
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
]

# The registry-only paths: registered public surfaces that MODEL_ATLAS does not
# declare, because it is a model atlas and does not list boundary, interpretation
# or anchor surfaces. Their absence from the atlas is expected, not a divergence.
# Used only by the test-facing inventory-agreement check below.
REGISTRY_ONLY_PATHS = [
    "SUMMARY_BOUNDARIES.md",
    "SUMMARY_CONTRACT.md",
    "MACHINE_INTERPRETATION_STATE.md",
    "SOURCE_USE_GUIDE.md",
    "MACHINE_READING_PRECEDENCE.md",
    "RELATION_STATUS_GUIDE.md",
    "public-anchors/ai-training-boundary-statement.md",
]

# MODEL_ATLAS is read only by the test-facing consistency check below, never by
# validate_public_metadata(). Keeping it out of the production read set keeps the
# validator's source dependencies exactly those the dependency inventory
# enumerates.
MODEL_ATLAS_FILE = "model-atlas/MODEL_ATLAS.md"
MODEL_ATLAS_FILE_DECLARATION_RE = re.compile(r"^- \*\*File:\*\* `([^`]+)`", re.M)

REQUIRED_DOES_NOT_ESTABLISH = {
    "third_party_intent",
    "platform_wide_behavior",
    "internal_registry_status",
    "legal_liability",
}

LIVE_CASE_STATUSES = {"observed", "corrected", "unresolved"}

PRIVATE_PATH_PATTERNS = [
    re.compile(r"^[A-Za-z]:[\\/].*"),
    re.compile(r"^/Users/"),
    re.compile(r"^/home/"),
    re.compile(r"^/var/"),
    re.compile(r"^/tmp/"),
    re.compile(r"\\\\"),
]

PROHIBITED_RECORD_FIELDS = {
    "internal_registry_status",
    "registry_status",
    "complete_archive_status",
    "formal_relation_status",
    "ontology_status",
    "semantic_supersession",
    "supersedes",
    "derived_from",
    "parent",
    "child",
    "prompt",
    "source_conversation",
}

PROHIBITED_PATH_FRAGMENTS = [
    "backend",
    "private",
    "working-corpus",
    "source-conversation",
    "prompt",
]

MANIFEST_ARTIFACTS = {
    "document_registry": "mwe-public-documents.json",
    "document_schema": "mwe-document.schema.json",
    "public_surface_schema": "mwe-public-surface.schema.json",
    "jsonld_context": "mwe-public-context.jsonld",
    "misreading_register": "public-misreading-register.json",
    "misreading_register_schema": "public-misreading-register.schema.json",
    "validator": "scripts/validate_public_metadata.py",
}


def append_error(errors: list[str], message: str) -> None:
    errors.append(message)


def is_repository_relative_path(value: Any) -> bool:
    """Return whether value is a platform-independent repository-relative path."""
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and not PureWindowsPath(value).drive
        and ".." not in PurePosixPath(value).parts
    )


def resolve_repo_path(relative_path: str) -> Path | None:
    if not is_repository_relative_path(relative_path):
        return None
    candidate = Path(relative_path)
    resolved = (_ACTIVE_ROOT / candidate).resolve()
    try:
        resolved.relative_to(_ACTIVE_ROOT)
    except ValueError:
        return None
    return resolved


def repo_file_exists(relative_path: str, errors: list[str]) -> bool:
    resolved = resolve_repo_path(relative_path)
    if resolved is None:
        append_error(errors, f"{relative_path}: path escapes repository root")
        return False
    if not resolved.is_file():
        append_error(errors, f"{relative_path}: referenced file does not exist")
        return False
    return True


def read_repo_text(relative_path: str, errors: list[str]) -> str | None:
    resolved = resolve_repo_path(relative_path)
    if resolved is None:
        append_error(errors, f"{relative_path}: path escapes repository root")
        return None
    try:
        return resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        append_error(errors, f"{relative_path}: file does not exist")
    except OSError as exc:
        append_error(errors, f"{relative_path}: could not read file: {exc}")
    return None


def load_json_file(relative_path: str, errors: list[str]) -> Any:
    text = read_repo_text(relative_path, errors)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        append_error(errors, f"{relative_path}: invalid JSON at line {exc.lineno}: {exc.msg}")
    return None


def looks_private_path(value: str) -> bool:
    return any(pattern.search(value) for pattern in PRIVATE_PATH_PATTERNS)


def schema_enums(schema: dict[str, Any]) -> dict[str, set[str]]:
    enums: dict[str, set[str]] = {}
    for key, definition in schema.get("properties", {}).items():
        if isinstance(definition, dict) and "enum" in definition:
            enums[key] = set(definition["enum"])
    return enums


def validate_required_json_files(loaded: dict[str, Any], errors: list[str]) -> None:
    for relative_path in JSON_FILES:
        if loaded.get(relative_path) is None:
            append_error(errors, f"{relative_path}: required JSON file did not parse")


def validate_schema_drafts(loaded: dict[str, Any], errors: list[str]) -> None:
    for relative_path in SCHEMA_FILES:
        schema = loaded.get(relative_path)
        if isinstance(schema, dict):
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                append_error(errors, f"{relative_path}: expected JSON Schema Draft 2020-12")


def validate_classification_support(record: dict[str, Any], errors: list[str]) -> None:
    repository_path = str(record.get("repository_path", ""))
    classification = record.get("publicly_declared_classification")

    if classification is None:
        if record.get("classification_evidence") == "explicit_in_file":
            append_error(errors, f"{repository_path}: explicit_in_file without declared classification")
        return

    if record.get("classification_evidence") != "explicit_in_file":
        append_error(errors, f"{repository_path}: declared classification requires explicit_in_file")
        return

    source_text = read_repo_text(repository_path, errors)
    if source_text is None:
        return

    first_80_lines = source_text.splitlines()[:80]
    if not any(str(classification) in line for line in first_80_lines):
        append_error(
            errors,
            f"{repository_path}: declared classification not found in first 80 source lines",
        )


def validate_expected_paths_match_inventory(errors: list[str]) -> None:
    """Prove the explicit safety list still equals the declared inventory.

    Test-facing consistency check. It is NOT called by validate_public_metadata()
    and does not run during ordinary validation: it reads MODEL_ATLAS.md, which
    is not part of the validator's production read set, and adding it there would
    put the validator's dependencies out of step with the dependency inventory
    that enumerates them. The test suite calls this helper directly instead.

    The division of labour is deliberate. Production validation enforces the
    explicit EXPECTED_REGISTRY_PATHS contract by set equality in both directions,
    catching a missing approved path and an added unapproved path alike. This
    helper independently proves that the explicit list itself still equals the
    files MODEL_ATLAS declares with a literal `- **File:**` line plus the seven
    known registry-only paths, so the safety net cannot silently drift away from
    the inventory it is meant to protect.

    This confirms an inventory identity only; it establishes no classification
    and no relation.
    """
    atlas_text = read_repo_text(MODEL_ATLAS_FILE, errors)
    if atlas_text is None:
        return

    declared = set(MODEL_ATLAS_FILE_DECLARATION_RE.findall(atlas_text))
    expected_union = declared | set(REGISTRY_ONLY_PATHS)
    listed = set(EXPECTED_REGISTRY_PATHS)

    if len(EXPECTED_REGISTRY_PATHS) != len(listed):
        append_error(errors, "validator: EXPECTED_REGISTRY_PATHS contains duplicate paths")

    missing = sorted(expected_union - listed)
    unexpected = sorted(listed - expected_union)
    if missing:
        append_error(
            errors,
            f"validator: EXPECTED_REGISTRY_PATHS is missing declared inventory paths {missing}",
        )
    if unexpected:
        append_error(
            errors,
            "validator: EXPECTED_REGISTRY_PATHS contains paths that are neither "
            f"MODEL_ATLAS-declared nor known registry-only paths {unexpected}",
        )


def validate_document_registry(
    registry: dict[str, Any],
    document_schema: dict[str, Any],
    errors: list[str],
) -> None:
    records = registry.get("@graph")
    if not isinstance(records, list):
        append_error(errors, "mwe-public-documents.json: @graph must be a list")
        return

    # The declared count is checked against the actual @graph length rather than
    # against a fixed number, so the registry can grow without the gate becoming
    # a second place that has to be edited in step with the records. The exact
    # approved membership is enforced separately by EXPECTED_REGISTRY_PATHS.
    declared_count = registry.get("record_count")
    if declared_count != len(records):
        append_error(
            errors,
            f"mwe-public-documents.json: declared record_count {declared_count!r} does not equal "
            f"@graph length {len(records)}",
        )

    for referenced_key in ("@context", "document_schema"):
        referenced_path = registry.get(referenced_key)
        if isinstance(referenced_path, str):
            repo_file_exists(referenced_path.removeprefix("./"), errors)
        else:
            append_error(errors, f"mwe-public-documents.json: missing {referenced_key}")

    if registry.get("scope") != "selected_public_documents_only":
        append_error(errors, "mwe-public-documents.json: invalid selected-document scope")
    if registry.get("authority_ceiling") != "metadata_only":
        append_error(errors, "mwe-public-documents.json: invalid authority ceiling")
    if registry.get("completeness") != "not_a_complete_archive_or_registry":
        append_error(errors, "mwe-public-documents.json: invalid completeness boundary")

    required = set(document_schema.get("required", []))
    allowed_fields = set(document_schema.get("properties", {}))
    enum_fields = schema_enums(document_schema)
    ids: list[str] = []
    paths: list[str] = []

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            append_error(errors, f"record {index}: must be an object")
            continue

        repository_path = str(record.get("repository_path", ""))
        ids.append(str(record.get("@id", "")))
        paths.append(repository_path)

        missing = sorted(required - set(record))
        if missing:
            append_error(errors, f"{repository_path or 'record ' + str(index)}: missing required fields {missing}")

        extra = sorted(set(record) - allowed_fields)
        if extra:
            append_error(errors, f"{repository_path}: fields not allowed by document schema {extra}")

        for field, allowed_values in enum_fields.items():
            if field in record and record[field] not in allowed_values:
                append_error(errors, f"{repository_path}: invalid {field} value {record[field]!r}")

        if record.get("@type") not in {"schema:CreativeWork", "schema:DigitalDocument"}:
            append_error(errors, f"{repository_path}: invalid @type {record.get('@type')!r}")

        repo_file_exists(repository_path, errors)

        for reference in record.get("boundary_references", []):
            if isinstance(reference, str):
                repo_file_exists(reference, errors)
            else:
                append_error(errors, f"{repository_path}: boundary reference must be a string")

        source_use_reference = record.get("source_use_reference")
        if source_use_reference != "SOURCE_USE_GUIDE.md":
            append_error(errors, f"{repository_path}: source_use_reference must be SOURCE_USE_GUIDE.md")
        elif isinstance(source_use_reference, str):
            repo_file_exists(source_use_reference, errors)

        validate_classification_support(record, errors)

        prohibited_fields = sorted(PROHIBITED_RECORD_FIELDS & set(record))
        if prohibited_fields:
            append_error(errors, f"{repository_path}: prohibited authority fields {prohibited_fields}")

        for fragment in PROHIBITED_PATH_FRAGMENTS:
            if fragment in repository_path.lower():
                append_error(errors, f"{repository_path}: prohibited private/backend path fragment")

        for value in record.values():
            if isinstance(value, str) and looks_private_path(value):
                append_error(errors, f"{repository_path}: private local path detected")

    if len(ids) != len(set(ids)):
        append_error(errors, "mwe-public-documents.json: duplicate @id values")

    if len(paths) != len(set(paths)):
        append_error(errors, "mwe-public-documents.json: duplicate repository_path values")

    missing_paths = sorted(set(EXPECTED_REGISTRY_PATHS) - set(paths))
    extra_paths = sorted(set(paths) - set(EXPECTED_REGISTRY_PATHS))
    if missing_paths:
        append_error(errors, f"mwe-public-documents.json: missing expected paths {missing_paths}")
    if extra_paths:
        append_error(errors, f"mwe-public-documents.json: unexpected registry paths {extra_paths}")


def validate_evidence_schema_file(evidence_schema: dict[str, Any], errors: list[str]) -> None:
    """Confirm the evidence schema file still declares the contract this validator
    enforces, so the schema and the validator cannot drift apart."""
    if evidence_schema.get("additionalProperties") is not False:
        append_error(errors, f"{EVIDENCE_SCHEMA_FILE}: top level must set additionalProperties false")

    required = set(evidence_schema.get("required", []))
    missing = sorted(EVIDENCE_TOP_LEVEL_KEYS - required)
    if missing:
        append_error(errors, f"{EVIDENCE_SCHEMA_FILE}: required must include {missing}")

    defs = evidence_schema.get("$defs")
    if not isinstance(defs, dict):
        append_error(errors, f"{EVIDENCE_SCHEMA_FILE}: missing $defs")
        return

    value_enum = defs.get("evidenceValue", {})
    if set(value_enum.get("enum", [])) != EVIDENCE_VALUES:
        append_error(errors, f"{EVIDENCE_SCHEMA_FILE}: evidenceValue enum is not the closed vocabulary")

    record_def = defs.get("evidenceRecord", {})
    if record_def.get("additionalProperties") is not False:
        append_error(errors, f"{EVIDENCE_SCHEMA_FILE}: evidenceRecord must set additionalProperties false")
    if set(record_def.get("required", [])) != {"repository_path", "field_evidence"}:
        append_error(
            errors,
            f"{EVIDENCE_SCHEMA_FILE}: evidenceRecord must require repository_path and field_evidence",
        )

    field_def = defs.get("fieldEvidence", {})
    if field_def.get("additionalProperties") is not False:
        append_error(errors, f"{EVIDENCE_SCHEMA_FILE}: fieldEvidence must set additionalProperties false")
    if set(field_def.get("required", [])) != set(EVIDENCE_TRACKED_FIELDS):
        append_error(
            errors,
            f"{EVIDENCE_SCHEMA_FILE}: fieldEvidence must require exactly the eleven tracked fields",
        )

    # No classification or relation value may live in the evidence manifest.
    for prohibited in ("publicly_declared_classification", "classification_evidence"):
        if prohibited in field_def.get("properties", {}):
            append_error(errors, f"{EVIDENCE_SCHEMA_FILE}: fieldEvidence must not declare {prohibited}")


def validate_evidence_manifest(
    evidence: dict[str, Any],
    evidence_schema: dict[str, Any],
    registry: dict[str, Any],
    errors: list[str],
) -> None:
    """Validate the per-field evidence manifest against the registry and the
    source files.

    This checks provenance bookkeeping only. It confirms that every recorded
    evidence value is drawn from the closed vocabulary, that coverage of the
    registry is exactly one-to-one, and that every source-derived claim is
    actually supported by the file on disk while every registry-policy claim
    corresponds to the absence of such a declaration. It confirms no
    classification, no relation, and no Registry status.
    """
    validate_evidence_schema_file(evidence_schema, errors)

    keys = set(evidence)
    unknown = sorted(keys - EVIDENCE_TOP_LEVEL_KEYS)
    if unknown:
        append_error(errors, f"{EVIDENCE_FILE}: unknown top-level fields {unknown}")
    missing = sorted(EVIDENCE_TOP_LEVEL_KEYS - keys)
    if missing:
        append_error(errors, f"{EVIDENCE_FILE}: missing top-level fields {missing}")
        return

    if evidence.get("evidence_schema_version") != EXPECTED_EVIDENCE_SCHEMA_VERSION:
        append_error(
            errors,
            f"{EVIDENCE_FILE}: evidence_schema_version must be {EXPECTED_EVIDENCE_SCHEMA_VERSION!r}",
        )
    if evidence.get("describes") != EXPECTED_EVIDENCE_DESCRIBES:
        append_error(errors, f"{EVIDENCE_FILE}: describes must be {EXPECTED_EVIDENCE_DESCRIBES!r}")
    else:
        repo_file_exists(EXPECTED_EVIDENCE_DESCRIBES.removeprefix("./"), errors)
    if evidence.get("scope") != EXPECTED_EVIDENCE_SCOPE:
        append_error(errors, f"{EVIDENCE_FILE}: scope must be {EXPECTED_EVIDENCE_SCOPE!r}")
    if evidence.get("authority_ceiling") != EXPECTED_EVIDENCE_AUTHORITY_CEILING:
        append_error(
            errors,
            f"{EVIDENCE_FILE}: authority_ceiling must be {EXPECTED_EVIDENCE_AUTHORITY_CEILING!r}",
        )
    if not isinstance(evidence.get("scope_note"), str) or not evidence["scope_note"]:
        append_error(errors, f"{EVIDENCE_FILE}: scope_note must be a non-empty string")

    schema_reference = evidence.get("$schema")
    if schema_reference != f"./{EVIDENCE_SCHEMA_FILE}":
        append_error(errors, f"{EVIDENCE_FILE}: $schema must reference ./{EVIDENCE_SCHEMA_FILE}")
    elif isinstance(schema_reference, str):
        repo_file_exists(schema_reference.removeprefix("./"), errors)

    entries = evidence.get("records")
    if not isinstance(entries, list):
        append_error(errors, f"{EVIDENCE_FILE}: records must be a list")
        return

    declared_count = evidence.get("record_count")
    if declared_count != len(entries):
        append_error(
            errors,
            f"{EVIDENCE_FILE}: record_count {declared_count!r} does not equal "
            f"number of records {len(entries)}",
        )

    registry_records = registry.get("@graph")
    if not isinstance(registry_records, list):
        append_error(errors, f"{EVIDENCE_FILE}: cannot compare coverage, registry @graph is invalid")
        return
    registry_paths = [
        record.get("repository_path")
        for record in registry_records
        if isinstance(record, dict) and isinstance(record.get("repository_path"), str)
    ]
    registry_by_path = {
        record["repository_path"]: record
        for record in registry_records
        if isinstance(record, dict) and isinstance(record.get("repository_path"), str)
    }

    evidence_paths: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            append_error(errors, f"{EVIDENCE_FILE}: evidence entry {index} must be an object")
            continue

        unknown_entry = sorted(set(entry) - {"repository_path", "field_evidence"})
        if unknown_entry:
            append_error(errors, f"evidence entry {index}: unknown fields {unknown_entry}")

        path = entry.get("repository_path")
        if not isinstance(path, str) or not path:
            append_error(errors, f"evidence entry {index}: repository_path must be a non-empty string")
            continue
        evidence_paths.append(path)

        field_evidence = entry.get("field_evidence")
        if not isinstance(field_evidence, dict):
            append_error(errors, f"{path}: field_evidence must be an object")
            continue

        missing_fields = sorted(set(EVIDENCE_TRACKED_FIELDS) - set(field_evidence))
        if missing_fields:
            append_error(errors, f"{path}: evidence missing tracked fields {missing_fields}")
        extra_fields = sorted(set(field_evidence) - set(EVIDENCE_TRACKED_FIELDS))
        if extra_fields:
            append_error(errors, f"{path}: evidence declares untracked fields {extra_fields}")

        for field, value in field_evidence.items():
            if value not in EVIDENCE_VALUES:
                append_error(errors, f"{path}: evidence value {value!r} for {field} is outside the closed vocabulary")

        if path not in registry_by_path:
            # Coverage error is reported below; no source cross-check is possible.
            continue

        validate_evidence_against_source(path, registry_by_path[path], field_evidence, errors)

    if len(evidence_paths) != len(set(evidence_paths)):
        append_error(errors, f"{EVIDENCE_FILE}: duplicate repository_path values")

    missing_paths = sorted(set(registry_paths) - set(evidence_paths))
    extra_paths = sorted(set(evidence_paths) - set(registry_paths))
    if missing_paths:
        append_error(errors, f"{EVIDENCE_FILE}: missing evidence for registry paths {missing_paths}")
    if extra_paths:
        append_error(errors, f"{EVIDENCE_FILE}: evidence for non-registry paths {extra_paths}")

    if evidence_paths and registry_paths and evidence_paths != registry_paths:
        append_error(errors, f"{EVIDENCE_FILE}: evidence records must follow registry order")


def validate_evidence_against_source(
    path: str,
    record: dict[str, Any],
    field_evidence: dict[str, Any],
    errors: list[str],
) -> None:
    """Validate mechanically checkable evidence claims against the source file,
    including bidirectional declaration checks for public-surface status,
    authority ceiling, and classification."""
    source_text = read_repo_text(path, errors)
    if source_text is None:
        return

    has_public_surface_block = bool(PUBLIC_SURFACE_STATUS_DECLARATION_RE.search(source_text))
    has_classification = bool(CLASSIFICATION_DECLARATION_RE.search(source_text))

    # public_surface_status: source_declared if and only if the file declares it.
    status_evidence = field_evidence.get("public_surface_status")
    if status_evidence == "source_declared" and not has_public_surface_block:
        append_error(
            errors,
            f"{path}: public_surface_status recorded as source_declared but the source "
            "declares no 'Public-surface status:' line",
        )
    if status_evidence == "registry_policy" and has_public_surface_block:
        append_error(
            errors,
            f"{path}: public_surface_status recorded as registry_policy but the source "
            "declares a 'Public-surface status:' line",
        )

    # authority_ceiling tracks the same source block as public_surface_status.
    ceiling_evidence = field_evidence.get("authority_ceiling")
    if ceiling_evidence != status_evidence:
        append_error(
            errors,
            f"{path}: authority_ceiling evidence {ceiling_evidence!r} does not match "
            f"public_surface_status evidence {status_evidence!r}; both track the same "
            "source public-surface block",
        )

    # classification fail-closed, in both directions.
    classification_evidence = field_evidence.get("classification")
    if classification_evidence == "source_declared" and not has_classification:
        append_error(
            errors,
            f"{path}: classification recorded as source_declared but the source declares "
            "no literal 'Classification:' line",
        )
    if classification_evidence == "not_asserted" and has_classification:
        append_error(
            errors,
            f"{path}: classification recorded as not_asserted but the source declares a "
            "literal 'Classification:' line",
        )
    # The manifest must agree with the registry's own fail-closed field.
    registry_explicit = record.get("classification_evidence") == "explicit_in_file"
    if registry_explicit != (classification_evidence == "source_declared"):
        append_error(
            errors,
            f"{path}: evidence classification {classification_evidence!r} disagrees with "
            f"registry classification_evidence {record.get('classification_evidence')!r}",
        )

    # name: the recorded naming basis must actually produce the registry name.
    name_evidence = field_evidence.get("name")
    registry_name = record.get("name")
    h1_match = H1_RE.search(source_text)
    h1 = h1_match.group(1) if h1_match else None
    declared_titles = [m.group(1) for m in DISPLAY_TITLE_DECLARATION_RE.finditer(source_text)]
    if name_evidence == "source_h1" and registry_name != h1:
        append_error(
            errors,
            f"{path}: name recorded as source_h1 but the registry name does not match the source H1",
        )
    if name_evidence == "source_declared_display_title" and registry_name not in declared_titles:
        append_error(
            errors,
            f"{path}: name recorded as source_declared_display_title but the registry name "
            "matches no declared display title in the source",
        )

    # Mechanical fields must actually be mechanically derivable.
    if field_evidence.get("repository_path") == "mechanical" and record.get("repository_path") != path:
        append_error(errors, f"{path}: evidence entry path does not match the registry record path")
    if field_evidence.get("canonical_public_url") == "mechanical":
        expected_url = CANONICAL_URL_PREFIX + path
        if record.get("canonical_public_url") != expected_url:
            append_error(
                errors,
                f"{path}: canonical_public_url recorded as mechanical but the registry value "
                "is not the derived URL",
            )

    # schema_const must match the schema constant it claims.
    if field_evidence.get("source_use_reference") == "schema_const":
        if record.get("source_use_reference") != "SOURCE_USE_GUIDE.md":
            append_error(
                errors,
                f"{path}: source_use_reference recorded as schema_const but the registry value "
                "is not the schema constant",
            )


def validate_misreading_register(register: dict[str, Any], errors: list[str]) -> None:
    if register.get("scope") != "public_interpretation_corrections_only":
        append_error(errors, "public-misreading-register.json: invalid scope")
    if register.get("authority_ceiling") != "public_correction_only":
        append_error(errors, "public-misreading-register.json: invalid authority_ceiling")

    register_document = register.get("register_document")
    if isinstance(register_document, str):
        repo_file_exists(register_document, errors)
    else:
        append_error(errors, "public-misreading-register.json: missing register_document")

    entries = register.get("entries")
    if not isinstance(entries, list):
        append_error(errors, "public-misreading-register.json: entries must be a list")
        return

    case_ids: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            append_error(errors, f"misreading entry {index}: must be an object")
            continue

        case_id = str(entry.get("case_id", ""))
        case_ids.append(case_id)
        if not re.fullmatch(r"MWE-MR-[0-9]{4}", case_id):
            append_error(errors, f"misreading entry {index}: invalid case_id {case_id!r}")

        if entry.get("authorial_confirmation") is not True:
            append_error(errors, f"{case_id}: authorial_confirmation must be true")

        evidence_urls = entry.get("evidence_urls", [])
        if entry.get("status") in LIVE_CASE_STATUSES and not evidence_urls:
            append_error(errors, f"{case_id}: live case requires at least one public evidence URL")

        if not isinstance(evidence_urls, list):
            append_error(errors, f"{case_id}: evidence_urls must be a list")
            evidence_urls = []

        for url in evidence_urls:
            if not isinstance(url, str) or not re.match(r"^https?://", url):
                append_error(errors, f"{case_id}: evidence URL must be public http(s)")
            elif looks_private_path(url):
                append_error(errors, f"{case_id}: private path used as evidence")

        does_not_establish = entry.get("does_not_establish", [])
        if not isinstance(does_not_establish, list):
            append_error(errors, f"{case_id}: does_not_establish must be a list")
            does_not_establish = []
        missing = sorted(REQUIRED_DOES_NOT_ESTABLISH - set(does_not_establish))
        if missing:
            append_error(errors, f"{case_id}: missing does_not_establish values {missing}")

        for value in entry.values():
            if isinstance(value, str) and looks_private_path(value):
                append_error(errors, f"{case_id}: private local path detected")
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and looks_private_path(item):
                        append_error(errors, f"{case_id}: private local path detected")

    if len(case_ids) != len(set(case_ids)):
        append_error(errors, "public-misreading-register.json: duplicate case IDs")


def validate_manifest(manifest: dict[str, Any], errors: list[str]) -> None:
    if manifest.get("$schema") != "./mwe-public-surface.schema.json":
        append_error(errors, "mwe-public-surface.json: missing public-surface schema reference")

    artifacts = manifest.get("machine_readable_artifacts")
    if not isinstance(artifacts, dict):
        append_error(errors, "mwe-public-surface.json: machine_readable_artifacts must be an object")
        artifacts = {}

    for key, expected_path in MANIFEST_ARTIFACTS.items():
        if artifacts.get(key) != expected_path:
            append_error(errors, f"mwe-public-surface.json: {key} must reference {expected_path}")
        repo_file_exists(expected_path, errors)

    canonical_entries = manifest.get("canonical_entries")
    if not isinstance(canonical_entries, dict):
        append_error(errors, "mwe-public-surface.json: canonical_entries must be an object")
        canonical_entries = {}

    for expected_path in MANIFEST_ARTIFACTS.values():
        if expected_path == "scripts/validate_public_metadata.py":
            continue
        if expected_path not in canonical_entries.values():
            append_error(errors, f"mwe-public-surface.json: canonical_entries missing {expected_path}")

    for key, value in canonical_entries.items():
        if isinstance(value, str):
            repo_file_exists(value, errors)
        else:
            append_error(errors, f"mwe-public-surface.json: canonical entry {key} is not a string")


def validate_public_metadata() -> int:
    errors: list[str] = []
    loaded = {relative_path: load_json_file(relative_path, errors) for relative_path in JSON_FILES}

    validate_required_json_files(loaded, errors)
    validate_schema_drafts(loaded, errors)

    if not errors:
        manifest = loaded["mwe-public-surface.json"]
        registry = loaded["mwe-public-documents.json"]
        document_schema = loaded["mwe-document.schema.json"]
        misreading_register = loaded["public-misreading-register.json"]
        evidence = loaded[EVIDENCE_FILE]
        evidence_schema = loaded[EVIDENCE_SCHEMA_FILE]

        if isinstance(registry, dict) and isinstance(document_schema, dict):
            validate_document_registry(registry, document_schema, errors)
        else:
            append_error(errors, "mwe-public-documents.json or mwe-document.schema.json has invalid structure")

        if isinstance(evidence, dict) and isinstance(evidence_schema, dict) and isinstance(registry, dict):
            validate_evidence_manifest(evidence, evidence_schema, registry, errors)
        else:
            append_error(errors, f"{EVIDENCE_FILE} or {EVIDENCE_SCHEMA_FILE} has invalid structure")

        if isinstance(misreading_register, dict):
            validate_misreading_register(misreading_register, errors)
        else:
            append_error(errors, "public-misreading-register.json has invalid structure")

        if isinstance(manifest, dict):
            validate_manifest(manifest, errors)
        else:
            append_error(errors, "mwe-public-surface.json has invalid structure")

    if errors:
        print("Public metadata validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    registry_count = len(loaded["mwe-public-documents.json"].get("@graph", []))
    evidence_count = len(loaded[EVIDENCE_FILE].get("records", []))
    case_count = len(loaded["public-misreading-register.json"].get("entries", []))
    print("Public metadata validation passed.")
    print(f"- registry records: {registry_count}")
    print(f"- evidence records: {evidence_count}")
    print(f"- misreading register cases: {case_count}")
    print("- scope: structure, references, and public metadata only")
    return 0


def git_blob_sha1(data: bytes) -> str:
    """Compute the Git blob object id for raw bytes without invoking Git."""
    header = b"blob " + str(len(data)).encode("ascii") + b"\x00"
    return hashlib.sha1(header + data).hexdigest()


def _load_generator_builder_module() -> Any:
    """Load the companion builder module from the generator root only.

    The module is loaded by absolute path from the generator root so the import
    can never resolve to a same-named module under the source root. No
    source-tree Python is imported or executed.
    """
    builder_path = GENERATOR_ROOT_RESOLVED / "scripts" / "build_public_surface_authority_map.py"
    spec = importlib.util.spec_from_file_location("_generator_builder", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load generator builder module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_inventory_structure(inventory: Any, errors: list[str]) -> bool:
    """Enforce the dependency-inventory schema (unknown fields, digest form,
    ordering, and purpose vocabulary). Returns True when structurally valid."""
    if not isinstance(inventory, dict):
        append_error(errors, "inventory: top-level value must be an object")
        return False

    keys = set(inventory)
    unknown = sorted(keys - INVENTORY_TOP_LEVEL_KEYS)
    if unknown:
        append_error(errors, f"inventory: unknown top-level fields {unknown}")
    missing = sorted(INVENTORY_TOP_LEVEL_KEYS - keys)
    if missing:
        append_error(errors, f"inventory: missing top-level fields {missing}")
    if missing:
        return False

    if inventory.get("inventory_schema_version") != EXPECTED_INVENTORY_SCHEMA_VERSION:
        append_error(
            errors,
            f"inventory: inventory_schema_version must be {EXPECTED_INVENTORY_SCHEMA_VERSION!r}",
        )
    if inventory.get("source_repository") != EXPECTED_SOURCE_REPOSITORY:
        append_error(
            errors,
            f"inventory: source_repository must be {EXPECTED_SOURCE_REPOSITORY!r}",
        )
    if not isinstance(inventory.get("interface_version"), str):
        append_error(errors, "inventory: interface_version must be a string")

    aggregate = inventory.get("aggregate_sha256")
    if not isinstance(aggregate, str) or not SHA256_RE.match(aggregate):
        append_error(errors, "inventory: aggregate_sha256 must be a lowercase 64-hex string")

    files = inventory.get("files")
    if not isinstance(files, list):
        append_error(errors, "inventory: files must be a list")
        return False
    if not files:
        append_error(errors, "inventory: files must not be empty")

    dependency_count = inventory.get("dependency_count")
    if dependency_count != len(files):
        append_error(
            errors,
            f"inventory: dependency_count {dependency_count!r} != number of files {len(files)}",
        )

    structurally_valid = True
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            append_error(errors, f"inventory file {index}: must be an object")
            structurally_valid = False
            continue
        item_keys = set(item)
        unknown_item = sorted(item_keys - INVENTORY_ITEM_KEYS)
        if unknown_item:
            append_error(errors, f"inventory file {index}: unknown fields {unknown_item}")
        missing_item = sorted(INVENTORY_ITEM_KEYS - item_keys)
        if missing_item:
            append_error(errors, f"inventory file {index}: missing fields {missing_item}")
            structurally_valid = False
            continue

        path = item["path"]
        if not isinstance(path, str) or not path:
            append_error(errors, f"inventory file {index}: path must be a non-empty string")
        else:
            if not is_repository_relative_path(path):
                append_error(errors, f"{path}: path must be repository-relative forward-slash form")
        byte_length = item["byte_length"]
        if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length < 0:
            append_error(errors, f"{path}: byte_length must be a non-negative integer")
        sha256 = item["sha256"]
        if not isinstance(sha256, str) or not SHA256_RE.match(sha256):
            append_error(errors, f"{path}: sha256 must be a lowercase 64-hex string")
        git_blob = item["git_blob_sha1"]
        if not isinstance(git_blob, str) or not GIT_BLOB_RE.match(git_blob):
            append_error(errors, f"{path}: git_blob_sha1 must be a lowercase 40-hex string")
        purposes = item["read_purposes"]
        if not isinstance(purposes, list) or not purposes:
            append_error(errors, f"{path}: read_purposes must be a non-empty list")
        else:
            invalid = sorted(set(str(p) for p in purposes) - INVENTORY_READ_PURPOSES)
            if invalid:
                append_error(errors, f"{path}: invalid read_purposes {invalid}")
            if purposes != sorted(set(purposes)):
                append_error(errors, f"{path}: read_purposes must be unique and sorted")

    paths = [item.get("path") for item in files if isinstance(item, dict)]
    if paths != sorted(p for p in paths if isinstance(p, str)):
        append_error(errors, "inventory: files must be sorted by path")
    string_paths = [p for p in paths if isinstance(p, str)]
    if len(string_paths) != len(set(string_paths)):
        append_error(errors, "inventory: duplicate file paths")

    if structurally_valid and isinstance(aggregate, str):
        material = "".join(f"{item['path']}:{item['sha256']}\n" for item in files)
        recomputed = hashlib.sha256(material.encode("utf-8")).hexdigest()
        if recomputed != aggregate:
            append_error(errors, "inventory: aggregate_sha256 does not match recomputed value")

    return structurally_valid


def verify_inventory_against_source(inventory: dict[str, Any], errors: list[str]) -> None:
    """Recompute every listed identity against the source root and confirm the
    inventory paths and purposes agree with the independently enumerated set."""
    files = inventory.get("files")
    if not isinstance(files, list):
        return

    # Recompute identity for every listed path (resolved under the source root).
    for item in files:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        resolved = resolve_repo_path(path)
        if resolved is None:
            append_error(errors, f"{path}: inventory path escapes source root")
            continue
        if not resolved.is_file():
            append_error(errors, f"{path}: inventory path does not exist under source root")
            continue
        data = resolved.read_bytes()
        if item.get("byte_length") != len(data):
            append_error(errors, f"{path}: byte_length does not match source")
        if item.get("sha256") != hashlib.sha256(data).hexdigest():
            append_error(errors, f"{path}: sha256 does not match source")
        if item.get("git_blob_sha1") != git_blob_sha1(data):
            append_error(errors, f"{path}: git_blob_sha1 does not match source")

    # Independently enumerate the expected dependency set from the source
    # metadata using the generator-root builder, and compare paths + purposes.
    try:
        builder = _load_generator_builder_module()
        expected = builder.collect_read_purposes(_ACTIVE_ROOT)
    except SystemExit:
        append_error(errors, "inventory: could not enumerate expected dependencies from source root")
        return
    expected_purposes = {path: sorted(purposes) for path, purposes in expected.items()}

    listed = {
        item["path"]: item.get("read_purposes")
        for item in files
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }

    missing_paths = sorted(set(expected_purposes) - set(listed))
    extra_paths = sorted(set(listed) - set(expected_purposes))
    if missing_paths:
        append_error(errors, f"inventory: missing expected dependency paths {missing_paths}")
    if extra_paths:
        append_error(errors, f"inventory: unexpected dependency paths {extra_paths}")

    for path in sorted(set(listed) & set(expected_purposes)):
        if listed[path] != expected_purposes[path]:
            append_error(
                errors,
                f"{path}: read_purposes {listed[path]} do not match expected {expected_purposes[path]}",
            )


def read_inventory_file(inventory_path: str, errors: list[str]) -> Any:
    """Read the caller-provided isolated inventory file (never written)."""
    path = Path(inventory_path)
    if not path.is_file():
        append_error(errors, f"{inventory_path}: inventory file does not exist")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        append_error(errors, f"{inventory_path}: invalid JSON at line {exc.lineno}: {exc.msg}")
        return None


def run_isolated(source_root: str, mode: str, inventory_path: str | None) -> int:
    global _ACTIVE_ROOT
    source_root_resolved = Path(source_root).resolve()
    if not source_root_resolved.is_dir():
        print(f"validate_public_metadata: error: --source-root does not exist or is not a directory", file=sys.stderr)
        return 1
    _ACTIVE_ROOT = source_root_resolved

    # All modes first run the existing public-metadata / source-boundary checks.
    metadata_rc = validate_public_metadata()
    if metadata_rc != 0:
        return metadata_rc

    if mode == "preflight":
        print("Preflight validation passed (existing metadata and source-boundary rules).")
        print(f"- source root: {source_root_resolved}")
        return 0

    # verify-inventory mode.
    errors: list[str] = []
    inventory = read_inventory_file(inventory_path, errors)  # type: ignore[arg-type]
    if inventory is not None:
        structurally_valid = validate_inventory_structure(inventory, errors)
        if structurally_valid:
            verify_inventory_against_source(inventory, errors)

    if errors:
        print("Inventory verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Inventory verification passed.")
    print(f"- source root: {source_root_resolved}")
    print(f"- inventory dependencies: {inventory['dependency_count']}")
    print(f"- aggregate_sha256: {inventory['aggregate_sha256']}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_public_metadata.py",
        description=(
            "Validate MWE public metadata. With no arguments, validates the "
            "generator/repository root (default mode). With --source-root and "
            "--mode, validates an explicit detached source checkout in either "
            "preflight or verify-inventory mode. Performs no writes in any mode."
        ),
    )
    parser.add_argument(
        "--source-root",
        metavar="DIR",
        help="Explicit detached source checkout to validate. Enables isolated mode.",
    )
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        help=(
            "preflight: validate existing metadata and source-boundary rules "
            "against the source root (no inventory). verify-inventory: also "
            "validate and cross-check the supplied dependency inventory."
        ),
    )
    parser.add_argument(
        "--inventory",
        metavar="FILE",
        help="Isolated dependency-inventory file. Required in verify-inventory mode.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))

    if args.source_root is None and args.mode is None and args.inventory is None:
        return validate_public_metadata()

    if args.source_root is None:
        print("validate_public_metadata: error: isolated mode requires --source-root", file=sys.stderr)
        return 2
    if args.mode is None:
        print("validate_public_metadata: error: isolated mode requires --mode", file=sys.stderr)
        return 2

    if args.mode == "verify-inventory" and args.inventory is None:
        print(
            "validate_public_metadata: error: verify-inventory mode requires --inventory",
            file=sys.stderr,
        )
        return 2
    if args.mode == "preflight" and args.inventory is not None:
        print(
            "validate_public_metadata: error: --inventory is not permitted in preflight mode",
            file=sys.stderr,
        )
        return 2

    return run_isolated(args.source_root, args.mode, args.inventory)


if __name__ == "__main__":
    sys.exit(main())
