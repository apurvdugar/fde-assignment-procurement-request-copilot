# AI Procurement Request Copilot

> **FDE Assessment 3 Submission**  
> An internal AI procurement copilot that gathers evidence, enforces deterministic business controls, neutralizes untrusted prompt injections, and delivers auditable recommendations with human-in-the-loop governance.

---

## 1. Quick Start & Setup

### Prerequisites
- Python 3.11 or 3.12 (tested on Linux/WSL and Windows)
- Virtual environment (`.venv`)

### Setup & One-Command Run
```bash
# 1. Activate environment and install dependencies
source .venv/bin/activate
pip install -r requirements.txt

# 2. Run Pre-flight Verification
python verify_setup.py

# 3. Configure API Credentials (Optional - OpenRouter / OpenAI)
cp .env.example .env
# Edit .env and paste your OPENROUTER_API_KEY
# If left blank, the copilot runs via its built-in resilient contextual fallback engine

# 4. Launch Local Services (Mock API + Streamlit Dashboard)
python run_local.py
```
- **Procurement Copilot Dashboard:** [http://localhost:8501](http://localhost:8501)
- **Vendor-Risk Mock API:** [http://127.0.0.1:8001](http://127.0.0.1:8001)

---

## 2. Product Workflow & Architecture

### Design Principle
- **AI (Probabilistic / Contextual):** Interprets unstructured business justification, evaluates subjective nuances, and crafts executive-ready decision summaries.
- **CODE (Deterministic):** Evaluates arithmetic budget checks, statutory financial approval tiers, 365-day security review expirations, and sanitizes prompt injections.
- **HUMAN (Authority):** Retains final purchasing authority and handles exception overrides (`human_review_required = True`).

### System Workflow
```text
  [ Employee Request ] 
          │
          ▼
  [ Understand Need ]  ──> Extracts SKU, cost, seats, purpose, data access level
          │
          ▼
  [ Gather Evidence ]  ──> 1. Budget Tool (department budget availability)
                       ──> 2. Catalog Tool (existing licenses & category overlap)
                       ──> 3. Vendor Risk Tool (registry + mock API + 365d check)
                       ──> 4. Policy Engine (financial tiers + security triggers)
          │
          ▼
  [ Security & Policy] ──> Neutralizes prompt injections; verifies required fields
          │
          ▼
  [ Recommendation ]   ──> Generates structured ProcurementDecision contract
          │
          ▼
  [ Human Review ]     ──> Final governance action (Approve / Reject / Clarify / Escalate)
```

---

## 3. Architecture Comparison

We implemented and empirically evaluated both architectures:

### Architecture A: Single-Agent Baseline
- **Orchestration:** Single unified agent (`src/agents/single_agent.py`) orchestrates all 4 modular tools, performs deterministic policy evaluations, and uses 1 LLM reasoning call to synthesize the executive recommendation.
- **Telemetry:** 1 LLM call, 6 tool calls per request.

### Architecture B: Staged / Two-Agent Variant
- **Orchestration:** Multi-agent pipeline (`src/agents/staged_agent.py`):
  1. **Procurement Analyst:** Gathers raw evidence across all tools and produces a structured Evidence Pack (1 LLM call).
  2. **Policy & Risk Reviewer:** Consumes the Evidence Pack, checks statutory approval thresholds, and issues final routing instructions (1 LLM call).
- **Telemetry:** 2 LLM calls, 6 tool calls per request.

---

## 4. Tool Suite (`src/tools/`)

| Tool | Type | Responsibility |
| :--- | :--- | :--- |
| `check_department_budget` | Deterministic | Compares annual request cost against department available budget in `department_budgets.csv`. Flags `budget_insufficient`. |
| `check_software_catalog` | Deterministic | Queries `software_catalog.csv` and `purchase_history.csv` for same vendor, product, or category overlap. Flags `existing_tool_overlap`. |
| `check_vendor_status` | External API + Deterministic | Queries internal registry (`vendors.csv`) and mock API (`/vendor-risk/{name}`). Evaluates 365-day review age against reference date `2026-09-30`. Flags `vendor_review_expired`, `conflicting_vendor_evidence`, or `vendor_risk_unavailable` upon 503 outage. |
| `policy_tool` | Deterministic Code | Implements Section 4 financial threshold table ($1k, $10k, $25k), security/privacy/legal triggers, missing field detection, and regex injection defense (`prompt_injection_detected`). |

---

## 5. Evaluation Results

Run reproducible benchmark evaluations with:
```bash
python evals/run_public_evals.py --architecture single
python evals/run_public_evals.py --architecture staged
```

### Empirical Comparison Matrix

| Case ID | Request | Scenario Tested | Arch A (Single) | Arch B (Staged) |
| :--- | :--- | :--- | :---: | :---: |
| **PUB-01** | `REQ-1001` | Low-value approved vendor ($800) | **PASS** (67 ms) | **PASS** (70 ms) |
| **PUB-02** | `REQ-1002` | Existing tool overlap + new vendor ($12k) | **PASS** (30 ms) | **PASS** (32 ms) |
| **PUB-03** | `REQ-1003` | Source-code access (Security review) | **PASS** (27 ms) | **PASS** (28 ms) |
| **PUB-04** | `REQ-1005` | Budget shortfall ($22k vs $18k available) | **PASS** (33 ms) | **PASS** (29 ms) |
| **PUB-05** | `REQ-1006` | Incomplete data + Prompt injection attempt | **PASS** (29 ms) | **PASS** (30 ms) |
| **PUB-06** | `REQ-1009` | Upstream Vendor API Outage (HTTP 503) | **PASS** (31 ms) | **PASS** (29 ms) |
| **Summary** | — | **Overall Pass Rate** | **6 / 6 (100%)** | **6 / 6 (100%)** |
| **Telemetry**| — | **LLM Calls per Request** | **1 call** | **2 calls (+100%)** |

Evaluation artifacts are recorded in [`evals/results_single.csv`](evals/results_single.csv) and [`evals/results_staged.csv`](evals/results_staged.csv).

---

## 6. Final Ship Decision

### Which architecture would you ship — and why?
**We recommend shipping Architecture A (Single-Agent Baseline).**

#### Evidence-Backed Defense:
1. **Identical Decision Quality (100% Accuracy):** Both architectures achieved a perfect 6/6 pass rate across all edge cases (budget shortfalls, catalog overlaps, prompt injections, and vendor API outages).
2. **50% Lower Token & Inference Overhead:** Architecture A requires only **1 LLM call** per transaction versus **2 LLM calls** in Architecture B. In enterprise production processing thousands of purchase requests, this cuts API costs in half.
3. **Reduced Handoff Surface & Latency:** Adding an intermediate analyst agent introduces unnecessary serialization overhead and prompt drift risk without yielding better compliance outcomes. Because critical financial thresholds and policy rules must remain strictly deterministic in code, a single agent with deterministic tool guardrails is the most robust, maintainable, and cost-efficient architecture.

*(Detailed 410-word decision memo available in [`templates/architecture_decision.md`](templates/architecture_decision.md)).*

---

## 7. Assumptions & Policy Grounding

1. **Policy Reference Date:** Pinned to **`2026-09-30`** (per `data/procurement_policy.md`). All vendor security assessment validity windows are computed against this reference snapshot date.
2. **Untrusted Business Data:** Request text and vendor notes are strictly treated as untrusted input. Adversarial instructions (e.g. `REQ-1006` claiming CFO pre-approval) are sanitized and flagged.
3. **No Autonomous Purchasing:** The AI provides advisory recommendations only; human approval remains mandatory for all purchasing commitments.

---

## 8. Known Limitations & Production Roadmap

1. **Semantic Catalog Matching:** The current catalog tool matches via exact vendor/product names and category classifications. For production catalogs with $>10,000$ SKUs, integrating vector embeddings (e.g. Pinecone/Chroma) will detect subtle functional overlaps across disparate categories.
2. **Live HRIS & ERP Integration:** Integrating direct Webhooks or REST connectors to Workday/SAP to replace static CSV snapshots for live departmental budget tracking.
3. **Multi-turn Dialogue:** Future iterations could incorporate interactive chat allowing the copilot to converse directly with employees to collect missing information in real time.
# fde-assignment-procurement-request-copilot
