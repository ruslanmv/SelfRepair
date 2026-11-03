"""Pattern review that does not call a model.

Rules fire only on added lines of the diff. A comment that talks about a
vulnerability is not a finding. Deterministic hits stay in the report even
when a later model report is empty.
"""
from __future__ import annotations

import re

from selfrepair.config.repo_config import ReviewerConfig
from selfrepair.reviewer.schemas import DiffSet, FindingDraft, ReviewEvent, ReviewReport

_RULES: tuple[tuple[str, str, str, str, re.Pattern[str], str], ...] = (
    (
        "security",
        "critical",
        "Private key committed",
        "A private key block was added.",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "Remove the key, rotate it, and load it from a secret store.",
    ),
    (
        "security",
        "critical",
        "Cloud access key committed",
        "An AWS access key id was added.",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "Revoke the key and read credentials from the environment.",
    ),
    (
        "security",
        "high",
        "Hard-coded credential",
        "A password, token, or API key literal was added.",
        re.compile(
            r"(?i)(password|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]{8,}['\"]"
        ),
        "Replace the literal with an environment variable or a secret manager.",
    ),
    (
        "security",
        "high",
        "Dynamic code execution",
        "eval() or exec() was added.",
        re.compile(r"\b(eval|exec)\s*\("),
        "Remove dynamic execution or constrain it to a trusted parser.",
    ),
    (
        "security",
        "high",
        "Shell injection risk",
        "A shell was invoked with shell=True.",
        re.compile(r"shell\s*=\s*True"),
        "Pass an argument list and keep shell=False.",
    ),
    (
        "security",
        "high",
        "Insecure deserialization",
        "pickle.loads was added.",
        re.compile(r"\bpickle\.loads\s*\("),
        "Reject untrusted pickle input and use a schema-checked format.",
    ),
    (
        "security",
        "medium",
        "TLS verification disabled",
        "Certificate verification was disabled.",
        re.compile(r"verify\s*=\s*False"),
        "Leave TLS verification on.",
    ),
)

_TEST_PATH = re.compile(r"(^|/)(tests?/|test_[^/]+\.py|[^/]+_test\.(py|go|js|ts)$)")


class DeterministicReviewEngine:
    """Rule review over added diff lines. Always available."""

    name = "deterministic"

    def review(
        self,
        event: ReviewEvent,
        diff: DiffSet,
        config: ReviewerConfig,
    ) -> ReviewReport:
        """Scan added lines and return grounded findings."""
        del config  # rules are not repo-configurable in this version
        findings: list[FindingDraft] = []
        saw_production = False
        saw_test = False
        for file in diff.files:
            if file.status == "binary":
                continue
            if _is_test(file.path):
                saw_test = True
            elif file.status != "removed":
                saw_production = True
            for line in file.lines:
                if line.side != "RIGHT":
                    continue
                findings.extend(_match_line(file.path, line.line, line.text))
        if saw_production and not saw_test:
            target = next(
                (
                    item
                    for item in diff.files
                    if not _is_test(item.path) and any(line.side == "RIGHT" for line in item.lines)
                ),
                None,
            )
            if target is not None:
                first = next(line for line in target.lines if line.side == "RIGHT")
                findings.append(
                    FindingDraft(
                        category="testing",
                        severity="low",
                        confidence=0.6,
                        file_path=target.path,
                        start_line=first.line,
                        side="RIGHT",
                        title="No test changes in this review",
                        description=(
                            "Production files changed and the diff contains no test file."
                        ),
                        evidence=first.text[:240],
                        suggested_fix="Add a regression test for the changed behavior.",
                        source="deterministic",
                    )
                )
        summary = (
            f"Deterministic review of {event.repo_full_name}@{event.head_sha[:12]} "
            f"found {len(findings)} grounded finding(s)."
        )
        return ReviewReport(summary=summary, findings=findings, engine="deterministic")


def _match_line(path: str, line_no: int, text: str) -> list[FindingDraft]:
    stripped = text.strip()
    if stripped.startswith(("#", "//", "/*", "*", "<!--")):
        return []
    found: list[FindingDraft] = []
    for category, severity, title, description, pattern, fix in _RULES:
        if pattern.search(text):
            found.append(
                FindingDraft(
                    category=category,  # type: ignore[arg-type]
                    severity=severity,  # type: ignore[arg-type]
                    confidence=0.95,
                    file_path=path,
                    start_line=line_no,
                    side="RIGHT",
                    title=title,
                    description=description,
                    evidence=text[:240],
                    suggested_fix=fix,
                    source="deterministic",
                )
            )
    return found


def _is_test(path: str) -> bool:
    return _TEST_PATH.search(path) is not None
