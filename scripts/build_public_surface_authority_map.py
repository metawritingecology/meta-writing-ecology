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
- never writes visualizations/public-surface-authority-map/data.json
- all paths are resolved inside the resolved root; traversal is rejected
- source metadata is preserved verbatim (no punctuation/Unicode/title repair)
- edges are navigation-only reference routing, never conceptual relations

Three invocation modes:

1. Historical target (verify-only; also the zero-argument default)
       python scripts/build_public_surface_authority_map.py
       python scripts/build_public_surface_authority_map.py --target historical
   Reads the tracked historical artifact, recomputes its byte length, SHA-256
   and Git blob identity, inspects its structural invariants, and compares every
   value with the pinned historical specification below. It writes nothing: the
   30-record artifact is immutable, and in-place regeneration of its output path
   is retired. Its provenance is the Git-pinned reconstruction at
   HISTORICAL_SOURCE_COMMIT through isolated candidate mode (see mode 3 and the
   visualization README). On any mismatch the run exits non-zero and emits the
   stable failure token HISTORICAL_ARTIFACT_IDENTITY_MISMATCH. An identity
   mismatch is a failure, never a regeneration request.

2. Expanded target
       python scripts/build_public_surface_authority_map.py \
         --target expanded --output <path>
   Builds from the live registry to an explicitly supplied, non-historical
   output path, under its own expected record count (EXPANDED_RECORD_COUNT). The
   output path is mandatory; omitting it emits EXPANDED_TARGET_REQUIRES_OUTPUT.
   An output that resolves to the historical artifact is rejected before
   anything is written, with the token HISTORICAL_OUTPUT_PATH_COLLISION;
   collision detection covers relative, absolute, parent-traversing, symlinked
   and hard-linked aliases. No expanded output path is ever selected implicitly.

3. Isolated candidate mode
       python <generator-root>/scripts/build_public_surface_authority_map.py \
         --source-root <detached-source-checkout> \
         --output <isolated-output-file> \
         --inventory-output <isolated-inventory-file>
   Reads every source input from the explicit --source-root, writes data.json
   and a deterministic dependency inventory to caller-approved isolated paths
   outside both the source root and the generator root. The source root and
   generator root are never modified. This mode never falls back to
   generator-root content. Its behaviour is unchanged.

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
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


GENERATOR_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_ROOT_RESOLVED = GENERATOR_ROOT.resolve()

DOCUMENTS_FILE = "mwe-public-documents.json"
SURFACE_FILE = "mwe-public-surface.json"
MISREADING_REGISTER_FILE = "public-misreading-register.json"

# ---------------------------------------------------------------------------
# Per-target generation specification.
#
# The expected record count and the output path are properties of a named
# target, not module-global coupling. The historical target is verify-only and
# owns the one tracked output path; the expanded target has its own record count
# and no implicit path at all.
# ---------------------------------------------------------------------------

TARGET_HISTORICAL = "historical"
TARGET_EXPANDED = "expanded"

# ---------------------------------------------------------------------------
# Expanded adjacency-map inputs.
#
# The expanded target builds a separate product: the public-surface adjacency
# map. Its visualization membership and rendering policy live in an independent
# visualization manifest, never in the document registry, so registry selection
# and visualization membership stay separate contracts.
# ---------------------------------------------------------------------------

MODEL_ATLAS_FILE = "model-atlas/MODEL_ATLAS.md"
RELATION_MAP_FILE = "model-atlas/RELATION_MAP.md"

# Pinned commit the expanded dataset is generated from. Recorded as provenance
# in the dataset and required to match the visualization manifest.
EXPANDED_SOURCE_COMMIT = "933274af9693d6d1d9fac36819aafdf56f9ab81d"

# Consumer ceiling for the tracked expanded dataset.
EXPANDED_MAX_DATA_BYTES = 262144

# Mechanical registry surface_role -> visualization_role mapping. This is a
# rendering-band assignment only: it asserts nothing about classification,
# Registry status, hierarchy, or ontology membership.
VISUALIZATION_ROLE_BY_SURFACE_ROLE = {
    "concept_node": "concept",
    "repository_orientation": "orientation",
    "public_anchor": "anchor",
    "boundary_document": "boundary",
    "interpretation_guide": "boundary",
    "source_use_guide": "boundary",
}

ROLE_CONCEPT = "concept"
ROLE_ORIENTATION = "orientation"
ROLE_BOUNDARY = "boundary"
ROLE_ANCHOR = "anchor"

EXPECTED_ROLE_DISTRIBUTION = {
    ROLE_CONCEPT: 49,
    ROLE_ORIENTATION: 2,
    ROLE_BOUNDARY: 7,
    ROLE_ANCHOR: 1,
}

EDGE_CLASS_SOURCE_NAMED = "source_named_adjacency"
EDGE_CLASS_NAVIGATION = "navigation_adjacency"

# Relation classes that are deliberately NOT rendered as semantic edges in this
# release. They are stated once at product level instead. Keeping the names here
# makes their exclusion explicit and testable.
NON_RENDERED_RELATION_CLASSES = [
    "governance_reference",
    "source_use_reference",
    "visual_layout_adjacency",
    "user_confirmed_relation",
]

CEILING_NONE = "none"

EXPANDED_BOUNDARY_STATEMENTS = [
    "Selected public surface only. This is not the full MWE archive, registry, "
    "methodology, or authority layer.",
    "All 59 registered public documents are represented; only concept records "
    "enter the semantic graph layout.",
    "MODEL_ATLAS field grouping is a navigation grouping. It is not a formal "
    "classification, ontology, hierarchy, priority order, confirmed relation, "
    "or internal Registry assignment.",
    "Source-declared adjacency is adjacency as written in the source document. "
    "It is not a confirmed relation, formal dependency, or ontology claim.",
    "Provisional navigation adjacency is a navigation surface drawn from "
    "RELATION_MAP.md. It is provisional and is not a confirmed relation.",
    "Governance references and source-use references are recorded in the "
    "document registry and are stated here at product level only. They are not "
    "rendered as semantic edges and contribute nothing to layout or degree.",
    "Visual position, band placement, and record order do not indicate "
    "conceptual importance, priority, or internal authority.",
    "Omission does not imply nonexistence.",
]

# Historical target: frozen artifact, verify-only, fixed path.
HISTORICAL_OUTPUT_FILE = "visualizations/public-surface-authority-map/data.json"
HISTORICAL_RECORD_COUNT = 30

# Expanded target: explicit caller-supplied path only, distinct record count.
# There is deliberately no EXPANDED_OUTPUT_FILE constant: an expanded output
# path is never selected implicitly.
EXPANDED_RECORD_COUNT = 59

# Pinned identity of the frozen historical artifact. These values describe the
# tracked artifact reconstructed from HISTORICAL_SOURCE_COMMIT. They are not
# updated to accommodate an unexpected file.
HISTORICAL_SOURCE_COMMIT = "3219fa03149b4bf1a229f059b4912b632028422b"
HISTORICAL_DATA_BYTES = 92903
HISTORICAL_DATA_SHA256 = "3b1e5993a52cbce340b85472fea1ae5ea6f921cf8f7751d2d635edc7b17216ea"
HISTORICAL_DATA_BLOB = "2d59c4fdd07a2a9ddfad94e2e214a2d1c84912af"
HISTORICAL_NODE_COUNT = 30
HISTORICAL_EDGE_COUNT = 161
HISTORICAL_BOUNDARY_REFERENCE_EDGES = 132
HISTORICAL_SOURCE_USE_REFERENCE_EDGES = 29
HISTORICAL_SELF_REFERENCES_OMITTED = 7
# Provenance fact of the pinned reconstruction, reported by the verify-only
# mode. It is a property of the pinned source commit, not of the artifact bytes
# and not of the live registry, so it is pinned and reported here and asserted
# by the reconstruction tests rather than recomputed from current registry
# state during verification.
HISTORICAL_DEPENDENCY_INVENTORY_COUNT = 39

# Stable failure tokens. Callers and tests match on these exact strings.
FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH = "HISTORICAL_ARTIFACT_IDENTITY_MISMATCH"
FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION = "HISTORICAL_OUTPUT_PATH_COLLISION"
FAILURE_EXPANDED_TARGET_REQUIRES_OUTPUT = "EXPANDED_TARGET_REQUIRES_OUTPUT"
FAILURE_EXPANDED_TARGET_REQUIRES_MANIFEST = "EXPANDED_TARGET_REQUIRES_VISUALIZATION_MANIFEST"
FAILURE_EXPANDED_MANIFEST_INVALID = "EXPANDED_VISUALIZATION_MANIFEST_INVALID"
FAILURE_EXPANDED_GROUPING_UNRESOLVED = "EXPANDED_GROUPING_UNRESOLVED"
FAILURE_EXPANDED_EDGE_ENDPOINT_UNRESOLVED = "EXPANDED_EDGE_ENDPOINT_UNRESOLVED"
FAILURE_EXPANDED_DATA_EXCEEDS_CEILING = "EXPANDED_DATA_EXCEEDS_CONSUMER_CEILING"

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


def build_nodes(
    root_resolved: Path,
    records: list[dict[str, Any]],
    expected_record_count: int = HISTORICAL_RECORD_COUNT,
) -> list[dict[str, Any]]:
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

    if len(nodes) != expected_record_count:
        fail(f"expected {expected_record_count} nodes, built {len(nodes)}")

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
                # Only route between the records built for this target.
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


def assemble_map_data(
    root_resolved: Path,
    expected_record_count: int = HISTORICAL_RECORD_COUNT,
) -> dict[str, Any]:
    """Read the approved inputs from root_resolved and assemble the map payload.

    This performs the same reads and validation the builder has always
    performed, parameterised by the resolved root and by the calling target's
    expected record count, so the same code path serves isolated candidate mode
    and the expanded target without either inheriting the other's count.
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
    if declared_count != expected_record_count:
        fail(f"{DOCUMENTS_FILE}: declared record_count {declared_count!r} != {expected_record_count}")

    records = documents.get("@graph")
    if not isinstance(records, list):
        fail(f"{DOCUMENTS_FILE}: @graph must be a list")
    if len(records) != expected_record_count:
        fail(f"{DOCUMENTS_FILE}: @graph has {len(records)} records, expected {expected_record_count}")

    # Confirm the surface manifest still declares the selected-document scope.
    surface_registry = surface.get("public_document_registry", {})
    if surface_registry.get("scope") != "selected_public_documents_only":
        fail(f"{SURFACE_FILE}: public_document_registry.scope is not selected_public_documents_only")

    nodes = build_nodes(root_resolved, records, expected_record_count)
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


# ---------------------------------------------------------------------------
# Expanded adjacency-map parsers.
#
# Every parser below is deterministic and refuses to guess. A reference that
# cannot be mapped to exactly one of the registered repository paths by an
# explicitly written path is reported and rejected, never resolved by name
# similarity, filename inference, shared vocabulary, or proximity.
# ---------------------------------------------------------------------------

SOURCE_ADJACENCY_HEADING = re.compile(
    r"^## Relationship to Adjacent (?:Models|Public Frameworks)\s*$"
)
# The declared source adjacency syntax: a top-level list item whose leading
# element is a Markdown link carrying an explicit repository-relative path.
SOURCE_ADJACENCY_ENTRY = re.compile(r"^- \[[^\]]*\]\(([^)]+)\)")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
ATLAS_FIELD_HEADING = re.compile(r"^## (.+?)\s*$")
ATLAS_ENTRY_FILE = re.compile(r"^- \*\*File:\*\* `([^`]+)`\s*$")


def read_source_text(root_resolved: Path, relative_path: str) -> str:
    """Read a source document as text, failing closed on an unreadable input."""
    resolved = resolve_under_root(root_resolved, relative_path)
    if resolved is None:
        fail(f"{relative_path}: path escapes source root")
    if not resolved.is_file():
        fail(f"{relative_path}: required source file does not exist")
    try:
        return resolved.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"{relative_path}: unable to read source file: {exc}")


def resolve_reference_path(reference: str, containing_path: str) -> str | None:
    """Resolve a written Markdown reference to a repository-relative path.

    Purely mechanical: strip any fragment, then apply './' and '../' against the
    directory of the containing document. Returns None when the reference is not
    a repository-relative path expression at all.
    """
    target = reference.split("#", 1)[0].strip()
    if not target or target.startswith("/") or "://" in target:
        return None
    parts = containing_path.split("/")[:-1]
    while target.startswith("./") or target.startswith("../"):
        if target.startswith("./"):
            target = target[2:]
        else:
            target = target[3:]
            if not parts:
                return None
            parts = parts[:-1]
    if not target:
        return None
    resolved = "/".join([*parts, target]) if parts else target
    return resolved if is_repository_relative_path(resolved) else None


def build_visualization_roles(records: list[dict[str, Any]]) -> dict[str, str]:
    """Map each registered repository path to its visualization role.

    The mapping is mechanical from the registry's existing surface_role. It
    introduces no new registry literal and changes no registry value.
    """
    roles: dict[str, str] = {}
    for index, record in enumerate(records, start=1):
        repository_path = record.get("repository_path")
        if not isinstance(repository_path, str) or not repository_path:
            fail(f"record {index}: missing repository_path")
        surface_role = record.get("surface_role")
        if surface_role not in VISUALIZATION_ROLE_BY_SURFACE_ROLE:
            fail(
                f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {repository_path}: unknown "
                f"surface_role {surface_role!r}; no visualization role is inferred "
                "for an unmapped registry role"
            )
        roles[repository_path] = VISUALIZATION_ROLE_BY_SURFACE_ROLE[surface_role]
    return roles


def parse_model_atlas_fields(
    root_resolved: Path,
    records: list[dict[str, Any]],
    roles: dict[str, str],
) -> dict[str, str]:
    """Resolve each concept record to exactly one MODEL_ATLAS navigation field.

    MODEL_ATLAS entries declare their own file explicitly ('- **File:** `...`')
    under a '## <field>' heading, so the assignment is read, never inferred from
    a filename. Zero, duplicate, or ambiguous assignments stop the run.
    """
    text = read_source_text(root_resolved, MODEL_ATLAS_FILE)
    field: str | None = None
    assignments: dict[str, list[str]] = {}

    for line in text.split("\n"):
        heading = ATLAS_FIELD_HEADING.match(line)
        if heading:
            field = heading.group(1)
            continue
        entry = ATLAS_ENTRY_FILE.match(line)
        if not entry:
            continue
        if field is None:
            fail(
                f"{FAILURE_EXPANDED_GROUPING_UNRESOLVED}: {MODEL_ATLAS_FILE}: entry "
                f"{entry.group(1)!r} appears before any field heading"
            )
        assignments.setdefault(entry.group(1), []).append(field)

    grouping: dict[str, str] = {}
    for repository_path, role in roles.items():
        if role != ROLE_CONCEPT:
            continue
        fields = assignments.get(repository_path, [])
        if len(fields) != 1:
            fail(
                f"{FAILURE_EXPANDED_GROUPING_UNRESOLVED}: {repository_path}: resolves "
                f"to {len(fields)} MODEL_ATLAS navigation field(s) ({fields!r}); "
                "exactly one is required and no field is selected by guessing"
            )
        grouping[repository_path] = fields[0]
    return grouping


def parse_source_named_adjacency(
    root_resolved: Path,
    records: list[dict[str, Any]],
    roles: dict[str, str],
) -> tuple[list[tuple[str, str]], int, int]:
    """Extract source-declared adjacency from the registered source documents.

    Only the declared adjacency syntax is read: a top-level list item inside the
    document's own adjacency section whose leading element is a Markdown link to
    an explicit repository-relative path. Ordinary prose, inline links, plain
    text names, fenced comparison blocks, Related Node Index text, boundary
    references, source-use links and DOI links are never treated as adjacency,
    because none of them declares a path that can be resolved without guessing.

    Direction is preserved exactly as written; no reverse edge is manufactured.

    Returns (retained concept-to-concept edges, raw directed count, count
    excluded for a non-concept endpoint).
    """
    registered = set(roles)
    raw: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for repository_path in roles:
        text = read_source_text(root_resolved, repository_path)
        lines = text.split("\n")
        starts = [i for i, line in enumerate(lines) if SOURCE_ADJACENCY_HEADING.match(line)]
        if not starts:
            continue
        start = starts[0]
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if lines[index].startswith("## "):
                end = index
                break

        for line in lines[start + 1 : end]:
            entry = SOURCE_ADJACENCY_ENTRY.match(line)
            if not entry:
                continue
            target = resolve_reference_path(entry.group(1), repository_path)
            if target is None or target not in registered:
                fail(
                    f"{FAILURE_EXPANDED_EDGE_ENDPOINT_UNRESOLVED}: {repository_path}: "
                    f"source adjacency entry {line.strip()!r} names "
                    f"{entry.group(1)!r}, which does not map to exactly one of the "
                    f"{len(registered)} registered public documents"
                )
            if target == repository_path:
                continue
            key = (repository_path, target)
            # Duplicate identical directed entries are rejected within this
            # class only; identical pairs in another class stay separate.
            if key in seen:
                continue
            seen.add(key)
            raw.append(key)

    retained = [
        edge
        for edge in raw
        if roles[edge[0]] == ROLE_CONCEPT and roles[edge[1]] == ROLE_CONCEPT
    ]
    return retained, len(raw), len(raw) - len(retained)


def parse_navigation_adjacency(
    root_resolved: Path,
    records: list[dict[str, Any]],
    roles: dict[str, str],
) -> tuple[list[tuple[str, str]], int, int]:
    """Extract provisional navigation adjacency as written in RELATION_MAP.md.

    Only the table's own 'Adjacent entries' column is read. Nothing is inferred
    from MODEL_ATLAS grouping, textual proximity, or shared vocabulary.
    Direction is preserved as written; reciprocal pairs remain two directed
    edges and are never collapsed.

    Returns (retained concept-to-concept edges, raw directed count, count
    excluded for a non-concept endpoint).
    """
    text = read_source_text(root_resolved, RELATION_MAP_FILE)
    registered = set(roles)
    raw: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for line in text.split("\n"):
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            continue
        file_links = MARKDOWN_LINK.findall(cells[1])
        if not file_links:
            continue
        source = resolve_reference_path(file_links[0], RELATION_MAP_FILE)
        if source is None or source not in registered:
            fail(
                f"{FAILURE_EXPANDED_EDGE_ENDPOINT_UNRESOLVED}: {RELATION_MAP_FILE}: "
                f"row entry {cells[1]!r} does not map to exactly one of the "
                f"{len(registered)} registered public documents"
            )
        for reference in MARKDOWN_LINK.findall(cells[5]):
            target = resolve_reference_path(reference, RELATION_MAP_FILE)
            if target is None or target not in registered:
                fail(
                    f"{FAILURE_EXPANDED_EDGE_ENDPOINT_UNRESOLVED}: "
                    f"{RELATION_MAP_FILE}: adjacent entry {reference!r} on row "
                    f"{cells[1]!r} does not map to exactly one of the "
                    f"{len(registered)} registered public documents"
                )
            if target == source:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            raw.append(key)

    retained = [
        edge
        for edge in raw
        if roles[edge[0]] == ROLE_CONCEPT and roles[edge[1]] == ROLE_CONCEPT
    ]
    return retained, len(raw), len(raw) - len(retained)


def compute_relation_evidence_ceilings(
    records: list[dict[str, Any]],
    roles: dict[str, str],
    source_named: list[tuple[str, str]],
    navigation: list[tuple[str, str]],
) -> dict[str, str]:
    """Record the strongest approved display evidence available per record.

    This is a display-evidence fact only. It is not a classification, hierarchy,
    confirmed relation, priority order, or ontology statement.
    """
    named_sources = {edge[0] for edge in source_named}
    navigation_endpoints = {edge[0] for edge in navigation} | {edge[1] for edge in navigation}

    ceilings: dict[str, str] = {}
    for repository_path, role in roles.items():
        if role != ROLE_CONCEPT:
            ceilings[repository_path] = CEILING_NONE
        elif repository_path in named_sources:
            ceilings[repository_path] = EDGE_CLASS_SOURCE_NAMED
        elif repository_path in navigation_endpoints:
            ceilings[repository_path] = EDGE_CLASS_NAVIGATION
        else:
            ceilings[repository_path] = CEILING_NONE
    return ceilings


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


def historical_artifact_path() -> Path:
    """Fully resolved location of the frozen historical artifact.

    Resolution follows symlinks, so every alias of the tracked file — relative,
    absolute, parent-traversing, or symlinked — collapses to this one path.
    """
    resolved = resolve_under_root(GENERATOR_ROOT_RESOLVED, HISTORICAL_OUTPUT_FILE)
    if resolved is None:
        fail(f"{HISTORICAL_OUTPUT_FILE}: historical artifact path escapes the generator root")
    return resolved


def historical_identity_mismatches(data: bytes) -> list[str]:
    """Compare artifact bytes with the pinned historical specification.

    Returns one description per mismatched value; an empty list means the
    artifact matches its pinned identity exactly. This is a pure function of the
    supplied bytes: it reads nothing and writes nothing.
    """
    mismatches: list[str] = []

    def check(label: str, found: Any, pinned: Any) -> None:
        if found != pinned:
            mismatches.append(f"{label}: found {found!r}, pinned {pinned!r}")

    check("byte length", len(data), HISTORICAL_DATA_BYTES)
    check("sha256", hashlib.sha256(data).hexdigest(), HISTORICAL_DATA_SHA256)
    check("git blob", git_blob_sha1(data), HISTORICAL_DATA_BLOB)

    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        mismatches.append(f"structure: artifact is not readable JSON ({exc})")
        return mismatches
    if not isinstance(parsed, dict):
        mismatches.append("structure: artifact top-level value must be an object")
        return mismatches

    nodes = parsed.get("nodes")
    edges = parsed.get("edges")
    check("nodes", len(nodes) if isinstance(nodes, list) else None, HISTORICAL_NODE_COUNT)
    check("edges", len(edges) if isinstance(edges, list) else None, HISTORICAL_EDGE_COUNT)

    edge_counts = parsed.get("edge_counts")
    if not isinstance(edge_counts, dict):
        edge_counts = {}
    check(
        "boundary-reference edges",
        edge_counts.get("boundary_reference"),
        HISTORICAL_BOUNDARY_REFERENCE_EDGES,
    )
    check(
        "source-use-reference edges",
        edge_counts.get("source_use_reference"),
        HISTORICAL_SOURCE_USE_REFERENCE_EDGES,
    )
    check(
        "self-references omitted",
        parsed.get("self_references_omitted_count"),
        HISTORICAL_SELF_REFERENCES_OMITTED,
    )
    return mismatches


def run_historical(artifact_path: Path | None = None) -> int:
    """Verify the frozen historical artifact. Writes nothing, ever.

    The artifact is opened read-only; it is never opened for writing, replaced,
    restored, or touched, so its bytes and its mtime are unchanged by this run.
    No inventory or other persistent artifact is produced. artifact_path exists
    so tests can inject an isolated copy instead of editing the tracked file.
    """
    path = historical_artifact_path() if artifact_path is None else artifact_path

    if not path.is_file():
        fail(
            f"{FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH}: "
            f"{HISTORICAL_OUTPUT_FILE}: tracked historical artifact does not exist"
        )

    try:
        data = path.read_bytes()
    except OSError as exc:
        # A file that exists but cannot be read (permissions, I/O error, a
        # dangling mount) must fail closed with the stable token, not with a
        # traceback. The artifact is only ever opened for reading.
        fail(
            f"{FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH}: "
            f"{HISTORICAL_OUTPUT_FILE}: unable to read tracked historical artifact: {exc}"
        )

    mismatches = historical_identity_mismatches(data)
    if mismatches:
        for mismatch in mismatches:
            print(f"build_public_surface_authority_map: {mismatch}", file=sys.stderr)
        fail(
            f"{FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH}: "
            f"{HISTORICAL_OUTPUT_FILE} does not match its pinned historical identity "
            f"({len(mismatches)} mismatched value(s)). The artifact is immutable: "
            "this is a failure, not a regeneration request."
        )

    print("Historical public-surface artifact verified. Nothing was written.")
    print(f"- artifact: {HISTORICAL_OUTPUT_FILE}")
    print(f"- pinned source commit: {HISTORICAL_SOURCE_COMMIT}")
    print(f"- byte length: {HISTORICAL_DATA_BYTES}")
    print(f"- sha256: {HISTORICAL_DATA_SHA256}")
    print(f"- git blob: {HISTORICAL_DATA_BLOB}")
    print(f"- nodes: {HISTORICAL_NODE_COUNT}")
    print(f"- edges: {HISTORICAL_EDGE_COUNT}")
    print(f"    - boundary_reference: {HISTORICAL_BOUNDARY_REFERENCE_EDGES}")
    print(f"    - source_use_reference: {HISTORICAL_SOURCE_USE_REFERENCE_EDGES}")
    print(f"- self-reference edges omitted: {HISTORICAL_SELF_REFERENCES_OMITTED}")
    print(
        f"- pinned dependency-inventory entries: {HISTORICAL_DEPENDENCY_INVENTORY_COUNT} "
        "(provenance of the pinned reconstruction; not recomputed from live registry state)"
    )
    print("- mode: verify-only; in-place regeneration of this path is retired")
    return 0


def resolve_expanded_output(path_str: str) -> Path:
    """Resolve an expanded-target output path, failing closed on any alias of
    the frozen historical artifact.

    Two independent checks, because path resolution alone is not sufficient:

    1. Resolved-path equality. Resolved paths are compared, never raw strings,
       so a relative path, an absolute path, a parent-traversing path and a
       symlink alias all collapse to the same real location.
    2. Same-file identity for an output path that already exists. A hard link
       is a distinct pathname that resolves to itself yet shares an inode with
       the artifact; writing through it would mutate the artifact. samefile
       compares device and inode, so it catches that case.

    If the candidate exists but its identity cannot be established, the run
    fails closed: an alias that cannot be ruled out is never allowed to reach a
    write. Both checks run before any generation or record-count processing, so
    a collision can never reach the live registry, a parent-directory creation
    or an open.
    """
    output_resolved = Path(path_str).resolve()
    historical = historical_artifact_path()

    collision = output_resolved == historical
    reason = "resolves to"
    if not collision and output_resolved.exists():
        try:
            collision = output_resolved.samefile(historical)
        except OSError:
            collision = True
            reason = "cannot be distinguished from"
        else:
            if collision:
                reason = "is a hard link to"

    if collision:
        fail(
            f"{FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION}: --output {reason} the frozen "
            f"historical artifact ({HISTORICAL_OUTPUT_FILE}); the expanded target must "
            "write to a distinct path"
        )
    return output_resolved


def load_visualization_manifest(manifest_path: str) -> dict[str, Any]:
    """Read the independent visualization manifest, failing closed if unusable.

    The manifest is a separate contract from mwe-public-documents.json. It is
    read here and never written, and the registry is never treated as the
    visualization-membership authority.
    """
    path = Path(manifest_path)
    if not path.is_file():
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {manifest_path}: visualization "
            "manifest does not exist"
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {manifest_path}: unable to read "
            f"visualization manifest: {exc}"
        )
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {manifest_path}: invalid JSON at "
            f"line {exc.lineno}: {exc.msg}"
        )
    if not isinstance(manifest, dict):
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {manifest_path}: top-level value "
            "must be an object"
        )
    return manifest


def assemble_adjacency_data(
    root_resolved: Path,
    manifest: dict[str, Any],
    manifest_label: str,
) -> dict[str, Any]:
    """Assemble the expanded public-surface adjacency dataset.

    Reads the registry for record identity, the visualization manifest for
    membership and rendering policy, MODEL_ATLAS for concept navigation
    grouping, RELATION_MAP for provisional navigation adjacency, and each
    registered source document for its own declared adjacency.
    """
    documents = load_json(root_resolved, DOCUMENTS_FILE)
    if not isinstance(documents, dict):
        fail(f"{DOCUMENTS_FILE}: top-level value must be an object")

    declared_count = documents.get("record_count")
    if declared_count != EXPANDED_RECORD_COUNT:
        fail(
            f"{DOCUMENTS_FILE}: declared record_count {declared_count!r} "
            f"!= {EXPANDED_RECORD_COUNT}"
        )
    records = documents.get("@graph")
    if not isinstance(records, list):
        fail(f"{DOCUMENTS_FILE}: @graph must be a list")
    if len(records) != EXPANDED_RECORD_COUNT:
        fail(
            f"{DOCUMENTS_FILE}: @graph has {len(records)} records, expected "
            f"{EXPANDED_RECORD_COUNT}"
        )

    roles = build_visualization_roles(records)
    registry_order = [record["repository_path"] for record in records]

    role_counts = {role: 0 for role in EXPECTED_ROLE_DISTRIBUTION}
    for role in roles.values():
        role_counts[role] = role_counts.get(role, 0) + 1
    if role_counts != EXPECTED_ROLE_DISTRIBUTION:
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: visualization role distribution "
            f"{role_counts!r} != approved {EXPECTED_ROLE_DISTRIBUTION!r}"
        )

    # --- manifest contract -------------------------------------------------
    if manifest.get("source_commit") != EXPANDED_SOURCE_COMMIT:
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {manifest_label}: source_commit "
            f"{manifest.get('source_commit')!r} != pinned generation source commit "
            f"{EXPANDED_SOURCE_COMMIT!r}"
        )
    if manifest.get("record_count") != EXPANDED_RECORD_COUNT:
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {manifest_label}: record_count "
            f"{manifest.get('record_count')!r} != {EXPANDED_RECORD_COUNT}"
        )
    manifest_records = manifest.get("records")
    if not isinstance(manifest_records, list) or len(manifest_records) != EXPANDED_RECORD_COUNT:
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {manifest_label}: records must be "
            f"a list of exactly {EXPANDED_RECORD_COUNT} entries"
        )

    manifest_paths = [entry.get("repository_path") for entry in manifest_records]
    if manifest_paths != registry_order:
        fail(
            f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {manifest_label}: records must be "
            "exactly 1:1 with the registry, in registry order"
        )

    grouping = parse_model_atlas_fields(root_resolved, records, roles)
    source_named, source_named_raw, source_named_excluded = parse_source_named_adjacency(
        root_resolved, records, roles
    )
    navigation, navigation_raw, navigation_excluded = parse_navigation_adjacency(
        root_resolved, records, roles
    )
    ceilings = compute_relation_evidence_ceilings(records, roles, source_named, navigation)

    by_path = {record["repository_path"]: record for record in records}
    nodes: list[dict[str, Any]] = []

    for entry in manifest_records:
        repository_path = entry["repository_path"]
        record = by_path[repository_path]
        role = roles[repository_path]

        if entry.get("visualization_membership") != "included":
            fail(
                f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {repository_path}: "
                f"visualization_membership {entry.get('visualization_membership')!r} "
                "is not 'included'; the approved membership is all 59 records"
            )
        if entry.get("visualization_role") != role:
            fail(
                f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {repository_path}: manifest "
                f"visualization_role {entry.get('visualization_role')!r} != role "
                f"{role!r} mapped from the registry surface_role"
            )
        if entry.get("display_label_source") != "registry_name":
            fail(
                f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {repository_path}: "
                "display_label_source must be 'registry_name'"
            )
        expected_grouping_source = (
            "model_atlas_field" if role == ROLE_CONCEPT else "visualization_role"
        )
        if entry.get("grouping_source") != expected_grouping_source:
            fail(
                f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {repository_path}: "
                f"grouping_source {entry.get('grouping_source')!r} != "
                f"{expected_grouping_source!r}"
            )
        if entry.get("relation_evidence_ceiling") != ceilings[repository_path]:
            fail(
                f"{FAILURE_EXPANDED_MANIFEST_INVALID}: {repository_path}: manifest "
                f"relation_evidence_ceiling {entry.get('relation_evidence_ceiling')!r} "
                f"!= recomputed {ceilings[repository_path]!r}"
            )

        label = record.get("name")
        if not isinstance(label, str) or not label:
            fail(f"{repository_path}: registry record has no usable name")

        nodes.append(
            {
                "id": repository_path,
                "repository_path": repository_path,
                "display_label": label,
                "display_label_source": "registry_name",
                "visualization_role": role,
                "visualization_membership": "included",
                "semantic_layout_participation": role == ROLE_CONCEPT,
                "grouping_source": expected_grouping_source,
                "grouping": grouping[repository_path] if role == ROLE_CONCEPT else role,
                "relation_evidence_ceiling": ceilings[repository_path],
                "canonical_public_url": record.get("canonical_public_url"),
            }
        )

    edges: list[dict[str, Any]] = []
    for edge_class, pairs, default_visible in (
        (EDGE_CLASS_SOURCE_NAMED, source_named, True),
        (EDGE_CLASS_NAVIGATION, navigation, False),
    ):
        for source, target in sorted(pairs):
            edges.append(
                {
                    "id": f"{edge_class}::{source}->{target}",
                    "source": source,
                    "target": target,
                    "edge_class": edge_class,
                    "directed": True,
                    "default_visible": default_visible,
                    "relation_status": edge_class,
                    "authority_ceiling": "navigation_only",
                }
            )

    grouping_distribution: dict[str, int] = {}
    for node in nodes:
        if node["visualization_role"] == ROLE_CONCEPT:
            key = node["grouping"]
            grouping_distribution[key] = grouping_distribution.get(key, 0) + 1

    ceiling_distribution: dict[str, int] = {}
    for value in ceilings.values():
        ceiling_distribution[value] = ceiling_distribution.get(value, 0) + 1

    return {
        "schema_version": "1.0",
        "title": "Public Surface Adjacency Map (expanded public surface)",
        "scope": "expanded_public_surface_visualization_membership",
        "authority_ceiling": "navigation_only",
        "source_commit": EXPANDED_SOURCE_COMMIT,
        "source_repository": SOURCE_REPOSITORY,
        "generated_from": [
            DOCUMENTS_FILE,
            "visualizations/public-surface-adjacency-map/visualization-manifest.json",
            MODEL_ATLAS_FILE,
            RELATION_MAP_FILE,
            "each registered public source document (declared adjacency section only)",
        ],
        "record_count": len(nodes),
        "boundary_statements": EXPANDED_BOUNDARY_STATEMENTS,
        "role_distribution": {
            role: role_counts[role] for role in sorted(EXPECTED_ROLE_DISTRIBUTION)
        },
        "semantic_layout_participant_count": sum(
            1 for node in nodes if node["semantic_layout_participation"]
        ),
        "fixed_band_record_count": sum(
            1 for node in nodes if not node["semantic_layout_participation"]
        ),
        "grouping_distribution": {
            key: grouping_distribution[key] for key in sorted(grouping_distribution)
        },
        "relation_evidence_ceiling_distribution": {
            key: ceiling_distribution[key] for key in sorted(ceiling_distribution)
        },
        "edge_classes": [
            {
                "edge_class": EDGE_CLASS_SOURCE_NAMED,
                "display_label": "Source-declared adjacency",
                "directed": True,
                "default_visible": True,
                "evidence_source": "the source document's own adjacency section",
                "is_confirmed_relation": False,
            },
            {
                "edge_class": EDGE_CLASS_NAVIGATION,
                "display_label": "Provisional navigation adjacency",
                "directed": True,
                "default_visible": False,
                "evidence_source": RELATION_MAP_FILE,
                "is_confirmed_relation": False,
            },
        ],
        "raw_edge_counts": {
            EDGE_CLASS_NAVIGATION: navigation_raw,
            EDGE_CLASS_SOURCE_NAMED: source_named_raw,
        },
        "edge_counts": {
            EDGE_CLASS_NAVIGATION: len(navigation),
            EDGE_CLASS_SOURCE_NAMED: len(source_named),
        },
        "excluded_non_concept_endpoint_counts": {
            EDGE_CLASS_NAVIGATION: navigation_excluded,
            EDGE_CLASS_SOURCE_NAMED: source_named_excluded,
        },
        "relation_classes_not_rendered": list(NON_RENDERED_RELATION_CLASSES),
        "transform_notes": {
            "record_order_implies_hierarchy": False,
            "node_size_implies_importance": False,
            "layout_position_implies_relation": False,
            "grouping_implies_classification_or_ontology": False,
            "adjacency_implies_confirmed_relation": False,
            "reverse_edges_inferred": False,
            "non_concept_records_participate_in_layout": False,
            "governance_or_source_use_edges_rendered": False,
        },
        "nodes": nodes,
        "edges": edges,
    }


def run_expanded(output: str, visualization_manifest: str | None) -> int:
    # Collision checking runs first, before the manifest requirement, before any
    # registry or edge processing, before parent creation, and before any write.
    output_resolved = resolve_expanded_output(output)

    if visualization_manifest is None:
        fail(
            f"{FAILURE_EXPANDED_TARGET_REQUIRES_MANIFEST}: --target {TARGET_EXPANDED} "
            "requires an explicit --visualization-manifest path; the document "
            "registry is never the visualization-membership authority"
        )

    manifest = load_visualization_manifest(visualization_manifest)
    data = assemble_adjacency_data(GENERATOR_ROOT_RESOLVED, manifest, visualization_manifest)

    payload = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    encoded = payload.encode("utf-8")
    if len(encoded) > EXPANDED_MAX_DATA_BYTES:
        fail(
            f"{FAILURE_EXPANDED_DATA_EXCEEDS_CEILING}: expanded dataset is "
            f"{len(encoded)} bytes, above the {EXPANDED_MAX_DATA_BYTES}-byte "
            "consumer ceiling"
        )

    output_resolved.parent.mkdir(parents=True, exist_ok=True)
    with output_resolved.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)

    print("Public Surface Adjacency Map data generated (expanded target).")
    print(f"- output: {output_resolved}")
    print(f"- visualization manifest: {visualization_manifest}")
    print(f"- source commit: {EXPANDED_SOURCE_COMMIT}")
    print(f"- records: {data['record_count']}")
    print(f"- semantic-layout concepts: {data['semantic_layout_participant_count']}")
    print(f"- fixed-band records: {data['fixed_band_record_count']}")
    for edge_class in (EDGE_CLASS_SOURCE_NAMED, EDGE_CLASS_NAVIGATION):
        print(
            f"    - {edge_class}: raw {data['raw_edge_counts'][edge_class]}, "
            f"retained {data['edge_counts'][edge_class]}, excluded non-concept "
            f"endpoint {data['excluded_non_concept_endpoint_counts'][edge_class]}"
        )
    print(f"- byte length: {len(encoded)} (ceiling {EXPANDED_MAX_DATA_BYTES})")
    print(f"- sha256: {hashlib.sha256(encoded).hexdigest()}")
    print(f"- git blob: {git_blob_sha1(encoded)}")
    print(
        "- not rendered as semantic edges: "
        + ", ".join(NON_RENDERED_RELATION_CLASSES)
    )
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

    data = assemble_map_data(source_root_resolved, HISTORICAL_RECORD_COUNT)
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
            "Authority-Ceiling Map. With no arguments, verifies the frozen "
            "historical artifact and writes nothing. The expanded target builds "
            "to an explicitly supplied, non-historical output path. In isolated "
            "candidate mode, reads every input from an explicit --source-root "
            "and writes the snapshot and a dependency inventory to isolated "
            "paths outside both the source root and the generator root."
        ),
    )
    parser.add_argument(
        "--target",
        choices=[TARGET_HISTORICAL, TARGET_EXPANDED],
        default=None,
        help=(
            f"Explicit generation target. {TARGET_HISTORICAL!r} (also the "
            "zero-argument default) verifies the frozen historical artifact and "
            f"writes nothing. {TARGET_EXPANDED!r} builds the expanded dataset "
            "and requires an explicit --output that is not the historical "
            "artifact. Omit --target to use isolated candidate mode."
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
            "Explicit data.json output path. Mandatory for the expanded target, "
            "where it must not resolve to the historical artifact. In isolated "
            "candidate mode it must resolve outside both the source root and "
            "the generator root."
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
    parser.add_argument(
        "--visualization-manifest",
        metavar="FILE",
        help=(
            "Independent visualization manifest declaring visualization "
            "membership and rendering policy. Mandatory for the expanded "
            "target. The document registry is never used as the "
            "visualization-membership authority."
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

    if args.target == TARGET_EXPANDED:
        unsupported = sorted(provided - {"--output"})
        if unsupported:
            fail(
                f"--target {TARGET_EXPANDED} accepts only --output and "
                f"--visualization-manifest; remove: {', '.join(unsupported)}"
            )
        if args.output is None:
            fail(
                f"{FAILURE_EXPANDED_TARGET_REQUIRES_OUTPUT}: --target {TARGET_EXPANDED} "
                "requires an explicit --output path; no expanded output path is "
                "selected implicitly"
            )
        return run_expanded(args.output, args.visualization_manifest)

    if args.visualization_manifest is not None:
        fail(
            "--visualization-manifest applies only to "
            f"--target {TARGET_EXPANDED}"
        )

    if args.target == TARGET_HISTORICAL:
        if provided:
            fail(
                f"--target {TARGET_HISTORICAL} is verify-only and writes nothing; "
                f"remove: {', '.join(sorted(provided))}"
            )
        return run_historical()

    if not provided:
        return run_historical()

    missing = sorted(set(isolated_flags) - provided)
    if missing:
        fail(
            "isolated candidate mode requires --source-root, --output, and "
            f"--inventory-output together; missing: {', '.join(missing)}"
        )

    return run_isolated(args.source_root, args.output, args.inventory_output)


if __name__ == "__main__":
    sys.exit(main())
