#!/usr/bin/env python3
"""Build deterministic data.json for the Public Surface and Authority-Ceiling Map.

This is a routine, deterministic transformation. It reads only approved public
metadata files, emits navigation-only node and edge data, and asserts nothing
about conceptual classification, internal Registry status, formal relations,
formal dependency, ontology, or semantic supersession.

Scope guarantees:
- standard library only
- no network access
- no Git operations
- no package installation
- reads only mwe-public-documents.json and mwe-public-surface.json to build data
- writes only visualizations/public-surface-authority-map/data.json (default mode)
- all paths are resolved inside the resolved root; traversal is rejected
- source metadata is preserved verbatim (no punctuation/Unicode/title repair)
- edges are navigation-only reference routing, never conceptual relations

Two invocation modes:

1. Default (backward-compatible) mode
       python scripts/build_public_surface_authority_map.py
   Reads the two approved inputs from the generator root and writes the tracked
   data.json in place. Behavior and output bytes are unchanged from prior
   releases. No dependency inventory is produced.

2. Isolated candidate mode
       python <generator-root>/scripts/build_public_surface_authority_map.py \
         --source-root <detached-source-checkout> \
         --output <isolated-output-file> \
         --inventory-output <isolated-inventory-file>
   Reads every source input from the explicit --source-root, writes data.json
   and a deterministic dependency inventory to caller-approved isolated paths
   outside both the source root and the generator root. The source root and
   generator root are never modified. This mode never falls back to
   generator-root content.

The dependency inventory records every source file that the builder or the
companion validator (validate_public_metadata.py) reads, opens, hashes, or
checks for existence in candidate mode, together with the exact read purpose(s)
for each path. It is a mechanical provenance record only; it asserts nothing
about classification, relations, public/private status, or Registry status, and
it never contains generator (executable transformation) identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


GENERATOR_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_ROOT_RESOLVED = GENERATOR_ROOT.resolve()

DOCUMENTS_FILE = "mwe-public-documents.json"
SURFACE_FILE = "mwe-public-surface.json"
MISREADING_REGISTER_FILE = "public-misreading-register.json"
OUTPUT_FILE = "visualizations/public-surface-authority-map/data.json"

EXPECTED_RECORD_COUNT = 27

# Provenance-inventory contract identities. These are stable facts fixed by the
# inventory schema/contract, not volatile run data.
INVENTORY_SCHEMA_VERSION = "1.0"
INTERFACE_VERSION = "1.0"
SOURCE_REPOSITORY = "metawritingecology/meta-writing-ecology"

# Closed read-purpose vocabulary (see mwe-public-surface-dependency-inventory.schema.json).
PURPOSE_DIRECT_INPUT = "direct_input"
PURPOSE_SCOPE_CONTEXT = "scope_context"
PURPOSE_REGISTRY_REFERENCED_DOCUMENT = "registry_referenced_document"
PURPOSE_CLASSIFICATION_EVIDENCE = "classification_evidence"
PURPOSE_REFERENCE_EXISTENCE_CHECK = "reference_existence_check"
PURPOSE_SCHEMA = "schema"

# Node fields copied verbatim from the registry record when present.
# Order here defines the deterministic key order in each output node.
NODE_STRING_FIELDS = [
    "name",
    "repository_path",
    "canonical_public_url",
    "surface_role",
    "public_surface_status",
    "authority_ceiling",
    "relation_default",
    "classification_evidence",
    "publicly_declared_classification",
]

# Explicit reference fields that may become navigation-only edges.
# Each maps a registry field name to its emitted relation_type.
REFERENCE_FIELDS = {
    "boundary_references": "boundary_reference",
    "source_use_reference": "source_use_reference",
}

BOUNDARY_STATEMENTS = [
    "Selected public surface only.",
    "Visual position does not indicate conceptual importance or internal authority.",
    "Reference routing does not establish a confirmed conceptual relation.",
    "Omission does not imply nonexistence.",
]


def fail(message: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"build_public_surface_authority_map: error: {message}", file=sys.stderr)
    sys.exit(1)


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


def resolve_under_root(root_resolved: Path, relative_path: str) -> Path | None:
    """Resolve a root-relative path, rejecting absolute paths, traversal, and
    symlink/reparse-point escape.

    The candidate is joined onto the already-resolved root and fully resolved
    (following symlinks). If the real resolved path is not contained within the
    resolved root, the access is rejected (fail closed).
    """
    if not is_repository_relative_path(relative_path):
        return None
    candidate = Path(relative_path)
    resolved = (root_resolved / candidate).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return None
    return resolved


def load_json(root_resolved: Path, relative_path: str) -> Any:
    resolved = resolve_under_root(root_resolved, relative_path)
    if resolved is None:
        fail(f"{relative_path}: path escapes source root")
    if not resolved.is_file():
        fail(f"{relative_path}: required input file does not exist")
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{relative_path}: invalid JSON at line {exc.lineno}: {exc.msg}")


def read_source_bytes(root_resolved: Path, relative_path: str) -> bytes:
    resolved = resolve_under_root(root_resolved, relative_path)
    if resolved is None:
        fail(f"{relative_path}: path escapes source root")
    if not resolved.is_file():
        fail(f"{relative_path}: referenced source file does not exist")
    return resolved.read_bytes()


def git_blob_sha1(data: bytes) -> str:
    """Compute the Git blob object id for raw bytes without invoking Git."""
    header = b"blob " + str(len(data)).encode("ascii") + b"\x00"
    return hashlib.sha1(header + data).hexdigest()


def strip_relative_prefix(reference: str) -> str:
    """Normalise a metadata reference to a repository-relative path."""
    if reference.startswith("./"):
        return reference[2:]
    return reference


def build_nodes(root_resolved: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            fail(f"record {index}: must be a JSON object")

        repository_path = record.get("repository_path")
        if not isinstance(repository_path, str) or not repository_path:
            fail(f"record {index}: missing repository_path")

        node_id = repository_path
        if node_id in seen_ids:
            fail(f"duplicate node id (repository_path): {node_id}")
        seen_ids.add(node_id)

        if repository_path in seen_paths:
            fail(f"duplicate repository_path: {repository_path}")
        seen_paths.add(repository_path)

        resolved = resolve_under_root(root_resolved, repository_path)
        if resolved is None:
            fail(f"{repository_path}: path escapes source root")
        if not resolved.is_file():
            fail(f"{repository_path}: referenced source file does not exist")

        node: dict[str, Any] = {"id": node_id}
        for field in NODE_STRING_FIELDS:
            if field in record:
                # Preserve source metadata verbatim; no normalization.
                node[field] = record[field]

        # Reference arrays are copied verbatim for the detail panel / table.
        boundary_references = record.get("boundary_references", [])
        if not isinstance(boundary_references, list):
            fail(f"{repository_path}: boundary_references must be a list")
        node["boundary_references"] = list(boundary_references)

        source_use_reference = record.get("source_use_reference")
        if source_use_reference is not None:
            node["source_use_reference"] = source_use_reference

        nodes.append(node)

    if len(nodes) != EXPECTED_RECORD_COUNT:
        fail(f"expected {EXPECTED_RECORD_COUNT} nodes, built {len(nodes)}")

    nodes.sort(key=lambda item: item["id"])
    return nodes


def build_edges(
    records: list[dict[str, Any]],
    node_ids: set[str],
) -> tuple[list[dict[str, Any]], int]:
    edges: list[dict[str, Any]] = []
    seen_edge_keys: set[tuple[str, str, str]] = set()
    self_references_omitted = 0

    for record in records:
        source = record.get("repository_path")
        if not isinstance(source, str):
            continue

        for field, relation_type in REFERENCE_FIELDS.items():
            raw = record.get(field)
            if raw is None:
                continue
            targets = raw if isinstance(raw, list) else [raw]
            for target in targets:
                if not isinstance(target, str):
                    continue
                # Only route between the 27 registry records.
                if target not in node_ids:
                    continue
                if target == source:
                    self_references_omitted += 1
                    continue
                key = (relation_type, source, target)
                if key in seen_edge_keys:
                    continue
                seen_edge_keys.add(key)
                edges.append(
                    {
                        "id": f"{relation_type}::{source}->{target}",
                        "source": source,
                        "target": target,
                        "relation_type": relation_type,
                        "relation_status": "navigation_only",
                        "evidence_source": source,
                        "authority_ceiling": "navigation_only",
                    }
                )

    edges.sort(key=lambda item: (item["relation_type"], item["source"], item["target"]))
    return edges, self_references_omitted


def assemble_map_data(root_resolved: Path) -> dict[str, Any]:
    """Read the approved inputs from root_resolved and assemble the map payload.

    This performs the same reads and validation the builder has always
    performed, parameterised by the resolved root so the same code path serves
    both default and isolated modes.
    """
    documents = load_json(root_resolved, DOCUMENTS_FILE)
    # mwe-public-surface.json is read only for scope confirmation; it does not
    # contribute node or edge records in this prototype.
    surface = load_json(root_resolved, SURFACE_FILE)

    if not isinstance(documents, dict):
        fail(f"{DOCUMENTS_FILE}: top-level value must be an object")
    if not isinstance(surface, dict):
        fail(f"{SURFACE_FILE}: top-level value must be an object")

    declared_count = documents.get("record_count")
    if declared_count != EXPECTED_RECORD_COUNT:
        fail(f"{DOCUMENTS_FILE}: declared record_count {declared_count!r} != {EXPECTED_RECORD_COUNT}")

    records = documents.get("@graph")
    if not isinstance(records, list):
        fail(f"{DOCUMENTS_FILE}: @graph must be a list")
    if len(records) != EXPECTED_RECORD_COUNT:
        fail(f"{DOCUMENTS_FILE}: @graph has {len(records)} records, expected {EXPECTED_RECORD_COUNT}")

    # Confirm the surface manifest still declares the selected-document scope.
    surface_registry = surface.get("public_document_registry", {})
    if surface_registry.get("scope") != "selected_public_documents_only":
        fail(f"{SURFACE_FILE}: public_document_registry.scope is not selected_public_documents_only")

    nodes = build_nodes(root_resolved, records)
    node_ids = {node["id"] for node in nodes}
    edges, self_references_omitted = build_edges(records, node_ids)

    edge_counts: dict[str, int] = {}
    for edge in edges:
        edge_counts[edge["relation_type"]] = edge_counts.get(edge["relation_type"], 0) + 1

    data = {
        "schema_version": "1.0",
        "title": "Public Surface and Authority-Ceiling Map",
        "scope": "selected_public_surface_only",
        "authority_ceiling": "navigation_only",
        "generated_from": [DOCUMENTS_FILE, SURFACE_FILE],
        "generated_record_count": len(nodes),
        "boundary_statements": BOUNDARY_STATEMENTS,
        "grouping_fields": [
            "surface_role",
            "authority_ceiling",
            "public_surface_status",
        ],
        "edge_counts": {key: edge_counts.get(key, 0) for key in sorted(REFERENCE_FIELDS.values())},
        "self_references_omitted_count": self_references_omitted,
        "nodes": nodes,
        "edges": edges,
        "transform_notes": {
            "self_references_omitted_from_edges": True,
            "record_order_implies_hierarchy": False,
            "node_size_implies_importance": False,
            "layout_position_implies_relation": False,
        },
    }
    return data


def collect_read_purposes(root_resolved: Path) -> dict[str, set[str]]:
    """Enumerate, from source metadata alone, every source file the builder or
    validator reads/opens/hashes/existence-checks in candidate mode, mapping
    each path to its exact read purpose(s).

    Derivation is metadata-driven and deterministic. No source-tree executable
    module is imported or run: paths are treated only as data. The mapping
    mirrors the observed candidate-mode access of build_public_surface_authority_map.py
    and validate_public_metadata.py.
    """
    purposes: dict[str, set[str]] = {}

    def add(path: str, purpose: str) -> None:
        purposes.setdefault(path, set()).add(purpose)

    documents = load_json(root_resolved, DOCUMENTS_FILE)
    surface = load_json(root_resolved, SURFACE_FILE)

    # Builder direct inputs.
    add(DOCUMENTS_FILE, PURPOSE_DIRECT_INPUT)          # parsed as the map registry
    add(SURFACE_FILE, PURPOSE_SCOPE_CONTEXT)           # parsed for scope confirmation

    # Registry-declared references (validate_document_registry existence checks).
    context_ref = documents.get("@context")
    if isinstance(context_ref, str):
        add(strip_relative_prefix(context_ref), PURPOSE_REFERENCE_EXISTENCE_CHECK)
    document_schema_ref = documents.get("document_schema")
    if isinstance(document_schema_ref, str):
        document_schema_path = strip_relative_prefix(document_schema_ref)
        add(document_schema_path, PURPOSE_REFERENCE_EXISTENCE_CHECK)
        add(document_schema_path, PURPOSE_SCHEMA)

    # Registry @graph records.
    records = documents.get("@graph")
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            repository_path = record.get("repository_path")
            if isinstance(repository_path, str) and repository_path:
                add(repository_path, PURPOSE_REGISTRY_REFERENCED_DOCUMENT)
                # The validator reads first source lines only when a public
                # classification is declared (validate_classification_support).
                if record.get("publicly_declared_classification") is not None:
                    add(repository_path, PURPOSE_CLASSIFICATION_EVIDENCE)
            boundary_references = record.get("boundary_references", [])
            if isinstance(boundary_references, list):
                for reference in boundary_references:
                    if isinstance(reference, str) and reference:
                        add(reference, PURPOSE_REFERENCE_EXISTENCE_CHECK)
            source_use_reference = record.get("source_use_reference")
            if isinstance(source_use_reference, str) and source_use_reference:
                add(source_use_reference, PURPOSE_REFERENCE_EXISTENCE_CHECK)

    # Surface manifest declared schema (applicable schema for the scope file).
    surface_schema_ref = surface.get("$schema")
    if isinstance(surface_schema_ref, str):
        add(strip_relative_prefix(surface_schema_ref), PURPOSE_SCHEMA)

    # Surface manifest artifact and canonical-entry existence checks
    # (validate_manifest). These pin every path the validator existence-checks
    # through the manifest, including the misreading register, its schema, and
    # the validator's own repository path (recorded only as an existence check,
    # never as generator identity).
    artifacts = surface.get("machine_readable_artifacts")
    if isinstance(artifacts, dict):
        for value in artifacts.values():
            if isinstance(value, str) and value:
                add(value, PURPOSE_REFERENCE_EXISTENCE_CHECK)
    canonical_entries = surface.get("canonical_entries")
    if isinstance(canonical_entries, dict):
        for value in canonical_entries.values():
            if isinstance(value, str) and value:
                add(value, PURPOSE_REFERENCE_EXISTENCE_CHECK)

    # Misreading register declared references (validate_misreading_register and
    # SCHEMA_FILES). The register document is existence-checked; the register
    # schema is validated as a JSON Schema.
    register = load_json(root_resolved, MISREADING_REGISTER_FILE)
    if isinstance(register, dict):
        register_document = register.get("register_document")
        if isinstance(register_document, str) and register_document:
            add(register_document, PURPOSE_REFERENCE_EXISTENCE_CHECK)
        register_schema_ref = register.get("$schema")
        if isinstance(register_schema_ref, str):
            add(strip_relative_prefix(register_schema_ref), PURPOSE_SCHEMA)

    return purposes


def build_dependency_inventory(root_resolved: Path) -> dict[str, Any]:
    """Build the deterministic, identity-bearing dependency inventory."""
    purposes = collect_read_purposes(root_resolved)

    files: list[dict[str, Any]] = []
    for path in sorted(purposes):
        data = read_source_bytes(root_resolved, path)
        files.append(
            {
                "path": path,
                "byte_length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "git_blob_sha1": git_blob_sha1(data),
                "read_purposes": sorted(purposes[path]),
            }
        )

    aggregate_material = "".join(f"{item['path']}:{item['sha256']}\n" for item in files)
    aggregate_sha256 = hashlib.sha256(aggregate_material.encode("utf-8")).hexdigest()

    return {
        "inventory_schema_version": INVENTORY_SCHEMA_VERSION,
        "source_repository": SOURCE_REPOSITORY,
        "interface_version": INTERFACE_VERSION,
        "dependency_count": len(files),
        "aggregate_sha256": aggregate_sha256,
        "files": files,
    }


def write_json_file(path: Path, data: Any) -> None:
    """Write UTF-8 with explicit LF newlines and a single final LF.

    newline="\n" disables platform newline translation; the JSON payload
    contains no line breaks other than the indent-2 formatting. Source Unicode
    is preserved verbatim (ensure_ascii=False).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")


def resolve_isolated_output(
    path_str: str,
    source_root_resolved: Path,
    generator_root_resolved: Path,
    label: str,
) -> Path:
    """Resolve a caller-provided output path and require it to live outside both
    the source root and the generator root (fail closed)."""
    resolved = Path(path_str).resolve()
    for root, name in (
        (source_root_resolved, "source root"),
        (generator_root_resolved, "generator root"),
    ):
        if resolved == root or root in resolved.parents:
            fail(f"{label} must resolve outside the {name}")
    return resolved


def run_default() -> int:
    root_resolved = GENERATOR_ROOT_RESOLVED
    data = assemble_map_data(root_resolved)

    output_resolved = resolve_under_root(root_resolved, OUTPUT_FILE)
    if output_resolved is None:
        fail(f"{OUTPUT_FILE}: output path escapes repository root")
    write_json_file(output_resolved, data)

    print("Public Surface and Authority-Ceiling Map data generated.")
    print(f"- output: {OUTPUT_FILE}")
    print(f"- nodes: {len(data['nodes'])}")
    print(f"- edges: {len(data['edges'])}")
    for relation_type in sorted(REFERENCE_FIELDS.values()):
        print(f"    - {relation_type}: {data['edge_counts'].get(relation_type, 0)}")
    print(f"- self-reference edges omitted: {data['self_references_omitted_count']}")
    print("- relation_status / authority_ceiling on every edge: navigation_only")
    return 0


def run_isolated(source_root: str, output: str, inventory_output: str) -> int:
    source_root_resolved = Path(source_root).resolve()
    if not source_root_resolved.is_dir():
        fail("--source-root does not exist or is not a directory")

    output_resolved = resolve_isolated_output(
        output, source_root_resolved, GENERATOR_ROOT_RESOLVED, "--output"
    )
    inventory_resolved = resolve_isolated_output(
        inventory_output, source_root_resolved, GENERATOR_ROOT_RESOLVED, "--inventory-output"
    )
    if output_resolved == inventory_resolved:
        fail("--output and --inventory-output must be distinct paths")

    data = assemble_map_data(source_root_resolved)
    inventory = build_dependency_inventory(source_root_resolved)

    write_json_file(output_resolved, data)
    write_json_file(inventory_resolved, inventory)

    print("Public Surface and Authority-Ceiling Map candidate generated (isolated mode).")
    print(f"- source root: {source_root_resolved}")
    print(f"- output: {output_resolved}")
    print(f"- inventory-output: {inventory_resolved}")
    print(f"- nodes: {len(data['nodes'])}")
    print(f"- edges: {len(data['edges'])}")
    print(f"- inventory dependencies: {inventory['dependency_count']}")
    print(f"- inventory aggregate_sha256: {inventory['aggregate_sha256']}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="build_public_surface_authority_map.py",
        description=(
            "Build deterministic data.json for the Public Surface and "
            "Authority-Ceiling Map. With no arguments, runs in default mode and "
            "writes the tracked data.json in place. In isolated candidate mode, "
            "reads every input from an explicit --source-root and writes the "
            "snapshot and a dependency inventory to isolated paths outside both "
            "the source root and the generator root."
        ),
    )
    parser.add_argument(
        "--source-root",
        metavar="DIR",
        help=(
            "Explicit detached source checkout to read all inputs from. "
            "Mandatory in isolated candidate mode. Never inferred from __file__, "
            "the current working directory, the output path, Git state, or "
            "environment variables."
        ),
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help=(
            "Isolated data.json output path. Must resolve outside both the "
            "source root and the generator root."
        ),
    )
    parser.add_argument(
        "--inventory-output",
        metavar="FILE",
        help=(
            "Isolated dependency-inventory output path. Must resolve outside "
            "both the source root and the generator root."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))

    isolated_flags = {
        "--source-root": args.source_root,
        "--output": args.output,
        "--inventory-output": args.inventory_output,
    }
    provided = {name for name, value in isolated_flags.items() if value is not None}

    if not provided:
        return run_default()

    missing = sorted(set(isolated_flags) - provided)
    if missing:
        fail(
            "isolated candidate mode requires --source-root, --output, and "
            f"--inventory-output together; missing: {', '.join(missing)}"
        )

    return run_isolated(args.source_root, args.output, args.inventory_output)


if __name__ == "__main__":
    sys.exit(main())
