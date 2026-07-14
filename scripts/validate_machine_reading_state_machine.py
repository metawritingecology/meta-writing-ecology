#!/usr/bin/env python3
"""Local validator for the Machine Reading Path and Inference-State Map prototype.

Standard library only. No network, no Git, no subprocess, no dynamic execution.
Reads only the prototype state-machine JSON and its example files. Modifies
nothing. Exits 0 on success and 1 on failure.

The semantic evaluator below is a generic, table-driven interpreter that mirrors
the frontend interpreter (visualizations/machine-reading-path-map/app.js). It
contains no domain constants: every rule, guard, claim scope, flag, and phrase
comes from the JSON model, which is the single declarative rule source consumed
by both the UI and this validator.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
VIS_DIR = os.path.join(REPO_ROOT, "visualizations", "machine-reading-path-map")
MODEL_PATH = os.path.join(VIS_DIR, "machine-reading-state-machine.json")
EXAMPLES_DIR = os.path.join(VIS_DIR, "examples")

# Approved public semantic-source files (validator check 8). Exactly these eight
# public boundary/interpretation files may be cited as semantic grounding. The
# repository-operation files AGENTS.md, CLAUDE.md, and README.md are followed as
# engineering instructions only and must not appear as semantic sources.
APPROVED_PUBLIC_FILES = {
    "MACHINE_INTERPRETATION_STATE.md",
    "MACHINE_READING_PRECEDENCE.md",
    "SOURCE_USE_GUIDE.md",
    "SUMMARY_BOUNDARIES.md",
    "SUMMARY_CONTRACT.md",
    "RELATION_STATUS_GUIDE.md",
    "AI-READING-GUIDE.md",
    "mwe-public-surface.json",
}
FORBIDDEN_SEMANTIC_SOURCE_FILES = {"AGENTS.md", "CLAUDE.md", "README.md"}

# Approved enums (validator check 3).
ENUM_SOURCE_ACCESS = ["direct_source", "partial_source", "summary_only", "navigation_only", "metadata_only"]
ENUM_CLASSIFICATION = ["explicit_file_statement", "none", "conflicting"]
ENUM_RELATION = ["explicit_authorial_confirmation", "explicit_public_relation_statement", "navigation_only", "none", "conflicting"]
ENUM_VERSION = ["explicit_supersession_statement", "no_explicit_supersession_statement", "unknown", "conflicting"]
ENUM_UNCERTAINTY = ["version_uncertain", "authority_uncertain", "classification_uncertain", "relation_uncertain", "conflict_unresolved", "source_scope_uncertain"]
ENUM_CLAIM_SCOPES = [
    "public_presence_only", "summary_surface_description_only", "partial_source_description_only",
    "navigation_adjacency_only", "file_self_description", "public_surface_classification",
    "explicit_public_relation_description", "authorial_confirmation_required", "prohibited_reconstruction",
]
ENUM_RESULT_STATES = ["bounded_output", "unresolved", "requires_authorial_confirmation", "prohibited_reconstruction"]
ENUM_STAGES = [
    "start", "access_resolved", "boundary_resolved", "classification_resolved", "relation_resolved",
    "version_resolved", "conflict_resolved", "output_bounded", "unresolved",
    "authorial_confirmation_required", "prohibited_reconstruction",
]

REQUIRED_TOP_KEYS = [
    "schema_version", "title", "status", "scope", "non_authority_statements",
    "input_definitions", "uncertainty_flags", "claim_scopes", "result_states",
    "universally_blocked_claims", "source_rules", "rules", "stages", "transitions",
    "test_case_references",
]

FIXED_PSEUDO = {"reconstruction_requested": False, "confirmed_relation_requested": False, "supersession_authority_required": False}

# Tokens that must never appear in the prototype JSON or example files: absolute
# local paths and internal/private source paths.
ABS_PATH_RE = re.compile(r"(^|[\s\"'(=:])(/(home|root|Users|tmp|var|mnt|opt|srv)/|[A-Za-z]:\\\\)")
PRIVATE_TOKEN_RE = re.compile(
    r"(backend[_-]?archive|internal[_-]?archive|private[_-]?registry|registry[_-]?private|"
    r"\.zip\b|/archive/|/private/|/backend/|internal_registry_data|unpublished[_-])",
    re.IGNORECASE,
)


class Result:
    def __init__(self):
        self.errors = []
        self.checks = 0

    def check(self, ok, label, detail=""):
        self.checks += 1
        if not ok:
            self.errors.append("FAIL [%s] %s" % (label, detail))
        return ok


# ---------------------------------------------------------------------------
# Generic guard interpreter + evaluator (mirrors app.js).
# ---------------------------------------------------------------------------
def eval_guard(guard, inp):
    if guard is None:
        return True
    if "always" in guard:
        return bool(guard["always"])
    if "all" in guard:
        return all(eval_guard(g, inp) for g in guard["all"])
    if "any" in guard:
        return any(eval_guard(g, inp) for g in guard["any"])
    if "not" in guard:
        return not eval_guard(guard["not"], inp)
    if "field" in guard:
        val = inp.get(guard["field"])
        if "equals" in guard:
            return val == guard["equals"]
        if "in" in guard:
            return val in guard["in"]
    return False


def evaluate(model, user_input):
    inp = dict(FIXED_PSEUDO)
    inp.update(user_input)
    terminal = {r["from_stage"]: r["id"] for r in model["result_states"]}
    transitions = model["transitions"]

    current = "start"
    path_stages = [current]
    path_transitions = []
    steps = 0
    while current not in terminal and steps < 100:
        steps += 1
        chosen = None
        for t in transitions:
            if t["from"] == "any" and eval_guard(t["guard"], inp):
                chosen = t
                break
        if chosen is None:
            for t in transitions:
                if t["from"] == current and eval_guard(t["guard"], inp):
                    chosen = t
                    break
        if chosen is None:
            break
        path_transitions.append(chosen["id"])
        current = chosen["to"]
        path_stages.append(current)
    result_state = terminal.get(current)

    cs_rules = [r for r in model["rules"] if r["type"] == "claim_scope_selection"]
    matched = [r for r in cs_rules if eval_guard(r["when"], inp)]
    max_scope = matched[0]["produces_claim_scope"] if matched else None
    supported = []
    for r in matched:
        if r["produces_claim_scope"] not in supported:
            supported.append(r["produces_claim_scope"])
    scope_by_id = {c["id"]: c for c in model["claim_scopes"]}
    allowed = []
    for sid in supported:
        for s in scope_by_id[sid]["supports"]:
            if s not in allowed:
                allowed.append(s)
    blocked = list(model["universally_blocked_claims"])
    for sid in supported:
        for b in scope_by_id[sid]["blocks"]:
            if b not in blocked:
                blocked.append(b)
    blocked = [b for b in blocked if b not in allowed]

    flag_order = [f["id"] for f in model["uncertainty_flags"]]
    produced = set()
    for r in model["rules"]:
        if r["type"] == "uncertainty_derivation" and eval_guard(r["when"], inp):
            produced.update(r["produces_flags"])
    flags = [f for f in flag_order if f in produced]

    language = []
    for r in model["rules"]:
        if r["type"] == "required_language" and eval_guard(r["when"], inp):
            if r["phrase"] not in language:
                language.append(r["phrase"])

    return {
        "maximum_claim_scope": max_scope,
        "supported_claim_scopes": supported,
        "result_state": result_state,
        "path_stages": path_stages,
        "path_transitions": path_transitions,
        "allowed_claims": allowed,
        "blocked_claims": blocked,
        "uncertainty_flags": flags,
        "required_limitation_language": language,
    }


def collect_strings(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            collect_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_strings(v, out)
    elif isinstance(obj, str):
        out.append(obj)


def main():
    r = Result()

    # (1) JSON parses.
    if not os.path.exists(MODEL_PATH):
        print("FAIL [1] model file missing: %s" % MODEL_PATH)
        return 1
    try:
        with open(MODEL_PATH, encoding="utf-8") as fh:
            raw = fh.read()
        model = json.loads(raw)
        r.check(True, "1", "model JSON parses")
    except Exception as exc:  # noqa: BLE001
        print("FAIL [1] model JSON does not parse: %s" % exc)
        return 1

    # (2) Required top-level keys exist.
    for key in REQUIRED_TOP_KEYS:
        r.check(key in model, "2", "missing top-level key: %s" % key)

    r.check(model.get("status") == "draft", "2b", "status must be draft")
    r.check(model.get("scope") == "public_source_only_reference_implementation", "2c", "scope mismatch")

    idefs = model.get("input_definitions", {})

    # (3) Enums match the approved specification.
    r.check(idefs.get("source_access_state", {}).get("values") == ENUM_SOURCE_ACCESS, "3", "source_access_state enum")
    r.check(idefs.get("classification_evidence", {}).get("values") == ENUM_CLASSIFICATION, "3", "classification_evidence enum")
    r.check(idefs.get("relation_evidence", {}).get("values") == ENUM_RELATION, "3", "relation_evidence enum")
    r.check(idefs.get("version_evidence", {}).get("values") == ENUM_VERSION, "3", "version_evidence enum")
    r.check([f["id"] for f in model.get("uncertainty_flags", [])] == ENUM_UNCERTAINTY, "3", "uncertainty_flags enum")
    r.check([c["id"] for c in model.get("claim_scopes", [])] == ENUM_CLAIM_SCOPES, "3", "claim_scopes enum")
    r.check([s["id"] for s in model.get("result_states", [])] == ENUM_RESULT_STATES, "3", "result_states enum")
    r.check([s["id"] for s in model.get("stages", [])] == ENUM_STAGES, "3", "stages enum")

    stage_ids = {s["id"] for s in model.get("stages", [])}
    scope_ids = {c["id"] for c in model.get("claim_scopes", [])}
    result_ids = {s["id"] for s in model.get("result_states", [])}
    result_from_stage = {s["from_stage"] for s in model.get("result_states", [])}

    # (4) Transition IDs unique.
    tids = [t["id"] for t in model.get("transitions", [])]
    r.check(len(tids) == len(set(tids)), "4", "duplicate transition IDs")

    # (5) Rule IDs unique.
    rids = [r_["id"] for r_ in model.get("rules", [])]
    r.check(len(rids) == len(set(rids)), "5", "duplicate rule IDs")

    # (6) Source-rule IDs unique.
    srids = [s["id"] for s in model.get("source_rules", [])]
    r.check(len(srids) == len(set(srids)), "6", "duplicate source-rule IDs")
    srid_set = set(srids)

    # (7) Every transition references at least one source rule (and those exist).
    for t in model.get("transitions", []):
        ids = t.get("source_rule_ids", [])
        r.check(len(ids) >= 1, "7", "transition %s has no source rule" % t.get("id"))
        for i in ids:
            r.check(i in srid_set, "7", "transition %s cites unknown source rule %s" % (t.get("id"), i))

    # (8) Every source rule references an approved public file.
    for s in model.get("source_rules", []):
        r.check(s.get("file") in APPROVED_PUBLIC_FILES, "8", "source rule %s cites non-approved file %s" % (s.get("id"), s.get("file")))
        r.check(s.get("file") not in FORBIDDEN_SEMANTIC_SOURCE_FILES, "8", "source rule %s cites repository-operation file %s as a semantic source" % (s.get("id"), s.get("file")))

    # (8b) The declared approved_public_sources list is exactly the eight approved files.
    declared = model.get("approved_public_sources", [])
    r.check(set(declared) == APPROVED_PUBLIC_FILES, "8b", "approved_public_sources must be exactly the eight approved files; got %s" % sorted(declared))
    r.check(not (set(declared) & FORBIDDEN_SEMANTIC_SOURCE_FILES), "8b", "approved_public_sources must not list AGENTS.md, CLAUDE.md, or README.md")

    # (9) Every source rule has a non-empty section heading or JSON pointer.
    for s in model.get("source_rules", []):
        heading = (s.get("section_heading") or "").strip()
        pointer = (s.get("json_pointer") or "").strip()
        r.check(bool(heading) or bool(pointer), "9", "source rule %s lacks heading/pointer" % s.get("id"))

    # (10) No transition refers to a missing stage.
    for t in model.get("transitions", []):
        if t.get("from") != "any":
            r.check(t.get("from") in stage_ids, "10", "transition %s from-stage missing" % t.get("id"))
        r.check(t.get("to") in stage_ids, "10", "transition %s to-stage missing" % t.get("id"))
    # transition supported_claim_scope must be a defined claim scope
    for t in model.get("transitions", []):
        r.check(t.get("supported_claim_scope") in scope_ids, "10b", "transition %s supported_claim_scope undefined" % t.get("id"))

    # (11) No rule produces an undefined claim scope.
    for r_ in model.get("rules", []):
        if r_.get("type") == "claim_scope_selection":
            r.check(r_.get("produces_claim_scope") in scope_ids, "11", "rule %s produces undefined claim scope" % r_.get("id"))

    # (12) No transition maps to an undefined result state (terminal stage must be a result-state source).
    for t in model.get("transitions", []):
        if t.get("to") in ("output_bounded", "unresolved", "authorial_confirmation_required", "prohibited_reconstruction"):
            r.check(t.get("to") in result_from_stage, "12", "transition %s terminal has no result state" % t.get("id"))
    # every uncertainty flag produced is defined
    for r_ in model.get("rules", []):
        if r_.get("type") == "uncertainty_derivation":
            for fl in r_.get("produces_flags", []):
                r.check(fl in ENUM_UNCERTAINTY, "12b", "rule %s produces undefined flag %s" % (r_.get("id"), fl))

    def ev(**kw):
        base = {
            "source_access_state": "direct_source",
            "boundary_loaded": True,
            "classification_evidence": "none",
            "relation_evidence": "none",
            "version_evidence": "no_explicit_supersession_statement",
        }
        base.update(kw)
        return evaluate(model, base)

    # (13) metadata_only cannot produce source-content claims.
    m = ev(source_access_state="metadata_only", version_evidence="unknown")
    r.check(m["maximum_claim_scope"] == "public_presence_only", "13", "metadata_only scope")
    r.check("Conceptual summary." in m["blocked_claims"], "13", "metadata_only must block conceptual summary")
    r.check(all("source file" not in a and "passage" not in a for a in m["allowed_claims"]), "13", "metadata_only leaked source-content claim")

    # (14) summary_only cannot produce direct-source claims.
    s = ev(source_access_state="summary_only")
    r.check(s["maximum_claim_scope"] == "summary_surface_description_only", "14", "summary_only scope")
    r.check("Full source-content claims." in m_blocks(s), "14", "summary_only must block full source-content claims")
    r.check("Describing explicit statements in the individual source file." not in s["allowed_claims"], "14", "summary_only leaked direct-source claim")

    # (15) navigation_only cannot produce confirmed relation.
    n = ev(source_access_state="navigation_only", relation_evidence="navigation_only")
    r.check(n["maximum_claim_scope"] == "navigation_adjacency_only", "15", "navigation_only scope")
    r.check("Confirmed relation." in n["blocked_claims"], "15", "navigation_only must block confirmed relation")

    # (16) partial_source cannot produce complete-source access.
    p = ev(source_access_state="partial_source")
    r.check(p["maximum_claim_scope"] == "partial_source_description_only", "16", "partial_source scope")
    r.check("Claiming complete-file access." in p["blocked_claims"], "16", "partial_source must block complete-file access")
    r.check("The source was only partially accessed." in p["required_limitation_language"], "16", "partial_source language")

    # (17) classification none cannot produce public classification.
    c = ev(classification_evidence="none")
    r.check(c["maximum_claim_scope"] != "public_surface_classification", "17", "classification none produced public classification")
    r.check("Formal classification without authorial confirmation." in c["blocked_claims"], "17", "classification none must block formal classification")

    # (18) conflicting classification produces authorial confirmation.
    r.check(ev(classification_evidence="conflicting")["result_state"] == "requires_authorial_confirmation", "18", "classification conflict result")

    # (19) conflicting relation produces authorial confirmation.
    r.check(ev(relation_evidence="conflicting")["result_state"] == "requires_authorial_confirmation", "19", "relation conflict result")

    # (20) version unknown produces unresolved.
    r.check(ev(version_evidence="unknown")["result_state"] == "unresolved", "20", "version unknown result")

    # (21) version conflicting produces authorial confirmation.
    r.check(ev(version_evidence="conflicting")["result_state"] == "requires_authorial_confirmation", "21", "version conflict result")

    # (22) no explicit supersession statement blocks supersession (without forcing unresolved).
    ns = ev(version_evidence="no_explicit_supersession_statement")
    r.check("Semantic supersession without an explicit supersession statement or authorial confirmation." in ns["blocked_claims"], "22", "supersession must stay blocked")
    r.check(ns["result_state"] == "bounded_output", "22", "no_explicit_supersession alone should not force unresolved")

    # (23) complete ontology/Registry/archive reconstruction remains blocked.
    for phrase in [
        "Reconstruction of the complete MWE ontology.",
        "Reconstruction of the complete internal Registry.",
        "Reconstruction of the complete archive or working corpus.",
    ]:
        r.check(phrase in model.get("universally_blocked_claims", []), "23", "missing universal block: %s" % phrase)
        r.check(phrase in ev()["blocked_claims"], "23", "universal block not applied: %s" % phrase)

    # (24) all six required examples produce their expected results.
    example_files = sorted(f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".json")) if os.path.isdir(EXAMPLES_DIR) else []
    r.check(len(example_files) == 6, "24", "expected 6 example files, found %d" % len(example_files))
    referenced = set(model.get("test_case_references", []))
    for fname in example_files:
        r.check(("examples/" + fname) in referenced, "24", "example not referenced in test_case_references: %s" % fname)
        with open(os.path.join(EXAMPLES_DIR, fname), encoding="utf-8") as fh:
            case = json.loads(fh.read())
        computed = evaluate(model, case["input"])
        exp = case.get("expected", {})
        if "maximum_claim_scope" in exp:
            r.check(computed["maximum_claim_scope"] == exp["maximum_claim_scope"], "24", "%s scope %s != %s" % (fname, computed["maximum_claim_scope"], exp["maximum_claim_scope"]))
        r.check(computed["result_state"] == exp.get("result_state"), "24", "%s result %s != %s" % (fname, computed["result_state"], exp.get("result_state")))
        for b in exp.get("must_block", []):
            r.check(b in computed["blocked_claims"], "24", "%s missing block %r" % (fname, b))
        for fl in exp.get("must_include_flags", []):
            r.check(fl in computed["uncertainty_flags"], "24", "%s missing flag %s" % (fname, fl))
        for ln in exp.get("must_include_language", []):
            r.check(ln in computed["required_limitation_language"], "24", "%s missing language %r" % (fname, ln))

    # (25) + (26) no absolute local paths and no internal/private source paths.
    scan_targets = [("machine-reading-state-machine.json", raw)]
    for fname in example_files:
        with open(os.path.join(EXAMPLES_DIR, fname), encoding="utf-8") as fh:
            scan_targets.append((fname, fh.read()))
    for label, text in scan_targets:
        r.check(not ABS_PATH_RE.search(text), "25", "absolute local path in %s" % label)
        r.check(not PRIVATE_TOKEN_RE.search(text), "26", "internal/private source token in %s" % label)

    # Report.
    if r.errors:
        print("Machine-reading state-machine validation FAILED (%d checks run)." % r.checks)
        for e in r.errors:
            print("  " + e)
        return 1
    print("Machine-reading state-machine validation passed.")
    print("- checks run: %d" % r.checks)
    print("- source rules: %d" % len(model.get("source_rules", [])))
    print("- rules: %d" % len(model.get("rules", [])))
    print("- transitions: %d" % len(model.get("transitions", [])))
    print("- stages: %d" % len(model.get("stages", [])))
    print("- example cases: %d / 6 passed" % len(example_files))
    return 0


def m_blocks(res):
    return res["blocked_claims"]


if __name__ == "__main__":
    sys.exit(main())
