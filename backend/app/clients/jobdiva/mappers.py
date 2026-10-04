"""Tolerant mappers from JobDiva v1 payloads to the DTOs in `app.models.jobdiva`.

All payload keys arrive normalized (lowercase alphanumerics; see client.normalize), so
`"job title"` → `jobtitle`, `CANDIDATEID` → `candidateid`. Field names are not fully documented
for BI endpoints, so each mapper checks several candidate keys. Adjust the key lists here after
running the Day-1 checks against live data.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any

from app.constants.jobdiva import CLIENT_FEEDBACK_HINTS, CONVERSATION_HINTS, SEARCH_TEXT_MIN_CHARS
from app.constants.pii import AUTH_HINTS, PII_KEYS
from app.models.jobdiva import CandidateRecord, Interaction, InteractionType, Job, Qualification, WorkHistoryItem


def pick(row: dict | None, *keys: str, default: Any = None) -> Any:
    if not row:
        return default
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list | dict) and not value:
            continue
        return value
    return default


def as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def as_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip()) if value not in (None, "") else None
    except ValueError:
        return None


_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
)


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):  # epoch millis
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value).date()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            return None
    return None


def iso(value: Any) -> str | None:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def clean_text(value: Any) -> str:
    """Unescape HTML entities, drop tags, collapse whitespace (keeping paragraph breaks)."""
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"(?i)<\s*br\s*/?>|</\s*(p|div|li|h\d)\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------- jobs


def map_job(row: dict) -> Job | None:
    job_id = as_str(pick(row, "id", "jobid"))
    if not job_id:
        return None
    description = pick(row, "jobdescription", "description", "postingdescription", "jobdesc")
    return Job(
        job_id=job_id,
        ref=as_str(
            pick(row, "reference", "jobdivano", "jobdivaref", "referenceno", "optionalref", "optionalreference")
        ),
        title=as_str(pick(row, "jobtitle", "title", "postingtitle")) or "(untitled job)",
        company=as_str(pick(row, "company", "companyname", "customername")),
        city=as_str(pick(row, "city")),
        state=as_str(pick(row, "state")),
        zipcode=as_str(pick(row, "zipcode", "zip")),
        status=as_str(pick(row, "jobstatus", "status")),
        job_type=as_str(pick(row, "jobtype", "positiontype")),
        onsite_remote=as_str(pick(row, "onsiteremote", "remotepercentage", "remote")),
        rate_min=as_float(pick(row, "minimumrate", "payratemin", "minimumbillrate", "billratemin")),
        rate_max=as_float(pick(row, "maximumrate", "payratemax", "maximumbillrate", "billratemax")),
        issue_date=iso(pick(row, "issuedate", "dateissued", "datecreated")),
        description_html=str(description) if description else None,
        description_text=clean_text(description) if description else None,
    )


# ---------------------------------------------------------------------- candidates


def candidate_id_of(row: dict) -> str | None:
    return as_str(pick(row, "candidateid", "candidateidinjd", "id", "employeeid", "docid"))


def _split_name(full: str | None) -> tuple[str | None, str | None]:
    if not full:
        return None, None
    if "," in full:
        last, first = (p.strip() for p in full.split(",", 1))
        return first or None, last or None
    parts = full.split()
    return (parts[0], " ".join(parts[1:]) or None) if parts else (None, None)


def map_candidate(
    row: dict, existing: CandidateRecord | None = None, *, from_search: bool = False
) -> CandidateRecord | None:
    cid = candidate_id_of(row)
    if not cid:
        return None
    rec = existing or CandidateRecord(candidate_id=cid)
    first, last = _split_name(as_str(pick(row, "candidatename", "name", "fullname")))
    phone = pick(row, "cellphone", "phone1", "homephone", "workphone", "phone", "candidatephone", "candidatephones")
    if isinstance(phone, list):
        phone = next((p for p in phone if p), None)
    update = {
        "first_name": as_str(pick(row, "firstname", "first", "candidatefirstname")) or first,
        "last_name": as_str(pick(row, "lastname", "last", "candidatelastname")) or last,
        "title": as_str(
            pick(row, "title", "currenttitle", "jobtitle", "position", "candidatetitle", "titleskillcertification")
        ),
        "employer": as_str(pick(row, "currentemployer", "currentcompany", "employer")),
        "city": as_str(pick(row, "city", "candidatecity")),
        "state": as_str(pick(row, "state", "candidatestate")),
        "zipcode": as_str(pick(row, "zipcode", "zip", "postalcode", "candidatezipcode")),
        "country": as_str(pick(row, "country")),
        "email": as_str(pick(row, "email", "emailaddress", "candidateemail")),
        "phone": as_str(phone),
        "years_experience": as_float(
            pick(row, "yearsofexperience", "yearsexperience", "totalexperience", "experienceyears", "years")
        ),
        "work_authorization": as_str(
            pick(row, "workauthorization", "visastatus", "citizenship", "workstatus", "legalstatus")
        ),
        "updated_on": iso(
            pick(
                row,
                "dateprofileupdated",
                "dateupdated",
                "datelastupdated",
                "lastupdated",
                "datemodified",
                "received",
                "datecreated",
            )
        ),
    }
    available = pick(row, "available", "availablenow")
    if available is not None:
        update["available"] = str(available).lower() in ("true", "1", "yes", "y")
    for key, value in update.items():
        if value is not None and getattr(rec, key) in (None, ""):
            setattr(rec, key, value)
    for q in as_rows(pick(row, "qualifications")):
        add_qualification(rec, q)
    skills = pick(row, "skills", "skill", "keywords")
    if isinstance(skills, list):
        for value in skills:
            add_qualification(rec, {"qualificationname": "Skills", "qualificationvalue": str(value)})
    elif isinstance(skills, str):
        add_qualification(rec, {"qualificationname": "Skills", "qualificationvalue": skills})
    # Search documents (Solr) may carry resume/summary text under undocumented keys: keep long text fields,
    # excluding contact/identity fields. PII is scrubbed again before anything reaches Claude.
    if from_search and rec.search_text is None:
        bits = [
            clean_text(v)
            for k, v in row.items()
            if isinstance(v, str)
            and (len(v) > SEARCH_TEXT_MIN_CHARS or k == "abstract")
            and k not in PII_KEYS
            and k != "lastnote"  # mapped as an interaction instead (map_last_note)
            and not k.endswith("id")
        ]
        rec.search_text = "\n\n".join(b for b in bits if b) or None
    return rec


def as_rows(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def add_qualification(rec: CandidateRecord, row: dict) -> None:
    name = (
        as_str(pick(row, "qualificationname", "categoryname", "name", "category", "qualification")) or "Qualification"
    )
    value = as_str(pick(row, "qualificationvalue", "value", "dcatnames", "description"))
    if not value:
        return
    for part in re.split(r"[;,|]\s*", value):
        part = part.strip()
        if part and not any(q.value.lower() == part.lower() and q.name == name for q in rec.qualifications):
            rec.qualifications.append(Qualification(name=name, value=part))
    if rec.work_authorization is None and any(h in name.lower() for h in AUTH_HINTS):
        rec.work_authorization = value


# --------------------------------------------------------------------- interactions


def map_note(row: dict, index: int) -> Interaction | None:
    content = clean_text(pick(row, "note", "notes", "notetext", "comments", "comment", "text", "description"))
    if not content:
        return None
    action = (as_str(pick(row, "actiontype", "action", "actionname", "type")) or "").lower()
    if any(h in action for h in CLIENT_FEEDBACK_HINTS):
        kind: InteractionType = "client_feedback"
    elif any(h in action for h in CONVERSATION_HINTS):
        kind = "recorded_conversations"
    else:
        kind = "notes"
    return Interaction(
        interaction_id=as_str(pick(row, "noteid", "id")) or f"note-{index}",
        type=kind,
        date=iso(pick(row, "datecreated", "actiondate", "notedate", "date", "dateupdated")),
        author=as_str(pick(row, "recruitername", "createdbyname", "createdby", "author", "username", "recruiter")),
        client=as_str(pick(row, "companyname", "company", "customername")),
        job_id=as_str(pick(row, "jobid", "link2anopenjob")),
        status=as_str(pick(row, "actiontype", "action")),
        content=content,
    )


def map_submittal(row: dict, index: int) -> list[Interaction]:
    """searchSubmittal (Submittal) and searchStart (Activity) rows carry submission, interview, hire and
    rejection details together; split them into typed interactions."""
    base_id = as_str(pick(row, "submittalid", "interviewscheduleid", "id")) or f"sub-{index}"
    client = as_str(pick(row, "companyname", "customername", "company", "client"))
    job_id = as_str(pick(row, "jobidinjd", "jobid"))
    job_title = as_str(pick(row, "jobtitle", "positiontitle", "title"))
    status = as_str(pick(row, "submittalstatus", "startstatus", "status", "pipelinestage"))
    # BI submittal rows carry flags instead of a status or interview/hire dates.
    flags = {
        k: str(row.get(k, "")).strip().lower() in ("1", "true", "y", "yes")
        for k in ("rejectflag", "interviewflag", "hireflag")
    }
    if not status and any(flags.values()):
        status = "Hired" if flags["hireflag"] else "Rejected" if flags["rejectflag"] else "Interviewed"
    notes = clean_text(pick(row, "internalnotes", "notes", "comments"))
    reject = clean_text(pick(row, "rejectioncomment", "rejectionreason", "rejectreason", "reason"))
    role = (job_title or (f"job {job_id}" if job_id else "a role")) + (f" at {client}" if client else "")
    out: list[Interaction] = []

    submitted = iso(pick(row, "submittaldate", "datesubmitted"))
    if submitted or pick(row, "submittalid", "submittalstatus"):
        text = (
            f"Submitted to {role}." + (f" Status: {status}." if status else "") + (f" Notes: {notes}" if notes else "")
        )
        out.append(
            Interaction(
                interaction_id=f"{base_id}-sub",
                type="submissions",
                date=submitted,
                client=client,
                job_id=job_id,
                job_title=job_title,
                status=status,
                content=text,
            )
        )
    interview = iso(pick(row, "interviewdate", "dateinterview", "interviewscheduledate", "dateinterviewed"))
    if not interview and flags["interviewflag"]:
        interview = submitted
    if interview:
        out.append(
            Interaction(
                interaction_id=f"{base_id}-int",
                type="interviews",
                date=interview,
                client=client,
                job_id=job_id,
                job_title=job_title,
                status=status,
                content=f"Interviewed for {role}.",
            )
        )
    hired = iso(pick(row, "hiredate", "startdate", "datehired", "datestarted"))
    if not hired and flags["hireflag"]:
        hired = submitted
    if hired:
        end = iso(pick(row, "enddate", "terminationdate"))
        text = f"Placed in {role}, started {hired}" + (f", ended {end}" if end else "") + "."
        if not submitted and notes:
            text += f" Notes: {notes}"
        out.append(
            Interaction(
                interaction_id=f"{base_id}-plc",
                type="placements",
                date=hired,
                client=client,
                job_id=job_id,
                job_title=job_title,
                status=status,
                content=text,
            )
        )
    rejected = iso(
        pick(row, "extdaterejected", "daterejected", "rejecteddate", "externalrejectdate", "internalrejectdate")
    )
    if reject or rejected or flags["rejectflag"]:
        out.append(
            Interaction(
                interaction_id=f"{base_id}-fb",
                type="client_feedback",
                date=rejected or submitted,
                client=client,
                job_id=job_id,
                job_title=job_title,
                status=status,
                content=f"Not selected for {role}." + (f" Comment: {reject}" if reject else ""),
            )
        )
    if not out and notes:
        out.append(
            Interaction(
                interaction_id=f"{base_id}-note",
                type="notes",
                date=submitted,
                client=client,
                job_id=job_id,
                job_title=job_title,
                status=status,
                content=notes,
            )
        )
    return out


def dedupe_interactions(items: list[Interaction]) -> list[Interaction]:
    """searchSubmittal and searchStart can describe the same record; keep one per (type, job, date)."""
    seen: set[tuple] = set()
    out = []
    for it in items:
        key = (it.type, it.job_id, it.date, it.content[:60] if it.type in ("notes", "client_feedback") else "")
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def map_experience(row: dict) -> WorkHistoryItem:
    """BI experience rows: {details: "Title | Company", date: "MM/YYYY - MM/YYYY"}; other shapes field by field."""
    details = as_str(pick(row, "details"))
    title = as_str(pick(row, "title", "jobtitle", "position"))
    company = as_str(pick(row, "company", "companyname", "employer"))
    if details and not (title or company):
        head, _, tail = details.partition("|")
        title, company = head.strip() or None, tail.strip() or None
    city, state = as_str(pick(row, "city")), as_str(pick(row, "state"))
    return WorkHistoryItem(
        title=title,
        period=as_str(pick(row, "date", "dates", "period")),
        company=company,
        location=", ".join(p for p in (city, state) if p) or None,
        start=iso(pick(row, "startdate", "fromdate", "datefrom")),
        end=iso(pick(row, "enddate", "todate", "dateto")),
        description=clean_text(pick(row, "description", "duties", "responsibilities")) or None,
    )


def apply_work_history(rec: CandidateRecord, rows: list[dict]) -> None:
    """Attach work history (most recent first, as JobDiva returns it) and fill a missing title/employer from it."""
    rec.work_history = [w for w in (map_experience(r) for r in rows) if w.title or w.company]
    if rec.work_history:
        latest = rec.work_history[0]
        rec.title = rec.title or latest.title
        rec.employer = rec.employer or latest.company


def newest_resume_id(rows: list[dict]) -> dict[str, str]:
    """Map candidate id → newest resume id from a (Candidates)ResumesDetail payload."""
    best: dict[str, tuple[str, str]] = {}
    for row in rows:
        cid = as_str(pick(row, "candidateid", "id"))
        rid = as_str(pick(row, "resumeid"))
        if not cid or not rid:
            continue
        stamp = iso(pick(row, "dateuploaded", "datecreated", "dateupdated", "resumedate")) or ""
        if cid not in best or stamp > best[cid][0]:
            best[cid] = (stamp, rid)
    return {cid: rid for cid, (_, rid) in best.items()}


def resume_text_of(row: dict | None) -> str | None:
    text = clean_text(pick(row, "plaintext", "resumetext", "text", "content"))
    return text or None


def map_last_note(row: dict) -> Interaction | None:
    """TalentSearch rows carry the candidate's most recent note as LASTNOTE."""
    content = clean_text(pick(row, "lastnote"))
    if not content:
        return None
    return Interaction(interaction_id=f"lastnote-{candidate_id_of(row)}", type="notes", content=content)
