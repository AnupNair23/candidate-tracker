from app.models.results import Funnel, QueryStat, RequirementFailure
from app.services.shortfall import explain
from tests.test_scoring_and_packets import intent


def test_no_explanation_when_target_met():
    assert explain(Funnel(shortlisted=30), intent(), target=30, review_depth=40) is None


def test_explains_binding_constraint_and_relaxation():
    funnel = Funnel(
        queries=[
            QueryStat(label="Already linked to this job", criteria="", returned=2),
            QueryStat(label="Title only", criteria="x", returned=20),
        ],
        pool=22,
        linked=2,
        excluded_by_filter={"location": 3},
        reviewed=19,
        assessed=17,
        not_assessed=2,
        not_assessed_reasons={"deadline": 2},
        not_a_fit=4,
        failing_requirements=[RequirementFailure(requirement_id="r1", label="CATIA V5", count=4, sole_blocker=3)],
        insufficient_evidence=1,
        shortlisted=12,
    )
    sf = explain(funnel, intent(), target=30, review_depth=40)
    assert sf is not None
    assert sf.headline == "Found 12 of 30 candidates."
    text = " ".join(sf.reasons)
    assert "only 22 unique candidates" in text
    assert "3 were outside the required 50-mile radius" in text
    assert "'CATIA V5' (4)" in text
    assert "2 candidates could not be reviewed" in text and "time limit" in text
    assert "unknown, not proof" in text
    assert any("Making 'CATIA V5' nice-to-have would admit up to 3" in s for s in sf.suggestions)


def test_zero_results():
    sf = explain(Funnel(pool=0, shortlisted=0), intent(), target=30, review_depth=40)
    assert sf is not None and sf.headline.startswith("No candidates")
