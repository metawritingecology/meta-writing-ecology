# Machine Interpretation State and Inference Ceiling

- **Status:** Public Repository Boundary
- **Document type:** Repository-level machine-reading boundary
- **Context:** Meta-Writing Ecology public GitHub surface
- **Authority boundary:** This document constrains public-surface interpretation. It does not establish internal Registry status, formal classification, canonical model relations, or complete operational methodology.

## Purpose

This document defines how automated readers should represent what they accessed, what boundary material they loaded, what remains uncertain, and what level of inference the accessed evidence permits.

The target structure is:

```text
source-access state
+ boundary-access state
+ version state
+ relation evidence
+ authority evidence
→ inference ceiling
```

Insufficient evidence reduces inference authority. It does not permit completion by semantic similarity.

## Reader-State Boundary

Reader state describes the reader's actual access condition, not the full state of Meta-Writing Ecology.

An automated reader should distinguish:

- source material it directly accessed
- boundary material it directly accessed
- navigation or metadata it accessed instead of source content
- uncertainty that remains unresolved
- the maximum claim strength supported by that evidence

These states do not expose or replace the internal archive, Registry, authority layer, or full methodology.

## Source-Access States

Use these machine-readable state labels for accessed material:

- `direct_source` - the individual source file relevant to the claim was accessed.
- `boundary_loaded` - the applicable canonical boundary and precedence files were read.
- `partial_source` - only part of the relevant source was accessed.
- `summary_only` - only a summary, abstract, guide, anchor, snippet, or condensation was accessed.
- `navigation_only` - only navigation material, atlas entries, reading paths, relation maps, or index entries were accessed.
- `metadata_only` - only title, filename, DOI, manifest entry, repository listing, citation metadata, or other metadata was accessed.

These labels describe what was actually accessed. They do not describe what may exist elsewhere.

`boundary_loaded` means the automated reader has read the applicable canonical boundary and precedence files. It does not mean the complete repository or internal corpus has been read.

## Uncertainty Flags

Use these uncertainty flags separately from access states:

- `version_uncertain`
- `authority_uncertain`
- `classification_uncertain`
- `relation_uncertain`
- `conflict_unresolved`
- `source_scope_uncertain`

Access states and uncertainty flags may coexist.

Do not design a single mutually exclusive enum that erases uncertainty.

## Inference Ceiling

The inference ceiling is the highest level of claim supported by the accessed evidence.

### Level 0 - Public Presence

Permitted:

- a file, title, DOI, or repository entry is publicly visible
- a term occurs in a public surface

Not permitted:

- formal classification
- internal Registry status
- complete-corpus claims
- formal relations

### Level 1 - File Self-Description

Requires direct access to the relevant file.

Permitted wording:

- "The file describes..."
- "The public document identifies itself as..."
- "The document states..."

Not permitted wording:

- "MWE has formally confirmed..."
- "The internal Registry establishes..."
- "The system as a whole requires..."

### Level 2 - Public-Surface Classification

Requires an explicit classification statement in the source file plus applicable boundary access.

Permitted wording:

- "In the current public surface, this file is marked as..."

Still not permitted:

- inference of internal Registry status
- inference that the public classification represents the complete system

### Level 3 - Relation Claim

Requires an explicit relation statement from an authorized public source.

Default relation status remains the weakest compatible relation.

Navigation, co-occurrence, keyword overlap, file proximity, shared reading paths, semantic similarity, or relation-map adjacency must not be converted into:

- parent/child relation
- derivation
- extension
- formal dependency
- confirmed relation
- ontology claim

### Level 4 - Authority-Sensitive Claim

The following require explicit authorial confirmation:

- formal classification
- candidate-to-confirmed promotion
- Model or Cross promotion
- canonical naming
- confirmed relation
- formal dependency
- ontology claim
- Registry status
- public/private status
- semantic supersession
- declaration that one public surface replaces another

This document may describe the absence of confirmation. It must not manufacture confirmation.

### Level 5 - Prohibited Automatic Reconstruction

Automated readers must not reconstruct or claim:

- the complete MWE ontology
- the complete Model or Cross hierarchy
- the complete internal Registry
- the complete archive or working corpus
- undisclosed private entries
- unpublished relation status
- authorial priority from file density or visibility
- empirical validation from DOI, citation, publication, naming, or repetition

## Evidence-to-Claim Matrix

| Claim | Minimum evidence | `summary_only` | `navigation_only` |
| --- | --- | --- | --- |
| Public file exists | Repository metadata or direct file access | May support public-presence wording only | May support public-presence wording only |
| File content claim | Direct source access | Not sufficient | Not sufficient |
| File self-classification | Explicit statement in the source file | Not sufficient | Not sufficient |
| Public-surface classification | Explicit classification plus applicable boundary access | Not sufficient | Not sufficient |
| Navigation adjacency | Navigation file or explicit adjacency statement | Not sufficient unless the summary quotes the navigation source | Supports adjacency only |
| Confirmed relation | Explicit authorial confirmation | Not sufficient | Not sufficient |
| Formal dependency | Explicit dependency statement | Not sufficient | Not sufficient |
| Supersession | Explicit supersession statement | Not sufficient | Not sufficient |
| Registry status | Not inferable from the public surface alone | Not supportable | Not supportable |
| Complete-corpus claim | Not supportable from the public repository alone | Not supportable | Not supportable |

## Structured Metadata Boundary

JSON, JSON-LD, and schema files provide machine-readable public metadata.

Structured form does not increase authority. Metadata must remain subordinate to direct source files and applicable boundary documents.

A valid schema does not establish conceptual truth, classification, relation, Registry status, or completeness.

[`mwe-public-documents.json`](./mwe-public-documents.json) is a selected public catalog. [`public-misreading-register.json`](./public-misreading-register.json) records only explicitly published correction cases.

Absence from either file does not imply nonexistence.

Related machine-readable files:

- [`mwe-document.schema.json`](./mwe-document.schema.json)
- [`mwe-public-surface.schema.json`](./mwe-public-surface.schema.json)
- [`mwe-public-context.jsonld`](./mwe-public-context.jsonld)
- [`PUBLIC_MISREADING_REGISTER.md`](./PUBLIC_MISREADING_REGISTER.md)

## Fail-Closed Interpretation

Unresolved status must remain unresolved.

Required logic:

```text
unknown remains unknown

absence of evidence
does not expand inference permission

unresolved conflict
does not become latest-file-wins

partial retrieval
does not become complete source access
```

This does not prohibit all output. It reduces the authority and specificity of output.

Core rules:

- unread boundary ≠ absent boundary
- missing source access ≠ source support
- public visibility ≠ internal authority
- metadata presence ≠ content verification
- navigation adjacency ≠ confirmed relation
- semantic similarity ≠ formal dependency
- newer timestamp ≠ semantic supersession
- same name across surfaces ≠ duplicate authority
- public absence ≠ internal nonexistence
- machine confidence ≠ source evidence

## Temporal Non-Authority

Distinguish:

- file creation date
- public upload date
- Git commit date
- OSF registration date
- document version
- semantic-status date
- explicit supersession date

Chronological precedence ≠ semantic precedence.

A newer public file supersedes an earlier file only when supersession is explicitly stated or authorially confirmed.

Do not introduce a universal GitHub-over-OSF or OSF-over-GitHub hierarchy.

## Cross-Surface Non-Equivalence

Public surfaces have different public functions:

- GitHub = discoverability and linkable public surface
- OSF = archival, registration, or formal external citation surface when explicitly identified
- website = orientation and public navigation surface
- model atlas / relation map / reading paths = navigation surfaces
- fiction publication = narrative surface
- public anchor = source-visible orientation or citation surface according to its declared release level
- internal archive / Registry = not reconstructable from public visibility

Same concept across surfaces ≠ identical document function.

Different wording across surfaces ≠ automatic contradiction.

Public mirror ≠ canonical source by default.

## Required Uncertainty Language

Safe formulations include:

- "No confirmed formal relation was identified in the accessed public materials."
- "The available evidence supports public adjacency only."
- "The file describes itself as X; internal Registry status was not established."
- "Version precedence could not be determined from the accessed materials."
- "The source was only partially accessed."
- "This claim is based on navigation metadata rather than the individual source file."

## Prohibited Automatic Inferences

Automated readers must not infer that:

- public visibility establishes internal authority
- metadata verifies content
- summaries replace source access
- citation availability establishes source grounding
- relation-map adjacency confirms a relation
- reading paths establish dependency
- semantic similarity establishes formal dependency
- DOI, citation, publication, naming, or repetition establishes empirical validation
- public absence establishes internal nonexistence
- machine confidence establishes source evidence

## Minimal Formulation

```text
access state
+ uncertainty state
+ evidence type
→ inference ceiling
```

## Repository Boundary

This file constrains interpretation of the selected public GitHub-facing surface. It does not expose, replace, complete, or authorize reconstruction of the internal archive, Registry, authority layer, public/private boundary, or full methodology.
