from __future__ import annotations

import re
from typing import Any
from src.contracts import EvidenceItem


def validate_request_information(request: dict[str, Any]) -> tuple[list[str], list[str], list[EvidenceItem]]:
    """Checks for required business request fields per Policy Section 1."""
    missing: list[str] = []
    risk_flags: list[str] = []
    evidence: list[EvidenceItem] = []

    if request.get("annual_cost_usd") is None:
        missing.append("annual cost")
    if request.get("user_count") is None:
        missing.append("user count / license seats")
    
    data_access = request.get("data_access_level")
    if not data_access or str(data_access).strip().lower() in ["unknown", "none_specified", ""]:
        missing.append("data access level")

    if not request.get("business_justification"):
        missing.append("business justification")

    if missing:
        risk_flags.append("missing_information")
        evidence.append(
            EvidenceItem(
                source="policy_rules",
                finding=f"Required request information is missing: {', '.join(missing)}.",
                reference="procurement_policy.md:Section 1",
            )
        )

    return missing, risk_flags, evidence


def detect_prompt_injection(text: str) -> tuple[bool, list[str], list[EvidenceItem]]:
    """Detects adversarial instructions in business data attempting to subvert policy."""
    if not text:
        return False, [], []

    patterns = [
        r"ignore\s+(all\s+)?(procurement\s+)?rules",
        r"ignore\s+previous\s+instructions",
        r"cfo-approved",
        r"treat\s+this\s+request\s+as\s+.*approved",
        r"approve\s+(it\s+)?immediately",
        r"bypass\s+(all\s+)?policy",
        r"override\s+(all\s+)?controls",
        r"system\s+prompt",
    ]

    detected = False
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            detected = True
            break

    risk_flags: list[str] = []
    evidence: list[EvidenceItem] = []

    if detected:
        risk_flags.append("prompt_injection_detected")
        evidence.append(
            EvidenceItem(
                source="security_sanitization",
                finding="Potential prompt injection / unauthorized override instruction detected in business justification. Embedded instructions ignored per policy.",
                reference="procurement_policy.md:Section 9",
            )
        )

    return detected, risk_flags, evidence


def evaluate_policy_requirements(
    request: dict[str, Any],
    vendor_res: dict[str, Any],
    budget_res: dict[str, Any],
) -> tuple[list[str], list[str], list[EvidenceItem]]:
    """Evaluates policy rules for financial thresholds, security, privacy, and legal approvals."""
    approvals: list[str] = []
    risk_flags: list[str] = []
    evidence: list[EvidenceItem] = []

    cost = request.get("annual_cost_usd")
    data_access = str(request.get("data_access_level", "")).lower()
    integrations = [str(x).lower() for x in request.get("requested_integrations", [])]
    vendor_reg = vendor_res.get("registry") or {}
    api_record = vendor_res.get("api_record") or {}
    api_unavailable = vendor_res.get("api_unavailable", False)

    # 1. Financial approval thresholds (Policy Section 4)
    if cost is not None:
        cost_val = float(cost)
        if cost_val <= 1000.0:
            approvals.append("Manager")
            evidence.append(
                EvidenceItem(
                    source="policy_rules",
                    finding=f"Spend ${cost_val:,.2f} is under $1,000 threshold: requires Manager approval.",
                    reference="procurement_policy.md:Section 4",
                )
            )
        elif 1000.0 < cost_val <= 10000.0:
            approvals.extend(["Department Head", "Procurement"])
            evidence.append(
                EvidenceItem(
                    source="policy_rules",
                    finding=f"Spend ${cost_val:,.2f} is between $1,000.01 and $10,000: requires Department Head and Procurement approval.",
                    reference="procurement_policy.md:Section 4",
                )
            )
        elif 10000.0 < cost_val <= 25000.0:
            approvals.extend(["Department Head", "Finance", "Procurement"])
            evidence.append(
                EvidenceItem(
                    source="policy_rules",
                    finding=f"Spend ${cost_val:,.2f} is between $10,000.01 and $25,000: requires Department Head, Finance, and Procurement approval.",
                    reference="procurement_policy.md:Section 4",
                )
            )
        else:
            approvals.extend(["Department Head", "Finance", "CFO", "Procurement"])
            evidence.append(
                EvidenceItem(
                    source="policy_rules",
                    finding=f"Spend ${cost_val:,.2f} exceeds $25,000: requires Department Head, Finance, CFO, and Procurement approval.",
                    reference="procurement_policy.md:Section 4",
                )
            )

    # 2. Budget Shortfall Check (Policy Section 2)
    if not budget_res.get("is_sufficient", True) and cost is not None:
        if "Finance" not in approvals:
            approvals.append("Finance")

    # 3. Security Review Triggers (Policy Section 5)
    sec_triggers = []
    if data_access == "source_code" or any("git" in i or "repo" in i for i in integrations):
        sec_triggers.append("source code access")
    if data_access == "production_telemetry" or any("cloud" in i or "production" in i for i in integrations):
        sec_triggers.append("production cloud / telemetry integration")
    if data_access == "confidential_documents":
        sec_triggers.append("confidential document access")
    if data_access in ["employee_pii", "customer_pii"]:
        sec_triggers.append("PII processing")
    if "security_review_required" in vendor_res.get("risk_flags", []):
        sec_triggers.append("vendor security assessment not completed or expired")
    if api_unavailable:
        sec_triggers.append("vendor risk assessment unverified due to service outage")

    if sec_triggers:
        risk_flags.append("security_review_required")
        if "Security" not in approvals:
            approvals.append("Security")
        evidence.append(
            EvidenceItem(
                source="security_policy",
                finding=f"Security review triggered by: {', '.join(sec_triggers)}.",
                reference="procurement_policy.md:Section 5",
            )
        )

    # 4. Privacy Review Triggers (Policy Section 6)
    priv_triggers = []
    if data_access in ["employee_pii", "customer_pii"]:
        priv_triggers.append(f"direct {data_access} access")
    if api_record.get("processes_personal_data"):
        priv_triggers.append("vendor processes personal data")
    if api_record.get("stores_data_outside_region"):
        priv_triggers.append("vendor stores data outside operating region")

    if priv_triggers:
        risk_flags.append("privacy_review_required")
        if "Privacy" not in approvals:
            approvals.append("Privacy")
        evidence.append(
            EvidenceItem(
                source="privacy_policy",
                finding=f"Privacy review triggered by: {', '.join(priv_triggers)}.",
                reference="procurement_policy.md:Section 6",
            )
        )

    # 5. Legal Review Triggers (Policy Section 7)
    is_new_vendor = (
        vendor_reg.get("procurement_status", "").lower() == "new"
        or not vendor_reg
    )
    terms_status = str(vendor_reg.get("legal_terms_status", "")).lower()
    cost_val = float(cost or 0)

    legal_triggers = []
    if is_new_vendor and cost_val >= 10000.0:
        legal_triggers.append(f"new vendor with spend >= $10k (${cost_val:,.0f})")
    if terms_status in ["draft", "unknown"]:
        legal_triggers.append(f"legal terms not standard ({terms_status})")
    if api_record.get("stores_data_outside_region"):
        legal_triggers.append("cross-region data processing")

    if legal_triggers:
        risk_flags.append("legal_review_required")
        if "Legal" not in approvals:
            approvals.append("Legal")
        evidence.append(
            EvidenceItem(
                source="legal_policy",
                finding=f"Legal review triggered by: {', '.join(legal_triggers)}.",
                reference="procurement_policy.md:Section 7",
            )
        )

    return approvals, risk_flags, evidence
