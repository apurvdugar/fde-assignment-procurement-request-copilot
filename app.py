from __future__ import annotations

import json
import os
from pathlib import Path
import streamlit as st

from src.solution import handle_request
from src.data_access import load_employees, load_budgets
from src.llm_client import get_llm_config

ROOT = Path(__file__).resolve().parent
REQUESTS = json.loads((ROOT / "data" / "requests.json").read_text(encoding="utf-8"))
BY_ID = {r["request_id"]: r for r in REQUESTS}

EMPLOYEES = load_employees().set_index("employee_id").to_dict("index")
BUDGETS = load_budgets().set_index("department").to_dict("index")

st.set_page_config(
    page_title="AI Procurement Request Copilot",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for executive polish
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 12px;
    }
    .badge-approved { background-color: #dcfce7; color: #166534; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem; }
    .badge-review { background-color: #fef9c3; color: #854d0e; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem; }
    .badge-danger { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem; }
    .badge-flag { background-color: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; padding: 3px 8px; border-radius: 6px; font-size: 0.8rem; margin-right: 6px; }
    .approval-pill { background-color: #e0e7ff; color: #3730a3; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem; margin-right: 6px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar
st.sidebar.title("🛡️ Procurement Copilot")
st.sidebar.caption("Enterprise AI Intake & Policy Engine")

request_id = st.sidebar.selectbox(
    "Select Purchase Request",
    list(BY_ID.keys()),
    format_func=lambda rid: f"{rid} - {BY_ID[rid]['product_name']}",
)
architecture = st.sidebar.radio(
    "Architecture",
    ["single", "staged"],
    format_func=lambda a: "Architecture A: Single-Agent Baseline" if a == "single" else "Architecture B: Staged Two-Agent",
)

llm_cfg = get_llm_config()
if llm_cfg["api_key"]:
    st.sidebar.success(f"OpenRouter connected: `{llm_cfg['model']}`")
else:
    st.sidebar.info("Deterministic fallback engine active (No API key found in `.env`)")

st.sidebar.divider()
st.sidebar.markdown(
    """
    **Design Principles**
    - **AI**: Interpret context & recommend
    - **Code**: Thresholds & deterministic checks
    - **Human**: Sensitive approvals & exceptions
    """
)

req = BY_ID[request_id]
emp_info = EMPLOYEES.get(req.get("requester_id", ""), {})
dept_name = emp_info.get("department", "Unknown")
dept_budget = BUDGETS.get(dept_name, {})

# Header
st.title(f"Purchase Request: {req['product_name']}")
st.caption(f"Request ID: `{req['request_id']}` • Submitted by {emp_info.get('name', 'Unknown')} ({dept_name}) • Policy Reference Date: `2026-09-30`")

col_left, col_right = st.columns([1.05, 0.95], gap="large")

with col_left:
    st.subheader("📋 Request Details")
    with st.container():
        c1, c2, c3 = st.columns(3)
        c1.metric("Vendor", req.get("vendor_name", "N/A"))
        cost_val = req.get("annual_cost_usd")
        c2.metric("Annual Cost", f"${cost_val:,.2f}" if cost_val is not None else "Unspecified")
        seats = req.get("user_count")
        c3.metric("Seats / Users", f"{seats}" if seats is not None else "Unspecified")

    st.markdown("**Business Justification:**")
    st.info(f"“{req.get('business_justification', 'No justification provided.')}”")

    st.markdown("**Operational Metadata:**")
    m1, m2 = st.columns(2)
    with m1:
        st.write(f"• **Category:** `{req.get('category', 'N/A')}`")
        st.write(f"• **Data Access Level:** `{req.get('data_access_level', 'N/A')}`")
    with m2:
        st.write(f"• **Urgency:** `{req.get('urgency', 'normal')}`")
        ints = req.get("requested_integrations", [])
        st.write(f"• **Integrations:** {', '.join([f'`{i}`' for i in ints]) if ints else 'None'}")

    st.markdown("**Department Budget Profile:**")
    if dept_budget:
        b1, b2, b3 = st.columns(3)
        b1.write(f"Total: **${dept_budget.get('annual_software_budget_usd', 0):,.0f}**")
        b2.write(f"Committed: **${dept_budget.get('committed_usd', 0):,.0f}**")
        b3.write(f"Available: **${dept_budget.get('available_usd', 0):,.0f}**")

with col_right:
    st.subheader("🤖 Copilot Recommendation")

    run_btn = st.button("Run Intake Analysis", type="primary", use_container_width=True)

    if run_btn or f"res_{request_id}_{architecture}" in st.session_state:
        if run_btn:
            with st.spinner(f"Analyzing via {architecture} architecture..."):
                result = handle_request(request_id, architecture=architecture)
                st.session_state[f"res_{request_id}_{architecture}"] = result
        else:
            result = st.session_state[f"res_{request_id}_{architecture}"]

        # Recommendation Banner
        has_critical = any(f in result.risk_flags for f in ["budget_insufficient", "prompt_injection_detected", "missing_information"])
        badge_style = "badge-danger" if has_critical else ("badge-review" if result.risk_flags else "badge-approved")
        
        st.markdown(
            f"""
            <div class="metric-card">
                <span class="{badge_style}">RECOMMENDATION</span>
                <p style="margin-top: 8px; font-size: 1.05rem; font-weight: 500;">{result.recommendation}</p>
                <hr style="margin: 8px 0;"/>
                <small style="color: #64748b;"><strong>Next Action:</strong> {result.next_step}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Required Approvals
        st.markdown("**Required Approval Chain:**")
        if result.required_approvals:
            pills = "".join([f'<span class="approval-pill">✓ {appr}</span>' for appr in result.required_approvals])
            st.markdown(f"<div>{pills}</div>", unsafe_allow_html=True)
        else:
            st.write("None specified")

        # Missing Information
        if result.missing_information:
            st.warning(f"⚠️ **Missing Information Required:** {', '.join(result.missing_information)}")

        # Risk Flags
        st.markdown("**Identified Risk & Policy Signals:**")
        if result.risk_flags:
            flag_spans = "".join([f'<span class="badge-flag">🏷️ {flag}</span>' for flag in result.risk_flags])
            st.markdown(f"<div style='margin-bottom: 12px;'>{flag_spans}</div>", unsafe_allow_html=True)
        else:
            st.success("No compliance or risk flags triggered.")

        # Telemetry
        if result.telemetry:
            st.caption(
                f"⚡ Telemetry: **{result.telemetry.llm_calls}** LLM call(s) • **{result.telemetry.tool_calls}** Tool call(s) • Tools: {', '.join(result.telemetry.tool_names)}"
            )

    else:
        st.info("Click **'Run Intake Analysis'** to evaluate this purchase request against policy, budget, catalog, and vendor status.")

st.divider()

# Evidence Panel
st.subheader("🔍 Grounded Evidence Dossier")
if f"res_{request_id}_{architecture}" in st.session_state:
    res = st.session_state[f"res_{request_id}_{architecture}"]
    
    t1, t2, t3 = st.tabs(["Audited Findings", "Raw JSON Contract", "Human Review Handoff"])
    with t1:
        for idx, item in enumerate(res.evidence, 1):
            with st.expander(f"{idx}. [{item.source}] {item.finding[:80]}...", expanded=True):
                st.write(f"**Finding:** {item.finding}")
                if item.reference:
                    st.caption(f"Source Reference: `{item.reference}`")
    with t2:
        st.json(res.model_dump())
    with t3:
        st.markdown("### Human Decision Console")
        st.caption("Policy Principle: The AI recommends next actions, but humans retain final purchasing authority.")
        
        act1, act2, act3, act4 = st.columns(4)
        if act1.button("✅ Approve Request", use_container_width=True):
            st.success(f"Request {request_id} approved for processing by Human Reviewer.")
        if act2.button("❌ Reject Request", use_container_width=True):
            st.error(f"Request {request_id} rejected by Human Reviewer.")
        if act3.button("📩 Request Clarification", use_container_width=True):
            st.warning(f"Clarification ticket opened with employee {req.get('requester_id')}.")
        if act4.button("⚡ Escalate Exception", use_container_width=True):
            st.info(f"Request {request_id} escalated to Finance & Executive Committee.")
else:
    st.write("Run the analysis above to inspect grounded evidence from budget, catalog, vendor API, and policy engines.")
