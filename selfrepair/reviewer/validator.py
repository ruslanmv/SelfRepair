"""Reject findings that do not cite the diff, then dedupe by fingerprint."""
from __future__ import annotations

from selfrepair.ci.redaction import redact
from selfrepair.reviewer.diff import line_allowed
from selfrepair.reviewer.fingerprints import fingerprint
from selfrepair.reviewer.schemas import DiffSet, FindingDraft, FindingRecord


def validate_findings(diff: DiffSet, drafts: list[FindingDraft]) -> list[FindingRecord]:
    """Keep grounded findings and collapse duplicates.

    A finding with a line that is not in the diff is dropped. A file-level
    finding is kept only when that file is in the diff. Evidence is redacted
    before it is stored or fingerprinted.
    """
    kept: dict[str, FindingRecord] = {}
    for draft in drafts:
        if not line_allowed(diff, draft.file_path, draft.start_line, draft.side):
            continue
        evidence = redact(draft.evidence or "").text if draft.evidence else None
        description = redact(draft.description).text
        digest = fingerprint(
            category=draft.category,
            file_path=draft.file_path,
            title=draft.title,
            evidence=evidence or description,
        )
        if digest in kept:
            continue
        end_line = draft.end_line or draft.start_line
        kept[digest] = FindingRecord(
            fingerprint=digest,
            category=draft.category,
            severity=draft.severity,
            confidence=draft.confidence,
            file_path=draft.file_path,
            start_line=draft.start_line,
            end_line=end_line,
            side=draft.side,
            title=draft.title[:255],
            description=description,
            evidence=evidence,
            suggested_fix=draft.suggested_fix,
            source=draft.source,
            validation_state="accepted",
        )
    return list(kept.values())
