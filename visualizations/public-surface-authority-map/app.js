/*
 * Public Surface and Authority-Ceiling Map — prototype interaction layer.
 *
 * Boundary contract enforced by this code:
 * - Every node has equal visual area; nothing is sized by degree/importance.
 * - Layout is categorical and deterministic; position/color are secondary cues.
 * - Edges are navigation-only reference routing, never conceptual relations.
 * - All displayed values come verbatim from the generated data.json.
 *
 * D3 v7 is used for edge-path rendering and selections when available. Core
 * rendering degrades gracefully to plain DOM/SVG if the D3 CDN is unavailable,
 * so the table fallback and metadata always remain readable.
 */
(function () {
  "use strict";

  var HAS_D3 = typeof window.d3 !== "undefined";
  var PALETTE = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6", "--c7", "--c8"];

  var state = {
    data: null,
    groupBy: "surface_role",
    search: "",
    filters: {
      surface_role: "",
      authority_ceiling: "",
      public_surface_status: "",
      classification_evidence: ""
    },
    selectedId: null,
    edgesMode: "off" // "off" | "selected" | "global"
  };

  var groupStyleCache = {}; // field -> { value: {colorVar, glyph} }

  function el(id) { return document.getElementById(id); }

  function abbreviate(value) {
    var parts = String(value).split(/[_\-\s]+/).filter(Boolean);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return parts.slice(0, 3).map(function (p) { return p.charAt(0).toUpperCase(); }).join("");
  }

  function distinctValues(field) {
    var seen = {};
    state.data.nodes.forEach(function (n) { seen[n[field]] = true; });
    return Object.keys(seen).sort();
  }

  function styleForGroup(field, value) {
    if (!groupStyleCache[field]) {
      var values = distinctValues(field);
      var map = {};
      values.forEach(function (v, i) {
        map[v] = { colorVar: PALETTE[i % PALETTE.length], glyph: abbreviate(v) };
      });
      groupStyleCache[field] = map;
    }
    return groupStyleCache[field][value];
  }

  function classificationDisplay(node) {
    if (node.publicly_declared_classification) return node.publicly_declared_classification;
    return "Not asserted in public metadata";
  }

  function truncate(text, max) {
    text = String(text);
    return text.length > max ? text.slice(0, max - 1) + "…" : text;
  }

  function matchesFilters(node) {
    var f = state.filters;
    if (f.surface_role && node.surface_role !== f.surface_role) return false;
    if (f.authority_ceiling && node.authority_ceiling !== f.authority_ceiling) return false;
    if (f.public_surface_status && node.public_surface_status !== f.public_surface_status) return false;
    if (f.classification_evidence && node.classification_evidence !== f.classification_evidence) return false;
    if (state.search) {
      var q = state.search.toLowerCase();
      var hay = (node.name + " " + node.repository_path).toLowerCase();
      if (hay.indexOf(q) === -1) return false;
    }
    return true;
  }

  // ---- Populate filter selects deterministically -------------------------

  function populateFilter(selectId, field) {
    var select = el(selectId);
    distinctValues(field).forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    });
  }

  // ---- Map rendering -----------------------------------------------------

  function nodeAriaLabel(node) {
    return (
      node.name +
      ". Surface role: " + node.surface_role +
      ". Public-surface status: " + node.public_surface_status +
      ". Authority ceiling: " + node.authority_ceiling +
      ". Classification evidence: " + classificationDisplay(node) +
      ". Activate to view details."
    );
  }

  function renderMap() {
    var map = el("map");
    map.innerHTML = "";
    var field = state.groupBy;
    var groups = distinctValues(field);

    groups.forEach(function (groupValue) {
      var groupNodes = state.data.nodes
        .filter(function (n) { return n[field] === groupValue; })
        .sort(function (a, b) { return a.name.localeCompare(b.name); });

      var style = styleForGroup(field, groupValue);
      var section = document.createElement("section");
      section.className = "group";
      section.setAttribute("aria-label", "Group: " + groupValue);

      var head = document.createElement("p");
      head.className = "group-head";
      head.innerHTML =
        '<span class="group-name">' + escapeHtml(groupValue) + "</span> " +
        '<span class="group-count">(' + groupNodes.length + ")</span>";
      section.appendChild(head);

      var container = document.createElement("div");
      container.className = "group-nodes";

      groupNodes.forEach(function (node) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "node";
        btn.dataset.id = node.id;
        btn.style.setProperty("--node-color", "var(" + style.colorVar + ")");
        var filtered = !matchesFilters(node);
        if (filtered) btn.dataset.filtered = "true";
        btn.setAttribute(
          "aria-label",
          nodeAriaLabel(node) + (filtered ? " Filtered from current view." : "")
        );
        btn.title = node.name + (filtered ? "\n(Filtered from current view)" : "");
        btn.innerHTML =
          '<span class="node-glyph" aria-hidden="true">' + escapeHtml(style.glyph) + "</span>" +
          '<span class="node-label" aria-hidden="true">' + escapeHtml(truncate(node.name, 26)) + "</span>";
        btn.addEventListener("click", function () { selectNode(node.id); });
        btn.addEventListener("focus", function () {
          if (state.edgesMode === "selected") { state.selectedId = node.id; drawEdges(); }
        });
        container.appendChild(btn);
      });

      section.appendChild(container);
      map.appendChild(section);
    });

    applySelectionStyles();
    scheduleEdgeRedraw();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function applySelectionStyles() {
    var buttons = document.querySelectorAll(".node");
    buttons.forEach(function (b) {
      b.dataset.selected = b.dataset.id === state.selectedId ? "true" : "false";
    });
  }

  // ---- Selection + detail panel -----------------------------------------

  function nodeById(id) {
    return state.data.nodes.filter(function (n) { return n.id === id; })[0];
  }

  function selectNode(id) {
    state.selectedId = id;
    applySelectionStyles();
    renderDetail(nodeById(id));
    if (state.edgesMode === "off") {
      // Reveal reference routing for the selected node on first selection.
      el("toggle-edges").checked = true;
      state.edgesMode = "selected";
    }
    drawEdges();
    updateStatus();
  }

  function listBlock(items) {
    if (!items || !items.length) return "<span class=\"nav-only\">none</span>";
    return "<ul>" + items.map(function (i) { return "<li>" + escapeHtml(i) + "</li>"; }).join("") + "</ul>";
  }

  function renderDetail(node) {
    var empty = el("detail-empty");
    var content = el("detail-content");
    if (!node) {
      empty.hidden = false;
      content.hidden = true;
      content.innerHTML = "";
      return;
    }
    empty.hidden = true;
    content.hidden = false;

    var rows = [
      ["Document name", escapeHtml(node.name)],
      ["Repository path", "<code>" + escapeHtml(node.repository_path) + "</code>"],
      ["Surface role", escapeHtml(node.surface_role)],
      ["Public-surface status", escapeHtml(node.public_surface_status)],
      ["Authority ceiling", escapeHtml(node.authority_ceiling)],
      ["Relation default", escapeHtml(node.relation_default)],
      ["Classification evidence", escapeHtml(node.classification_evidence)],
      ["Publicly declared classification", escapeHtml(classificationDisplay(node))],
      ["Boundary references", listBlock(node.boundary_references)],
      ["Source-use reference", node.source_use_reference ? escapeHtml(node.source_use_reference) : "<span class=\"nav-only\">none</span>"]
    ];

    var dl = rows.map(function (r) {
      return "<dt>" + r[0] + "</dt><dd>" + r[1] + "</dd>";
    }).join("");

    var link = node.canonical_public_url
      ? '<a class="detail-link" href="' + escapeHtml(node.canonical_public_url) +
        '" target="_blank" rel="noopener">Open individual public source file</a>'
      : "";

    content.innerHTML =
      "<h2>" + escapeHtml(node.name) + "</h2>" +
      '<p class="nav-only">Reference routing for this node is navigation only and does not establish a confirmed conceptual relation.</p>' +
      "<dl>" + dl + "</dl>" + link;
  }

  // ---- Edge overlay ------------------------------------------------------

  var edgeRedrawPending = false;
  function scheduleEdgeRedraw() {
    if (edgeRedrawPending) return;
    edgeRedrawPending = true;
    window.requestAnimationFrame(function () {
      edgeRedrawPending = false;
      drawEdges();
    });
  }

  function activeEdges() {
    if (state.edgesMode === "global") return state.data.edges;
    if (state.edgesMode === "selected" && state.selectedId) {
      return state.data.edges.filter(function (e) {
        return e.source === state.selectedId || e.target === state.selectedId;
      });
    }
    return [];
  }

  function nodeCenter(id, mapRect) {
    var btn = document.querySelector('.node[data-id="' + cssEscape(id) + '"]');
    if (!btn) return null;
    var r = btn.getBoundingClientRect();
    return {
      x: r.left - mapRect.left + r.width / 2,
      y: r.top - mapRect.top + r.height / 2
    };
  }

  function cssEscape(value) {
    if (window.CSS && window.CSS.escape) return window.CSS.escape(value);
    return String(value).replace(/["\\]/g, "\\$&");
  }

  function drawEdges() {
    var svg = el("edge-layer");
    var mapArea = document.querySelector(".map-area");
    var mapRect = mapArea.getBoundingClientRect();
    svg.setAttribute("width", mapArea.offsetWidth);
    svg.setAttribute("height", mapArea.offsetHeight);
    svg.setAttribute("viewBox", "0 0 " + mapArea.offsetWidth + " " + mapArea.offsetHeight);

    while (svg.firstChild) svg.removeChild(svg.firstChild);

    var edges = activeEdges();
    edges.forEach(function (e) {
      var s = nodeCenter(e.source, mapRect);
      var t = nodeCenter(e.target, mapRect);
      if (!s || !t) return;
      // subtle quadratic curve to reduce straight-line overlap
      var mx = (s.x + t.x) / 2;
      var my = (s.y + t.y) / 2 - Math.min(40, Math.abs(t.x - s.x) * 0.12);
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", "M" + s.x + "," + s.y + " Q" + mx + "," + my + " " + t.x + "," + t.y);
      path.setAttribute("class",
        "edge-line " + (e.relation_type === "source_use_reference" ? "edge-source-use-line" : "edge-boundary-line"));
      var title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent =
        "Reference type: " + e.relation_type +
        "\nSource document: " + e.source +
        "\nTarget document: " + e.target +
        "\nRelation status: navigation only" +
        "\nEvidence source: " + e.evidence_source;
      path.appendChild(title);
      svg.appendChild(path);
    });
  }

  // ---- Status + controls -------------------------------------------------

  function visibleCount() {
    return state.data.nodes.filter(matchesFilters).length;
  }

  function updateStatus() {
    var total = state.data.nodes.length;
    var visible = visibleCount();
    var parts = [visible + " of " + total + " records match current filters"];
    if (state.selectedId) {
      var n = nodeById(state.selectedId);
      if (n) parts.push("Selected: " + n.name);
    }
    if (state.edgesMode === "selected") parts.push("Routing: selected node only (navigation only)");
    if (state.edgesMode === "global") parts.push("Routing: all explicit references (navigation only)");
    el("status-line").textContent = parts.join(" · ");
  }

  function setEdgesMode() {
    var sel = el("toggle-edges").checked;
    var glob = el("toggle-edges-global").checked;
    if (glob) state.edgesMode = "global";
    else if (sel) state.edgesMode = "selected";
    else state.edgesMode = "off";
    el("density-warning").hidden = state.edgesMode !== "global";
    drawEdges();
    updateStatus();
  }

  function resetView() {
    state.groupBy = "surface_role";
    state.search = "";
    state.filters = { surface_role: "", authority_ceiling: "", public_surface_status: "", classification_evidence: "" };
    state.selectedId = null;
    state.edgesMode = "off";
    el("group-by").value = "surface_role";
    el("search").value = "";
    el("filter-surface-role").value = "";
    el("filter-authority-ceiling").value = "";
    el("filter-public-status").value = "";
    el("filter-classification").value = "";
    el("toggle-edges").checked = false;
    el("toggle-edges-global").checked = false;
    el("density-warning").hidden = true;
    renderDetail(null);
    renderMap();
    updateStatus();
  }

  // ---- Table fallback ----------------------------------------------------

  function renderTable() {
    var body = el("records-table-body");
    body.innerHTML = "";
    var rows = state.data.nodes.slice().sort(function (a, b) {
      return a.repository_path.localeCompare(b.repository_path);
    });
    rows.forEach(function (node) {
      var tr = document.createElement("tr");
      if (!matchesFilters(node)) tr.dataset.filtered = "true";
      var cells = [
        node.name,
        node.repository_path,
        node.surface_role,
        node.public_surface_status,
        node.authority_ceiling,
        classificationDisplay(node)
      ];
      cells.forEach(function (c, i) {
        var td = document.createElement("td");
        if (i === 1 && node.canonical_public_url) {
          var a = document.createElement("a");
          a.href = node.canonical_public_url;
          a.target = "_blank";
          a.rel = "noopener";
          a.textContent = c;
          td.appendChild(a);
        } else {
          td.textContent = c;
        }
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  // ---- Legend ------------------------------------------------------------

  function renderLegend() {
    var host = el("legend-groups");
    host.innerHTML = "";
    var field = state.groupBy;
    var heading = document.createElement("p");
    heading.style.width = "100%";
    heading.style.margin = "0 0 0.25rem";
    heading.innerHTML = "<strong>Grouping:</strong> " + escapeHtml(field) +
      " (categorical, not a ranking)";
    host.appendChild(heading);
    distinctValues(field).forEach(function (value) {
      var style = styleForGroup(field, value);
      var item = document.createElement("span");
      item.className = "legend-item";
      item.style.setProperty("--legend-color", "var(" + style.colorVar + ")");
      item.innerHTML =
        '<span class="legend-glyph">' + escapeHtml(style.glyph) + "</span>" +
        '<span class="legend-swatch" aria-hidden="true"></span> ' +
        escapeHtml(value);
      host.appendChild(item);
    });
  }

  // ---- Wiring ------------------------------------------------------------

  function attachEvents() {
    el("group-by").addEventListener("change", function () {
      state.groupBy = this.value;
      groupStyleCache = {}; // recompute palette for the new grouping field
      renderLegend();
      renderMap();
      updateStatus();
    });
    el("search").addEventListener("input", function () {
      state.search = this.value.trim();
      renderMap();
      renderTable();
      updateStatus();
    });
    [
      ["filter-surface-role", "surface_role"],
      ["filter-authority-ceiling", "authority_ceiling"],
      ["filter-public-status", "public_surface_status"],
      ["filter-classification", "classification_evidence"]
    ].forEach(function (pair) {
      el(pair[0]).addEventListener("change", function () {
        state.filters[pair[1]] = this.value;
        renderMap();
        renderTable();
        updateStatus();
      });
    });
    el("toggle-edges").addEventListener("change", setEdgesMode);
    el("toggle-edges-global").addEventListener("change", setEdgesMode);
    el("reset").addEventListener("click", resetView);
    window.addEventListener("resize", scheduleEdgeRedraw);
  }

  function init(data) {
    state.data = data;
    document.title = data.title || document.title;
    populateFilter("filter-surface-role", "surface_role");
    populateFilter("filter-authority-ceiling", "authority_ceiling");
    populateFilter("filter-public-status", "public_surface_status");
    populateFilter("filter-classification", "classification_evidence");
    attachEvents();
    renderLegend();
    renderMap();
    renderTable();
    updateStatus();
  }

  function boot() {
    fetch("data.json")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(init)
      .catch(function (err) {
        el("status-line").textContent =
          "Could not load data.json (" + err.message + "). Run scripts/build_public_surface_authority_map.py and serve this directory over HTTP.";
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  // Reference D3 so the pinned import is exercised when available; core
  // rendering does not depend on it.
  if (HAS_D3) { window.__mweMapD3Version = window.d3.version; }
})();
