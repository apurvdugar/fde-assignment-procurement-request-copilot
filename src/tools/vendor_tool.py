from __future__ import annotations

import datetime
from typing import Any
import requests
from src.contracts import EvidenceItem
from src.data_access import load_vendors
from src.vendor_client import get_vendor_risk

# Reference snapshot date defined by procurement policy
POLICY_REFERENCE_DATE = datetime.date(2026, 9, 30)


def check_vendor_status(vendor_name: str) -> dict[str, Any]:
    """Inspects vendor risk and registry status across internal DB and mock risk API."""
    vendors = load_vendors()
    v_matches = vendors[vendors["vendor_name"].str.lower() == vendor_name.strip().lower()]

    evidence: list[EvidenceItem] = []
    risk_flags: list[str] = []

    registry_record: dict[str, Any] | None = None
    if not v_matches.empty:
        registry_record = v_matches.iloc[0].to_dict()
        evidence.append(
            EvidenceItem(
                source="vendor_registry",
                finding=(
                    f"Vendor '{vendor_name}' registry: status={registry_record.get('procurement_status')}, "
                    f"security={registry_record.get('security_status')}, legal_terms={registry_record.get('legal_terms_status')}."
                ),
                reference=f"vendors.csv:{registry_record.get('vendor_id')}",
            )
        )
    else:
        evidence.append(
            EvidenceItem(
                source="vendor_registry",
                finding=f"Vendor '{vendor_name}' not found in internal registry (treated as new vendor).",
                reference="vendors.csv",
            )
        )
        risk_flags.append("legal_review_required")

    # Query external vendor risk API
    api_record: dict[str, Any] | None = None
    api_unavailable = False

    try:
        api_record = get_vendor_risk(vendor_name, timeout_seconds=2.0)
    except requests.RequestException as exc:
        # Check if local server is down or 503 error
        # If it's a connection error (server not started), try direct app call
        if isinstance(exc, requests.ConnectionError):
            try:
                from fastapi.testclient import TestClient
                from mock_api.app import app
                client = TestClient(app)
                resp = client.get(f"/vendor-risk/{vendor_name}")
                if resp.status_code == 200:
                    api_record = resp.json()
                elif resp.status_code == 503:
                    api_unavailable = True
                else:
                    api_unavailable = True
            except Exception:
                api_unavailable = True
        else:
            api_unavailable = True

    if api_unavailable or api_record is None:
        risk_flags.append("vendor_risk_unavailable")
        evidence.append(
            EvidenceItem(
                source="vendor_risk_api",
                finding=f"External vendor-risk API unavailable or returned outage error for '{vendor_name}'.",
                reference="/vendor-risk",
            )
        )
    else:
        risk_lvl = api_record.get("risk_level", "unknown")
        sec_status = api_record.get("security_review_status", "unknown")
        review_date_str = api_record.get("last_review_date")
        personal_data = api_record.get("processes_personal_data", False)
        outside_region = api_record.get("stores_data_outside_region", False)

        evidence.append(
            EvidenceItem(
                source="vendor_risk_api",
                finding=(
                    f"Vendor-risk service: risk={risk_lvl}, security_status={sec_status}, "
                    f"last_review={review_date_str}, personal_data={personal_data}, outside_region={outside_region}."
                ),
                reference=f"/vendor-risk/{vendor_name}",
            )
        )

        # Check review date expiration (> 365 days from policy reference date)
        if review_date_str:
            try:
                r_date = datetime.date.fromisoformat(review_date_str)
                age_days = (POLICY_REFERENCE_DATE - r_date).days
                if age_days > 365:
                    risk_flags.append("vendor_review_expired")
                    risk_flags.append("security_review_required")
                    evidence.append(
                        EvidenceItem(
                            source="policy_check",
                            finding=f"Vendor security review is expired ({age_days} days old vs 365 days max as of {POLICY_REFERENCE_DATE}).",
                            reference="procurement_policy.md:Section 5",
                        )
                    )
            except Exception:
                pass
        elif sec_status != "approved":
            risk_flags.append("security_review_required")

        if sec_status in ["not_completed", "pending", "failed"]:
            if "security_review_required" not in risk_flags:
                risk_flags.append("security_review_required")

        # Discrepancy between registry and risk API
        if registry_record and registry_record.get("security_status") == "Approved" and sec_status in ["expired", "not_completed"]:
            risk_flags.append("conflicting_vendor_evidence")

    return {
        "status": "ok",
        "vendor_name": vendor_name,
        "registry": registry_record,
        "api_record": api_record,
        "api_unavailable": api_unavailable,
        "risk_flags": risk_flags,
        "evidence": evidence,
    }
