from app.models.assessment import AssessmentOut, BatchOut, ContributionOut, VerdictOut
from app.models.intent import Requirement
from app.models.pipeline import Evidence, Packet
from app.services.validation import validate_batch

REQS = [
    Requirement(id="r1", text="CATIA V5", kind="skill", must_have=True, aliases=["CATIA"], source="query"),
    Requirement(id="r2", text="GD&T", kind="skill", must_have=True, aliases=["ASME Y14.5"], source="query"),
    Requirement(id="r3", text="AS9100", kind="keyword", must_have=False, aliases=[], source="job"),
]


def packet(handle: str, cid: str, items: list[tuple[str, str]]) -> Packet:
    ev = {
        f"{handle}-e{i:02d}": Evidence(eid=f"{handle}-e{i:02d}", source=src, label=src, text=text)
        for i, (src, text) in enumerate(items, start=1)
    }
    return Packet(handle=handle, candidate_id=cid, evidence=ev)


PACKETS = {
    "c01": packet(
        "c01",
        "500",
        [("resume", "Used CATIA V5 daily on airframe brackets."), ("client_feedback", "Client: GD&T depth was light.")],
    ),
    "c02": packet(
        "c02", "501", [("profile", "Skills: SolidWorks, ASME Y14.5"), ("placements", "Placed at Aerodyne 2023.")]
    ),
}


def assessment(handle, verdicts, contributions=(), reason="ok"):
    return AssessmentOut(
        handle=handle,
        verdicts=[VerdictOut(requirement_id=r, status=s, evidence_ids=e) for r, s, e in verdicts],
        source_contributions=[
            ContributionOut(source=s, effect=f, summary="x", evidence_ids=e) for s, f, e in contributions
        ],
        reason=reason,
        concerns=[],
        injection_suspected=False,
    )


def test_fabricated_duplicate_and_missing_handles():
    out = BatchOut(
        assessments=[
            assessment("c01", [("r1", "met", ["c01-e01"])]),
            assessment("c01", [("r1", "unknown", [])]),  # duplicate
            assessment("c99", [("r1", "met", ["c99-e01"])]),  # fabricated
        ]
    )
    validated, missing, issues = validate_batch(PACKETS, REQS, out)
    assert set(validated) == {"c01"}
    assert missing == {"c02"}
    assert any("unknown handle" in i for i in issues)
    assert any("duplicate" in i for i in issues)
    assert validated["c01"].verdicts["r1"].status == "met"


def test_evidence_from_another_candidate_is_removed_and_claim_downgraded():
    out = BatchOut(assessments=[assessment("c02", [("r1", "met", ["c01-e01"])])])
    validated, _, _ = validate_batch(PACKETS, REQS, out)
    v = validated["c02"].verdicts["r1"]
    assert v.evidence_ids == []
    assert v.status == "unverified"
    assert any("another candidate" in i for i in validated["c02"].issues)


def test_met_must_be_supported_by_cited_text():
    # c02's profile mentions ASME Y14.5 (alias of GD&T) but not CATIA.
    out = BatchOut(assessments=[assessment("c02", [("r1", "met", ["c02-e01"]), ("r2", "met", ["c02-e01"])])])
    validated, _, _ = validate_batch(PACKETS, REQS, out)
    assert validated["c02"].verdicts["r1"].status == "unverified"
    assert validated["c02"].verdicts["r2"].status == "met"


def test_not_met_without_evidence_becomes_unknown_and_missing_verdicts_are_unknown():
    out = BatchOut(assessments=[assessment("c01", [("r2", "not_met", []), ("r1", "not_met", ["c01-e01"])])])
    validated, _, _ = validate_batch(PACKETS, REQS, out)
    verdicts = validated["c01"].verdicts
    assert verdicts["r2"].status == "unknown"  # absence of evidence is not proof
    assert verdicts["r1"].status == "not_met"  # cites evidence, kept
    assert verdicts["r3"].status == "unknown"  # never mentioned by the model


def test_contribution_evidence_must_match_its_source():
    out = BatchOut(
        assessments=[
            assessment(
                "c01",
                [],
                contributions=[
                    ("client_feedback", "negative", ["c01-e02"]),
                    ("placements", "positive", ["c01-e01"]),  # e01 is a resume item
                ],
            )
        ]
    )
    validated, _, _ = validate_batch(PACKETS, REQS, out)
    sources = [c.source for c in validated["c01"].contributions]
    assert sources == ["client_feedback"]
