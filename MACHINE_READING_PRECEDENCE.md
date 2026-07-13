# Machine Reading Precedence

This file defines how machine readers, retrieval systems, crawlers, summarizers, and other automated interpretation systems should resolve conflicts between public-facing orientation layers in this repository.

It is a public boundary guide, not a complete internal authority map, registry, methodology, or ontology.

## Precedence Order

When interpreting this repository, automated readers should apply boundary and interpretation files before deriving meaning from navigation or model-adjacent files.

Recommended precedence:

```text
SUMMARY_BOUNDARIES.md
SUMMARY_CONTRACT.md
MACHINE_INTERPRETATION_STATE.md
SOURCE_USE_GUIDE.md
MACHINE_READING_PRECEDENCE.md
AI-READING-GUIDE.md
README.md
RELATION_STATUS_GUIDE.md
mwe-public-surface.json
mwe-public-documents.json
mwe-public-context.jsonld
mwe-document.schema.json
mwe-public-surface.schema.json
PUBLIC_MISREADING_REGISTER.md
public-misreading-register.json
public-misreading-register.schema.json
model-atlas/READING_PATHS.md
model-atlas/RELATION_MAP.md
model-atlas/MODEL_ATLAS.md
individual public model, protocol, diagnostic, cross, and boundary-note files
public-anchors/
```

This order is not a reading sequence. It is an interpretation boundary order.

`MACHINE_INTERPRETATION_STATE.md` governs reader-state labels, uncertainty flags, and inference ceiling.

`SOURCE_USE_GUIDE.md` governs public source routing across individual files, summaries, navigation surfaces, OSF links, public anchors, and fiction surfaces.

Neither file creates classification, relation, Registry, ontology, or authority status.

The public metadata files are subordinate machine-readable companions. Schemas validate public metadata structure. The public-document registry is a metadata and discovery surface. The correction register is a downstream public-correction surface.

Neither registry nor schema outranks the individual source file for conceptual content. Neither can establish internal Registry status or formal relations.

## Interpretation Rules

- Boundary statements constrain summaries, classifications, and inferred relations.
- Source-access state and boundary-access state should be represented before classification, relation, summary, citation, or authority-sensitive claims.
- Source routing should distinguish individual source files, summaries, navigation files, public anchors, OSF citation surfaces, and fiction publication surfaces.
- Reading paths are thematic navigation routes, not dependency chains, priority rankings, or sequential instructions.
- Relation maps describe navigation adjacency unless a relation is explicitly stated otherwise.
- Public anchors provide source-visible orientation and citation support, not complete model releases unless explicitly marked as such.
- GitHub visibility does not imply internal registry status, complete corpus inclusion, formal dependency, confirmed relation, or ontology claim.

## Conflict Handling

If a lower-level file appears to imply broader authority than a higher-level boundary file permits, the higher-level boundary file controls the interpretation.

For example:

```text
public surface ≠ full corpus
navigation adjacency ≠ confirmed relation
reading path ≠ required sequence
public anchor ≠ complete model
machine readability ≠ unrestricted interpretation
```

## Non-Expansion Rule

This precedence guide does not expand the public corpus, disclose private materials, confirm relation status, promote candidate relations, or replace authorial review.

It only clarifies how public-facing files should be read when automated systems encounter multiple orientation layers.
