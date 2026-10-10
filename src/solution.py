from __future__ import annotations

from src.contracts import Architecture, ProcurementDecision
from src.data_access import get_request
from src.agents.single_agent import run_single_agent
from src.agents.staged_agent import run_staged_agents


def handle_request(request_id: str, architecture: Architecture = "single") -> ProcurementDecision:
    """Assessment adapter.
    Evaluated by the public and hidden test suites.
    Supports Architecture A ('single') and Architecture B ('staged').
    """
    request = get_request(request_id)

    if architecture == "single":
        return run_single_agent(request)
    elif architecture == "staged":
        return run_staged_agents(request)
    else:
        raise ValueError(f"Unknown architecture mode: {architecture}")
