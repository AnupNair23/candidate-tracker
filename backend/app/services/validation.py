"""Step 6 — deterministic validation of Claude's batch output before anything reaches the UI.

Checks referential integrity (handles, evidence ids belong to the same candidate and match the cited
source) and evidence support (a `met`/`partial` verdict must cite text mentioning the requirement;
`not_met` must cite conflicting evidence, otherwise it is downgraded to `unknown`).
"""

from __future__ import annotations

from app.constants.assessment import (
    CONCERN_CHARS,
    CONTRIBUTION_SUMMARY_CHARS,
    MAX_CONCERNS,
    REASON_CHARS,
    TEXT_CHECKED_KINDS,
)
from app.models.assessment import BatchOut
from app.models.intent import Requirement
from app.models.pipeline import Packet, ValidatedAssessment, ValidatedContribution, ValidatedStatus, ValidatedVerdict
from app.utils.text import clip, supports


def validate_batch(
    packets: dict[str, Packet], requirements: list[Requirement], out: BatchOut
) -> tuple[dict[str, ValidatedAssessment], set[str], list[str]]:
    """Return (validated by handle, handles missing from output, batch-level issues)."""
    req_by_id = {r.id: r for r in requirements}
    validated: dict[str, ValidatedAssessment] = {}
    batch_issues: list[str] = []

    for item in out.assessments:
        packet = packets.get(item.handle)
        if packet is None:
            batch_issues.append(f"unknown handle {item.handle!r} dropped")
            continue
        if item.handle in validated:
            batch_issues.append(f"duplicate assessment for {item.handle} dropped")
            continue
        issues: list[str] = []

        def own_ids(ids: list[str], _packet: Packet = packet, _issues: list[str] = issues) -> list[str]:
            keep: list[str] = []
            for eid in ids:
                if eid in _packet.evidence:
                    if eid not in keep:
                        keep.append(eid)
                elif eid.split("-")[0] in packets:
                    _issues.append(f"evidence {eid} belongs to another candidate; removed")
                else:
                    _issues.append(f"evidence {eid} does not exist; removed")
            return keep

        verdicts: dict[str, ValidatedVerdict] = {}
        for v in item.verdicts:
            req = req_by_id.get(v.requirement_id)
            if req is None:
                issues.append(f"verdict for unknown requirement {v.requirement_id!r} dropped")
                continue
            if v.requirement_id in verdicts:
                continue
            ids = own_ids(v.evidence_ids)
            status: ValidatedStatus = v.status
            downgraded: str | None = None
            if status in ("met", "partial"):
                if not ids:
                    status, downgraded = "unverified", v.status
                elif req.kind in TEXT_CHECKED_KINDS and not any(
                    supports(req.text, req.aliases, packet.evidence[e].text) for e in ids
                ):
                    status, downgraded = "unverified", v.status
            elif status == "not_met":
                if not ids:
                    status, downgraded = "unknown", "not_met"
            else:  # unknown
                ids = []
            if downgraded:
                issues.append(f"{req.id} {downgraded} → {status} (evidence did not support it)")
            verdicts[req.id] = ValidatedVerdict(req.id, status, ids, downgraded)
        for req in requirements:
            verdicts.setdefault(req.id, ValidatedVerdict(req.id, "unknown", []))

        contributions: list[ValidatedContribution] = []
        for c in item.source_contributions:
            ids = [e for e in own_ids(c.evidence_ids) if packet.evidence[e].source == c.source]
            if not ids:
                issues.append(f"{c.source} contribution without matching evidence dropped")
                continue
            contributions.append(
                ValidatedContribution(c.source, c.effect, clip(c.summary, CONTRIBUTION_SUMMARY_CHARS), ids)
            )

        validated[item.handle] = ValidatedAssessment(
            handle=item.handle,
            candidate_id=packet.candidate_id,
            verdicts=verdicts,
            contributions=contributions,
            reason=clip(item.reason, REASON_CHARS),
            concerns=[clip(c, CONCERN_CHARS) for c in item.concerns if c.strip()][:MAX_CONCERNS],
            injection_suspected=item.injection_suspected,
            issues=issues,
        )

    missing = set(packets) - set(validated)
    return validated, missing, batch_issues
