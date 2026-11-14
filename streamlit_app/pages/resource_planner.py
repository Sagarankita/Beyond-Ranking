from __future__ import annotations

from typing import Any

import streamlit as st

from streamlit_app.api.client import DashboardApiError
from streamlit_app.components.live import (
    candidate_label,
    manifest_download,
    render_evidence_strip,
    render_reference_and_candidate,
)
from streamlit_app.components.ui import page_header, panel_heading
from streamlit_app.data.adapters import title_case
from streamlit_app.pages.live_state import api_client, api_unavailable


def _preset_options(defaults: dict[str, Any]) -> dict[str, dict[str, Any]]:
    base = {
        "budget_limit": float(defaults["defaults"]["budget_limit"]),
        "faculty_total": float(defaults["defaults"]["faculty_total"]),
        "cost_multipliers": {},
    }
    presets = {"Base reference": base}
    for raw in defaults["presets"]:
        value = {**base, "cost_multipliers": {}}
        if "budget_limit" in raw:
            value["budget_limit"] = float(raw["budget_limit"])
        if "faculty_total" in raw:
            value["faculty_total"] = float(raw["faculty_total"])
        value["cost_multipliers"] = dict(raw.get("cost_multiplier", {}))
        presets[title_case(raw["name"])] = value
    return presets


def _initialize_inputs(defaults: dict[str, Any]) -> None:
    st.session_state.setdefault("planner_budget_crore", float(defaults["defaults"]["budget_limit"]) / 10_000_000)
    st.session_state.setdefault("planner_faculty", float(defaults["defaults"]["faculty_total"]))
    st.session_state.setdefault("planner_algorithm", "nsga2")
    st.session_state.setdefault("planner_seed", 18001)
    for variable in defaults["decision_variables"]:
        if variable["cost_mode"] != "non_monetary":
            st.session_state.setdefault(f"multiplier_{variable['name']}", 1.0)


def _apply_preset(preset: dict[str, Any], defaults: dict[str, Any]) -> None:
    st.session_state["planner_budget_crore"] = float(preset["budget_limit"]) / 10_000_000
    st.session_state["planner_faculty"] = float(preset["faculty_total"])
    for variable in defaults["decision_variables"]:
        if variable["cost_mode"] != "non_monetary":
            st.session_state[f"multiplier_{variable['name']}"] = float(
                preset["cost_multipliers"].get(variable["name"], 1.0)
            )


def _overrides(defaults: dict[str, Any]) -> dict[str, Any]:
    multipliers = {}
    for variable in defaults["decision_variables"]:
        if variable["cost_mode"] == "non_monetary":
            continue
        value = float(st.session_state[f"multiplier_{variable['name']}"])
        if abs(value - 1.0) > 1e-12:
            multipliers[variable["name"]] = value
    return {
        "budget_limit": float(st.session_state["planner_budget_crore"]) * 10_000_000,
        "budget_unit": "INR",
        "faculty_total": float(st.session_state["planner_faculty"]),
        "faculty_unit": "annual FTE",
        "cost_multipliers": multipliers,
    }


def _render_errors(errors: dict[str, str]) -> None:
    st.error("The scenario needs correction before it can run.")
    for field, message in errors.items():
        st.markdown(f"- **{title_case(field)}:** {message}")


def _run(client, defaults: dict[str, Any], overrides: dict[str, Any]) -> None:
    validation = client.validate(overrides)
    st.session_state["br_validation"] = validation
    if not validation.get("valid"):
        _render_errors(validation.get("field_errors", {}))
        return

    request = {
        "track_id": defaults["track_id"],
        "overrides": overrides,
        "algorithm": st.session_state["planner_algorithm"],
        "seed": int(st.session_state["planner_seed"]),
        "evaluation_budget": int(defaults["interactive_evaluation_budget"]),
    }
    status = client.create_run(request)
    status_box = st.status("Optimization queued", expanded=True)

    def update(current: dict[str, Any]) -> None:
        phase = title_case(current.get("phase", current["status"]))
        status_box.update(label=f"Run status: {phase}", state="running")

    if status["status"] in {"queued", "running"}:
        status = client.wait_for_run(status["run_id"], on_status=update)
    st.session_state["br_run_status"] = status
    st.session_state["br_validation"] = validation
    if status["status"] == "complete":
        candidates = client.candidates(status["run_id"])
        st.session_state["br_candidates"] = candidates
        if candidates:
            st.session_state["br_selected_candidate_id"] = candidates[0]["candidate_id"]
            status_box.update(
                label=f"Complete: {len(candidates)} feasible strategies revalidated",
                state="complete",
                expanded=False,
            )
        else:
            status_box.update(label="Complete: no feasible solution found", state="error")
    elif status["status"] in {"failed", "interrupted"}:
        status_box.update(label=f"Run {status['status']}", state="error")
        error = status.get("error") or {}
        st.error(error.get("message", "The run did not complete."))
        if error.get("fields"):
            _render_errors(error["fields"])
    else:
        status_box.update(label="Run is still active. Use Refresh status below.", state="running")


def render() -> None:
    page_header(
        "Validated live planning",
        "Resource Planner",
        "Edit supported scenario inputs, run one approved optimizer, and inspect only independently revalidated feasible strategies.",
    )
    try:
        client = api_client()
        defaults = client.defaults()
    except DashboardApiError as exc:
        api_unavailable(exc)
        return

    _initialize_inputs(defaults)
    presets = _preset_options(defaults)
    render_evidence_strip()

    controls, results = st.columns([0.82, 1.45], gap="large")
    with controls:
        panel_heading(
            "Scenario inputs",
            "Configure a supported run",
            "Defaults and bounds come from the versioned backend configuration.",
        )
        preset_name = st.selectbox("Scenario preset", list(presets), key="planner_preset")
        if st.button("Apply preset", width="stretch"):
            _apply_preset(presets[preset_name], defaults)
            st.rerun()

        with st.form("planner_form"):
            st.number_input(
                "Available budget (₹ crore)",
                min_value=0.1,
                step=0.1,
                key="planner_budget_crore",
                help="Converted to exact INR before validation. This is a scenario limit, not observed spending.",
            )
            st.number_input(
                "Available faculty capacity (annual FTE)",
                min_value=0.1,
                step=0.25,
                key="planner_faculty",
                help="Includes the fixed teaching floor and controllable effort allocations.",
            )

            with st.expander("Advanced cost assumptions"):
                st.caption("Multipliers change configured costs only. Decision bounds, floors, dependencies, and KPI rules remain read-only.")
                for variable in defaults["decision_variables"]:
                    if variable["cost_mode"] == "non_monetary":
                        continue
                    st.number_input(
                        f"{title_case(variable['name'])} cost multiplier",
                        min_value=0.1,
                        max_value=10.0,
                        step=0.05,
                        key=f"multiplier_{variable['name']}",
                        help=f"Evidence: {variable['provenance']}. Base unit: {variable['unit']}.",
                    )

            st.selectbox(
                "Algorithm",
                options=list(defaults["algorithms"]),
                format_func=lambda value: value.upper().replace("_", " "),
                key="planner_algorithm",
            )
            st.number_input("Reproducibility seed", min_value=0, step=1, key="planner_seed")
            st.caption(f"Interactive mode uses exactly {defaults['interactive_evaluation_budget']} candidate evaluations. This is not a statistical algorithm comparison.")
            validate_clicked = st.form_submit_button("Validate inputs", width="stretch")
            run_clicked = st.form_submit_button("Run optimization", type="primary", width="stretch")

        overrides = _overrides(defaults)
        try:
            if validate_clicked:
                st.session_state["br_validation"] = client.validate(overrides)
            if run_clicked:
                _run(client, defaults, overrides)
        except DashboardApiError as exc:
            if exc.fields:
                _render_errors(exc.fields)
            else:
                st.error(f"{exc.code}: {exc}")

        validation = st.session_state.get("br_validation")
        if validation:
            if validation.get("valid"):
                st.success("Inputs are valid for the canonical evaluator.")
                st.caption(f"Scenario hash: `{validation['scenario_hash']}`")
            else:
                _render_errors(validation.get("field_errors", {}))

        with st.expander("Read-only model constraints"):
            commitments = defaults["service_commitments"]
            st.write(f"Minimum teaching: {commitments['minimum_teaching_fte']} annual FTE")
            st.write(f"Minimum student support: {commitments['minimum_student_support_fte']} annual FTE")
            st.write(f"Minimum service: {commitments['minimum_service_fte']} annual FTE")
            st.caption("Variable bounds, increments, integrality, dependencies, and conservative KPI services are enforced by the backend and cannot be edited here.")

    with results:
        panel_heading(
            "Run output",
            "Validated strategies",
            "Select a feasible archive candidate to inspect exact allocations, trade-offs, constraints, and uncertainty.",
        )
        status = st.session_state.get("br_run_status")
        candidates = st.session_state.get("br_candidates", [])
        validation = st.session_state.get("br_validation")

        if status and status["status"] in {"queued", "running"}:
            if st.button("Refresh run status", width="stretch"):
                try:
                    refreshed = client.run_status(status["run_id"])
                    st.session_state["br_run_status"] = refreshed
                    if refreshed["status"] == "complete":
                        st.session_state["br_candidates"] = client.candidates(status["run_id"])
                    st.rerun()
                except DashboardApiError as exc:
                    st.error(str(exc))

        if not candidates:
            if status and status.get("result") == "no_feasible_solution":
                st.warning("The run completed but produced no feasible archive candidates. Adjust the supported scenario inputs and run again.")
            else:
                st.info("No live strategies yet. Validate the scenario, then run optimization.")
            if validation and validation.get("valid"):
                render_reference_and_candidate(validation, None, show_kpis=False)
            return

        labels = {candidate_label(item, index): item["candidate_id"] for index, item in enumerate(candidates)}
        selected_id = st.selectbox(
            "Selected validated strategy",
            options=list(labels.values()),
            format_func=lambda value: next(label for label, item_id in labels.items() if item_id == value),
            key="br_selected_candidate_id",
        )
        candidate = next(item for item in candidates if item["candidate_id"] == selected_id)
        st.success(f"Feasible and independently revalidated · {len(candidates)} candidate(s) available")
        if candidate.get("support_flags"):
            active_warnings = [
                name
                for name, active in candidate["support_flags"].items()
                if active is True or (isinstance(active, list) and len(active) > 0)
            ]
            if active_warnings:
                st.warning("Model-support warning: " + ", ".join(title_case(name) for name in active_warnings))

        if validation and validation.get("valid"):
            render_reference_and_candidate(validation, candidate)
        if status:
            manifest_download(status, candidate)
