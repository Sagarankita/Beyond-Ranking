const CATALOG = {
  synthetic: {
    title: "Synthetic method fixture",
    version: "phase7-synthetic-v1",
    badge: "Synthetic · not empirical",
    banner: "Method fixture only — allocations and KPI responses are illustrative synthetic outputs and must not be presented as observed institutional effects.",
    root: "data/synthetic/",
    manifest: "manifest.json",
    files: {
      portfolio: "strategy_portfolio.csv",
      allocations: "current_vs_strategy_allocations.csv",
      kpis: "current_vs_strategy_kpis.csv",
      utilization: "resource_utilization.csv",
      constraints: "constraint_checks.csv",
      robustness: "scenario_robustness.csv",
      assumptions: "assumption_sensitivity.csv",
      candidates: "reoptimized_candidates.csv",
      algorithms: "algorithm_comparison.csv"
    },
    artifacts: [
      ["Strategy portfolio", "strategy_portfolio.csv", "Selected saved strategies and rules"],
      ["Allocation comparison", "current_vs_strategy_allocations.csv", "Current and recommended decision values"],
      ["KPI intervals", "current_vs_strategy_kpis.csv", "Persisted predictions and uncertainty"],
      ["Constraint ledger", "constraint_checks.csv", "Named residuals and pass status"],
      ["Scenario robustness", "scenario_robustness.csv", "Monte Carlo scenario assessments"],
      ["Assumption sensitivity", "assumption_sensitivity.csv", "Saved uncertainty sensitivity"],
      ["Manifest", "manifest.json", "Hashes, rules, environment and evidence boundary"]
    ]
  },
  mixed: {
    title: "Public + synthetic VJTI scenario",
    version: "vjti_public_plus_synthetic_experiments_v1",
    badge: "Mixed evidence · scenario",
    banner: "Public evidence calibrates this package, but intervention responses remain synthetic scenario predictions. No causal or observed improvement claim is supported.",
    root: "data/mixed/",
    manifest: "experiment_manifest.json",
    files: {
      allocations: "strategy_allocations.csv",
      kpis: "strategy_kpis.csv",
      utilization: "strategy_resource_summary.csv",
      constraints: "strategy_constraints.csv",
      robustness: "strategy_uncertainty.csv",
      candidates: "pooled_reference_front.csv",
      objectives: "strategy_objectives.csv",
      algorithms: "algorithm_summary.csv",
      evidence: "kpi_evidence_registry.csv",
      checks: "independent_checks.csv"
    },
    artifacts: [
      ["Strategy allocations", "strategy_allocations.csv", "Long-form saved allocation decisions"],
      ["KPI intervals", "strategy_kpis.csv", "Associational predictions and intervals"],
      ["Resource summary", "strategy_resource_summary.csv", "Cost, budget and effort feasibility"],
      ["Constraint ledger", "strategy_constraints.csv", "Named evaluator residuals"],
      ["Strategy uncertainty", "strategy_uncertainty.csv", "Common-draw uncertainty summary"],
      ["Pooled reference front", "pooled_reference_front.csv", "Saved multi-objective frontier"],
      ["Experiment manifest", "experiment_manifest.json", "Frozen protocol, hashes and claims"]
    ]
  },
  empirical: {
    title: "Empirical public evidence",
    version: "vjti-ceit-public-plus-synthetic-v1",
    badge: "Observed + derived · descriptive",
    banner: "Descriptive public evidence only — there is no empirical intervention-response model or empirical optimization run in this package.",
    root: "data/empirical/",
    manifest: "manifest.json",
    files: {
      coverage: "provenance_coverage.csv",
      sources: "source_register.csv",
      publicOnly: "public_only_sensitivity.csv",
      evidence: "kpi_evidence_registry.csv"
    },
    artifacts: [
      ["Provenance coverage", "provenance_coverage.csv", "Field-level observed, derived and synthetic coverage"],
      ["Source register", "source_register.csv", "Authoritative public source inventory"],
      ["Public-only sensitivity", "public_only_sensitivity.csv", "Descriptive denominator checks"],
      ["KPI evidence registry", "kpi_evidence_registry.csv", "Model support and claim boundaries"],
      ["Public data manifest", "manifest.json", "File and source hashes"]
    ]
  }
};

const state = { mode: "synthetic", data: null, strategy: null, cache: new Map() };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const human = (value) => String(value ?? "").replace(/^policy_/, "").replaceAll("__", " · ").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const pct = (value, digits = 0) => `${(number(value) * 100).toFixed(digits)}%`;
const money = (value) => {
  const n = number(value);
  const sign = n < 0 ? "−" : "";
  const absolute = Math.abs(n);
  if (absolute >= 1e7) return `${sign}₹${(absolute / 1e7).toFixed(2)} Cr`;
  if (absolute >= 1e5) return `${sign}₹${(absolute / 1e5).toFixed(1)} L`;
  return `${sign}₹${absolute.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
};
const fmt = (value, name = "") => {
  const n = number(value);
  if (/budget|funding|support$|cost|remaining/i.test(name) && Math.abs(n) > 1000) return money(n);
  if (Math.abs(n) >= 1000) return n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
  if (Math.abs(n) < 1 && n !== 0) return n.toFixed(3);
  return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
};

function parseCSV(text) {
  const rows = [];
  let row = [], value = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i], next = text[i + 1];
    if (char === '"' && quoted && next === '"') { value += '"'; i++; }
    else if (char === '"') quoted = !quoted;
    else if (char === "," && !quoted) { row.push(value); value = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") i++;
      row.push(value); value = "";
      if (row.some(cell => cell !== "")) rows.push(row);
      row = [];
    } else value += char;
  }
  if (value || row.length) { row.push(value); rows.push(row); }
  const headers = rows.shift() || [];
  return rows.map(values => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

async function fetchText(url) {
  if (state.cache.has(url)) return state.cache.get(url);
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url} (${response.status})`);
  const text = await response.text();
  state.cache.set(url, text);
  return text;
}

async function loadMode(mode) {
  const config = CATALOG[mode];
  const entries = await Promise.all(Object.entries(config.files).map(async ([key, file]) => [key, parseCSV(await fetchText(config.root + file))]));
  const manifest = JSON.parse(await fetchText(config.root + config.manifest));
  return { ...Object.fromEntries(entries), manifest };
}

function strategiesFor(mode, data) {
  if (mode === "synthetic") return [...new Set(data.allocations.map(row => row.strategy))];
  if (mode === "mixed") return [...new Set(data.allocations.filter(row => row.strategy_type === "policy_selection").map(row => row.strategy_id))];
  return [];
}

async function setMode(mode) {
  state.mode = mode;
  state.data = null;
  state.strategy = null;
  $$(".lens").forEach(button => button.classList.toggle("active", button.dataset.mode === mode));
  $("#loading").hidden = false;
  $("#dashboard").hidden = true;
  $("#error").hidden = true;
  updateHeader();
  try {
    state.data = await loadMode(mode);
    const strategies = strategiesFor(mode, state.data);
    state.strategy = strategies.includes("balanced") ? "balanced" : strategies.includes("policy_balanced") ? "policy_balanced" : strategies[0] || null;
    render();
    $("#loading").hidden = true;
    $("#dashboard").hidden = false;
  } catch (error) {
    $("#loading").hidden = true;
    $("#error").hidden = false;
    $("#error").innerHTML = `<b>Artifact snapshot could not be loaded.</b><br>${esc(error.message)}`;
  }
}

function updateHeader() {
  const config = CATALOG[state.mode];
  $("#page-title").textContent = config.title;
  $("#version-select").innerHTML = `<option>${esc(config.version)}</option>`;
  $("#manifest-download").href = config.root + config.manifest;
  const banner = $("#evidence-banner");
  banner.className = `evidence-banner ${state.mode}`;
  banner.innerHTML = `<span class="banner-tag">${esc(config.badge)}</span><span>${esc(config.banner)}</span>`;
}

function render() {
  renderStrategySelect();
  renderOverview();
  renderAllocations();
  renderKpis();
  renderConstraints();
  renderPareto();
  renderRobustness();
  renderEvidence();
  renderProvenance();
}

function renderStrategySelect() {
  const strategies = strategiesFor(state.mode, state.data);
  const label = $("#strategy-label");
  label.style.display = strategies.length ? "grid" : "none";
  $("#strategy-select").innerHTML = strategies.map(value => `<option value="${esc(value)}" ${value === state.strategy ? "selected" : ""}>${esc(human(value))}</option>`).join("");
}

function summaryCards(items) {
  $("#summary-cards").innerHTML = items.map(item => `
    <article class="summary-card">
      <p class="kicker">${esc(item.kicker)}</p>
      <span class="number">${esc(item.value)}${item.delta ? `<small class="delta">${esc(item.delta)}</small>` : ""}</span>
      <span class="label">${esc(item.label)}</span>
    </article>`).join("");
}

function renderOverview() {
  const d = state.data, mode = state.mode;
  let cards, interpretation, claims, meta;
  if (mode === "synthetic") {
    const algorithms = new Set(d.algorithms.map(row => row.algorithm)).size;
    const selected = d.portfolio.filter(row => row.selection_status === "selected");
    const util = d.utilization.find(row => row.strategy === state.strategy) || d.utilization[1];
    const passing = d.constraints.filter(row => row.strategy === state.strategy && row.passed === "True").length;
    const total = d.constraints.filter(row => row.strategy === state.strategy).length;
    cards = [
      { kicker: "Saved strategies", value: selected.length, label: "Post-optimization portfolio views" },
      { kicker: "Compared methods", value: algorithms, label: "Matched-budget benchmark algorithms" },
      { kicker: "Budget utilization", value: pct(util?.budget_utilization), label: "Selected saved strategy" },
      { kicker: "Constraints", value: `${passing}/${total}`, label: "Named checks passed" }
    ];
    interpretation = [
      ["Reproducible comparison", "All views are read directly from versioned reporting artifacts."],
      ["Supported objective", "Research is the only meaningfully modeled benefit family in this fixture."],
      ["Portfolio caution", "Several named policies resolve to the same allocation; labels do not imply unique solutions."],
      ["No causal inference", "Predicted changes are methodological outputs, not measured department outcomes."]
    ];
    claims = ["Synthetic method fixture", "Illustrative reference allocation", "Approximate pooled Pareto front", "No institution-specific claim"];
    meta = [d.manifest.report_id, d.manifest.portfolio_scenario, `${d.manifest.unique_selected_allocations} unique allocation`];
  } else if (mode === "mixed") {
    const strategies = strategiesFor(mode, d).length;
    const algorithms = d.algorithms.length;
    const scenarios = new Set(d.utilization.map(row => row.scenario).filter(value => value !== "base")).size;
    const selected = d.utilization.find(row => row.strategy_id === state.strategy);
    cards = [
      { kicker: "Policy views", value: strategies, label: "Saved base-scenario selections" },
      { kicker: "Compared methods", value: algorithms, label: "Frozen matched-budget experiment" },
      { kicker: "Stress scenarios", value: scenarios, label: "Held-fixed and reoptimized pairs" },
      { kicker: "Selected cost", value: money(selected?.total_cost), label: `Remaining ${money(selected?.budget_remaining)}` }
    ];
    interpretation = [
      ["Publicly calibrated", "Observed and derived public values inform the fixture baseline."],
      ["Synthetic responses", "Every intervention-response KPI model is generator-validated, not empirically fitted."],
      ["Frozen protocol", "The experiment protocol was fixed before the pilot and records matched candidate evaluations."],
      ["Scenario use only", "Selections compare plausible trade-offs; they do not forecast causal improvement."]
    ];
    claims = [d.manifest.claims?.prediction, d.manifest.claims?.causal, d.manifest.claims?.dea, "All independent checks passed"];
    meta = [d.manifest.analysis_id, `${d.manifest.completed_comparison_runs}/${d.manifest.declared_comparison_runs} runs`, `${d.manifest.matched_candidate_evaluations} evaluations/run`];
  } else {
    const sourceCount = d.sources.length;
    const observed = d.coverage.filter(row => row.provenance === "observed_public").reduce((sum, row) => sum + number(row.count), 0);
    const derived = d.coverage.filter(row => row.provenance === "derived_public").reduce((sum, row) => sum + number(row.count), 0);
    cards = [
      { kicker: "Public sources", value: sourceCount, label: "Registered authoritative documents" },
      { kicker: "Observed records", value: observed, label: "Coverage entries marked observed_public" },
      { kicker: "Derived records", value: derived, label: "Coverage entries marked derived_public" },
      { kicker: "Empirical runs", value: "0", label: "No intervention-response optimization" }
    ];
    interpretation = [
      ["Descriptive evidence", "Public records support baseline context and selected outcome descriptions."],
      ["Traceable sources", "Each downloaded source has authority, period, access date and SHA-256 metadata."],
      ["Mixed package boundary", "Synthetic-calibrated fields exist separately and never become empirical observations."],
      ["No optimizer result", "This lane intentionally shows no recommended allocation or predicted KPI response."]
    ];
    claims = ["Observed and derived facts only", "No causal effect estimate", "No empirical intervention model", "No recommended allocation"];
    meta = [d.manifest.package_id, d.manifest.evidence_status, `${sourceCount} source snapshots`];
  }
  summaryCards(cards);
  $("#snapshot-meta").innerHTML = meta.filter(Boolean).map(value => `<span class="meta-chip">${esc(value)}</span>`).join("");
  $("#interpretation").innerHTML = interpretation.map(([title, body]) => `<div class="interpretation-item"><b>${esc(title)}</b><p>${esc(body)}</p></div>`).join("");
  $("#claim-status").innerHTML = `<div class="claim-stack">${claims.filter(Boolean).map(item => `<div class="claim-row"><i>✓</i><span>${esc(item)}</span></div>`).join("")}</div>`;
}

function allocationRows() {
  const d = state.data;
  if (state.mode === "synthetic") return d.allocations.filter(row => row.strategy === state.strategy).map(row => ({ name: row.variable, unit: row.unit, current: number(row.current), recommended: number(row.recommended) }));
  if (state.mode === "mixed") {
    const current = new Map(d.allocations.filter(row => row.strategy_id === "current").map(row => [row.decision, number(row.value)]));
    return d.allocations.filter(row => row.strategy_id === state.strategy).map(row => ({ name: row.decision, unit: "", current: current.get(row.decision) ?? 0, recommended: number(row.value) }));
  }
  return [];
}

function renderAllocations() {
  const rows = allocationRows();
  if (!rows.length) {
    $("#allocation-chart").innerHTML = empty("No empirical allocation recommendation exists", "The evidence-only package intentionally contains no optimization result.");
    $("#utilization").innerHTML = empty("Not applicable", "Utilization requires a saved allocation.");
    return;
  }
  $("#allocation-chart").innerHTML = `<div class="legend"><span><i class="current"></i>Current</span><span><i class="recommended"></i>${esc(human(state.strategy))}</span></div>` + rows.map(row => {
    const max = Math.max(Math.abs(row.current), Math.abs(row.recommended), 1);
    const delta = row.recommended - row.current;
    return `<div class="allocation-row">
      <div class="allocation-name"><b>${esc(human(row.name))}</b><small>${esc(row.unit || "saved decision unit")}</small></div>
      <div class="bar-pair"><div class="bar-track"><div class="bar current" style="width:${Math.max(1, Math.abs(row.current) / max * 100)}%"></div></div><div class="bar-track"><div class="bar recommended" style="width:${Math.max(1, Math.abs(row.recommended) / max * 100)}%"></div></div></div>
      <div class="allocation-value"><b>${esc(fmt(row.recommended, row.name))}</b><small class="${delta >= 0 ? "positive" : "negative"}">${delta >= 0 ? "+" : ""}${esc(fmt(delta, row.name))}</small></div>
    </div>`;
  }).join("");

  let util;
  if (state.mode === "synthetic") {
    const row = state.data.utilization.find(item => item.strategy === state.strategy);
    util = [
      ["Budget", number(row?.budget_utilization), `${money(row?.cost)} of ${money(row?.budget_limit)}`],
      ["Research FTE", number(row?.research_fte_utilization), `${fmt(row?.research_fte)} of ${fmt(row?.research_fte_capacity)} FTE`]
    ];
  } else {
    const row = state.data.utilization.find(item => item.strategy_id === state.strategy);
    const budget = number(row?.total_cost) + number(row?.budget_remaining);
    util = [
      ["Budget", budget ? number(row?.total_cost) / budget : 0, `${money(row?.total_cost)} of ${money(budget)}`],
      ["Faculty effort", Math.min(1, number(row?.allocated_faculty_fte) / 10), `${fmt(row?.allocated_faculty_fte)} FTE allocated`]
    ];
  }
  $("#utilization").innerHTML = util.map(([label, value, detail]) => `<div class="util-block"><div class="util-head"><span>${esc(label)}</span><b>${pct(value, 1)}</b></div><div class="util-track"><i class="${value > 1 ? "warn" : ""}" style="width:${Math.min(100, value * 100)}%"></i></div><div class="util-foot">${esc(detail)}</div></div>`).join("");
}

function kpiRows() {
  const d = state.data;
  if (state.mode === "synthetic") return d.kpis.filter(row => row.strategy === state.strategy).map(row => ({ name: row.kpi, current: number(row.current_prediction), prediction: number(row.recommended_prediction), lower: number(row.recommended_lower), upper: number(row.recommended_upper), delta: number(row.predicted_difference) }));
  if (state.mode === "mixed") {
    const current = new Map(d.kpis.filter(row => row.strategy_id === "current").map(row => [row.kpi, row]));
    return d.kpis.filter(row => row.strategy_id === state.strategy).map(row => ({ name: row.kpi, current: number(current.get(row.kpi)?.prediction), prediction: number(row.prediction), lower: number(row.lower), upper: number(row.upper), delta: number(row.prediction) - number(current.get(row.kpi)?.prediction) }));
  }
  return [];
}

function renderKpis() {
  const rows = kpiRows();
  if (!rows.length) { $("#kpi-chart").innerHTML = empty("No empirical KPI response intervals", "Public descriptive outcomes are shown in Evidence status, not as modeled intervention responses."); return; }
  $("#kpi-chart").innerHTML = rows.map(row => {
    const min = Math.min(row.lower, row.current, 0), max = Math.max(row.upper, row.current, 1), span = max - min || 1;
    const left = (row.lower - min) / span * 100, width = (row.upper - row.lower) / span * 100, point = (row.prediction - min) / span * 100, current = (row.current - min) / span * 100;
    return `<div class="kpi-row"><div class="kpi-name"><b>${esc(human(row.name))}</b><small>Saved prediction interval</small></div><div class="interval-track"><i class="interval-axis"></i><i class="interval" style="left:${left}%;width:${Math.max(1,width)}%"></i><i class="interval-current" style="left:${current}%" title="Current ${row.current}"></i><i class="interval-point" style="left:${point}%"></i></div><div class="kpi-values"><b>${esc(fmt(row.prediction, row.name))}</b><small>${esc(fmt(row.lower, row.name))}–${esc(fmt(row.upper, row.name))} · <span class="${row.delta >= 0 ? "positive" : "negative"}">${row.delta >= 0 ? "+" : ""}${esc(fmt(row.delta, row.name))}</span></small></div></div>`;
  }).join("");
}

function constraintRows() {
  if (state.mode === "synthetic") return state.data.constraints.filter(row => row.strategy === state.strategy).map(row => ({ name: row.constraint, residual: number(row.residual), passed: row.passed === "True", source: state.strategy }));
  if (state.mode === "mixed") return state.data.constraints.filter(row => row.strategy_id === state.strategy).map(row => ({ name: row.constraint, residual: number(row.residual), passed: number(row.residual) <= 1e-9, source: row.source_artifact }));
  return [];
}

function renderConstraints() {
  const rows = constraintRows();
  const passed = rows.filter(row => row.passed).length;
  $("#constraint-tally").innerHTML = rows.length ? `<span class="pass">${passed} passed</span><span class="fail">${rows.length - passed} failed</span>` : `<span class="pass">Evidence-only lane</span>`;
  if (!rows.length) { $("#constraints-table").innerHTML = empty("No allocation constraints to evaluate", "This lane contains descriptive public evidence only."); return; }
  const sorted = [...rows].sort((a,b) => Number(a.passed) - Number(b.passed) || Math.abs(b.residual) - Math.abs(a.residual));
  $("#constraints-table").innerHTML = `<table><thead><tr><th>Constraint</th><th>Residual</th><th>Status</th><th>Source</th></tr></thead><tbody>${sorted.map(row => `<tr><td>${esc(human(row.name))}</td><td><code>${esc(row.residual.toExponential(2))}</code></td><td><span class="status-badge ${row.passed ? "pass" : "fail"}">${row.passed ? "● Passed" : "● Failed"}</span></td><td>${esc(human(row.source))}</td></tr>`).join("")}</tbody></table>`;
}

function renderPareto() {
  if (state.mode === "empirical") {
    $("#tradeoff-copy").textContent = "An empirical Pareto frontier is not available because no empirical intervention-response evaluator exists.";
    $("#pareto-chart").innerHTML = empty("No empirical Pareto front", "A frontier would imply modeled intervention responses that this evidence package does not support.");
    return;
  }
  let points, selected, xLabel, yLabel;
  if (state.mode === "synthetic") {
    points = state.data.candidates.filter(row => row.scenario_id === "budget_base_20m").map(row => ({ x: number(row.cost) / 1e6, y: number(row.objective_benefit__research) }));
    selected = state.data.portfolio.filter(row => row.strategy === state.strategy && row.selection_status === "selected").map(row => ({ x: number(row.cost) / 1e6, y: number(row.objective_benefit__research) }));
    xLabel = "Cost · INR millions"; yLabel = "Research benefit";
    $("#tradeoff-copy").textContent = "Cost is a reporting dimension; research benefit is the supported objective in this synthetic fixture.";
  } else {
    points = state.data.candidates.map(row => ({ x: -number(row.objective__research), y: -number(row.objective__student_development) }));
    selected = state.data.objectives.filter(row => row.strategy_id === state.strategy && ["research", "student_development"].includes(row.objective)).reduce((acc,row) => { const item = acc[0] || {x:0,y:0}; if (row.objective === "research") item.x = number(row.benefit); else item.y = number(row.benefit); return [item]; }, []);
    xLabel = "Research benefit"; yLabel = "Student-development benefit";
    $("#tradeoff-copy").textContent = "The persisted pooled reference front is shown in benefit space; all four families are synthetic scenario responses.";
  }
  $("#pareto-chart").innerHTML = scatterSvg(points, selected, xLabel, yLabel);
}

function scatterSvg(points, selected, xLabel, yLabel) {
  if (!points.length) return empty("No saved frontier points", "The selected artifact contains no candidates.");
  const width = 920, height = 410, left = 66, right = 24, top = 25, bottom = 58;
  const xs = points.map(p=>p.x).concat(selected.map(p=>p.x)), ys = points.map(p=>p.y).concat(selected.map(p=>p.y));
  let xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
  if (xmin === xmax) xmax += 1; if (ymin === ymax) ymax += 1;
  const sx = x => left + (x-xmin)/(xmax-xmin)*(width-left-right), sy = y => top + (ymax-y)/(ymax-ymin)*(height-top-bottom);
  const ticks = [0,.25,.5,.75,1];
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Pareto trade-off scatter plot">${ticks.map(t=>{const x=left+t*(width-left-right), y=top+t*(height-top-bottom); return `<line class="grid-line" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}"/><line class="grid-line" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}"/><text class="axis-label" x="${x}" y="${height-bottom+20}" text-anchor="middle">${fmt(xmin+t*(xmax-xmin))}</text><text class="axis-label" x="${left-12}" y="${height-bottom-t*(height-top-bottom)+3}" text-anchor="end">${fmt(ymin+t*(ymax-ymin))}</text>`}).join("")}<line class="axis-line" x1="${left}" y1="${height-bottom}" x2="${width-right}" y2="${height-bottom}"/><line class="axis-line" x1="${left}" y1="${top}" x2="${left}" y2="${height-bottom}"/>${points.map(p=>`<circle class="point" cx="${sx(p.x)}" cy="${sy(p.y)}" r="4"/>`).join("")}${selected.map(p=>`<circle class="point selected" cx="${sx(p.x)}" cy="${sy(p.y)}" r="7"/>`).join("")}<text class="axis-label" x="${(left+width-right)/2}" y="${height-10}" text-anchor="middle">${esc(xLabel)}</text><text class="axis-label" x="15" y="${height/2}" text-anchor="middle" transform="rotate(-90 15 ${height/2})">${esc(yLabel)}</text></svg><div class="plot-note"><span class="status-badge pass">● Saved candidates</span> <span class="status-badge fail">● Selected strategy</span></div>`;
}

function renderRobustness() {
  if (state.mode === "empirical") {
    $("#robustness-chart").innerHTML = empty("No intervention robustness run", "Public-only denominator checks remain available below.");
    const rows = state.data.publicOnly;
    $("#assumptions").innerHTML = `<div class="assumption-list">${rows.map(row => `<div class="assumption"><b><span>${esc(human(row.outcome))}</span><span>${esc(fmt(row.rate))}</span></b><p>Descriptive ratio using ${esc(human(row.denominator))}; causal claim: ${esc(row.causal_claim)}</p></div>`).join("")}</div>`;
    return;
  }
  let rows, assumptions;
  if (state.mode === "synthetic") {
    rows = state.data.robustness.filter(row => row.assumption_id === "base" && row.assessment_mode === "reoptimized" && row.policy === state.strategy).slice(0,8).map(row => ({ name: row.assessed_scenario_id, probability: number(row.probability_feasible) }));
    const selected = state.data.assumptions.filter(row => row.assessment_mode === "reoptimized" && row.policy === state.strategy && row.assessed_scenario_id === "budget_base_20m");
    assumptions = selected.map(row => ({ name: row.assumption_id, body: `Uncertainty ×${row.prediction_uncertainty_scale}; cost CV ${pct(row.unit_cost_coefficient_of_variation)}; feasible ${pct(row.probability_feasible,1)}` }));
  } else {
    rows = state.data.robustness.filter(row => row.strategy_id === state.strategy || row.strategy_id.endsWith("__reoptimized")).slice(0,9).map(row => ({ name: row.strategy_id, probability: number(row.feasibility_probability) }));
    assumptions = [
      { name: "Common uncertainty draws", body: `${state.data.robustness[0]?.draws || 0} matched draws from ${state.data.robustness[0]?.draw_artifact || "saved artifact"}.` },
      { name: "Frozen comparison", body: `${state.data.manifest.completed_comparison_runs} completed runs with ${state.data.manifest.matched_candidate_evaluations} evaluations each.` },
      { name: "No causal interpretation", body: state.data.manifest.claims?.causal || "No causal claim." }
    ];
  }
  $("#robustness-chart").innerHTML = rows.map(row => `<div class="robust-row"><b>${esc(human(row.name))}</b><div class="probability-track"><i class="${row.probability < .95 ? "risk" : ""}" style="width:${Math.max(1,row.probability*100)}%"></i></div><code>${pct(row.probability,1)}</code></div>`).join("");
  $("#assumptions").innerHTML = `<div class="assumption-list">${assumptions.slice(0,6).map(item => `<div class="assumption"><b><span>${esc(human(item.name))}</span></b><p>${esc(item.body)}</p></div>`).join("")}</div>`;
}

function renderEvidence() {
  let items;
  if (state.mode === "synthetic") {
    items = [
      ["Research impact", "Synthetic response model", "synthetic", "Meaningfully supported within this method fixture; not institution-specific."],
      ["Innovation", "Unsupported", "unsupported", "Score is retained for schema completeness but lacks evidence-backed response behavior."],
      ["Student development", "Unsupported", "unsupported", "No supported departmental response model in the synthetic fixture."],
      ["Societal contribution", "Unsupported", "unsupported", "No supported departmental response model in the synthetic fixture."],
      ["Reference allocation", "Illustrative", "synthetic", "Current values are illustrative rather than observed institutional allocations."],
      ["Benchmark conclusion", "Method comparison", "synthetic", "Results compare algorithms on one fixture and do not establish a generally best method."]
    ];
  } else {
    const registry = state.data.evidence;
    items = registry.map(row => [human(row.kpi), human(row.status), row.status === "unsupported" ? "unsupported" : row.status === "public_descriptive" ? "" : "synthetic", row.claim_boundary]);
  }
  $("#evidence-grid").innerHTML = items.map(([title,type,tone,body]) => `<article class="evidence-item"><header><h3>${esc(title)}</h3><span class="evidence-type ${esc(tone)}">${esc(type)}</span></header><p>${esc(body)}</p></article>`).join("");
}

function artifactHash(file) {
  const manifest = state.data.manifest;
  if (state.mode === "synthetic") {
    if (file === "manifest.json") return manifest.config_sha256;
    const match = Object.values(manifest.source_artifacts || {}).find(item => String(item.path).endsWith(file));
    return match?.sha256 || "Declared in report manifest";
  }
  if (state.mode === "mixed") return manifest.artifact_hashes?.[file] || (file === "experiment_manifest.json" ? manifest.config_sha256 : "Declared in experiment package");
  return manifest.generated_files?.[file] || (file === "manifest.json" ? manifest.config_sha256 : "Declared in public data package");
}

function renderProvenance() {
  const config = CATALOG[state.mode];
  $("#provenance-list").innerHTML = config.artifacts.map(([name,file,description]) => `<div class="artifact-row"><div><b>${esc(name)}</b><small>${esc(description)}</small></div><div class="artifact-hash" title="${esc(artifactHash(file))}">SHA-256 · ${esc(artifactHash(file))}</div><a class="download-link" href="${esc(config.root + file)}" download>Download ↓</a></div>`).join("");
}

function empty(title, body) {
  return `<div class="empty-state"><div><span>○</span><b>${esc(title)}</b><p>${esc(body)}</p></div></div>`;
}

$("#strategy-select").addEventListener("change", event => { state.strategy = event.target.value; render(); });
$$(".lens").forEach(button => button.addEventListener("click", () => {
  $(".sidebar").classList.remove("open");
  setMode(button.dataset.mode);
}));
$(".mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
$$(".nav a").forEach(link => link.addEventListener("click", () => {
  $$(".nav a").forEach(item => item.classList.toggle("active", item === link));
  $(".sidebar").classList.remove("open");
}));

setMode("synthetic");
