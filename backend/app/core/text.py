"""Markdown sanitisation.

Rich text is stored as Markdown and a sanitised HTML rendering. Only this
allow-list may survive; scripts, styles, iframes, event attributes and
javascript: URLs never do. The SPA renders the sanitised HTML.
"""

import markdown as markdown_lib
import nh3

ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h2",
    "h3",
    "h4",
    "hr",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}

LINK_REL = "noopener noreferrer nofollow"


def render_markdown(source: str | None, *, max_chars: int = 20000) -> str:
    if not source:
        return ""
    text = source[:max_chars]
    html = markdown_lib.markdown(text, extensions=["extra", "sane_lists"])
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel=LINK_REL,
        url_schemes={"http", "https", "mailto"},
    )


def plain_text(source: str | None, *, limit: int = 200) -> str:
    if not source:
        return ""
    cleaned = nh3.clean(source, tags=set(), attributes={})
    return " ".join(cleaned.split())[:limit]

