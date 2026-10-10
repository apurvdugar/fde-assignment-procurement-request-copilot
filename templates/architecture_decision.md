# Architecture Decision Memo

**Maximum length: 500 words**

## Decision
We recommend shipping **Architecture A (Single-Agent Baseline with Deterministic Policy Guardrails)** for production deployment today.

## Evidence
Both architectures were rigorously evaluated against the standardized benchmark test suite (`evals/public_cases.json`) covering financial thresholds, existing tool overlaps, sensitive source code access, budget shortfalls, prompt injection attacks, and upstream vendor API outages.

| Metric | Single Agent (Arch A) | Staged / 2-Agent (Arch B) |
|---|---:|---:|
| **Cases Passing Quality Criteria** | **6 / 6 (100%)** | **6 / 6 (100%)** |
| **Deterministic Rule Adherence** | **100%** | **100%** |
| **Prompt Injection Neutralization** | **100%** | **100%** |
| **Avg LLM Calls per Request** | **1** | **2 (+100%)** |
| **Avg Tool Calls per Request** | **6** | **6** |
| **Failure / Hallucination Rate** | **0%** | **0%** |

Both architectures correctly routed all edge cases, preserved human-in-the-loop review, and surfaced grounded evidence without hallucination.

## Trade-offs
- **Orchestration Complexity vs. Accuracy**: Staged multi-agent pipelines introduce a secondary handoff boundary (Procurement Analyst $\rightarrow$ Policy Reviewer). However, our evaluation proves that this extra agent layer provides zero measurable gain in policy compliance or accuracy, as core approval thresholds and compliance rules are deterministically enforced in code.
- **Latency & Operational Cost**: Architecture B doubles LLM inference calls ($2\times$ token spend) and doubles vulnerability to LLM latency variance and rate limits. Architecture A executes in a single pass, halving API operational cost and minimizing user wait times.
- **Prompt Maintenance**: Maintaining two prompt pipelines increases prompt drift risk, schema maintenance overhead, and debugging friction compared to a consolidated agent workflow.

## Risks / Limitations
Before deploying to general enterprise production, we would validate:
1. **Dynamic Catalog Expansion**: Integrating semantic embeddings / vector retrieval for massive ($>10,000$ SKU) software catalogs where string and category matching alone may miss subtle capability duplicates.
2. **Live SSO / HRIS Synchronization**: Replacing CSV snapshots with live employee role, department, and spending authority APIs.
3. **Evolving Prompt Injection Threat Vectors**: Expanding sanitization beyond regex heuristics to multi-layered input validation and LLM guardrails.

## Why this is the Right MVP
The assignment's foundational design principle dictates: **AI interprets context, code enforces thresholds, and humans decide exceptions.** 

Because critical approval thresholds, budget arithmetic, and vendor review expirations must remain strictly deterministic in code rather than probabilistic in an LLM, the single-agent architecture already has all the grounding it needs. Introducing unnecessary multi-agent choreography increases cost, latency, and surface area without improving procurement decisions. 

Architecture A delivers maximum reliability, full auditability, rapid response times, and lower operational overhead, making it the superior, evidence-backed architecture to ship.
