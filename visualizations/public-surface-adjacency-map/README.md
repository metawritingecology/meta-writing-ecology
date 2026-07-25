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
| `source_named_adjacency` | Source-declared adjacency | yes | **on** | the source document's own adjacency section |
| `navigation_adjacency` | Provisional navigation adjacency | yes | **off** | `model-atlas/RELATION_MAP.md` |

Both classes are kept separate and are never merged. Direction is preserved
exactly as written; no reciprocity is inferred and no reverse edge is
manufactured. Identical directed pairs occurring in both classes remain two
distinct edges — deduplication happens only within a class, never across
classes. Enabling the navigation layer changes no node position.

Only concept-to-concept edges are rendered. An edge whose endpoint cannot be
mapped to exactly one of the 59 registry paths by an explicitly written path is
rejected rather than guessed.

### Counts at the pinned source

| edge class | raw directed | retained concept-to-concept | excluded, non-concept endpoint |
|---|---|---|---|
| `source_named_adjacency` | 180 | 180 | 0 |
| `navigation_adjacency` | 201 | 194 | 7 |

Source-declared adjacency is extracted only from the declared adjacency syntax:
a top-level list item inside the document's own
`## Relationship to Adjacent Models` / `## Relationship to Adjacent Public
Frameworks` section whose leading element is a Markdown link carrying an
explicit repository-relative path. Ordinary prose, inline links, plain-text
names, fenced comparison blocks, Related Node Index text, boundary references,
source-use links, DOI links, shared vocabulary, and filenames are never treated
as adjacency, because none of them declares a path resolvable without guessing.
Of the 28 registered and unregistered files carrying an adjacency heading, 18
registered documents declare adjacency in that syntax.

### Relation-evidence ceiling

Each record records the strongest approved **display evidence** available for
it. This is not a classification, hierarchy, confirmed relation, priority order,
or ontology statement.

| ceiling | records |
|---|---|
| `source_named_adjacency` | 18 |
| `navigation_adjacency` | 31 |
| `none` | 10 |

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
| byte length | 202303 |
| SHA-256 | `370cde8431641a4d5118e72379564deea0012cef42e49cf6542d319c8f46da69` |
| Git blob | `161501533c2378a24aac666252577974fdee9acc` |
| nodes | 59 |
| edges | 374 (180 source-declared + 194 navigation) |

`visualization-manifest.json`

| property | value |
|---|---|
| byte length | 18550 |
| SHA-256 | `b1db120e3bbaef0d35ff95fa79de3231f9b4f8f183b2a60b7f8729c459112d12` |
| Git blob | `1ce71b0abd2e8485cf807db0a9ba0898b1f23e55` |
| records | 59, exactly 1:1 with the registry, in registry order |

The dataset carries no generated timestamp: a timestamp would make generation
nondeterministic.

### Consumer ceiling

Consumers may assume a ceiling of **262144 bytes**. The tracked dataset is
202303 bytes, within that ceiling. The generator refuses to write a dataset
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

Generation is deterministic: repeated runs from the same source produce
byte-identical output. The generator refuses any `--output` that resolves to or
aliases the frozen historical artifact, and that check runs before any registry
read, edge processing, parent-directory creation, or write.

## Files

- `data.json` — the expanded adjacency dataset
- `visualization-manifest.json` — independent visualization membership and rendering policy
- `visualization-manifest.schema.json` — JSON Schema (Draft 2020-12) for the manifest
- `README.md` — this file
