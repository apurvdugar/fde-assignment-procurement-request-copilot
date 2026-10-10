from __future__ import annotations

from typing import Any
from src.contracts import EvidenceItem
from src.data_access import load_software_catalog, load_purchase_history


def check_software_catalog(product_name: str, vendor_name: str, category: str | None) -> dict[str, Any]:
    """Deterministic tool to check catalog for existing software, category overlap, and active subscriptions."""
    catalog = load_software_catalog()
    history = load_purchase_history()

    p_norm = product_name.strip().lower()
    v_norm = vendor_name.strip().lower()
    cat_norm = (category or "").strip().lower()

    # Exact product match
    exact_matches = catalog[catalog["product_name"].str.lower() == p_norm]
    # Vendor matches
    vendor_matches = catalog[catalog["vendor_name"].str.lower() == v_norm]
    # Category matches
    category_matches = catalog[catalog["category"].str.lower() == cat_norm] if cat_norm else catalog.iloc[0:0]

    evidence: list[EvidenceItem] = []
    risk_flags: list[str] = []
    has_overlap = False

    is_expansion = any(term in p_norm for term in ["add-on", "expansion", "seats", "tier upgrade", "training pack"])

    if not exact_matches.empty:
        row = exact_matches.iloc[0]
        evidence.append(
            EvidenceItem(
                source="software_catalog",
                finding=f"Existing license found: {row['product_name']} ({row['scope']}, {row['licensed_seats']} seats, ${row['annual_cost_usd']:,.0f}/yr).",
                reference=f"software_catalog.csv:{row['software_id']}",
            )
        )
        if not is_expansion:
            has_overlap = True
            risk_flags.append("existing_tool_overlap")
    elif not vendor_matches.empty:
        row = vendor_matches.iloc[0]
        evidence.append(
            EvidenceItem(
                source="software_catalog",
                finding=f"Vendor {row['vendor_name']} already provides {row['product_name']} ({row['status']}).",
                reference=f"software_catalog.csv:{row['software_id']}",
            )
        )
    
    # Overlap with competing software in same category
    competing_tools = [
        f"{r['product_name']} ({r['vendor_name']})"
        for _, r in category_matches.iterrows()
        if r["vendor_name"].lower() != v_norm
    ]

    if competing_tools:
        competing_list = ", ".join(competing_tools)
        evidence.append(
            EvidenceItem(
                source="software_catalog",
                finding=f"Existing approved software in category '{category}': {competing_list}.",
                reference="software_catalog.csv",
            )
        )
        if not is_expansion and vendor_matches.empty:
            has_overlap = True
            if "existing_tool_overlap" not in risk_flags:
                risk_flags.append("existing_tool_overlap")

    if not evidence:
        evidence.append(
            EvidenceItem(
                source="software_catalog",
                finding=f"No existing software or active contracts found for {product_name} in category '{category}'.",
                reference="software_catalog.csv",
            )
        )

    return {
        "status": "ok",
        "has_overlap": has_overlap,
        "is_expansion": is_expansion,
        "risk_flags": risk_flags,
        "evidence": evidence,
        "competing_tools": competing_tools,
    }
