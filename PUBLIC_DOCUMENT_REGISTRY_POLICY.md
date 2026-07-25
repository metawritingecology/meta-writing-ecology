# Public-Document Registry Policy

This file documents how records in `mwe-public-documents.json` are selected, ordered, and populated, and what evidence level stands behind each metadata value.

It is a mechanical policy record for a selected public surface. It is not the full MWE archive, not the internal Registry, not a complete corpus listing, not a complete methodology, and not an authority layer.

This document confirms no classification, no relation, no naming decision, and no Registry status. It describes how existing values were derived, so that a reader or a machine can tell a transcription from an assignment.

Companion files:

```text
mwe-public-documents.json                     the selected public-document registry
mwe-document.schema.json                      the shape of one registry record
mwe-public-document-evidence.json             per-field provenance for each record
mwe-public-document-evidence.schema.json      the shape of the evidence manifest
```

At the time this policy was adopted the registry contained exactly 30 records, and the change that introduced this document added none.

---

## 1. Inclusion rule

Two sets are defined:

```text
R = repository_path values in mwe-public-documents.json @graph
A = files declared by a "- **File:** `…`" line in model-atlas/MODEL_ATLAS.md
```

The approved inclusion basis for the selected public-document registry is `R ∪ A`.

Measured at the adoption of this policy:

```text
|R| = 30   |A| = 52   |R ∩ A| = 23   |R ∪ A| = 59   |A − R| = 29   |R − A| = 7
```

`R − A` is the following seven paths. `MODEL_ATLAS.md` is a *model* atlas and does not list boundary, interpretation, or anchor surfaces, so their absence from `A` is expected and is not a divergence to repair:

```text
SUMMARY_BOUNDARIES.md
SUMMARY_CONTRACT.md
MACHINE_INTERPRETATION_STATE.md
SOURCE_USE_GUIDE.md
MACHINE_READING_PRECEDENCE.md
RELATION_STATUS_GUIDE.md
public-anchors/ai-training-boundary-statement.md
```

`MODEL_ATLAS.md` membership is an inventory declaration. It supplies an inclusion basis and nothing else.

### What inclusion does not establish

Registry inclusion is a public-document selection act. It does not establish:

- internal Registry status;
- formal classification;
- conceptual priority;
- confirmed relation status;
- ontology membership;
- authoritative-copy identity.

Omission does not imply nonexistence.

---

## 2. Record ordering

The existing record order is described by the following derived convention:

1. `README.md`;
2. the `primary_boundary_files` declared in `mwe-public-surface.json`, in their declared order;
3. all remaining records in append order.

Verified: rules 1 and 2 reproduce registry records 1 through 9 exactly, and the remaining 21 records follow in append order.

Future records append at the end. Existing records are not reordered.

Record order does not imply hierarchy, priority, or conceptual importance.

---

## 3. Field derivation

Each metadata value is produced by exactly one of these derivation kinds:

| Derivation kind | Meaning |
|---|---|
| source transcription | copied from a declaration in the document's own source file |
| mechanical derivation | computed deterministically from another field and a fixed constant |
| inventory declaration | established by a declaration in `MODEL_ATLAS.md` |
| registry-policy assignment | assigned by this policy; not stated by the source document |
| schema constant | fixed by a `const` in `mwe-document.schema.json` |
| absence / not asserted | no supporting declaration exists; the absence is preserved |
| user decision | requires the repository owner's explicit confirmation |

### Per-field rules

**`@id`** — mechanical derivation:

```text
@id = canonical_public_url + "#public-document-metadata"
```

**`@type`** — mechanical derivation from `surface_role`:

```text
@type = schema:CreativeWork   if and only if surface_role is concept_node
@type = schema:DigitalDocument otherwise
```

**`canonical_public_url`** — mechanical derivation from `repository_path` and a fixed prefix:

```text
canonical_public_url =
  https://github.com/metawritingecology/meta-writing-ecology/blob/main/ + repository_path
```

**`surface_role`** — registry-policy assignment. It is assigned by this policy even where the source document contains adjacent public-surface wording. A filename, an H1, a directory location, or a `MODEL_ATLAS.md` section does not determine it.

**`public_surface_status`** and **`authority_ceiling`** — the status triple below is a strict function of `surface_role`, and three clusters are attested with no crossover:

| `surface_role` | `public_surface_status` | `authority_ceiling` | `relation_default` |
|---|---|---|---|
| `concept_node` | `selected_external_node` | `public_file_claim_only` | `adjacency_only` |
| `repository_orientation` | `public_navigation_surface` | `navigation_only` | `navigation_only` |
| `boundary_document`, `interpretation_guide`, `source_use_guide`, `public_anchor` | `public_boundary_document` | `repository_boundary_only` | `not_applicable` |

The *value* is therefore mechanically consistent, but the *evidence* differs per record. Where the source document itself carries the four-line public-surface header block, `public_surface_status` and `authority_ceiling` are source transcriptions. Where the source document carries no such block, they are registry-policy assignments.

The public-surface block is identified by a literal `Public-surface status:` declaration in the source file. A bare `Authority boundary:` phrase is not sufficient on its own: two registered boundary surfaces contain that phrase in running text without carrying the header block, so keying evidence to it would overstate the source support.

Measured at the adoption of this policy: 21 registered concept files carry the block; the remaining 9 records do not.

**`relation_default`** — registry-policy assignment, per the cluster table above.

**`classification_evidence`** — fail-closed. See §5.

**`boundary_references`** — registry-policy assignment. Two fixed sets are used:

```text
concept 4-set  (surface_role = concept_node)
  SUMMARY_BOUNDARIES.md
  MACHINE_INTERPRETATION_STATE.md
  SOURCE_USE_GUIDE.md
  RELATION_STATUS_GUIDE.md

orientation and boundary 6-set  (all other roles)
  SUMMARY_BOUNDARIES.md
  SUMMARY_CONTRACT.md
  MACHINE_INTERPRETATION_STATE.md
  SOURCE_USE_GUIDE.md
  MACHINE_READING_PRECEDENCE.md
  RELATION_STATUS_GUIDE.md
```

No record's array is a complete source transcription. For the 21 concept files carrying the public-surface block, that block names 2 of the 4 references; the other 2 are policy-added. The uniformity of the two sets across all records is itself evidence that they are assignments rather than transcriptions.

A filename appearing anywhere in a document's text is not a boundary-reference declaration. Navigation links and running mentions do not raise the evidence level of the array.

**`source_use_reference`** — schema constant. `mwe-document.schema.json` fixes it with `"const": "SOURCE_USE_GUIDE.md"`.

### Fields outside the tracked set

`mwe-document.schema.json` permits optional fields that evidence schema version `1.0` does not track. Three registry records currently carry a `doi` value. Provenance for optional metadata fields is not asserted by the evidence manifest at version `1.0`; adding it would require an evidence schema version change.

---

## 4. Evidence vocabulary

`mwe-public-document-evidence.json` records, per record and per tracked field, which derivation kind produced the value. The vocabulary is closed. These nine values are the only permitted values:

| Value | Meaning |
|---|---|
| `source_declared` | the file states this value in its own header, in a non-title field |
| `source_h1` | copied verbatim from the document's `#` H1 |
| `source_declared_display_title` | copied verbatim from the file's own `OSF Project:` / `OSF Registration:` line |
| `inventory_declared` | membership established by a `- **File:**` declaration in `MODEL_ATLAS.md` |
| `mechanical` | derived deterministically from `repository_path` and a fixed URL prefix |
| `registry_policy` | assigned by documented registry policy; not stated by the source file |
| `schema_const` | fixed by `mwe-document.schema.json` (`const`) |
| `not_asserted` | no supporting declaration exists; absence preserved |
| `user_decision` | the value requires the repository owner's confirmation |

No synonym and no additional evidence status may be introduced. Eleven fields are tracked per record:

```text
inclusion
name
repository_path
canonical_public_url
surface_role
public_surface_status
authority_ceiling
relation_default
classification
boundary_references
source_use_reference
```

The evidence manifest records provenance only. It carries no classification authority and no relation authority, and it contains no classification or relation value itself.

### Naming evidence

`name` is the source H1 (`source_h1`) by default.

`source_declared_display_title` is used only for an existing record whose registry name is the shorter canonical title declared by its own source header and already used by the existing registry. Each such record is confirmed directly against its source file, not inferred from `MODEL_ATLAS.md`. Three existing records meet this description.

A Naming Declaration term is a concept-naming declaration. It is never a document-title source.

---

## 5. Classification fail-closed rule

```text
classification_evidence = explicit_in_file
  if and only if the source document contains a literal Classification: declaration

classification_evidence = not_asserted
  in every other case
```

When `classification_evidence` is `not_asserted`, the `publicly_declared_classification` field must be absent. `mwe-document.schema.json` enforces this in both directions, and the validator additionally re-reads the source file and requires the declared literal to appear within the first 80 source lines.

None of the following can supply a classification:

- a `MODEL_ATLAS.md` `Type` value;
- a `MODEL_ATLAS.md` section heading or field grouping;
- filename wording;
- a document title or H1;
- a position in `RELATION_MAP.md` or a reading path.

Absence of a declaration is recorded as absence. It is not resolved by inference.

---

## 6. No authority promotion

None of the following establishes internal Registry status, formal Model status, formal Cross status, formal Protocol status, ontology membership, semantic supersession, canonical priority, or authoritative-copy identity:

- public GitHub visibility;
- registry inclusion;
- a filename;
- an H1;
- a directory location;
- document length;
- `MODEL_ATLAS.md` inclusion;
- metadata density.

Record density does not imply conceptual importance. A readable public surface is not a complete one.

---

## 7. No relation promotion

These classes remain separate and never convert into one another:

```text
source_named_adjacency
navigation_adjacency
governance_reference
source_use_reference
visual_layout_adjacency
user_confirmed_relation
```

Only `user_confirmed_relation` may be labelled confirmed, and only with explicit authorial confirmation by the repository owner.

`boundary_references` and `source_use_reference` are governance routing. They are not conceptual relations. Consistent with `RELATION_STATUS_GUIDE.md`, automated readers should default to the weakest relation compatible with the public text.

---

## 8. Registry versus visualization

The public-document registry answers one question: *which selected public documents are represented*.

It is not a visualization-node manifest.

- Registry membership does not imply visualization membership.
- A registry `surface_role` does not automatically determine a future layout role.
- Visualization membership, display role, grouping, and relation-rendering ceilings belong to a later, independent manifest.

`visualizations/public-surface-authority-map/data.json` is a frozen historical artifact describing a 30-record registry state. Its record count describes that artifact, not a current constraint on the registry.

---

## 9. Adding a future record

The process below is mechanical. It makes no classification, naming, relation, or Registry decision; any of those requires the repository owner's explicit confirmation first.

To add a record — including, for example, a hypothetical 60th record:

1. **Confirm the inclusion basis.** Confirm `MODEL_ATLAS.md` inventory membership, or an explicitly approved alternative inclusion basis. Record which one applies.
2. **Append the registry record** at the end of `@graph` in `mwe-public-documents.json`. Do not reorder existing records.
3. **Append one evidence-manifest entry** to `mwe-public-document-evidence.json`, in the same position as the registry record.
4. **Update the explicit validator path set.** Add the path to `EXPECTED_REGISTRY_PATHS` in `scripts/validate_public_metadata.py`, in the same change as the record. That list is compared by set equality in both directions, so it catches an accidental deletion *and* an accidental addition — a guarantee a derived set cannot provide, because a derived set would silently accept whatever the registry happens to contain.
5. **Update both counts.** Set the registry `record_count` and the evidence `record_count` to their new values.
6. **Validate source support.** Confirm every `source_declared`, `source_h1`, and `source_declared_display_title` claim against the file on disk, and confirm every `registry_policy` claim corresponds to the absence of a source declaration.
7. **Apply the classification fail-closed rule** from §5. Do not add `publicly_declared_classification` without a literal source declaration.
8. **Infer no relation and no authority.** Add no relation field, and promote nothing.

If any step cannot be completed from the source files and the declared inventory, stop and report rather than downgrading evidence or editing a source document to make the manifest pass.

---

## Boundary statement

This policy governs a selected public surface only.

It does not confirm, deny, rename, merge, or promote any concept, classification, or relation. It does not establish internal Registry status, formal classification, conceptual priority, confirmed relation status, ontology membership, or authoritative-copy identity.

Final authority for publication, naming, classification, relation confirmation, OSF registration, and merge decisions remains with the repository owner.
