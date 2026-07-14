/*
 * Machine Reading Path and Inference-State Map — prototype interaction layer.
 *
 * This file is a generic, table-driven interpreter of the single declarative
 * rule source, machine-reading-state-machine.json. It contains NO domain
 * constants: every input value, guard, claim scope, uncertainty flag, result
 * state, transition, and required phrase is read from the JSON. The Python
 * validator (scripts/validate_machine_reading_state_machine.py) implements the
 * identical interpreter, so the frontend, validator, and examples cannot drift.
 *
 * What this represents: the order in which public-source reading rules execute,
 * and the bounded claim they permit. What it does NOT represent: any AI system's
 * internal reasoning, a chain of thought, a confidence or truth score, the
 * internal Registry, or a complete MWE policy or ontology.
 *
 * D3 v7 (pinned) is used to draw the deterministic flow diagram when available.
 * If D3 is unavailable, the diagram degrades to a plain-DOM SVG and the full
 * result stays readable as text; nothing essential depends on D3.
 */
(function () {
  "use strict";

  var HAS_D3 = typeof window.d3 !== "undefined";
  var FIXED = {
    reconstruction_requested: false,
    confirmed_relation_requested: false,
    supersession_authority_required: false
  };

  var model = null;
  var input = null;

  function el(id) { return document.getElementById(id); }

  // -------------------------------------------------------------------------
  // Generic guard interpreter + evaluator (mirror of the Python validator).
  // -------------------------------------------------------------------------
  function evalGuard(guard, inp) {
    if (!guard) return true;
    if ("always" in guard) return !!guard.always;
    if ("all" in guard) return guard.all.every(function (g) { return evalGuard(g, inp); });
    if ("any" in guard) return guard.any.some(function (g) { return evalGuard(g, inp); });
    if ("not" in guard) return !evalGuard(guard.not, inp);
    if ("field" in guard) {
      var val = inp[guard.field];
      if ("equals" in guard) return val === guard.equals;
      if ("in" in guard) return guard["in"].indexOf(val) !== -1;
    }
    return false;
  }

  function evaluate(m, userInput) {
    var inp = {};
    var k;
    for (k in FIXED) inp[k] = FIXED[k];
    for (k in userInput) inp[k] = userInput[k];

    var terminal = {};
    m.result_states.forEach(function (r) { terminal[r.from_stage] = r.id; });

    var current = "start";
    var pathStages = [current];
    var pathTransitions = [];
    var steps = 0;
    while (!(current in terminal) && steps < 100) {
      steps++;
      var chosen = null;
      var i;
      for (i = 0; i < m.transitions.length; i++) {
        if (m.transitions[i].from === "any" && evalGuard(m.transitions[i].guard, inp)) { chosen = m.transitions[i]; break; }
      }
      if (!chosen) {
        for (i = 0; i < m.transitions.length; i++) {
          if (m.transitions[i].from === current && evalGuard(m.transitions[i].guard, inp)) { chosen = m.transitions[i]; break; }
        }
      }
      if (!chosen) break;
      pathTransitions.push(chosen.id);
      current = chosen.to;
      pathStages.push(current);
    }
    var resultState = terminal[current] || null;

    var csRules = m.rules.filter(function (r) { return r.type === "claim_scope_selection"; });
    var matched = csRules.filter(function (r) { return evalGuard(r.when, inp); });
    var maxScope = matched.length ? matched[0].produces_claim_scope : null;
    var supported = [];
    matched.forEach(function (r) { if (supported.indexOf(r.produces_claim_scope) === -1) supported.push(r.produces_claim_scope); });

    var scopeById = {};
    m.claim_scopes.forEach(function (c) { scopeById[c.id] = c; });

    var allowed = [];
    supported.forEach(function (sid) {
      scopeById[sid].supports.forEach(function (s) { if (allowed.indexOf(s) === -1) allowed.push(s); });
    });
    var blocked = m.universally_blocked_claims.slice();
    supported.forEach(function (sid) {
      scopeById[sid].blocks.forEach(function (b) { if (blocked.indexOf(b) === -1) blocked.push(b); });
    });
    blocked = blocked.filter(function (b) { return allowed.indexOf(b) === -1; });

    var flagOrder = m.uncertainty_flags.map(function (f) { return f.id; });
    var produced = {};
    m.rules.forEach(function (r) {
      if (r.type === "uncertainty_derivation" && evalGuard(r.when, inp)) {
        r.produces_flags.forEach(function (f) { produced[f] = true; });
      }
    });
    var flags = flagOrder.filter(function (f) { return produced[f]; });

    var language = [];
    m.rules.forEach(function (r) {
      if (r.type === "required_language" && evalGuard(r.when, inp)) {
        if (language.indexOf(r.phrase) === -1) language.push(r.phrase);
      }
    });

    // source rules used = union over traversed transitions + supported scopes + fired rules
    var used = [];
    function add(ids) { ids.forEach(function (id) { if (used.indexOf(id) === -1) used.push(id); }); }
    pathTransitions.forEach(function (tid) {
      var t = m.transitions.filter(function (x) { return x.id === tid; })[0];
      if (t) add(t.source_rule_ids);
    });
    supported.forEach(function (sid) { add(scopeById[sid].source_rule_ids); });
    m.rules.forEach(function (r) {
      if ((r.type === "uncertainty_derivation" || r.type === "required_language") && evalGuard(r.when, inp)) add(r.source_rule_ids);
    });

    return {
      input: userInput,
      maximum_claim_scope: maxScope,
      supported_claim_scopes: supported,
      result_state: resultState,
      path_stages: pathStages,
      path_transitions: pathTransitions,
      allowed_claims: allowed,
      blocked_claims: blocked,
      uncertainty_flags: flags,
      required_limitation_language: language,
      source_rules_used: used
    };
  }

  // -------------------------------------------------------------------------
  // Controls
  // -------------------------------------------------------------------------
  function defaultInput() {
    var d = model.input_definitions;
    return {
      source_access_state: d.source_access_state.default,
      boundary_loaded: d.boundary_loaded.default,
      classification_evidence: d.classification_evidence.default,
      relation_evidence: d.relation_evidence.default,
      version_evidence: d.version_evidence.default
    };
  }

  function buildControls() {
    var d = model.input_definitions;

    // Source access — radio group with per-value descriptions.
    var accessBox = el("access-group");
    d.source_access_state.values.forEach(function (v) {
      var lab = document.createElement("label");
      lab.className = "radio";
      var rb = document.createElement("input");
      rb.type = "radio"; rb.name = "source_access_state"; rb.value = v;
      rb.addEventListener("change", function () { input.source_access_state = v; recompute(); });
      lab.appendChild(rb);
      lab.appendChild(document.createTextNode(v));
      accessBox.appendChild(lab);
      var desc = document.createElement("span");
      desc.className = "val-desc";
      desc.textContent = d.source_access_state.descriptions[v] || "";
      accessBox.appendChild(desc);
    });

    // Boundary loaded — radio (true/false).
    var boundaryBox = el("boundary-group");
    [true, false].forEach(function (v) {
      var lab = document.createElement("label");
      lab.className = "radio";
      var rb = document.createElement("input");
      rb.type = "radio"; rb.name = "boundary_loaded"; rb.value = String(v);
      rb.addEventListener("change", function () { input.boundary_loaded = v; recompute(); });
      lab.appendChild(rb);
      lab.appendChild(document.createTextNode(v ? "true — applicable boundary material loaded" : "false — boundary not loaded"));
      boundaryBox.appendChild(lab);
    });

    buildSelect("classification_evidence", "classification-select");
    buildSelect("relation_evidence", "relation-select");
    buildSelect("version_evidence", "version-select");

    // Examples
    var exWrap = el("examples");
    (model.test_case_references || []).forEach(function (ref) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Load " + ref.replace("examples/", "").replace(/\.json$/, "");
      btn.addEventListener("click", function () { loadExample(ref, btn); });
      exWrap.appendChild(btn);
    });

    el("reset-btn").addEventListener("click", function () { input = defaultInput(); syncControls(); recompute(); });
  }

  function buildSelect(field, elementId) {
    var d = model.input_definitions[field];
    var sel = el(elementId);
    d.values.forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = d.descriptions && d.descriptions[v] ? (v + " — " + d.descriptions[v]) : v;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", function () { input[field] = sel.value; recompute(); });
  }

  function syncControls() {
    document.querySelectorAll('input[name="source_access_state"]').forEach(function (rb) {
      rb.checked = (rb.value === input.source_access_state);
    });
    document.querySelectorAll('input[name="boundary_loaded"]').forEach(function (rb) {
      rb.checked = (rb.value === String(input.boundary_loaded));
    });
    el("classification-select").value = input.classification_evidence;
    el("relation-select").value = input.relation_evidence;
    el("version-select").value = input.version_evidence;
  }

  function loadExample(ref, btn) {
    fetch(ref).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      input = {
        source_access_state: data.input.source_access_state,
        boundary_loaded: data.input.boundary_loaded,
        classification_evidence: data.input.classification_evidence,
        relation_evidence: data.input.relation_evidence,
        version_evidence: data.input.version_evidence
      };
      syncControls();
      recompute(data.title || null);
    }).catch(function (e) {
      showLoadError("Could not load example " + ref + " (" + e.message + "). Set the inputs manually on the left.");
    });
  }

  // -------------------------------------------------------------------------
  // Diagram (deterministic left-to-right flow)
  // -------------------------------------------------------------------------
  var TERM_CLASS = {
    output_bounded: "output",
    unresolved: "unresolved",
    authorial_confirmation_required: "authorial",
    prohibited_reconstruction: "prohibited"
  };

  function stageLayout() {
    // resolution stages laid out along a single row; terminals stacked in the last column.
    var W = 900, colGap = W / 8;
    var midY = 70, nodeW = 96, nodeH = 46;
    var pos = {};
    model.stages.forEach(function (s) {
      var x = 10 + s.column * colGap;
      var y = midY;
      if (s.kind === "terminal") { y = 20 + s.row * 66; }
      pos[s.id] = { x: x, y: y, w: nodeW, h: nodeH, stage: s };
    });
    return { pos: pos, width: W + 60, height: 20 + 4 * 66 + 20 };
  }

  function renderDiagram(res) {
    var wrap = el("diagram");
    wrap.innerHTML = "";
    var layout = stageLayout();
    var pos = layout.pos;
    var activeStages = {};
    res.path_stages.forEach(function (s) { activeStages[s] = true; });
    var activeTrans = {};
    res.path_transitions.forEach(function (t) { activeTrans[t] = true; });

    var SVGNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("class", "flow");
    svg.setAttribute("viewBox", "0 0 " + layout.width + " " + layout.height);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", diagramAriaLabel(res));

    // edges
    model.transitions.forEach(function (t) {
      if (t.from === "any") return; // reconstruction guard; drawn only in text
      var a = pos[t.from], b = pos[t.to];
      if (!a || !b) return;
      var path = document.createElementNS(SVGNS, "path");
      var x1 = a.x + a.w, y1 = a.y + a.h / 2;
      var x2 = b.x, y2 = b.y + b.h / 2;
      var mx = (x1 + x2) / 2;
      var d = "M" + x1 + "," + y1 + " C" + mx + "," + y1 + " " + mx + "," + y2 + " " + x2 + "," + y2;
      path.setAttribute("d", d);
      path.setAttribute("class", "edge" + (activeTrans[t.id] ? " active" : ""));
      svg.appendChild(path);
    });

    // nodes
    model.stages.forEach(function (s) {
      var p = pos[s.id];
      var g = document.createElementNS(SVGNS, "g");
      var cls = "node";
      if (s.kind === "terminal") {
        cls = "node term " + TERM_CLASS[s.id];
        cls += activeStages[s.id] ? " active" : " inactive";
      } else {
        cls += activeStages[s.id] ? " active passed" : "";
      }
      g.setAttribute("class", cls);
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      var stateWord = activeStages[s.id] ? "active" : (s.kind === "terminal" ? "inactive" : "not on path");
      g.setAttribute("aria-label", s.label + " stage, " + stateWord + ". " + s.description);
      g.addEventListener("focusin", function () { showStageInfo(s, activeStages[s.id]); });
      g.addEventListener("click", function () { showStageInfo(s, activeStages[s.id]); });
      g.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showStageInfo(s, activeStages[s.id]); }
      });

      var rect = document.createElementNS(SVGNS, "rect");
      rect.setAttribute("x", p.x); rect.setAttribute("y", p.y);
      rect.setAttribute("width", p.w); rect.setAttribute("height", p.h);
      rect.setAttribute("rx", "6");
      g.appendChild(rect);

      var label = document.createElementNS(SVGNS, "text");
      label.setAttribute("x", p.x + p.w / 2); label.setAttribute("y", p.y + (s.kind === "terminal" ? 18 : 20));
      label.setAttribute("text-anchor", "middle");
      wrapText(label, s.label, p.w - 8, SVGNS, p.x + p.w / 2);
      g.appendChild(label);

      if (activeStages[s.id]) {
        var mark = document.createElementNS(SVGNS, "text");
        mark.setAttribute("x", p.x + p.w / 2); mark.setAttribute("y", p.y + p.h - 6);
        mark.setAttribute("text-anchor", "middle");
        mark.setAttribute("class", "stage-sub");
        mark.textContent = "● active";
        g.appendChild(mark);
      }
      svg.appendChild(g);
    });

    wrap.appendChild(svg);

    if (HAS_D3) {
      // Use D3 selections purely to confirm/attach the active-edge emphasis;
      // rendering is identical either way, so this stays a progressive layer.
      try { window.d3.select(svg).selectAll("path.edge.active").attr("marker-end", null); } catch (e) { /* noop */ }
    }

    // textual path (always present, screen-reader friendly)
    renderTextualPath(res);
  }

  function wrapText(textEl, str, maxWidth, ns, cx) {
    // Simple two-line wrap for long terminal labels.
    var words = str.split(" ");
    if (words.length <= 2 || str.length <= 12) { textEl.textContent = str; return; }
    var mid = Math.ceil(words.length / 2);
    var line1 = words.slice(0, mid).join(" ");
    var line2 = words.slice(mid).join(" ");
    var t1 = document.createElementNS(ns, "tspan");
    t1.setAttribute("x", cx); t1.setAttribute("dy", "0"); t1.textContent = line1;
    var t2 = document.createElementNS(ns, "tspan");
    t2.setAttribute("x", cx); t2.setAttribute("dy", "13"); t2.textContent = line2;
    textEl.appendChild(t1); textEl.appendChild(t2);
  }

  function diagramAriaLabel(res) {
    return "Rule-execution path: " + res.path_stages.join(" then ") +
      ". Terminal result: " + res.result_state + ". This diagram shows the order of public-source reading rules, not any hidden reasoning.";
  }

  function renderTextualPath(res) {
    var box = el("path-textual");
    box.innerHTML = "";
    var h = document.createElement("h3");
    h.textContent = "Rule-execution path (text)";
    box.appendChild(h);
    var ol = document.createElement("ol");
    var stageById = {};
    model.stages.forEach(function (s) { stageById[s.id] = s; });
    res.path_stages.forEach(function (sid, i) {
      var li = document.createElement("li");
      li.textContent = stageById[sid] ? stageById[sid].label : sid;
      if (i < res.path_transitions.length) {
        var t = model.transitions.filter(function (x) { return x.id === res.path_transitions[i]; })[0];
        if (t) {
          var span = document.createElement("span");
          span.className = "tstep";
          span.textContent = " → " + t.id + ": " + t.condition;
          li.appendChild(span);
        }
      }
      ol.appendChild(li);
    });
    box.appendChild(ol);
  }

  function showStageInfo(stage, active) {
    var box = el("stage-info");
    box.textContent = stage.label + " — " + stage.description +
      (stage.kind === "terminal"
        ? (active ? " This is the terminal reached for the current inputs." : " Not the terminal reached for the current inputs.")
        : (active ? " On the current rule-execution path." : " Not reached for the current inputs."));
  }

  // -------------------------------------------------------------------------
  // Result panel
  // -------------------------------------------------------------------------
  function labelForScope(id) {
    var c = model.claim_scopes.filter(function (x) { return x.id === id; })[0];
    return c ? c.label : id;
  }
  function resultStateMeta(id) {
    return model.result_states.filter(function (x) { return x.id === id; })[0] || { label: id, meaning: "" };
  }

  function renderResult(res, exampleTitle) {
    // result state
    var rs = resultStateMeta(res.result_state);
    var rsBox = el("result-state");
    rsBox.className = "result-state state-" + res.result_state;
    rsBox.innerHTML = "";
    var rl = document.createElement("span");
    rl.className = "rs-label"; rl.textContent = rs.label;
    var rt = document.createElement("span");
    rt.textContent = "(" + res.result_state + ")";
    var rm = document.createElement("span");
    rm.className = "rs-meaning"; rm.textContent = rs.meaning;
    rsBox.appendChild(rl); rsBox.appendChild(rt); rsBox.appendChild(rm);

    // scope
    var scopeBox = el("scope-line");
    scopeBox.innerHTML = "Maximum claim scope: ";
    var sc = document.createElement("span");
    sc.className = "scope-id";
    sc.textContent = res.maximum_claim_scope ? labelForScope(res.maximum_claim_scope) + " (" + res.maximum_claim_scope + ")" : "none";
    scopeBox.appendChild(sc);

    fillTokenList("allowed-list", res.allowed_claims, "allow", "No allowed public-source claim at this scope.");
    fillTokenList("blocked-list", res.blocked_claims, "block", "No blocked claims recorded.");
    fillTokenList("limitation-list", res.required_limitation_language, "limitation", "No required limitation language for these inputs.");

    // flags — show all defined flags, mark which are on (non-color-only via data-on + text)
    var flagsBox = el("flags-list");
    flagsBox.innerHTML = "";
    model.uncertainty_flags.forEach(function (f) {
      var on = res.uncertainty_flags.indexOf(f.id) !== -1;
      var li = document.createElement("li");
      li.setAttribute("data-on", String(on));
      li.textContent = (on ? "● " : "○ ") + f.id + (on ? " (present)" : " (absent)");
      flagsBox.appendChild(li);
    });

    renderSourceRules(res);
    renderTextSummary(res, exampleTitle);
  }

  function fillTokenList(id, items, cls, emptyMsg) {
    var ul = el(id);
    ul.innerHTML = "";
    if (!items.length) {
      var note = document.createElement("li");
      note.className = "empty-note"; note.textContent = emptyMsg;
      ul.appendChild(note);
      return;
    }
    items.forEach(function (t) {
      var li = document.createElement("li");
      li.className = cls; li.textContent = t;
      ul.appendChild(li);
    });
  }

  function renderSourceRules(res) {
    var box = el("source-rules");
    box.innerHTML = "";
    var byId = {};
    model.source_rules.forEach(function (s) { byId[s.id] = s; });
    if (!res.source_rules_used.length) {
      var p = document.createElement("p");
      p.className = "empty-note"; p.textContent = "No source rules referenced for these inputs.";
      box.appendChild(p);
      return;
    }
    res.source_rules_used.forEach(function (id) {
      var sr = byId[id];
      if (!sr) return;
      var det = document.createElement("details");
      var sum = document.createElement("summary");
      sum.textContent = sr.id + " — " + sr.file;
      det.appendChild(sum);
      var body = document.createElement("div");
      body.className = "sr-body";
      var dl = document.createElement("dl");
      dl.appendChild(dt("Rule")); dl.appendChild(dd(sr.id));
      dl.appendChild(dt("File")); dl.appendChild(ddCode(sr.file));
      if (sr.section_heading) { dl.appendChild(dt("Section")); dl.appendChild(dd(sr.section_heading)); }
      if (sr.json_pointer) { dl.appendChild(dt("JSON pointer")); dl.appendChild(ddCode(sr.json_pointer)); }
      dl.appendChild(dt("Supports")); dl.appendChild(dd(sr.supports));
      dl.appendChild(dt("Does not establish")); dl.appendChild(dd(sr.does_not_establish));
      body.appendChild(dl);
      det.appendChild(body);
      box.appendChild(det);
    });
  }
  function dt(t) { var e = document.createElement("dt"); e.textContent = t; return e; }
  function dd(t) { var e = document.createElement("dd"); e.textContent = t; return e; }
  function ddCode(t) { var e = document.createElement("dd"); var c = document.createElement("code"); c.textContent = t; e.appendChild(c); return e; }

  function renderTextSummary(res, exampleTitle) {
    var lines = [];
    if (exampleTitle) lines.push("Example: " + exampleTitle);
    lines.push("Selected inputs:");
    lines.push("  source_access_state    = " + res.input.source_access_state);
    lines.push("  boundary_loaded        = " + res.input.boundary_loaded);
    lines.push("  classification_evidence= " + res.input.classification_evidence);
    lines.push("  relation_evidence      = " + res.input.relation_evidence);
    lines.push("  version_evidence       = " + res.input.version_evidence);
    lines.push("");
    lines.push("Result state: " + res.result_state);
    lines.push("Maximum claim scope: " + (res.maximum_claim_scope || "none"));
    lines.push("Rule-execution path: " + res.path_stages.join(" -> "));
    lines.push("");
    lines.push("Allowed claims:");
    (res.allowed_claims.length ? res.allowed_claims : ["(none)"]).forEach(function (a) { lines.push("  + " + a); });
    lines.push("Blocked claims:");
    (res.blocked_claims.length ? res.blocked_claims : ["(none)"]).forEach(function (b) { lines.push("  - " + b); });
    lines.push("Uncertainty flags present: " + (res.uncertainty_flags.length ? res.uncertainty_flags.join(", ") : "(none)"));
    lines.push("Required limitation language:");
    (res.required_limitation_language.length ? res.required_limitation_language : ["(none)"]).forEach(function (l) { lines.push("  * " + l); });
    lines.push("Source rules used: " + (res.source_rules_used.length ? res.source_rules_used.join(", ") : "(none)"));
    lines.push("");
    lines.push("Note: unresolved means insufficient public evidence, not system failure.");
    lines.push("Authorial confirmation is an authority boundary, not a confidence score.");
    el("text-summary-pre").textContent = lines.join("\n");
  }

  // -------------------------------------------------------------------------
  function recompute(exampleTitle) {
    var res = evaluate(model, input);
    renderDiagram(res);
    renderResult(res, exampleTitle);
  }

  function showLoadError(msg) {
    var box = el("load-error");
    box.textContent = msg;
    box.className = "load-error show";
  }

  function init() {
    // fill static non-authority statements + boundary
    var na = el("non-authority");
    if (na && model.non_authority_statements) {
      model.non_authority_statements.forEach(function (s) {
        var li = document.createElement("li"); li.textContent = s; na.appendChild(li);
      });
    }
    el("d3-status").textContent = HAS_D3
      ? "D3 v7 loaded: interactive flow diagram active."
      : "D3 unavailable (offline or blocked): the diagram uses a plain-DOM fallback and the full result stays readable as text below.";
    buildControls();
    input = defaultInput();
    syncControls();
    recompute();
    el("app-loading").style.display = "none";
    el("app-body").hidden = false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    fetch("machine-reading-state-machine.json").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      model = data;
      init();
    }).catch(function (e) {
      showLoadError("Could not load machine-reading-state-machine.json (" + e.message +
        "). Serve this directory over HTTP (see README) and reload. The static boundary statements above remain valid.");
      el("app-loading").textContent = "Data failed to load. See the message above.";
    });
  });
})();
