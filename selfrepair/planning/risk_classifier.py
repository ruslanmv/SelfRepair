"""Overall risk classification for a repair plan.

Classifies a plan's risk as low / medium / high from the detected issue
severities. Optionally consults the OllaBridge ``risk-classifier`` alias, but
ALWAYS degrades to deterministic rules offline.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from selfrepair.analyzers.repo_analyzer import Issue

logger = logging.getLogger(__name__)

_RANK = {"low": 0, "medium": 1, "high": 2}
_SEVERITY_TO_RISK = {
    "info": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "high",
}


def _coerce(issues: Any) -> list[Issue]:
    out: list[Issue] = []
    for item in issues:
        if isinstance(item, Issue):
            out.append(item)
        elif isinstance(item, dict):
            out.append(
                Issue(
                    id=item.get("id", "unknown"),
                    severity=item.get("severity", "medium"),
                    description=item.get("description", ""),
                    recommended_action=item.get("recommended_action", ""),
                )
            )
    return out


def classify_risk_rules(issues: Any) -> str:
    """Deterministic, offline risk classification."""
    issue_list = _coerce(issues)
    if not issue_list:
        return "low"
    worst = "low"
    for issue in issue_list:
        risk = _SEVERITY_TO_RISK.get(issue.severity, "medium")
        if _RANK[risk] > _RANK[worst]:
            worst = risk
    # Many simultaneous issues bump risk by one level (capped at high).
    if len(issue_list) >= 4 and worst == "low":
        worst = "medium"
    return worst


def classify_risk(
    issues: Any,
    *,
    llm_client: Any | None = None,
    model: str = "risk-classifier",
) -> str:
    """Classify overall risk, optionally via the risk-classifier LLM alias.

    Falls back to deterministic rules on any failure or when no client is
    provided, so this is safe offline.
    """
    rule_result = classify_risk_rules(issues)
    if llm_client is None:
        return rule_result

    try:
        issue_list = _coerce(issues)
        payload = [i.to_dict() for i in issue_list]
        system = (
            "You are a release-risk classifier. Given a JSON list of repository "
            "issues, respond with exactly one word: low, medium, or high."
        )
        prompt = (
            "Classify the overall repair risk for these issues and answer with a "
            "single word (low/medium/high):\n" + json.dumps(payload)
        )
        # OllaBridgeClient.chat(prompt, system) -> str
        raw = llm_client.chat(prompt, system=system)
        answer = str(raw).strip().lower()
        for level in ("high", "medium", "low"):
            if level in answer:
                return level
        return rule_result
    except Exception as exc:  # degrade to rules offline / on error
        logger.warning("risk-classifier LLM unavailable, using rules: %s", exc)
        return rule_result
