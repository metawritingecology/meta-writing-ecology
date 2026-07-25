# Public Surface and Authority-Ceiling Map

A local, reviewable D3 prototype that visualizes the selected public-document
records declared in `mwe-public-documents.json`.

## 1. Purpose

Present the selected public-surface documents by their public source function,
surface role, public-surface status, declared authority ceiling, and explicit
classification evidence, so a reader can navigate the public surface without
inferring authority, hierarchy, or conceptual relations.

## 2. Scope

Selected public surface only. This interface represents 30 selected
public-document records. It is **not** the internal Registry, **not** a complete
archive, **not** a formal ontology, and **not** an authoritative conceptual
relation graph. Inclusion does not imply priority; omission does not imply
nonexistence.

## 3. Data sources

Generated deterministically from repository files only:

- `mwe-public-documents.json` — the sole source of document-node records.
- `mwe-public-surface.json` — read only to confirm public-surface scope.

No conceptual Markdown, filename inference, or semantic similarity is used.

## 4. Transformation process

`scripts/build_public_surface_authority_map.py` (Python standard library only,
no network, no Git, no installs) reads the two approved inputs to produce the
`data.json` tracked in this directory. In-place regeneration of that file is now
retired and the builder no longer writes it; see section 16. The transformation
that produced it:

- requires exactly 30 records with unique IDs and repository paths;
- requires every repository path to exist inside the repository;
- copies node metadata verbatim (no punctuation/Unicode/title repair);
- emits edges only from the explicit `boundary_references` and
  `source_use_reference` fields, and only between the 30 records;
- omits self-reference edges and records the omission count;
- marks every edge `relation_status: navigation_only` and
  `authority_ceiling: navigation_only`;
- sorts nodes and edges deterministically (running twice yields no diff).

## 5. Local preview

From the repository root (or from this directory):

```
python -m http.server 8000
```

Then open:

```
http://localhost:8000/visualizations/public-surface-authority-map/
```

The page fetches `data.json` over HTTP, so it must be served (not opened as a
`file://` URL).

## 6. Visual encodings

- **Node** = one selected public-document record. All nodes have **equal visual
  area**. Node size never encodes degree, references, classification, authority,
  or importance.
- **Group / column** = a declared public metadata category (default:
  `surface_role`). Grouping is categorical and deterministic, not a ranking.
- **Color + glyph** = secondary cue for the current grouping value only. Color
  is never authority; a matching glyph and text label accompany every color.
- **Edge** = an explicit navigation-only reference (`boundary_reference` or
  `source_use_reference`). Edges are never conceptual relations, derivations, or
  dependencies. Line style (solid vs. dashed) distinguishes the two reference
  types.

Vertical order, horizontal order, spacing, proximity, and edge density are
presentation only and carry no conceptual meaning.

## 7. Interaction

- Group by surface role, authority ceiling, or public-surface status.
- Search by document name or repository path.
- Filter by surface role, authority ceiling, public-surface status, and
  classification evidence.
- Reset control restores the default view.
- Reference routing is **off by default**. A per-node toggle shows routing
  incident to the selected/focused node; a secondary global toggle shows all
  explicit routing behind a visible density warning.
- Selecting a node opens a detail panel with its declared metadata and a link to
  the individual public source file.

Filtering never alters the underlying data; filtered nodes are dimmed and
labeled "Filtered from current view", never "does not exist".

## 8. Accessibility

- Nodes are real `<button>` elements: keyboard focusable with visible focus
  rings and screen-reader labels.
- All controls are labeled semantic form elements.
- Color is always paired with a glyph and text label (no color-only meaning).
- Essential information is available in the detail panel and the table fallback,
  not hover-only.
- A textual table fallback lists all 30 records
  (`name`, `repository_path`, `surface_role`, `public_surface_status`,
  `authority_ceiling`, `classification_evidence`).
- `prefers-reduced-motion` disables transitions; `prefers-color-scheme`
  provides light and dark themes with adequate contrast.
- Layout is responsive down to small screens.

## 9. Boundary statements

The always-visible banner and scope panel state, without requiring interaction:

- Selected public surface only.
- Visual position does not indicate conceptual importance or internal authority.
- Reference routing does not establish a confirmed conceptual relation.
- Omission does not imply nonexistence.
- The public registry is not the internal Registry or a complete archive.

## 10. Non-authority statement

This visualization is a selected public-surface navigation interface. It is not
the internal Registry, a complete archive, a formal ontology, or an
authoritative conceptual relation graph. The layout is categorical and
deterministic; it is not a measurement of conceptual importance.

## 11. Verification command

```
python scripts/build_public_surface_authority_map.py
```

(Use `python3` if `python` is not on PATH.) Run from the repository root.

This is a verify-only command. It reads the tracked `data.json`, recomputes its
byte length, SHA-256 and Git blob identity, inspects its structural invariants,
compares every value with the pinned historical specification, and writes
nothing. It is no longer a rebuild command; see section 16.

## 12. Validation commands

```
python scripts/validate_public_metadata.py
python scripts/build_public_surface_authority_map.py
```

Neither command writes `data.json`. The builder fails non-zero on invalid input;
in isolated candidate mode it remains deterministic, so two runs against the
same source root produce byte-identical output.

## 13. Known limitations

- This is a first prototype: a deterministic categorical (grouped) layout, not a
  force-directed or measured graph.
- Only explicit `boundary_reference` and `source_use_reference` routing is shown.
  No conceptual, candidate, confirmed, or dependency relations are represented.
- Because boundary documents are referenced by many records, the global routing
  overlay is dense; density is presentation only and does not imply importance.
- **D3 dependency:** D3 v7 (pinned `d3@7.9.0`) is loaded from
  `https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js`. Network access to that
  CDN is required for the D3-enhanced path; core rendering, metadata, and the
  table fallback still work if the CDN is unavailable. No D3 bundle is vendored
  into the repository.

## 14. Isolated candidate mode (source/generator separation)

The builder and validator also support an isolated candidate mode that reads
every input from an explicit, detached source checkout. This lets an
independently reviewed generator checkout process a separately pinned content
checkout without binding content to the code's own location. It exists for
auditable, reproducible candidate generation; it changes no map semantics and
carries no additional authority.

Two immutable inputs are kept separate:

- the **source root** supplies content and metadata;
- the **generator root** supplies the executable transformation and validation.

Approval of one never approves the other. This mode never falls back to
generator-root content.

Builder (writes an isolated snapshot and a dependency inventory outside both
roots):

```
python <generator-root>/scripts/build_public_surface_authority_map.py \
  --source-root <detached-source-checkout> \
  --output <isolated-output-file> \
  --inventory-output <isolated-inventory-file>
```

- `--source-root` is mandatory in isolated mode and is resolved explicitly. It
  is never inferred from `__file__`, the current working directory, the output
  path, Git state, or environment variables.
- Every source read resolves under the source root; absolute paths, parent
  traversal, and symlink/reparse-point escape fail closed.
- `--output` and `--inventory-output` must resolve outside both the source root
  and the generator root. Neither root is modified.
- Output bytes are UTF-8 with LF newlines and one final LF; two runs are
  byte-identical.

Validator (no writes in any mode):

```
# Preflight: existing metadata and source-boundary rules against the source root
python <generator-root>/scripts/validate_public_metadata.py \
  --source-root <detached-source-checkout> --mode preflight

# Inventory verification: existing validation plus inventory schema, identity
# recomputation, and path/purpose cross-check against the source root
python <generator-root>/scripts/validate_public_metadata.py \
  --source-root <detached-source-checkout> --mode verify-inventory \
  --inventory <isolated-inventory-file>
```

Isolated candidate mode is unchanged. The local commands in sections 11–12 are
verify-only; see section 16.

Source-tree Python files are treated only as data. Neither tool imports or
executes any module discovered under the source root.

## 15. Dependency inventory

In isolated mode the builder emits a deterministic dependency inventory
(`mwe-public-surface-dependency-inventory.schema.json`) recording every source
file the builder or the validator reads, opens, hashes, or checks for existence
in candidate mode, with the exact read purpose(s) for each path:

- `direct_input` — parsed as the registry that produces the map;
- `scope_context` — parsed to confirm the selected-document scope;
- `registry_referenced_document` — a selected registry `repository_path`;
- `classification_evidence` — first source lines read to confirm a declared
  public classification;
- `reference_existence_check` — existence verified because a metadata field
  (boundary reference, source-use reference, manifest artifact, canonical
  entry, `@context`, `document_schema`, or register document) points to it;
- `schema` — validated as a JSON Schema.

Each entry records the repository-relative path, byte length, lowercase SHA-256,
and Git blob id. The inventory contains only stable facts. It never contains
timestamps, absolute paths, host or user names, run IDs, other volatile run
evidence, or generator (executable transformation) identity. A source file that
happens to share a path with the validator is recorded only as an existence
check, never as generator identity.

The inventory is a mechanical provenance record. It asserts nothing about
conceptual classification, relations, public/private status, Registry status, or
candidate acceptance, and adding it activates nothing.

## 16. Historical artifact

This directory contains a **frozen historical artifact**: the 30-record
`data.json` snapshot. It is immutable. In-place regeneration of its output path
is retired, and no live-registry generation can overwrite it.

**Verify-only invocation.** Both of these read the tracked artifact, recompute
its identity, check its structural invariants against the pinned specification
below, and write nothing:

```
python scripts/build_public_surface_authority_map.py
python scripts/build_public_surface_authority_map.py --target historical
```

Neither opens the artifact for writing, replaces it temporarily, restores it
after a run, alters its modification time, or creates any file beside it. An
explicit historical target is not permitted to regenerate the artifact and
accepts no output-bearing flag.

**Fail-closed behaviour.** A historical identity mismatch is a failure, not a
regeneration request. The pinned values are never updated to accommodate an
unexpected file. Three stable failure tokens are emitted on standard error:

- `HISTORICAL_ARTIFACT_IDENTITY_MISMATCH` — the tracked artifact does not match
  its pinned identity, or is missing, or cannot be read. A file that exists but
  cannot be opened for reading (permissions, I/O error) fails closed with this
  token rather than raising.
- `HISTORICAL_OUTPUT_PATH_COLLISION` — an expanded output is an alias of the
  historical artifact. Collision detection covers five alias forms:

  ```
  relative path
  absolute path
  parent traversal
  symlink alias
  hard-link alias
  ```

  Resolved paths are compared, never raw strings, which covers the first four.
  Resolved-path equality is supplemented by same-file identity checking (device
  and inode) for an output path that already exists, which covers a hard link —
  a distinct pathname that resolves to itself yet shares an inode with the
  artifact. An output whose identity cannot be established fails closed. Both
  checks run before any generation or record-count processing, so a collision
  never reaches the live registry, a directory creation or an open.
- `EXPANDED_TARGET_REQUIRES_OUTPUT` — the expanded target was invoked without an
  explicit `--output`.

**Expanded generation.** Expanded output is a separate target with its own
expected record count and no implicit path:

```
python scripts/build_public_surface_authority_map.py \
  --target expanded --output <path>
```

`--output` is mandatory and must resolve to a path distinct from the historical
artifact. No expanded artifact is produced, committed or retained at this phase;
the expanded target is prepared here and generation is deferred to a later
authorized visualization phase.

**Pinned historical identity.** The nine invariants of the frozen artifact:

```
source commit               3219fa03149b4bf1a229f059b4912b632028422b
byte length                 92903
SHA-256                     3b1e5993a52cbce340b85472fea1ae5ea6f921cf8f7751d2d635edc7b17216ea
Git blob                    2d59c4fdd07a2a9ddfad94e2e214a2d1c84912af
nodes                       30
edges                       161
boundary-reference edges    132
source-use-reference edges  29
self-references omitted     7
dependency-inventory items  39
```

The first eight structural values are checked directly against the artifact
bytes at every verification. The dependency-inventory count is a provenance fact
of the pinned source commit rather than a property of the artifact bytes, so it
is pinned and reported by the verify-only mode and proven only by the pinned
reconstruction below. It is never recomputed from current registry state:
verification reads the artifact and nothing else, so it stays correct as the
live registry changes.

**Reconstruction.** Git history plus the isolated candidate mode already
reproduce the artifact byte for byte, which is why no duplicate frozen registry
is kept. Reconstruct from the pinned source commit with clean temporary
directories:

```bash
git archive 3219fa03149b4bf1a229f059b4912b632028422b | (mkdir -p /tmp/mwe-src && tar -x -C /tmp/mwe-src)
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_public_surface_authority_map.py \
  --source-root /tmp/mwe-src \
  --output /tmp/mwe-out/data.json \
  --inventory-output /tmp/mwe-out/inventory.json
# expect: 92903 bytes, sha256 3b1e5993…, blob 2d59c4fd…, 30 nodes, 161 edges, 39 inventory deps
```

The reconstruction reads the pinned source commit, never the live registry and
never current `main`.

This section records generator behaviour and artifact identity only. It makes no
classification, relation, Registry-status, visualization-membership or
public/private determination.
