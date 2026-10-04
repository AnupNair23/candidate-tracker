"""Job detail rendering."""

# HTML tags kept when sanitizing a job description (all attributes are stripped).
DESCRIPTION_ALLOWED_TAGS = [
    "p",
    "br",
    "ul",
    "ol",
    "li",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "span",
    "div",
]
