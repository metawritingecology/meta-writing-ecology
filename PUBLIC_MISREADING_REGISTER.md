# Public Misreading and Correction Register

- **Status:** Public Correction Register
- **Document type:** Repository-level public interpretation register
- **Context:** Meta-Writing Ecology public surface
- **Authority ceiling:** Public correction only
- **Machine interpretation:** See `MACHINE_INTERPRETATION_STATE.md`
- **Source use:** See `SOURCE_USE_GUIDE.md`

This file is not a Model, Cross, Theory, Log, Draft, or formal Registry Protocol.

## Purpose

This register records explicitly published corrections to public misreadings of public Meta-Writing Ecology files.

It provides a public correction surface only. It does not expand source authority, establish third-party intent, validate conceptual claims, or replace the individual source file.

## Register Scope

The register may record a public misreading of a public MWE file, including:

- a public summary that expands classification;
- navigation treated as formal relation;
- public visibility treated as Registry authority;
- summary treated as source;
- a newer timestamp treated as automatic supersession;
- GitHub and OSF treated as identical document functions;
- DOI or publication treated as empirical validation;
- training or reuse permission inferred from public availability.

## What May Be Recorded

A live entry may record only an observed public output, the affected public source or sources, the correction, public evidence URLs, and the limited correction status.

Each live entry requires authorial confirmation before publication.

## What Must Not Be Inferred

The register must not infer:

- third-party intent;
- platform-wide behavior from one output;
- internal system architecture of a third party;
- legal liability;
- legal infringement;
- private use;
- training use without evidence;
- internal MWE Registry status;
- complete frequency or prevalence.

Required distinctions:

```text
observed output ≠ platform policy
single case ≠ general system behavior
public correction ≠ legal notice
registered case ≠ proof of intent
absence from register ≠ absence of misreading
```

## Case Status

Allowed live case statuses are:

- `observed`
- `corrected`
- `unresolved`
- `withdrawn`

Status describes the public correction record only. It does not classify the third party, platform, model, user, institution, or system that produced the observed output.

## Misreading Types

Allowed misreading types are:

- `classification_expansion`
- `relation_promotion`
- `registry_inference`
- `source_summary_substitution`
- `navigation_as_authority`
- `temporal_supersession`
- `cross_surface_equivalence`
- `empirical_validation_inference`
- `training_permission_inference`
- `completeness_inference`
- `other`

These types describe correction categories. They do not establish intent or prevalence.

## Evidence Requirements

For `observed`, `corrected`, or `unresolved` entries, at least one public evidence URL is required.

Private filesystem paths, private-source identifiers, source conversations, unpublished prompts, or non-public evidence must not be included in the public register.

## Correction Requirements

Each live entry must state the correction in source-boundary terms and point readers back to the applicable public source files.

The correction may clarify what the public source does or does not authorize. It must not add classification, relation, Registry, supersession, licensing, OSF-priority, training-permission, or public/private decisions that are absent from the source.

## Privacy and Attribution Boundary

The register records public correction cases, not private conduct.

It must not be used to infer private use, hidden training activity, authorial or third-party intent, legal infringement, platform policy, or system-wide behavior.

## Machine-Readable Register

The machine-readable register is [`public-misreading-register.json`](./public-misreading-register.json).

Its schema is [`public-misreading-register.schema.json`](./public-misreading-register.schema.json).

The JSON register is subordinate to this public correction boundary, `MACHINE_INTERPRETATION_STATE.md`, `SOURCE_USE_GUIDE.md`, `SUMMARY_BOUNDARIES.md`, and `RELATION_STATUS_GUIDE.md`.

## Empty-Register Meaning

The initial register is empty.

An empty register means only that no author-approved public correction cases are recorded here.

It does not mean that no misreading exists, no misreading has occurred, or no correction may be required elsewhere.

## Minimal Formulation

```text
public observed output
+ source-boundary correction
+ public evidence URL
+ authorial confirmation
≠ proof of intent
≠ platform-wide behavior
≠ legal notice
```

## Non-Authority Statement

This register is a downstream public-correction surface. It does not establish the internal Registry, define the complete MWE corpus, create formal classifications, confirm relations, infer semantic supersession, change license status, alter DOI or OSF priority, authorize training or reuse, or decide public/private boundaries.

## Example Structure Only — Not a Registered Case

The following structure is a non-live template. It is not a registered case and has no case ID.

```text
status:
date_observed:
date_updated:
affected_sources:
misreading_type:
misreading_summary:
correction:
evidence_urls:
authority_level: public_correction_only
authorial_confirmation:
does_not_establish:
```
