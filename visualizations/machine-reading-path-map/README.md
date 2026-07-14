# Machine Reading Path and Inference-State Map

A local, reviewable D3 prototype that simulates how public-source reading rules
execute over the selected public boundary surface of Meta-Writing Ecology, and
what bounded claim the accessed evidence permits.

## 1. Purpose

Show, step by step, for a given reading situation:

- what kind of source material was actually accessed;
- whether public boundary material was loaded;
- what classification, relation, and version evidence is available;
- what claims are currently supported;
- what claims are blocked;
- what uncertainty language is required;
- whether the result is bounded, unresolved, or requires authorial confirmation;
- which public source rule supports each decision.

## 2. Draft status

Status: **draft**. Scope: **public_source_only_reference_implementation**.
This is a fresh prototype for review, not a released component.

## 3. Public-source-only scope

Every rule is grounded in a public file already present in this repository (see
section 6). No backend archive, private Registry, prior ZIP, or unpublished
material was read or used. The prototype JSON is not added to any public
manifest or registry.

## 4. What the prototype represents

The **order in which public-source reading rules execute** (a rule-execution
path) and the **bounded claim** that the accessed evidence permits. The state
graph is a public-rule execution path.

## 5. What it does not represent

This prototype is a public-source-only reference implementation of reading
boundaries. It does not represent third-party AI internal reasoning, the
internal Registry, a complete MWE policy, a formal ontology, or an automatic
authority system.

It is not a website search function, a representation of an AI model's hidden
reasoning, a chain-of-thought display, a truth validator, an automatic
classification system, an automatic relation-confirmation system, a canonical
MWE machine policy, or a formal MWE Protocol. It does not confirm
classification, relation, semantic supersession, or public/private status.
Missing information is not automatically reconstructed.

## 6. Approved public source files

Semantic grounding is limited to these **eight** public boundary/interpretation
files. Each source rule names one of them plus an exact section heading or JSON
pointer:

- `MACHINE_INTERPRETATION_STATE.md`
- `MACHINE_READING_PRECEDENCE.md`
- `SOURCE_USE_GUIDE.md`
- `SUMMARY_BOUNDARIES.md`
- `SUMMARY_CONTRACT.md`
- `RELATION_STATUS_GUIDE.md`
- `AI-READING-GUIDE.md`
- `mwe-public-surface.json`

`AGENTS.md`, `CLAUDE.md`, and `README.md` are followed as repository-operation
instructions only; they are **not** semantic sources for this state machine.

## 7. Input model

Five inputs (defined in `machine-reading-state-machine.json` under
`input_definitions`):

- **source_access_state** (exactly one): `direct_source`, `partial_source`,
  `summary_only`, `navigation_only`, `metadata_only`.
- **boundary_loaded** (boolean): separate from source access. `false` never
  increases permission.
- **classification_evidence**: `explicit_file_statement`, `none`, `conflicting`.
- **relation_evidence**: `explicit_authorial_confirmation`,
  `explicit_public_relation_statement`, `navigation_only`, `none`,
  `conflicting`.
- **version_evidence**: `explicit_supersession_statement`,
  `no_explicit_supersession_statement`, `unknown`, `conflicting`.

The evaluation is fail-closed: unknown stays unknown, missing evidence lowers
the claim ceiling, conflicting evidence is not auto-resolved, newer material
does not auto-supersede older material, partial access is not complete access,
navigation is not a conceptual relation, and metadata is not conceptual content.

## 8. Claim scopes

`public_presence_only`, `summary_surface_description_only`,
`partial_source_description_only`, `navigation_adjacency_only`,
`file_self_description`, `public_surface_classification`,
`explicit_public_relation_description`, `authorial_confirmation_required`, and
`prohibited_reconstruction`. Each scope declares what it supports and what it
blocks. Scopes are not a quality score or authority rank.

The displayed **maximum claim scope** is chosen by the precedence encoded in the
`claim_scope_selection` rules; every lower supported operation is still listed
under allowed claims.

## 9. Result states

- **bounded_output** — a clearly bounded public-source claim can be produced.
- **unresolved** — insufficient public evidence for the displayed claim scope.
- **requires_authorial_confirmation** — an authority boundary was reached.
- **prohibited_reconstruction** — a defined blocked category; not reachable from
  the five simulator inputs (there is no input that requests reconstruction).

Precedence: prohibited_reconstruction, then requires_authorial_confirmation,
then unresolved, then bounded_output. `relation = none` and `classification =
none` block their respective claims only; they do not by themselves force
unresolved.

## 10. Transition model

Eleven stages — `start`, `access_resolved`, `boundary_resolved`,
`classification_resolved`, `relation_resolved`, `version_resolved`,
`conflict_resolved`, and the four terminals — connected by 14 transitions
(`T001`–`T014`). The evaluator walks the transitions from `start`: at each step
it takes the first transition whose guard passes, and stops at a terminal stage.
The terminal stage maps to the result state. Every transition carries a guard,
an effect, a supported claim scope, and one or more source-rule IDs. `T014`
(`any` → `prohibited_reconstruction`) is defined but not reachable here.

## 11. Required source grounding

Each transition and each rule cites `source_rule_ids`. Each source rule names a
public file plus an exact section heading or JSON pointer, states what it
supports, and states what it does not establish. The right-hand panel expands
the source rules used for the current inputs.

## 12. Example cases

`examples/` holds six input+expected cases, exercised by both the frontend
example buttons and the validator:

1. `case-01-direct-source-classification.json` — bounded_output,
   public_surface_classification.
2. `case-02-metadata-only.json` — unresolved, public_presence_only.
3. `case-03-navigation-only.json` — bounded_output, navigation_adjacency_only.
4. `case-04-summary-only.json` — unresolved, summary_surface_description_only.
5. `case-05-version-unknown.json` — unresolved, file_self_description.
6. `case-06-classification-conflict.json` — requires_authorial_confirmation.

## 13. Local preview

From the repository root (or from this directory), serve over HTTP — the page
fetches local JSON, so it must be served rather than opened as a `file://` URL:

```
python -m http.server 8000
```

Then open:

```
http://localhost:8000/visualizations/machine-reading-path-map/
```

No API key, private service, database, Cloudflare service, search index,
backend server, or external MWE archive is required.

## 14. Validator command

From the repository root:

```
python scripts/validate_machine_reading_state_machine.py
```

Standard library only; no network, Git, or subprocess. It parses the model and
examples, checks the enums, ID uniqueness, source grounding, and stage/transition
integrity, and runs every example through the same rule evaluator the UI uses.
Exit 0 on success, 1 on failure.

## 15. Accessibility

Keyboard-operable controls and stage nodes (nodes are `tabindex`-focusable,
`role="button"`, and respond to Enter/Space), visible focus, semantic labels, a
screen-reader-readable result, non-color-only status encoding (shape, border
style, `✓`/`✗`, and `present`/`absent` text), reduced-motion support, a
responsive layout, and a complete text summary usable without the diagram. A
`<noscript>` block and a data-load-failure message explain the no-JavaScript and
offline cases.

## 16. D3 dependency

D3 v7.9.0 is loaded from one pinned CDN import
(`https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js`). It is used only to help
draw the deterministic flow diagram. If the CDN is unavailable, the page falls
back to a plain-DOM SVG diagram and the full result stays readable as text;
nothing essential depends on D3. No package.json, vendored bundle, analytics,
telemetry, cookies, localStorage, or external data call is added.

## 17. Known limitations

- The horizontal stage flow scrolls inside its own container on narrow layouts;
  the always-present textual rule-execution path lists the full sequence.
- `prohibited_reconstruction` is defined but intentionally unreachable in this
  first prototype, which offers no reconstruction-request input.
- Section headings and JSON pointers are recorded as authored references; the
  validator checks they are present and non-empty and that the file is approved,
  but does not re-open the source files.
- This is a reading-boundary reference implementation, not a measurement tool:
  scope order is not a confidence, correctness, or authority ranking.

## 18. Non-authority statement

This prototype is a public-source-only reference implementation of reading
boundaries. It does not represent third-party AI internal reasoning, the
internal Registry, a complete MWE policy, a formal ontology, or an automatic
authority system.

Unresolved means insufficient public evidence, not system failure. Authorial
confirmation is an authority boundary, not a confidence score.
