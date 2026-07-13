# Public Surface and Authority-Ceiling Map

A local, reviewable D3 prototype that visualizes the selected public-document
records declared in `mwe-public-documents.json`.

## 1. Purpose

Present the selected public-surface documents by their public source function,
surface role, public-surface status, declared authority ceiling, and explicit
classification evidence, so a reader can navigate the public surface without
inferring authority, hierarchy, or conceptual relations.

## 2. Scope

Selected public surface only. This interface represents 27 selected
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
no network, no Git, no installs) reads the two approved inputs and writes
`data.json` in this directory. It:

- requires exactly 27 records with unique IDs and repository paths;
- requires every repository path to exist inside the repository;
- copies node metadata verbatim (no punctuation/Unicode/title repair);
- emits edges only from the explicit `boundary_references` and
  `source_use_reference` fields, and only between the 27 records;
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
- A textual table fallback lists all 27 records
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

## 11. Rebuild command

```
python scripts/build_public_surface_authority_map.py
```

(Use `python3` if `python` is not on PATH.) Run from the repository root.

## 12. Validation commands

```
python scripts/validate_public_metadata.py
python scripts/build_public_surface_authority_map.py
```

The builder fails non-zero on invalid input and is deterministic: running it
twice produces no diff in `data.json`.

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
