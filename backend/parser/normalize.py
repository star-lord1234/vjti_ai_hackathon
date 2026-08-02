import re
from copy import deepcopy


# --------------------------------------------------
# Marathi -> English digits
# --------------------------------------------------

MARATHI_DIGITS = str.maketrans(
    "०१२३४५६७८९",
    "0123456789"
)


# --------------------------------------------------
# Common OCR mistakes
# --------------------------------------------------

OCR_FIXES = {

    "$": "8",

    "|": "1",

    "l": "1",

    "I": "1",

    "O": "0",

    "o": "0",

    "—": "-",

    "–": "-",

    "−": "-",

    "“": '"',

    "”": '"',

    "‘": "'",

    "’": "'",

}


# --------------------------------------------------
# Department aliases
# --------------------------------------------------

DEPARTMENT_ALIASES = {
    "प्र शा मा": "प्रशामा",
    "विशि -": "विशि-",
    "आस्था -": "आस्था-",
    "संकीर्ण -": "संकीर्ण-",
}


# --------------------------------------------------
# Generic cleaners
# --------------------------------------------------

def normalize_digits(text):

    if not text:
        return text

    return text.translate(MARATHI_DIGITS)


def normalize_whitespace(text):

    if not text:
        return text

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def apply_ocr_fixes(text):

    if not text:
        return text

    for old, new in OCR_FIXES.items():

        text = text.replace(old, new)

    return text


# --------------------------------------------------
# GR NUMBER
# --------------------------------------------------
def normalize_gr_number(gr):
    """
    Normalize a GR number while preserving its structure.

    Example:
    प्रशामा-२०१०/(११५/१०)/विशि-२
        ->
    प्रशामा-2010/(115/10)/विशि-2
    """

    if not gr:
        return None

    # Marathi digits -> English digits
    gr = normalize_digits(gr)

    # Fix OCR punctuation
    gr = apply_ocr_fixes(gr)

    # Normalize whitespace
    gr = normalize_whitespace(gr)

    # Remove spaces around separators
    gr = re.sub(r"\s*/\s*", "/", gr)
    gr = re.sub(r"\s*-\s*", "-", gr)
    gr = re.sub(r"\(\s*", "(", gr)
    gr = re.sub(r"\s*\)", ")", gr)

    # Normalize प्र.क्र. variants to a consistent token for matching
    gr = re.sub(r"प्र\.?\s*क्र\.?\s*", "प्रक्र", gr)

    # Fix department aliases
    for old, new in DEPARTMENT_ALIASES.items():
        gr = gr.replace(old, new)

    return gr


# --------------------------------------------------
# Canonical GR number
# --------------------------------------------------

def canonical_gr_number(gr):
    """
    Canonical key used ONLY for matching.

    प्रशामा-2010/(115/10)/विशि-2

    ->
    प्रशामा201011510विशि2
    """

    if not gr:
        return None

    gr = normalize_gr_number(gr)

    gr = gr.lower()

    # Remove punctuation only
    gr = re.sub(r"[()\[\]{}:;.,/\\-]", "", gr)

    # Remove spaces
    gr = re.sub(r"\s+", "", gr)

    return gr


# Preserve common English acronyms/codes in Marathi subject lines
PRESERVED_ENGLISH_TOKENS = frozenset({
    "AICTE", "ITI", "UGC", "NBA", "NAAC", "NTA", "NEET", "JEE", "GATE",
    "CBSE", "ICSE", "SSC", "HSC", "MSBTE", "DBT", "DST", "ICAR", "NABARD",
    "RTE", "SC", "ST", "OBC", "EWS", "PWD", "PHD", "PDF", "GR", "GOI",
})


def apply_light_text_fixes(text):
    """Punctuation normalization without I/l/o OCR substitutions (preserves AICTE, ITI, etc.)."""
    if not text:
        return text
    for old, new in (
        ("—", "-"), ("–", "-"), ("−", "-"),
        ("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"),
    ):
        text = text.replace(old, new)
    return text


# --------------------------------------------------
# Subject
# --------------------------------------------------

def normalize_subject(subject):

    if not subject:
        return None

    subject = apply_light_text_fixes(subject)
    subject = normalize_digits(subject)

    # Strip lowercase-only OCR garbage but keep acronyms (AICTE, ITI) and mixed-case tokens
    def _subject_token_filter(match: re.Match) -> str:
        token = match.group(0)
        if token.upper() in PRESERVED_ENGLISH_TOKENS:
            return token
        if token.isupper() and len(token) >= 2:
            return token
        if any(c.isupper() for c in token):
            return token
        return ""

    subject = re.sub(r"\b[a-z]{3,}\b", _subject_token_filter, subject)
    subject = normalize_whitespace(subject)

    return subject or None


# --------------------------------------------------
# References
# --------------------------------------------------
def parse_gr_number(gr):

    empty = {
        "department_code": None,
        "year": None,
        "file_number": None,
        "subfile_number": None,
        "section": None,
    }

    if not gr:
        return empty

    gr = normalize_gr_number(gr)

    patterns = [
        (
            r"^(?P<department>.+?)-"
            r"(?P<year>\d{4})"
            r"/\((?P<file>\d+)"
            r"/(?P<subfile>\d+)\)"
            r"/(?P<section>.+)$"
        ),
        (
            r"^(?P<department>.+?)-"
            r"(?P<year>\d{4})"
            r"/प्रक्र(?P<file>\d+)"
            r"/(?P<section>.+)$"
        ),
        (
            r"^(?P<department>.+?)-"
            r"(?P<year>\d{4})"
            r"/\((?P<file>\d+)\)"
            r"/(?P<section>.+)$"
        ),
        (
            r"^(?P<department>.+?)-"
            r"(?P<year>\d{4})"
            r"/(?P<file>\d+)"
            r"/(?P<subfile>\d+)"
            r"/(?P<section>.+)$"
        ),
        (
            r"^(?P<department>.+?)-"
            r"(?P<year>\d{4})"
            r"/(?P<section>.+)$"
        ),
    ]

    for pattern in patterns:
        m = re.match(pattern, gr)
        if not m:
            continue
        groups = m.groupdict()
        file_num = groups.get("file")
        subfile_num = groups.get("subfile")
        return {
            "department_code": groups["department"].strip(),
            "year": int(groups["year"]),
            "file_number": int(file_num) if file_num else None,
            "subfile_number": int(subfile_num) if subfile_num else None,
            "section": (groups.get("section") or "").strip() or None,
        }

    return empty

def normalize_references(refs):

    if not refs:

        return []

    cleaned = []

    for ref in refs:

        item = deepcopy(ref)

        raw = item.get("raw")

        raw = apply_ocr_fixes(raw)

        raw = normalize_digits(raw)

        raw = normalize_whitespace(raw)

        item["raw"] = raw

        cleaned.append(item)

    return cleaned


# --------------------------------------------------
# Document Type
# --------------------------------------------------

DOCUMENT_TYPES = {

    "शासन निर्णय": "Government Resolution",

    "शासन परिपत्रक": "Government Circular",

    "शासन पत्र": "Government Letter",

    "शासन पूरक पत्र": "Supplementary Government Letter",

    "कार्यालयीन आदेश": "Office Order",

    "अधिसूचना": "Notification"

}


# --------------------------------------------------
# Main
# --------------------------------------------------

def normalize_metadata(metadata):

    metadata = deepcopy(metadata)

    metadata["gr_number_original"] = metadata.get("gr_number")

    metadata["gr_number_normalized"] = normalize_gr_number(
        metadata.get("gr_number")
    )

    metadata["gr_number_canonical"] = canonical_gr_number(
        metadata.get("gr_number")
    )

    components = parse_gr_number(
        metadata["gr_number_normalized"]
    )

    metadata.update(components)

    metadata.pop("gr_components", None)

    metadata["subject"] = normalize_subject(

        metadata.get("subject")

    )

    metadata["references"] = normalize_references(

        metadata.get("references")

    )

    if metadata.get("date"):

        value = metadata["date"]
        if hasattr(value, "isoformat"):
            metadata["date"] = value.isoformat()
        else:
            # Already a string (e.g. YYYY-MM-DD from JSON / rule extractor)
            metadata["date"] = str(value).strip() or None

    metadata["document_type_en"] = DOCUMENT_TYPES.get(

        metadata.get("document_type"),

        None

    )

    return metadata