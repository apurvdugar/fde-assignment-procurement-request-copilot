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


def run_single_agent(request: dict[str, Any]) -> ProcurementDecision:
    """Architecture A: Single-agent baseline.
    Orchestrates evidence gathering across all tools, applies deterministic rules,
    and uses LLM reasoning to synthesize recommendation and next steps.
    """
    counter = RunTelemetryCounter()
    req_id = request.get("request_id", "REQ-UNKNOWN")
    evidence: list[EvidenceItem] = []
    risk_flags_set: set[str] = set()

    # Tool 1: Budget Tool
    counter.record_tool_call("check_department_budget")
    budget_res = check_department_budget(request.get("requester_id", ""), request.get("annual_cost_usd"))
    evidence.extend(budget_res.get("evidence", []))
    risk_flags_set.update(budget_res.get("risk_flags", []))

    # Tool 2: Catalog Tool
    counter.record_tool_call("check_software_catalog")
    catalog_res = check_software_catalog(
        request.get("product_name", ""),
        request.get("vendor_name", ""),
        request.get("category"),
    )
    evidence.extend(catalog_res.get("evidence", []))
    risk_flags_set.update(catalog_res.get("risk_flags", []))

    # Tool 3: Vendor Risk Tool
    counter.record_tool_call("check_vendor_status")
    vendor_res = check_vendor_status(request.get("vendor_name", ""))
    evidence.extend(vendor_res.get("evidence", []))
    risk_flags_set.update(vendor_res.get("risk_flags", []))

    # Tool 4: Request validation & injection checks (Policy engine)
    counter.record_tool_call("validate_request_information")
    missing_info, miss_flags, miss_ev = validate_request_information(request)
    evidence.extend(miss_ev)
    risk_flags_set.update(miss_flags)

    counter.record_tool_call("detect_prompt_injection")
    _, inj_flags, inj_ev = detect_prompt_injection(request.get("business_justification", ""))
    evidence.extend(inj_ev)
    risk_flags_set.update(inj_flags)

    # Tool 5: Policy rules and approvals
    counter.record_tool_call("evaluate_policy_requirements")
    approvals, pol_flags, pol_ev = evaluate_policy_requirements(request, vendor_res, budget_res)
    evidence.extend(pol_ev)
    risk_flags_set.update(pol_flags)

    risk_flags = sorted(list(risk_flags_set))

    # AI Reasoning: Synthesize executive recommendation & next step
    recommendation = ""
    next_step = ""

    # Call LLM via OpenRouter
    llm_prompt = f"""
You are the Procurement Copilot (Architecture A: Single Agent).
Inspect the following purchase request and gathered tool evidence:

Request ID: {req_id}
Product: {request.get('product_name')} | Vendor: {request.get('vendor_name')}
Annual Cost: ${request.get('annual_cost_usd')} | Users: {request.get('user_count')}
Justification: {request.get('business_justification')}
Data Access Level: {request.get('data_access_level')}

Tools findings:
- Budget: {budget_res.get('status')} (Available: ${budget_res.get('available_usd', 0):,.2f})
- Catalog Overlap: {catalog_res.get('has_overlap')} (Competing: {catalog_res.get('competing_tools')})
- Vendor Status: Registry={vendor_res.get('registry', {}).get('procurement_status')}, API Unavailable={vendor_res.get('api_unavailable')}
- Risk Flags: {risk_flags}
- Missing Information: {missing_info}
- Required Approvals: {approvals}

Provide a JSON response with:
1. "recommendation": A concise 1-2 sentence recommendation on whether to proceed, hold for review, or reject duplicate/incomplete requests.
2. "next_step": A concrete next step for procurement and human approvers.
Respond in JSON format: {{"recommendation": "...", "next_step": "..."}}
"""
    counter.record_llm_call()
    llm_output = call_llm(llm_prompt, response_json=True)

    if llm_output:
        try:
            parsed = json.loads(llm_output)
            recommendation = parsed.get("recommendation", "")
            next_step = parsed.get("next_step", "")
        except Exception:
            pass

    # Deterministic fallback / augmentation if LLM returned empty
    if not recommendation:
        if "missing_information" in risk_flags or missing_info:
            recommendation = "Hold request: Incomplete submission requires clarification from requester before review."
            next_step = f"Request missing information from employee: {', '.join(missing_info)}."
        elif "budget_insufficient" in risk_flags:
            recommendation = "Escalate for budget exception: Department budget is insufficient for requested annual amount."
            next_step = "Route to Finance and Department Head for budget allocation approval."
        elif "existing_tool_overlap" in risk_flags:
            recommendation = "Hold for overlap assessment: Existing approved software in catalog may satisfy business requirements."
            next_step = "Request team review of existing software catalog alternatives prior to purchasing new tools."
        elif "vendor_risk_unavailable" in risk_flags:
            recommendation = "Hold for manual vendor risk assessment: Upstream vendor security service is unavailable."
            next_step = "Route to Security team for manual vendor risk verification."
        elif "security_review_required" in risk_flags or "privacy_review_required" in risk_flags:
            recommendation = "Route for compliance and security review: Tool involves sensitive data or unverified vendor status."
            next_step = f"Initiate review cycle with {', '.join(approvals)}."
        else:
            recommendation = "Proceed to business approval: Request complies with procurement policy and budget limits."
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
