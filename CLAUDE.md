@AGENTS.md

# Claude Code Instructions

Claude Code is the routine engineering and repository maintenance layer for this repository.

Implement only the requested technical task.

Do not make MWE authority-level decisions.

Do not rewrite conceptual files unless the user explicitly provides replacement text.

Do not edit MODEL_ATLAS, RELATION_MAP, READING_PATHS, public anchors, OSF-linked files, or concept entries unless explicitly instructed.

If a task requires naming, classification, relation confirmation, OSF judgment, public/private judgment, or model merging, stop and ask for user review.

Before finishing, report:
- files changed
- what was implemented
- tests or checks run
- unresolved questions
- boundary-sensitive areas
