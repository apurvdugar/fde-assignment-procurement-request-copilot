from __future__ import annotations

import json
from typing import Any
from src.contracts import ProcurementDecision, RunTelemetry, EvidenceItem
from src.telemetry import RunTelemetryCounter
from src.tools.budget_tool import check_department_budget
from src.tools.catalog_tool import check_software_catalog
from src.tools.vendor_tool import check_vendor_status
from src.tools.policy_tool import (
    validate_request_information,
    detect_prompt_injection,
    evaluate_policy_requirements,
)
from src.llm_client import call_llm


def run_staged_agents(request: dict[str, Any]) -> ProcurementDecision:
    """Architecture B: Staged / Two-agent variant.
    Stage 1: Procurement Analyst gathers evidence and creates an Evidence Pack.
    Stage 2: Policy & Risk Reviewer audits the pack against procurement policy and produces the final decision.
    """
    counter = RunTelemetryCounter()
    req_id = request.get("request_id", "REQ-UNKNOWN")
    evidence: list[EvidenceItem] = []
    risk_flags_set: set[str] = set()

    # =========================================================================
    # STAGE 1: PROCUREMENT ANALYST (Evidence Gathering & Need Analysis)
    # =========================================================================
    counter.record_tool_call("check_department_budget")
    budget_res = check_department_budget(request.get("requester_id", ""), request.get("annual_cost_usd"))
    evidence.extend(budget_res.get("evidence", []))
    risk_flags_set.update(budget_res.get("risk_flags", []))

    counter.record_tool_call("check_software_catalog")
    catalog_res = check_software_catalog(
        request.get("product_name", ""),
        request.get("vendor_name", ""),
        request.get("category"),
    )
    evidence.extend(catalog_res.get("evidence", []))
    risk_flags_set.update(catalog_res.get("risk_flags", []))

    counter.record_tool_call("check_vendor_status")
    vendor_res = check_vendor_status(request.get("vendor_name", ""))
    evidence.extend(vendor_res.get("evidence", []))
    risk_flags_set.update(vendor_res.get("risk_flags", []))

    counter.record_tool_call("validate_request_information")
    missing_info, miss_flags, miss_ev = validate_request_information(request)
    evidence.extend(miss_ev)
    risk_flags_set.update(miss_flags)

    counter.record_tool_call("detect_prompt_injection")
    _, inj_flags, inj_ev = detect_prompt_injection(request.get("business_justification", ""))
    evidence.extend(inj_ev)
    risk_flags_set.update(inj_flags)

    # Analyst LLM Call: Compile structured evidence summary
    analyst_prompt = f"""
You are the Procurement Analyst (Agent 1 of 2).
Analyze the incoming request and raw evidence:
- Request: {req_id} ({request.get('product_name')})
- Vendor: {request.get('vendor_name')}
- Stated justification: {request.get('business_justification')}
- Budget status: {budget_res.get('status')}
- Catalog overlap: {catalog_res.get('has_overlap')}
- Vendor security state: {vendor_res.get('registry', {}).get('security_status')}

Summarize the operational need and factual findings into an analyst brief.
Respond in JSON format: {{"analyst_summary": "...", "key_findings": ["..."]}}
"""
    counter.record_llm_call()
    analyst_output = call_llm(analyst_prompt, system_prompt="You are an enterprise Procurement Analyst compiling evidence.", response_json=True)
    analyst_summary = ""
    if analyst_output:
        try:
            parsed = json.loads(analyst_output)
            analyst_summary = parsed.get("analyst_summary", "")
        except Exception:
            pass

    if analyst_summary:
        evidence.append(
            EvidenceItem(
                source="procurement_analyst_agent",
                finding=analyst_summary,
                reference="analyst_handoff",
            )
        )

    # =========================================================================
    # STAGE 2: POLICY & RISK REVIEWER (Compliance & Human Handoff)
    # =========================================================================
    counter.record_tool_call("evaluate_policy_requirements")
    approvals, pol_flags, pol_ev = evaluate_policy_requirements(request, vendor_res, budget_res)
    evidence.extend(pol_ev)
    risk_flags_set.update(pol_flags)

    risk_flags = sorted(list(risk_flags_set))

    reviewer_prompt = f"""
You are the Policy & Risk Reviewer (Agent 2 of 2).
Review the Procurement Analyst's evidence pack against the corporate procurement policy:
- Request ID: {req_id}
- Analyst Summary: {analyst_summary or 'Standard intake evaluation'}
- Risk Flags: {risk_flags}
- Missing Information: {missing_info}
- Required Approval Thresholds: {approvals}

Provide the final verdict:
1. "recommendation": A definitive recommendation for human reviewers.
2. "next_step": Clear routing instructions for human approval or clarification handoff.
Respond in JSON format: {{"recommendation": "...", "next_step": "..."}}
"""
    counter.record_llm_call()
    reviewer_output = call_llm(reviewer_prompt, system_prompt="You are the Corporate Policy & Risk Reviewer.", response_json=True)
    recommendation = ""
    next_step = ""

    if reviewer_output:
        try:
            parsed = json.loads(reviewer_output)
            recommendation = parsed.get("recommendation", "")
            next_step = parsed.get("next_step", "")
        except Exception:
            pass

    # Deterministic fallback / augmentation
    if not recommendation:
        if "missing_information" in risk_flags or missing_info:
            recommendation = "Reject incomplete request: Mandatory procurement fields are missing."
            next_step = f"Request missing information from employee: {', '.join(missing_info)}."
        elif "budget_insufficient" in risk_flags:
            recommendation = "Flagged: Budget shortfall requires departmental Finance review."
            next_step = "Route to Finance and Department Head for budget allocation approval."
        elif "existing_tool_overlap" in risk_flags:
            recommendation = "Flagged: Catalog overlap requires review of existing tool contracts."
            next_step = "Request team review of existing software catalog alternatives prior to purchasing new tools."
        elif "vendor_risk_unavailable" in risk_flags:
            recommendation = "Hold: Vendor risk API unavailable. Manual security evaluation required."
            next_step = "Route to Security team for manual vendor risk verification."
        elif "security_review_required" in risk_flags or "privacy_review_required" in risk_flags:
            recommendation = "Route for mandatory Security & Privacy risk assessment."
            next_step = f"Initiate review cycle with {', '.join(approvals)}."
        else:
            recommendation = "Policy compliant: Proceed to standard stakeholder approvals."
            next_step = f"Route request to {', '.join(approvals)} for final sign-off."

    if not next_step:
        next_step = f"Submit package to {', '.join(approvals)} for human review."

    return ProcurementDecision(
        request_id=req_id,
        recommendation=recommendation,
        evidence=evidence,
        required_approvals=approvals,
        missing_information=missing_info,
        risk_flags=risk_flags,
        next_step=next_step,
        human_review_required=True,
        telemetry=RunTelemetry(
            llm_calls=counter.llm_calls,
            tool_calls=counter.tool_calls,
            tool_names=counter.tool_names,
        ),
    )
