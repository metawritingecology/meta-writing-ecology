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
- reads only mwe-public-documents.json and mwe-public-surface.json
- writes only visualizations/public-surface-authority-map/data.json
- all paths are resolved inside the repository root; traversal is rejected
- source metadata is preserved verbatim (no punctuation/Unicode/title repair)
- edges are navigation-only reference routing, never conceptual relations
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROOT_RESOLVED = ROOT.resolve()

DOCUMENTS_FILE = "mwe-public-documents.json"
SURFACE_FILE = "mwe-public-surface.json"
OUTPUT_FILE = "visualizations/public-surface-authority-map/data.json"

EXPECTED_RECORD_COUNT = 27

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


def resolve_repo_path(relative_path: str) -> Path | None:
    """Resolve a repository-relative path, rejecting absolute paths and traversal."""
    candidate = Path(relative_path)
    if candidate.is_absolute():
        return None
    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(ROOT_RESOLVED)
    except ValueError:
        return None
    return resolved


def load_json(relative_path: str) -> Any:
    resolved = resolve_repo_path(relative_path)
    if resolved is None:
        fail(f"{relative_path}: path escapes repository root")
    if not resolved.is_file():
        fail(f"{relative_path}: required input file does not exist")
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{relative_path}: invalid JSON at line {exc.lineno}: {exc.msg}")


def build_nodes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

        resolved = resolve_repo_path(repository_path)
        if resolved is None:
            fail(f"{repository_path}: path escapes repository root")
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


def main() -> int:
    documents = load_json(DOCUMENTS_FILE)
    # mwe-public-surface.json is read only for scope confirmation; it does not
    # contribute node or edge records in this prototype.
    surface = load_json(SURFACE_FILE)

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

    nodes = build_nodes(records)
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

    output_resolved = resolve_repo_path(OUTPUT_FILE)
    if output_resolved is None:
        fail(f"{OUTPUT_FILE}: output path escapes repository root")
    output_resolved.parent.mkdir(parents=True, exist_ok=True)
    # Write UTF-8 with explicit LF newlines so output is byte-reproducible on
    # Windows, macOS, and Linux. newline="\n" disables platform newline
    # translation; the JSON payload contains no line breaks other than the
    # indent-2 formatting, and one final LF terminates the file. Source Unicode
    # is preserved verbatim (ensure_ascii=False).
    with output_resolved.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")

    print("Public Surface and Authority-Ceiling Map data generated.")
    print(f"- output: {OUTPUT_FILE}")
    print(f"- nodes: {len(nodes)}")
    print(f"- edges: {len(edges)}")
    for relation_type in sorted(REFERENCE_FIELDS.values()):
        print(f"    - {relation_type}: {edge_counts.get(relation_type, 0)}")
    print(f"- self-reference edges omitted: {self_references_omitted}")
    print("- relation_status / authority_ceiling on every edge: navigation_only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
