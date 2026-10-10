# Workflow & Architecture Specifications

## 1. End-to-End Workflow Diagram

```text
       [ Employee Purchase Request ]
                     │
                     ▼
       ┌─────────────────────────────┐
       │     Procurement Copilot     │
       │   Intake & Parsing Engine   │
       └──────────────┬──────────────┘
                      │
       ┌──────────────┴───────────────────────────┐
       ▼                                          ▼
[ Architecture A: Single Agent ]   [ Architecture B: Staged Two-Agent ]
  • Single Agent Intake Pipeline     • Stage 1: Procurement Analyst
  • Unified Tool Orchestration       • Stage 2: Policy & Risk Reviewer
       │                                          │
       └──────────────┬───────────────────────────┘
                      │
                      ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                    Tool & Evidence Layer                     │
 ├────────────────────────────┬─────────────────────────────────┤
 │ 1. Budget Tool             │ available vs requested cost     │
 │ 2. Catalog Tool            │ category & license overlap      │
 │ 3. Vendor Risk Tool        │ API + registry + 365d validity  │
 │ 4. Policy & Security Tool  │ injection sanitization & tiers  │
 └────────────────────────────┬─────────────────────────────────┘
                              │
                              ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                Deterministic Code Checks                     │
 ├──────────────────────────────────────────────────────────────┤
 │ • Financial Tier: <= $1k (Manager) | $1k-$10k (Dept+Proc)    │
 │   $10k-$25k (Dept+Fin+Proc) | > $25k (+CFO)                  │
 │ • Security: Source code / Cloud / PII / Stale audit          │
 │ • Privacy: PII / Cross-region data storage                   │
 │ • Legal: Spend >= $10k with new vendor / non-standard terms  │
 │ • Injection: Neutralize prompt injection in untrusted text   │
 └────────────────────────────┬─────────────────────────────────┘
                              │
                              ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                     LLM Reasoning Layer                      │
 │     (OpenRouter / Gemini / Claude / GPT / Resilient Fallback)│
 │  • Interpret operational context                             │
 │  • Formulate executive recommendation & next action steps    │
 └────────────────────────────┬─────────────────────────────────┘
                              │
                              ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                 ProcurementDecision Contract                 │
 │  • recommendation   • required_approvals   • risk_flags      │
 │  • evidence[]       • missing_information  • telemetry       │
 └────────────────────────────┬─────────────────────────────────┘
                              │
                              ▼
 ┌──────────────────────────────────────────────────────────────┐
 │              Human-in-the-Loop Review Console                │
 │    [Approve]   [Reject]   [Request Info]   [Escalate]        │
 └──────────────────────────────────────────────────────────────┘
```

## 2. Tools Breakdown

1. **`check_department_budget` (Deterministic)**:
   - Compares requested `annual_cost_usd` against `available_usd` in `department_budgets.csv`.
   - Triggers `budget_insufficient` risk flag and forces Finance approval when cost exceeds available funds.
2. **`check_software_catalog` (Deterministic)**:
   - Queries `software_catalog.csv` and `purchase_history.csv` for same product, vendor, or category.
   - Triggers `existing_tool_overlap` risk flag if alternative software is already licensed company-wide.
3. **`check_vendor_status` (External API + Deterministic Reconciliation)**:
   - Reconciles internal vendor registry (`vendors.csv`) with the mock vendor-risk endpoint (`/vendor-risk/{vendor_name}`).
   - Deterministically calculates whether vendor security assessment is older than 365 days relative to the policy snapshot date (`2026-09-30`).
   - Handles simulated service outages (e.g. 503 errors for NimbusAI) gracefully by flagging `vendor_risk_unavailable`.
4. **`policy_tool` (Deterministic Rules Engine & Security Sanitizer)**:
   - Enforces the statutory 4-tier approval threshold table.
   - Evaluates security, privacy, and legal triggers based on data access levels and vendor contract states.
   - Detects prompt injection in untrusted request justification text, neutralizing override attempts.

## 3. Division of Responsibility: AI vs. Code vs. Human

- **Code (Deterministic)**: Financial thresholds, budget arithmetic, 365-day expiration calculations, missing required fields, and injection pattern neutralization.
- **AI (Probabilistic / Contextual)**: Synthesizing justification context, drafting clear stakeholder recommendations, and explaining nuanced next steps.
- **Human (Authority)**: Purchasing decisions, commercial commitments, budget exception sign-offs, and final approvals (`human_review_required = True`).
