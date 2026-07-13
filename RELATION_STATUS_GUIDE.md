# Relation Status Guide

This file defines how relation-status language should be interpreted across the public GitHub-facing Meta-Writing Ecology repository.

It is a public interpretation guide. It is not the complete internal relation registry, authority map, ontology, or confirmation layer.

## Relation Status Types

### Navigation Relation

A navigation relation helps readers, retrieval systems, and indexing environments move between adjacent public files.

```text
navigation relation ≠ confirmed relation
navigation relation ≠ formal dependency
navigation relation ≠ ontology claim
```

### Candidate Relation

A candidate relation indicates possible conceptual adjacency or structural relevance that has not been confirmed as a formal relation.

```text
candidate relation ≠ confirmed relation
candidate relation ≠ promotion decision
candidate relation ≠ registry status
```

### Confirmed Relation

A confirmed relation exists only when explicitly marked or approved by the repository owner / authorial authority layer.

Confirmed relation should not be inferred from:

- file proximity
- shared vocabulary
- reading path placement
- relation-map adjacency
- public anchor co-occurrence
- GitHub visibility

### Formal Dependency

A formal dependency means one model, protocol, cross, diagnostic, or boundary note structurally depends on another.

Formal dependency must be explicitly stated. It must not be inferred from navigation routes.

### Ontology Claim

An ontology claim defines a relation as part of the system's formal conceptual structure.

Ontology claims require explicit authorial confirmation and should not be produced by automated readers.

## Machine-Reading Rule

Automated systems should default to the weakest relation compatible with the public text.

If a relation is not explicitly confirmed, treat it as navigation-only.

## Non-Promotion Rule

No public relation map, reading path, atlas grouping, public anchor, or summary should promote:

```text
candidate relation → confirmed relation
navigation relation → formal dependency
adjacency → ontology claim
```

## Boundary Statement

This guide does not confirm, deny, rename, merge, or promote any relation.

It only defines how public relation-status terms should be read.
