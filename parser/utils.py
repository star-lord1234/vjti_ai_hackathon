import re


def extract_between(text: str, start: str, end: str):

    pattern = rf"{start}\s*[:：-]?\s*(.*?)\s*{end}"

    match = re.search(
        pattern,
        text,
        re.DOTALL
    )

    if match:
        return match.group(1).strip()

    return None


def safe_search(pattern, text):

    match = re.search(pattern, text, re.DOTALL)

    if match:
        return match.group(1).strip()

    return None