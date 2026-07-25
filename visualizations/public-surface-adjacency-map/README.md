# Public Surface Adjacency Map — expanded dataset

This directory contains a **separate expanded visualization product** for the
GitHub-visible public surface of Meta-Writing Ecology.

It does **not** replace, supersede, correct, or deprecate the frozen 30-node
product in `visualizations/public-surface-authority-map/`. That artifact remains
immutable and independently verifiable. The two products describe different
selections at different times and stand side by side.

This dataset is prepared data only. No page publication has occurred, and the
website route for this product remains undecided and outside the scope of this
phase.

## Boundary statements

Selected public surface only. This directory does not represent the full MWE
archive, backend corpus, complete registry, complete methodology, or authority
layer. If a public surface is readable, it must not be treated as complete.

MODEL_ATLAS field grouping is a navigation grouping.
It is not a formal classification, ontology, hierarchy, priority order,
confirmed relation, or internal Registry assignment.

Neither rendered edge class is a confirmed relation. Source-declared adjacency
is adjacency as written in the source document. Provisional navigation adjacency
is a navigation surface drawn from `RELATION_MAP.md`. Neither establishes a
confirmed relation, formal dependency, or ontology claim.

Visual position, band placement, and record order do not indicate conceptual
importance, priority, or internal authority. Omission does not imply
nonexistence.

## Two separate contracts

Registry selection and visualization membership are **separate contracts**.

- `mwe-public-documents.json` is the public-document registry. It decides which
  documents are registered.
- `visualization-manifest.json` is an independent visualization manifest. It
  decides visualization membership and rendering policy only.

The manifest is not embedded into the registry and does not extend the registry
contract. Its authority ceiling is
`visualization_membership_and_rendering_policy_only`. Visualization membership
does not imply Registry status, and visualization role does not imply
classification.

## Membership and roles

All 59 registered records are represented in this product
(`visualization_membership = included`; no record is `excluded` or `pending`).

| visualization role | records | rendering |
|---|---|---|
| concept | 49 | semantic graph layout |
| orientation | 2 | fixed orientation band |
| boundary | 7 | fixed boundary band |
| anchor | 1 | fixed boundary band, role retained as `anchor` |

Representation is not layout participation. Only the 49 concept records enter
the semantic graph layout. The 10 non-concept records remain selectable and
readable, but they create no semantic edges, receive no semantic rank or
centrality, and do not affect concept positioning. Their inclusion does not
imply concept status.

Displayed labels equal the registry `name` byte-for-byte
(`display_label_source = registry_name`). Labels are not derived from filenames,
MODEL_ATLAS headings, Naming Declarations, DOI titles, or shortened forms.

Concept records group by MODEL_ATLAS navigation field; non-concept records group
by visualization role. Each concept resolves to exactly one field, read from the
entry's own declared `- **File:**` line under its `##` field heading.

## Edge classes

| edge class | display label | directed | default visible | evidence source |
|---|---|---|---|---|
| `source_named_adjacency` | Source-declared adjacency | yes | **on** | internal registered Markdown document links inside the source document's formal adjacency section |
| `navigation_adjacency` | Provisional navigation adjacency | yes | **off** | `model-atlas/RELATION_MAP.md` |

Both classes are kept separate and are never merged. Direction is preserved
exactly as written; no reciprocity is inferred and no reverse edge is
manufactured. Identical directed pairs occurring in both classes remain two
distinct edges — deduplication happens only within a class, never across
classes. Enabling the navigation layer changes no node position.

Only concept-to-concept edges are rendered. An edge whose endpoint cannot be
mapped to exactly one of the 59 registry paths by an explicitly written path is
rejected rather than guessed.

Each edge carries `relation_status` (the evidence class itself) and
`authority_ceiling` (always `navigation_only`). Neither field promotes adjacency
into a formal or confirmed relation, and no edge ever carries a confirmed
status.

### Counts at the pinned source

| edge class | raw unique directed | retained concept-to-concept | excluded, non-concept endpoint |
|---|---|---|---|
| `source_named_adjacency` | 189 | 189 | 0 |
| `navigation_adjacency` | 201 | 194 | 7 |

`source_named_adjacency` includes only internal registered Markdown
document links written inside a formal adjacency section.

Bare conceptual names and prose are human-readable adjacency discussion,
but are not converted into machine edges without a separate authorial
alias or relation mapping.

This is a machine-readable edge contract. Every Markdown link inside the formal
section counts, wherever it appears — at the start of a bullet, later in a
bullet, in a sentence, in a table row, or inside a fenced block. Only the href
is resolved; the visible link label is never used to identify a target, so no
edge depends on a human-readable concept name.

Bare concept names, plain-text bullets, fenced comparison-block labels,
descriptive prose, and `=` definitions create no edge **and are not treated as
unresolved candidates**. Their omission from the graph is a limit of what P5
encodes mechanically. It is not a statement that the relation does not exist.

External URLs, DOI links, OSF links, fragment-only anchors, and non-Markdown
targets are ignored and never fail the build. A link that does look like an
internal repository-relative Markdown document reference but escapes the
repository, resolves to nothing, or lands outside the 59-record registry fails
closed with `EXPANDED_SOURCE_ADJACENCY_UNRESOLVED`.

Source-link declaration audit at the pinned source:

| measure | count |
|---|---|
| documents with a formal adjacency section | 28 |
| documents with more than one formal section | 0 |
| Markdown links found inside those sections | 190 |
| accepted internal registered link declarations | 190 |
| ignored external / fragment / non-document links | 0 |
| self-references omitted | 0 |
| same-section repeated evidence occurrences | 1 |
| unresolved internal Markdown links | 0 |
| unique source-named directed edges | 189 |

**Same-section evidence consolidation.** When one document names the same target
more than once inside its single formal adjacency section — for example once in
explanatory prose and once in the structured list — those are two evidence
occurrences for one adjacency, not two semantic edges. They consolidate into one
directed edge, and every evidence line is retained in the generation audit. At
the pinned source this occurs exactly once, in
`responsibility-alignment-diagnostics.md` at lines 446 and 450, both resolving to
`responsibility-alignment-model.md`.

Consolidation applies only within one document's single formal section, for the
same resolved target and the same edge class. Everything else still fails closed
with `EXPANDED_DUPLICATE_DIRECTED_EDGE`: a duplicate `navigation_adjacency` pair
in `RELATION_MAP.md`, a document carrying more than one formal adjacency
section, and any duplicate that cannot be safely attributed to repeated evidence
for one edge.

### Relation-evidence ceiling

Each record records the strongest approved **display evidence** available for
it. This is not a classification, hierarchy, confirmed relation, priority order,
or ontology statement.

| ceiling | records |
|---|---|
| `source_named_adjacency` | 20 |
| `navigation_adjacency` | 29 |
| `none` | 10 |

The source-named ceiling is computed from accepted, non-self Markdown-link
declarations **before** non-concept rendering filtration, so a record keeps its
source-level evidence even when its valid targets are filtered out of the
rendered graph. A formal adjacency section written only in bare conceptual names
carries no machine-readable link and so does not by itself establish a
source-named ceiling.

## Governance and source-use references

Governance references and source-use references are recorded in the document
registry and are stated here at product level only. In this release they are
**not** rendered: there is no governance edge, no source-use edge, no governance
toggle, and no governance overlay. They contribute nothing to layout, degree, or
any metric. Nothing in the registry's `boundary_references` is weakened,
removed, or reinterpreted by this product.

No user-confirmed relations are authorized in this release, and none appear.
`user_confirmed_relation` is the only class that could ever be described as
confirmed, and it is empty.

## Dataset identity

Generated from pinned source commit
`933274af9693d6d1d9fac36819aafdf56f9ab81d`.

`data.json`

| property | value |
|---|---|
| byte length | 206617 |
| SHA-256 | `0b763eb78fea5c53364609ecc5d7019422c54b950d32f29f79ad37f24f1637b7` |
| Git blob | `3077568edeeb0d6a769899a1a3cf79c3f9152f83` |
| nodes | 59 |
| edges | 383 (189 source-declared + 194 navigation) |

`visualization-manifest.json`

| property | value |
|---|---|
| byte length | 18554 |
| SHA-256 | `b6ea211e265631b984f0e9ea53fb7301f3fd0986dbdaa2a9d349c0524591d0fe` |
| Git blob | `159ac950abf2172bcdd2cc420afde63578140eb8` |
| records | 59, exactly 1:1 with the registry, in registry order |

The dataset carries no generated timestamp: a timestamp would make generation
nondeterministic.

### Consumer ceiling

Consumers may assume a ceiling of **262144 bytes**. The tracked dataset is
206617 bytes, within that ceiling. The generator refuses to write a dataset
above it.

## Deterministic reconstruction

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/build_public_surface_authority_map.py \
  --target expanded \
  --visualization-manifest \
    visualizations/public-surface-adjacency-map/visualization-manifest.json \
  --output \
    visualizations/public-surface-adjacency-map/data.json
```

The manifest is validated in production against its tracked JSON Schema
(Draft 2020-12, resolved relative to the manifest file) before any dataset is
built; any contract failure stops the run with
`EXPANDED_VISUALIZATION_MANIFEST_INVALID` and writes nothing. Unreadable,
missing, non-regular, path-escaping or non-UTF-8 source inputs fail closed with
`EXPANDED_SOURCE_INPUT_UNREADABLE`.

Expanded generation enumerates its own dependency provenance in memory: **64**
dependencies with aggregate SHA-256
`a89f1aefd341778f89e7b1e810ed760ddb7de7ff30564bda93fdaeb7a451918f`, covering the
registry, the visualization manifest and its schema, `MODEL_ATLAS.md`,
`RELATION_MAP.md`, and every registered source document audited for adjacency. A
test proves bidirectional equality between the enumerated inventory and the
files actually read. No tracked dependency-inventory file is written, and the
pinned 39-entry historical reconstruction is untouched.

Generation is deterministic: repeated runs from the same source produce
byte-identical output. The generator refuses any `--output` that resolves to or
aliases the frozen historical artifact, and that check runs before any registry
read, edge processing, parent-directory creation, or write.

## Files

- `data.json` — the expanded adjacency dataset
- `visualization-manifest.json` — independent visualization membership and rendering policy
- `visualization-manifest.schema.json` — JSON Schema (Draft 2020-12) for the manifest
- `README.md` — this file
