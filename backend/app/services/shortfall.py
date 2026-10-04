"""Step 8 — deterministic funnel explanation when fewer than the target candidates qualify.

Built only from counted funnel numbers, so it cannot misstate them.
"""

from __future__ import annotations

from app.constants.ranking import DEFAULT_RADIUS_MI
from app.constants.search import LINKED_QUERY_LABEL, NOT_ASSESSED_LABELS
from app.models.intent import SearchIntent
from app.models.results import Funnel, Shortfall


def explain(funnel: Funnel, intent: SearchIntent, target: int, review_depth: int) -> Shortfall | None:
    n = funnel.shortlisted
    if n >= target:
        return None
    reasons: list[str] = []
    suggestions: list[str] = []
    searches = sum(1 for q in funnel.queries if q.label != LINKED_QUERY_LABEL)

    if funnel.pool == 0:
        reasons.append(f"JobDiva returned no candidates across {searches} searches.")
    elif funnel.pool < target:
        reasons.append(
            f"JobDiva returned only {funnel.pool} unique candidates across {searches} searches"
            + (f" (including {funnel.linked} already linked to this job)." if funnel.linked else ".")
        )
    errored = [q.label for q in funnel.queries if q.error]
    if errored:
        reasons.append(f"{len(errored)} JobDiva search(es) failed: {', '.join(errored)}.")
    if funnel.retrieval_partial:
        reasons.append("JobDiva retrieval stopped early (per-search call budget), so some matches were not loaded.")

    loc_ex = funnel.excluded_by_filter.get("location", 0)
    if loc_ex:
        radius = intent.location.radius_mi if intent.location and intent.location.radius_mi else DEFAULT_RADIUS_MI
        reasons.append(f"{loc_ex} were outside the required {radius}-mile radius (known distance).")
        suggestions.append(
            f"Widening or un-requiring the location filter would re-admit {loc_ex} candidates for review."
        )
    yrs_ex = funnel.excluded_by_filter.get("years", 0)
    if yrs_ex:
        min_years = intent.years.min if intent.years else None
        reasons.append(f"{yrs_ex} had fewer than the required {min_years} years on their JobDiva profile.")
        suggestions.append(f"Lowering or un-requiring minimum years would re-admit {yrs_ex} candidates for review.")

    if funnel.not_a_fit:
        top = funnel.failing_requirements[0] if funnel.failing_requirements else None
        detail = f"; most often '{top.label}' ({top.count})" if top else ""
        reasons.append(f"{funnel.not_a_fit} reviewed candidates have evidence that contradicts a must-have{detail}.")
        for f in funnel.failing_requirements[:2]:
            if f.sole_blocker:
                suggestions.append(
                    f"Making '{f.label}' nice-to-have would admit up to {f.sole_blocker} more reviewed candidates."
                )
    if funnel.insufficient_evidence:
        reasons.append(
            f"{funnel.insufficient_evidence} reviewed candidates had no evidence for any requirement in their JobDiva "
            "records — that is unknown, not proof they lack the skills."
        )
    if funnel.not_assessed:
        why = ", ".join(
            f"{count} because {NOT_ASSESSED_LABELS.get(reason, reason)}"
            for reason, count in sorted(funnel.not_assessed_reasons.items(), key=lambda kv: -kv[1])
        )
        reasons.append(f"{funnel.not_assessed} candidates could not be reviewed ({why}).")
        suggestions.append("Retry the search to review the candidates that were not assessed.")
    if funnel.prescreened_out:
        reasons.append(
            f"{funnel.prescreened_out} more candidates matched the search but ranked below the top {review_depth} "
            "that are reviewed in depth."
        )
        suggestions.append("Tighten the must-have skills or title so the in-depth review covers closer matches.")
    if funnel.pool < target and not suggestions:
        suggestions.append(
            "Broaden the title synonyms or reduce must-have skills; JobDiva search returned few matches."
        )

    headline = "No candidates met the bar for this search." if n == 0 else f"Found {n} of {target} candidates."
    return Shortfall(headline=headline, reasons=reasons, suggestions=list(dict.fromkeys(suggestions)))
