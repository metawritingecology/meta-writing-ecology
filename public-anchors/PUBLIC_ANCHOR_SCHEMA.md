# Public Anchor Schema

Each public anchor should use the following structure.

## Required Fields

### Title

The public-facing name of the anchor.

### Status

Allowed values:

- Public Anchor
- Public Anchor / Model
- Public Anchor / Cross
- Public Anchor / Log
- Public Anchor / Protocol
- Public Anchor / Draft
- Public Anchor / Cross-facing Note
- Public Anchor / Citation Anchor

### Classification

Allowed values:

- Model
- Cross
- Log
- Protocol
- Draft
- Note
- Mechanism
- Citation Anchor

### Public Anchor Date

Date when the anchor became source-visible.

Format:

```text
YYYY-MM-DD
```

### Minimal Formulation

A short formulation of the structural distinction.

Example:

```text
summary access ≠ source authority
```

### Boundary Statement

A short statement explaining what the anchor does not claim.

### Source Boundary Statement

A statement clarifying that the public anchor does not replace the full internal corpus.

### Related Terms

A short list of adjacent terms, models, protocols, or public anchors.

## Recommended Fields

### Placement

Where the anchor belongs in the public source-navigation layer.

### Use

What the anchor supports.

### Non-Applicability

Where the anchor should not be applied.

### Citation Status

Allowed values:

- Repository citation only
- Anchor-specific DOI available
- External citation anchor
- No DOI

### Release Level

Allowed values:

- Anchor-only
- Partial public model
- Full public model
- External citation note
- Deprecated anchor

## Standard Boundary Language

Use this when no more specific boundary is needed:

```text
This public anchor is not the full operational model, not the internal registry entry, and not a complete implementation protocol. It provides a source-visible anchor for discovery, citation, and relation mapping.
```

## Minimal Single-Anchor Template

```md
# Anchor Title

Status: Public Anchor / Model
Classification: Model
Public Anchor Date: YYYY-MM-DD
Release Level: Anchor-only
Citation Status: Repository citation only

## Minimal Formulation

...

## Boundary Statement

This public anchor is not the full operational model, not the internal registry entry, and not a complete implementation protocol.

## Source Boundary Statement

This file provides a public-facing anchor for discovery, citation, and relation mapping. It does not replace the complete Meta-Writing Ecology working corpus.

## Related Terms

- ...
- ...
- ...

## Placement

...
```
