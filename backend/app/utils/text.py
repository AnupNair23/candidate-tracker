"""Text helpers: untrusted-data escaping, PII scrubbing and term matching."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+|\b(?:linkedin|github|facebook|twitter|x)\.com/\S*", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z0-9][\w.]*\s){1,4}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Circle|Cir|"
    r"Parkway|Pkwy|Highway|Hwy|Terrace|Ter)\b\.?(?:,?\s*(?:Apt|Suite|Unit|#)\s*[\w-]+)?"
)
_EDU_RE = re.compile(
    r"\b(?:B\.?S\.?|B\.?A\.?|B\.?E\.?|M\.?S\.?|M\.?A\.?|MBA|Ph\.?D|Bachelor'?s?|Master'?s?|Doctorate|Associate'?s?|"
    r"Diploma|University|College|Institute of|Graduated|Graduation|Class of|High School|GED)\b",
    re.I,
)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_BIRTH_RE = re.compile(
    r"(?i)\b(?:d\.?o\.?b\.?|date of birth|birth ?date|born on|born in)\s*[:\-]?\s*[\w/,. -]{0,20}"
    r"|\bage\s*[:\-]?\s*\d{1,3}\b"
)
_GENDER_RE = re.compile(r"(?i)\b(?:gender|sex|marital status|nationality|religion)\s*[:\-]\s*\w+")

_STOPWORDS = {
    "and",
    "or",
    "the",
    "of",
    "in",
    "a",
    "an",
    "for",
    "with",
    "to",
    "on",
    "at",
    "sr",
    "jr",
    "senior",
    "junior",
    "lead",
    "i",
    "ii",
    "iii",
    "iv",
}


def escape_untrusted(text: str | None) -> str:
    """Escape so untrusted text cannot open or close prompt tags (e.g. `</candidate>`)."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def scrub_pii(text: str | None, names: list[str | None] | None = None) -> str:
    """Remove contact details, the candidate's own name, street addresses and age proxies."""
    if not text:
        return ""
    out = _EMAIL_RE.sub("[email]", text)
    out = _URL_RE.sub("[link]", out)
    out = _PHONE_RE.sub("[phone]", out)
    out = _ADDRESS_RE.sub("[address]", out)
    out = _BIRTH_RE.sub("[redacted]", out)
    out = _GENDER_RE.sub("[redacted]", out)
    for name in names or []:
        if name and len(name.strip()) >= 2:
            out = re.sub(rf"(?<![\w]){re.escape(name.strip())}(?![\w])", "[candidate]", out, flags=re.I)
    lines = []
    for line in out.split("\n"):
        if _EDU_RE.search(line):
            line = _YEAR_RE.sub("[year]", line)
        lines.append(line)
    return "\n".join(lines)


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def term_in_text(term: str, text: str) -> bool:
    """Case-insensitive match of `term` in `text`, bounded so 'C' doesn't match 'CATIA'."""
    t = norm(term)
    if not t:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", norm(text)) is not None


def tokens(text: str | None) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#&./]+", norm(text)) if t not in _STOPWORDS and len(t) >= 2}


def supports(requirement_text: str, aliases: list[str], evidence_text: str) -> bool:
    """True if the evidence mentions the requirement, one of its aliases, or all its core tokens."""
    for term in [requirement_text, *aliases]:
        if term_in_text(term, evidence_text):
            return True
    core = tokens(requirement_text)
    if core and len(core) <= 4:
        ev = tokens(evidence_text)
        return core <= ev
    return False


def clip(text: str | None, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
