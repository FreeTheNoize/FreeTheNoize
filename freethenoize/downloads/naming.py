"""Title clean-up and filename templates."""
import re
import string

# Promo noise uploaders put in titles: "[FREE DL]", "(Out Now!)", "*PREMIERE*"…
_NOISE_WORDS = (
    r"free\s*(?:dl|d/?l|download)|out\s*now!*|premiere|preview|snippet"
    r"|buy\s*=\s*free(?:\s*download)?|click\s*buy(?:\s*for\s*free\s*(?:dl|download))?"
    r"|supported\s*by\s*[^)\]}]*"
)
_BRACKETED_NOISE = re.compile(
    rf"\s*[\[\(\{{*]\s*(?:{_NOISE_WORDS})\s*[\]\)\}}*]", re.IGNORECASE
)
_TRAILING_NOISE = re.compile(
    rf"\s*(?:\||//|\*|—|–|-)\s*(?:{_NOISE_WORDS})\s*$", re.IGNORECASE
)
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

DEFAULT_TEMPLATE = "{artist} - {title}"
TEMPLATE_FIELDS = ("artist", "title", "uploader", "playlist", "index", "date", "id")


def clean_title(title: str) -> str:
    previous = None
    while previous != title:
        previous = title
        title = _BRACKETED_NOISE.sub("", title)
        title = _TRAILING_NOISE.sub("", title)
    return re.sub(r"\s{2,}", " ", title).strip() or previous.strip()


def split_artist_title(title: str, uploader: str) -> tuple[str, str]:
    """SoundCloud has no artist field; most uploads use "Artist - Title"."""
    for sep in (" - ", " – ", " — "):
        if sep in title:
            artist, rest = title.split(sep, 1)
            if artist.strip() and rest.strip():
                return artist.strip(), rest.strip()
    return uploader, title


def safe_filename(name: str, max_len: int = 180) -> str:
    name = _ILLEGAL.sub("_", name)
    name = re.sub(r"\s{2,}", " ", name).strip().rstrip(". ")
    if name.lower() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:max_len].rstrip(". ") or "untitled"


class _Blank(dict):
    def __missing__(self, key):
        return ""


def render_template(template: str, fields: dict) -> str:
    try:
        # Only allow plain {field} names; no attribute access or indexing.
        for _, field, _, _ in string.Formatter().parse(template):
            if field and field not in TEMPLATE_FIELDS:
                raise ValueError(field)
        rendered = template.format_map(_Blank(fields))
    except (ValueError, KeyError, IndexError):
        rendered = DEFAULT_TEMPLATE.format_map(_Blank(fields))
    # Collapse separators left dangling by empty fields: "Artist -  - Title".
    rendered = re.sub(r"(\s*-\s*){2,}", " - ", rendered).strip(" -_")
    return safe_filename(rendered)
