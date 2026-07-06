# Agent Rules for the Meta-Writing Ecology Public Corpus Repository

This repository is a GitHub-visible public surface for Meta-Writing Ecology (MWE).

It may contain selected public model nodes, boundary notes, diagnostic orientations, public anchors, relation maps, reading paths, and OSF-linked conceptual mirrors.

It does not represent the full MWE archive, backend corpus, complete registry, complete methodology, or authority layer.

Agents may perform approved technical and organizational tasks only.

## Role Allocation

### GPT Conversation
Use GPT conversation for:
- structural reasoning
- classification judgment
- naming judgment
- public/private boundary review
- OSF / GitHub / website positioning
- deciding whether a relation is candidate, navigation, confirmed, formal dependency, or ontology claim
- deciding whether a public entry should exist

### Claude Code
Use Claude Code for routine engineering and repo-local maintenance:
- Markdown file movement only when explicitly instructed
- JSON / CSV transformation
- link checks
- script creation
- inventory generation
- prepared graph data generation
- build or formatting support if applicable
- mechanical repository maintenance

Claude Code must not decide:
- MWE model classification
- OSF priority
- formal Model / Cross / Log / Protocol / Draft status
- public/private boundary
- naming authority
- registry confirmation
- relation validity
- candidate-to-confirmed promotion
- whether a concept should be added, merged, renamed, or removed

### Codex
Reserve Codex for boundary-sensitive repository work:
- public-surface consistency audits
- relation map review
- candidate vs confirmed relation checks
- OSF / GitHub / website alignment
- metadata architecture
- high-risk batch edits
- review of Claude Code output
- scripts that encode MWE classification or public-exclusion logic

## Relation Status Rules

Preserve these distinctions:

- candidate relation
- navigation relation
- confirmed relation
- formal dependency
- ontology claim

Candidate or navigation relations must not be promoted into confirmed relations without explicit user confirmation.

Relation maps, model atlases, reading paths, and public anchors are navigation surfaces unless explicitly stated otherwise.

## Allowed Work

Agents may:
- add or update agent instruction files
- generate inventories or review packets
- transform user-approved data into JSON / CSV
- check links or file references
- prepare technical scaffolding for approved public graph data
- update worklogs

## Not Allowed

Agents must not:
- rewrite MWE conceptual files
- rename concepts
- invent new relations
- promote candidate relations
- remove boundary statements
- change OSF priority
- treat this repository as the full MWE archive
- treat public anchors as full operational models
- change MODEL_ATLAS, RELATION_MAP, READING_PATHS, or public anchors unless explicitly instructed
- delete or reorganize files without explicit approval

## Public Boundary Rule

Public-facing entries must not imply that this repository contains the full MWE system, archive, registry, methodology, or authority structure.

If a public surface is readable, it must not be treated as complete.

## Required Worklog

After any change, update AGENT_WORKLOG.md with:
- agent used
- task performed
- files changed
- tests or checks run
- unresolved questions
- risks or assumptions

The user remains final authority for publication, naming, classification, relation confirmation, OSF registration, and merge decisions.
