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


# --------------------------------------------------
# Subject
# --------------------------------------------------

def normalize_subject(subject):

    if not subject:
        return None

    subject = apply_ocr_fixes(subject)

    subject = normalize_digits(subject)

    # remove OCR garbage like "fag"

    subject = re.sub(

        r"\b[a-zA-Z]{2,}\b",

        "",

        subject

    )

    subject = normalize_whitespace(subject)

    return subject


# --------------------------------------------------
# References
# --------------------------------------------------
def parse_gr_number(gr):

    empty = {
        "department_code": None,
        "year": None,
        "file_number": None,
        "subfile_number": None,
        "section": None
    }

    if not gr:
        return empty

    gr = normalize_gr_number(gr)

    pattern = (
        r"^(?P<department>.+?)-"
        r"(?P<year>\d{4})"
        r"/\((?P<file>\d+)"
        r"/(?P<subfile>\d+)\)"
        r"/(?P<section>.+)$"
    )

    m = re.match(pattern, gr)

    if not m:
        return empty

    return {
        "department_code": m.group("department").strip(),
        "year": int(m.group("year")),
        "file_number": int(m.group("file")),
        "subfile_number": int(m.group("subfile")),
        "section": m.group("section").strip()
    }

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