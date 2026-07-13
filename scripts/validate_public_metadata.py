#!/usr/bin/env python3
"""Validate public metadata structure for the MWE public repository.

This validator checks JSON shape, references, enum use, selected registry
coverage, and public correction-register constraints. It is not conceptual,
empirical, Registry, relation, ontology, or corpus-completeness authority.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROOT_RESOLVED = ROOT.resolve()

JSON_FILES = [
    "mwe-public-surface.json",
    "mwe-public-documents.json",
    "mwe-public-context.jsonld",
    "public-misreading-register.json",
    "mwe-document.schema.json",
    "mwe-public-surface.schema.json",
    "public-misreading-register.schema.json",
]

SCHEMA_FILES = [
    "mwe-document.schema.json",
    "mwe-public-surface.schema.json",
    "public-misreading-register.schema.json",
]

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
]

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


def resolve_repo_path(relative_path: str) -> Path | None:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        return None
    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(ROOT_RESOLVED)
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


def validate_document_registry(
    registry: dict[str, Any],
    document_schema: dict[str, Any],
    errors: list[str],
) -> None:
    records = registry.get("@graph")
    if not isinstance(records, list):
        append_error(errors, "mwe-public-documents.json: @graph must be a list")
        return

    if len(records) != 27:
        append_error(errors, f"mwe-public-documents.json: expected 27 records, found {len(records)}")

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

        if isinstance(registry, dict) and isinstance(document_schema, dict):
            validate_document_registry(registry, document_schema, errors)
        else:
            append_error(errors, "mwe-public-documents.json or mwe-document.schema.json has invalid structure")

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
    case_count = len(loaded["public-misreading-register.json"].get("entries", []))
    print("Public metadata validation passed.")
    print(f"- registry records: {registry_count}")
    print(f"- misreading register cases: {case_count}")
    print("- scope: structure, references, and public metadata only")
    return 0


def main() -> int:
    return validate_public_metadata()


if __name__ == "__main__":
    sys.exit(main())
