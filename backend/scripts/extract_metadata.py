import json
import os
import time
import sys
import re
import traceback
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import httpx
from tqdm import tqdm
from pydantic import ValidationError

from parser.metadata import GRMetadata
from parser.normalize import normalize_gr_number
from parser.paths import resolve_text_folder
from parser.rule_extractor import rule_extract, get_missing_fields, CORE_FIELDS

from llm.config import default_ingest_model

# Fast model for residual LLM fills
MODEL = default_ingest_model()

# Phase 1: pure regex — very high parallelism (no API)
RULE_WORKERS = int(os.getenv("RULE_WORKERS", str(max(16, (os.cpu_count() or 4) * 4))))

# Phase 2: LLM only for incomplete docs (keys share one org → keep at 1)
LLM_WORKERS = int(os.getenv("LLM_WORKERS", "1"))

# Pace LLM starts to avoid TPM thrashing on shared org
_MIN_REQUEST_GAP = float(os.getenv("MIN_REQUEST_GAP", "0.35"))
_request_lock = threading.Lock()
_last_request_at = 0.0

TEXT_FOLDER = resolve_text_folder(ROOT)
OUTPUT_FOLDER = ROOT / "metadata"
OUTPUT_FOLDER.mkdir(exist_ok=True)

ERROR_LOG = ROOT / "failed_metadata.txt"
_error_lock = threading.Lock()
_tpd_block_event = threading.Event()

# Lazy — rule phase must not wait on LLM client init
_api_manager = None


def get_api_manager():
    global _api_manager
    if _api_manager is None:
        from llm.manager import LLMClientManager

        _api_manager = LLMClientManager()
    return _api_manager


SYSTEM_PROMPT = """
You are an expert at extracting metadata from Maharashtra Government Resolution (GR) OCR documents.

Your task is ONLY to extract the requested metadata fields.

Return EXACTLY one valid JSON object.

Do NOT include markdown.
Do NOT include explanations.
Do NOT include comments.
Do NOT include ```json.
Do NOT include trailing commas.

Return only JSON.

----------------------------
FIELD DEFINITIONS
----------------------------

document_type

Look ONLY in the document header.

It is usually one of:

- शासन निर्णय
- शासन पत्र
- शासन परिपत्रक
- कार्यालयीन आदेश
- अधिसूचना
- शासन पूरक पत्र

Return the exact Marathi text.

If not found return null.


department

The issuing department is usually printed directly below

महाराष्ट्र शासन

Return the complete department name.

Do not shorten it.

If not found return null.


gr_number

Extract ONLY the official document number printed after one of these labels:

क्रमांक
क्रमांक :
क्र.
क्र :

Copy the identifier exactly as printed.

Do NOT normalize.

Do NOT translate.

Do NOT change Marathi digits.

Do NOT include शासन निर्णय / क्र. / क्रमांक prefixes.


date

Extract the official GR issue date.

Look for labels like

दिनांक

दि.

Convert the result to

YYYY-MM-DD

If no date exists return null.


subject

Extract ONLY the text after

विषय

विषय :

If there is no विषय label, use the title block above महाराष्ट्र शासन.

If the subject spans multiple lines, join them into one sentence.

Return the complete subject.


references

Extract ONLY references listed under

वाचा

Each reference should be

{
    "raw": "...",
    "date": "YYYY-MM-DD or null"
}

If there is no वाचा section return [].


----------------------------
IMPORTANT
----------------------------

Never invent values.

Never infer missing metadata.

Never normalize text.

Preserve Marathi exactly.

If a value cannot be found, return null.

Your output MUST be parseable by Python json.loads().
"""


def build_llm_prompt(missing_fields: list[str]) -> str:
    """Ask the model for only the fields regex could not fill."""

    field_list = "\n".join(f"- {name}" for name in missing_fields)
    schema_fields = {name: None for name in missing_fields}
    if "references" in missing_fields:
        schema_fields["references"] = []

    schema = json.dumps(schema_fields, ensure_ascii=False, indent=4)

    return (
        SYSTEM_PROMPT
        + "\n\nThe following metadata fields are missing:\n\n"
        + field_list
        + "\n\nExtract ONLY these fields.\n"
        + "Do not return the others.\n\n"
        + "Return JSON with exactly this shape (null if not found):\n\n"
        + schema
    )


def merge_metadata(base: GRMetadata, llm_data: dict) -> GRMetadata:
    """
    Fill only empty fields on base from llm_data.
    Never overwrite values already set by the rule extractor.
    """

    merged = base.model_dump()

    for key, value in llm_data.items():
        if key == "filename":
            continue
        if key not in merged and key not in CORE_FIELDS and key != "references":
            continue

        current = merged.get(key)
        empty = current is None or (isinstance(current, str) and not current.strip())
        if key == "references":
            empty = not current

        if empty and value is not None:
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value

    return GRMetadata(**merged)


def save_metadata(metadata: GRMetadata):

    output = OUTPUT_FOLDER / metadata.filename.replace(".txt", ".json")
    tmp = output.with_suffix(".json.tmp")

    data = metadata.model_dump()
    data["gr_normalised"] = normalize_gr_number(data.get("gr_number"))

    # Compact JSON → faster writes for 6k files
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)

    tmp.replace(output)


def parse_duration(text: str) -> float:
    """Parse retry-after durations like 1m19.488s, 2m7.872s, 19.5s, 500ms."""

    total = 0.0
    parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(ms|h|m|s)", text, re.IGNORECASE)

    if not parts:
        try:
            return float(text)
        except ValueError:
            return 60.0

    for value, unit in parts:
        v = float(value)
        u = unit.lower()
        if u == "h":
            total += v * 3600
        elif u == "m":
            total += v * 60
        elif u == "ms":
            total += v / 1000.0
        else:
            total += v

    return total if total > 0 else 60.0


def parse_retry_after(error) -> tuple[float, bool]:
    """
    Returns (seconds, is_daily_quota).
    Daily quota (TPD/RPD) should pause the run for later resume.
    """

    message = str(error)
    lower = message.lower()
    is_daily = any(
        x in lower
        for x in (
            "tokens per day",
            "tpd",
            "requests per day",
            "rpd",
        )
    )

    try:
        headers = getattr(getattr(error, "response", None), "headers", None) or {}
        for key in ("retry-after", "Retry-After"):
            if key in headers:
                return float(headers[key]), is_daily
    except Exception:
        pass

    match = re.search(r"try again in\s+([0-9hms\.]+)", message, re.IGNORECASE)
    if match:
        return parse_duration(match.group(1)), is_daily

    return 60.0, is_daily


def _acquire_request_slot():
    """Pace outbound calls so workers don't stampede a shared org limit."""

    global _last_request_at

    with _request_lock:
        now = time.time()
        wait = _MIN_REQUEST_GAP - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.time()


_DIGIT_PREFIX = tuple("०१२३४५६७८९0123456789")
_BODY_MARKERS = ("प्रस्तावना", "शासन निर्णय", "शासन परिपत्रक", "आदेश :", "आदेश:")


def extract_header(text: str) -> str:
    """
    Keep the GR header plus the वाचा block (references),
    stopping at प्रस्तावना / body.
    """

    header = []
    seen_vacha = False

    for line in text.splitlines():

        line = line.strip()
        if not line:
            continue

        if not seen_vacha and any(x in line for x in ("वाचा", "बाचा")):
            header.append(line)
            seen_vacha = True
            continue

        if seen_vacha:
            # Numbered reference lines often contain "शासन निर्णय" — keep those.
            if any(m in line for m in _BODY_MARKERS) and not line.startswith(_DIGIT_PREFIX):
                break

            header.append(line)

            if len(header) >= 55:
                break
            continue

        header.append(line)

        if len(header) >= 40:
            break

    return "\n".join(header)


def llm_extract_missing(text, missing_fields, filename, retries=5):
    """Call the LLM only for the listed missing fields."""

    header = extract_header(text)

    if not header.strip():
        return {}

    system_prompt = build_llm_prompt(missing_fields)
    api_manager = get_api_manager()
    max_tokens = min(700, 80 + 60 * len(missing_fields))
    if "references" in missing_fields:
        max_tokens = max(max_tokens, 500)

    attempt = 0
    rate_limit_rounds = 0

    while attempt < retries:

        if _tpd_block_event.is_set():
            return None

        idx, client = api_manager.wait_for_client(max_wait=90)

        if client is None:
            _tpd_block_event.set()
            return None

        try:

            _acquire_request_slot()

            completion = client.chat.completions.create(
                model=MODEL,
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": header},
                ],
            )

            content = completion.choices[0].message.content
            if not content:
                attempt += 1
                time.sleep(0.5 + attempt)
                continue

            data = json.loads(content)
            if not isinstance(data, dict):
                attempt += 1
                continue

            return {k: data.get(k) for k in missing_fields if k in data}

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after, is_daily = parse_retry_after(e)
                kind = "daily quota" if is_daily else "rate limit"
                print(f"{kind} on LLM (~{retry_after:.0f}s)")
                api_manager.mark_rate_limited(idx, retry_after, all_keys=True)
                rate_limit_rounds += 1
                if is_daily and retry_after >= 45:
                    _tpd_block_event.set()
                    log_failure(
                        filename,
                        f"Daily quota hit (retry_after={retry_after:.1f}s). Re-run later to resume.",
                    )
                    return None
                if rate_limit_rounds >= 20:
                    log_failure(
                        filename,
                        f"Too many rate limits (retry_after={retry_after:.1f}s).",
                    )
                    return None
                continue
            attempt += 1
            time.sleep(min(2 ** attempt, 20))
            continue

        except ValidationError as e:
            attempt += 1
            if attempt >= retries:
                log_failure(filename, str(e))
                return None
            time.sleep(0.3)
            continue

        except (httpx.ConnectError, httpx.TimeoutException):
            print("Network issue")
            attempt += 1
            time.sleep(min(2 ** attempt, 20))
            continue

        except json.JSONDecodeError:
            attempt += 1
            time.sleep(0.3 + attempt * 0.3)
            continue

        except Exception as e:
            print(e)
            attempt += 1
            time.sleep(min(2 ** attempt, 20))
            continue

    return None


def extract_metadata(text: str, filename: str | None = None) -> GRMetadata | None:
    """
    Hybrid extractor public interface.

    1. Rule-based extraction
    2. LLM only for missing CORE_FIELDS (+ references if वाचा present but empty)
    3. Merge without overwriting rule values
    """

    metadata = rule_extract(text, filename=filename)
    missing = get_missing_fields(metadata, text=text)

    if not missing:
        return metadata

    llm_data = llm_extract_missing(text, missing, filename or "")

    if llm_data is None:
        if _tpd_block_event.is_set():
            return None
        return metadata

    if filename:
        metadata.filename = filename

    return merge_metadata(metadata, llm_data)


def log_failure(filename, error):

    with _error_lock:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write(filename + "\n")
            f.write(str(error) + "\n\n")


def _output_path(txt_path: Path) -> Path:
    return OUTPUT_FOLDER / txt_path.name.replace(".txt", ".json")


def process_rule_file(txt_path: Path):
    """
    Phase 1 worker: regex only.
    Always writes/refreshes a JSON (including references from वाचा/संदर्भ).
    Returns ('ok_rule', None) | ('need_llm', (path, text, ruled)) | ('fail', None) | ('skip', None)
    """

    try:
        text = txt_path.read_text(encoding="utf-8", errors="ignore")
        ruled = rule_extract(text, filename=txt_path.name)

        out = _output_path(txt_path)
        if out.exists() and out.stat().st_size > 2:
            try:
                existing = json.loads(out.read_text(encoding="utf-8"))
                # Prefer non-null existing core fields (may be LLM-filled),
                # but always refresh references from rules when rules found any.
                merged = {
                    "filename": txt_path.name,
                    "document_type": existing.get("document_type") or ruled.document_type,
                    "department": existing.get("department") or ruled.department,
                    "gr_number": existing.get("gr_number") or ruled.gr_number,
                    "date": existing.get("date") or ruled.date,
                    "subject": existing.get("subject") or ruled.subject,
                    "references": (
                        [r.model_dump() for r in ruled.references]
                        if ruled.references
                        else (existing.get("references") or [])
                    ),
                    "gr_normalised": existing.get("gr_normalised"),
                }
                meta = GRMetadata(**merged)
                save_metadata(meta)
                missing = get_missing_fields(meta, text=text)
                if not missing:
                    return "skip", None
                return "need_llm", (txt_path, text, meta)
            except Exception:
                pass

        save_metadata(ruled)
        missing = get_missing_fields(ruled, text=text)

        if not missing:
            return "ok_rule", None

        return "need_llm", (txt_path, text, ruled)

    except Exception:
        log_failure(txt_path.name, traceback.format_exc())
        return "fail", None


def process_llm_file(item) -> str:
    """Phase 2 worker: fill only missing fields via LLM, then save."""

    if _tpd_block_event.is_set():
        return "paused"

    txt_path, text, ruled = item
    missing = get_missing_fields(ruled, text=text)

    try:
        if not missing:
            save_metadata(ruled)
            return "ok_rule"

        llm_data = llm_extract_missing(text, missing, txt_path.name)

        if llm_data is None:
            save_metadata(ruled)
            if _tpd_block_event.is_set():
                return "paused"
            return "fail"

        metadata = merge_metadata(ruled, llm_data)
        metadata.filename = txt_path.name
        save_metadata(metadata)
        return "ok_llm"

    except Exception:
        log_failure(txt_path.name, traceback.format_exc())
        try:
            save_metadata(ruled)
        except Exception:
            pass
        return "fail"


def main():

    _tpd_block_event.clear()
    t0 = time.time()

    files = sorted(TEXT_FOLDER.glob("*.txt"))
    print(f"Found {len(files)} documents.")
    print(
        f"Fast hybrid: Phase1 rules x{RULE_WORKERS} (writes ALL jsons), "
        f"Phase2 LLM backfill x{LLM_WORKERS} ({MODEL})."
    )

    # Phase 1 always runs over every file that is missing or incomplete
    ok_rule = fail = skipped = 0
    need_llm = []

    with ThreadPoolExecutor(max_workers=RULE_WORKERS) as executor:
        futures = [executor.submit(process_rule_file, path) for path in files]
        with tqdm(total=len(files), desc="Phase1 rules→json") as bar:
            for future in as_completed(futures):
                status, payload = future.result()
                if status == "ok_rule":
                    ok_rule += 1
                elif status == "need_llm":
                    need_llm.append(payload)
                elif status == "skip":
                    skipped += 1
                elif status == "fail":
                    fail += 1
                bar.update(1)

    json_count = sum(1 for _ in OUTPUT_FOLDER.glob("*.json"))
    print(
        f"Phase1 done in {time.time() - t0:.1f}s — "
        f"jsons={json_count} rule_complete={ok_rule} "
        f"llm_queue={len(need_llm)} skip={skipped} fail={fail}"
    )

    ok_llm = paused = 0

    if need_llm and not _tpd_block_event.is_set():
        get_api_manager()
        workers = max(1, LLM_WORKERS)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_llm_file, item) for item in need_llm]
            with tqdm(total=len(need_llm), desc="Phase2 LLM backfill") as bar:
                for future in as_completed(futures):
                    status = future.result()
                    if status == "ok_llm":
                        ok_llm += 1
                    elif status == "fail":
                        fail += 1
                    elif status == "paused":
                        paused += 1
                    bar.update(1)

    elapsed = time.time() - t0
    print(
        f"Done in {elapsed / 60:.1f} min. "
        f"rule_complete={ok_rule} llm_filled={ok_llm} "
        f"fail={fail} skipped={skipped} paused={paused} "
        f"json_files={sum(1 for _ in OUTPUT_FOLDER.glob('*.json'))}"
    )
    if paused:
        print(
            "Paused on API quota — JSONs already exist; re-run to backfill missing fields."
        )


if __name__ == "__main__":
    main()
