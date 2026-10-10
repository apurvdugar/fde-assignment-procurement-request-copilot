from __future__ import annotations

from typing import Any
from src.contracts import EvidenceItem
from src.data_access import load_budgets, load_employees


def check_department_budget(requester_id: str, annual_cost_usd: float | int | None) -> dict[str, Any]:
    """Deterministic tool to verify department budget availability."""
    employees = load_employees()
    budgets = load_budgets()

    emp_matches = employees[employees["employee_id"] == requester_id]
    if emp_matches.empty:
        return {
            "status": "error",
            "department": "Unknown",
            "evidence": [EvidenceItem(source="budget_check", finding=f"Employee {requester_id} not found", reference="employees.csv")],
            "risk_flags": ["missing_information"],
            "is_sufficient": False,
        }

    emp = emp_matches.iloc[0]
    department = str(emp["department"])

    b_matches = budgets[budgets["department"] == department]
    if b_matches.empty:
        return {
            "status": "error",
            "department": department,
            "evidence": [EvidenceItem(source="budget_check", finding=f"No budget record found for department {department}", reference="department_budgets.csv")],
            "risk_flags": ["budget_insufficient"],
            "is_sufficient": False,
        }

    b_row = b_matches.iloc[0]
    available_usd = float(b_row["available_usd"])
    total_budget_usd = float(b_row["annual_software_budget_usd"])
    committed_usd = float(b_row["committed_usd"])

    if annual_cost_usd is None:
        return {
            "status": "indeterminate",
            "department": department,
            "available_usd": available_usd,
            "total_budget_usd": total_budget_usd,
            "committed_usd": committed_usd,
            "evidence": [
                EvidenceItem(
                    source="budget_check",
                    finding=f"Department {department} has ${available_usd:,.2f} available out of ${total_budget_usd:,.2f}, but requested cost is unspecified.",
                    reference=f"department_budgets.csv:{department}",
                )
            ],
            "risk_flags": [],
            "is_sufficient": False,
        }

    cost = float(annual_cost_usd)
    is_sufficient = cost <= available_usd
    risk_flags: list[str] = []
    if not is_sufficient:
        risk_flags.append("budget_insufficient")

    finding = (
        f"Department {department} has ${available_usd:,.2f} available. "
        f"Requested amount is ${cost:,.2f}. Budget is {'sufficient' if is_sufficient else 'insufficient (shortfall $' + f'{cost - available_usd:,.2f})'}."
    )

    return {
        "status": "ok",
        "department": department,
        "available_usd": available_usd,
        "requested_usd": cost,
        "is_sufficient": is_sufficient,
        "risk_flags": risk_flags,
        "evidence": [
            EvidenceItem(
                source="budget_check",
                finding=finding,
                reference=f"department_budgets.csv:{department}",
            )
        ],
    }
