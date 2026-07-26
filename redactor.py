import itertools
import re
import sys
import threading
from io import BytesIO
from pathlib import Path
from dataclasses import dataclass
from typing import Callable

PLACEHOLDER_MAP = {
    "NAME": "[REDACTED_NAME]",
    "TAJ": "[REDACTED_TAJ]",
    "PHONE": "[REDACTED_PHONE]",
    "EMAIL": "[REDACTED_EMAIL]",
    "DATE_OF_BIRTH": "[REDACTED_DOB]",
    "ADDRESS": "[REDACTED_ADDRESS]",
    "LOCATION": "[REDACTED_LOCATION]",
    "ORGANIZATION": "[REDACTED_ORG]",
    "DOCTOR_ID": "[REDACTED_DOCTOR_ID]",
    "COMPANY_ID": "[REDACTED_COMPANY_ID]",
    "RECORD_ID": "[REDACTED_RECORD_ID]",
}


@dataclass
class PiiSpan:
    start: int
    end: int
    label: str
    text: str
    score: float | None = None  # NER confidence; None for regex spans


@dataclass
class FileEvent:
    """Structured per-file progress event for GUI consumers.

    stage: "converting" | "redacting" | "done" | "failed"
    counts: per-label redaction counts, only set on "done"
    """

    path: str
    stage: str
    counts: dict[str, int] | None = None
    output_name: str | None = None
    error: str | None = None


# --- Regex patterns for Hungarian PII ---

_TAJ_RE = re.compile(r"\b(\d{3})[-\s]?(\d{3})[-\s]?(\d{3})\b")
_TAJ_CONTEXT_RE = re.compile(
    r"(?i)taj[-\s]?sz[aá]m|t[aá]rsadalombiztos[ií]t[aá]si|tb\s*sz[aá]m|biztos[ií]t[aá]si\s*sz[aá]m"
)

_PHONE_RE = re.compile(
    # +36/06-prefixed numbers, or bare mobile numbers like "30/482-7035"
    r"(?:\+36|06)[-\s.]?(?:1|[2-9]\d)[-\s.]?\d{3}[-\s.]?\d{2,4}"
    r"|\b(?:20|30|31|50|70)\s?/\s?\d{3}[-\s.]?\d{4}\b"
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_DATE_NUMERIC_RE = re.compile(
    r"\b(?:19|20)\d{2}[.\-/]\s?(?:0[1-9]|1[0-2])[.\-/]\s?(?:0[1-9]|[12]\d|3[01])\.?\b"
)

_HU_MONTHS = (
    r"(?:janu[aá]r|febru[aá]r|m[aá]rcius|[aá]prilis|m[aá]jus|j[uú]nius"
    r"|j[uú]lius|augusztus|szeptember|okt[oó]ber|november|december)"
)
_DATE_TEXT_RE = re.compile(
    rf"\b(?:19|20)\d{{2}}\.?\s*{_HU_MONTHS}\s*\d{{1,2}}\.?\b", re.IGNORECASE
)

_STREET_TYPES = (
    r"(?:utca|[uú]t|t[eé]r|k[oö]r[uú]t|fasor|k[oö]z|sor|"
    r"d[uű]l[oő]|major|telep|lak[oó]telep|s[eé]t[aá]ny|rakpart)"
)
_ADDRESS_STREET_RE = re.compile(
    rf"\b[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+\s+{_STREET_TYPES}\s+\d+[./\-]?\s*\d*",
    re.IGNORECASE,
)
_POSTAL_CITY_RE = re.compile(r"\b[1-9]\d{3}\s+[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+")

_FIELD_SEP = r"[\s:.|·…\n]*[:\|]?[\s.·…\n]*"

_NAME_KEYWORDS = (
    # birth name
    r"(?:sz[uü]l(?:et[eé]si)?\s*n[eé]v[eé]?"
    r"|le[aá]nykori\s*n[eé]v[eé]?"
    # mother's name
    r"|anyja\s*n[eé]v[eé]?"
    r"|any[aá]n[eé]v"
    r"|anyja\s*sz[uü]l(?:et[eé]si)?\s*n[eé]v[eé]?"
    r"|a\.\s*n[eé]v"
    # patient name
    r"|beteg\s*n[eé]v[eé]?"
    r"|p[aá]ciens\s*n[eé]v[eé]?"
    r"|kezelt\s*n[eé]v[eé]?"
    r"|vizsg[aá]lt\s*szem[eé]ly"
    r"|vizsg[aá]lt\s*n[eé]v[eé]?"
    r"|ell[aá]tott\s*n[eé]v[eé]?"
    r"|gondozott\s*n[eé]v[eé]?"
    r"|[uü]gyf[eé]l\s*n[eé]v[eé]?"
    r"|kliensn[eé]v"
    r"|kliens\s*n[eé]v[eé]?"
    # generic name field
    r"|n[eé]v"
    # insured
    r"|biztos[ií]tott\s*n[eé]v[eé]?"
    # legal representative
    r"|t[oö]rv[eé]nyes\s*k[eé]pvisel[oő]\s*n[eé]v[eé]?"
    r"|hozz[aá]tartoz[oó]\s*n[eé]v[eé]?"
    r"|kapcsolattart[oó]\s*n[eé]v[eé]?"
    # referrer
    r"|beutal[oó]\s*orvos"
    r"|k[eé]r[oő]\s*orvos"
    r"|h[aá]zi\s*orvos"
    # clinician context labels
    r"|bek[uü]ld[oő]\s*orvos"
    r"|kezel[oő]\s*orvos"
    r"|valid[aá]l[oó]"
    r"|vizsg[aá]latot\s*v[eé]gezte"
    r"|leletez[oő]\s*orvos"
    # signed declarations ("Alulírott <name> igazolom...")
    r"|alul[ií]rott"
    r")"
)
_HU_NAME_PART = r"[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+(?:n[eé])?"
# ALL-CAPS variant: OCR'd receipts/headers print names as "MINTA-HORVATH ARON"
# (often accent-stripped). Only ever used label- or context-anchored — bare
# caps word pairs are everywhere in document headers.
_HU_NAME_PART_UC = r"[A-ZÁÉÍÓÖŐÚÜŰ]{2,}(?:N[EÉ])?"
_HU_NAME_SEP = r"[\s\n\-–—\.]+?"
_HU_FULL_NAME = rf"(?:{_HU_NAME_PART}{_HU_NAME_SEP}){{1,4}}{_HU_NAME_PART}"
_HU_FULL_NAME_UC = rf"(?:{_HU_NAME_PART_UC}{_HU_NAME_SEP}){{1,4}}{_HU_NAME_PART_UC}"
# Case-explicit alternatives, wrapped in (?-i:) where the surrounding pattern
# is (?i). Letting the case-insensitive flag reach the name classes makes
# [A-Z][a-z]+ match anything ("Megnevezés" → keyword "nev" + "name" "ezés...").
_HU_FULL_NAME_ANYCASE = rf"(?:{_HU_FULL_NAME}|{_HU_FULL_NAME_UC})"

_NAME_FIELD_RE = re.compile(
    rf"(?i)(?<![a-záéíóöőúüű]){_NAME_KEYWORDS}{_FIELD_SEP}(?-i:({_HU_FULL_NAME_ANYCASE}))",
)

_NAME_TABLE_RE = re.compile(
    rf"(?i)\|\s*{_NAME_KEYWORDS}\s*\|\s*(?-i:({_HU_FULL_NAME_ANYCASE}))\s*\|",
)

# "<NAME> részére" (made out to <name>): receipts and certificates carry the
# patient name in free text with no field label, frequently in ALL CAPS.
# Capped at 3 name parts: with the match anchored at "részére", the regex
# would otherwise greedily pull preceding non-name words into the name.
_NAME_RESZERE_RE = re.compile(
    rf"((?:(?:{_HU_NAME_PART}|{_HU_NAME_PART_UC})[ \t\-–—.]+?){{1,2}}"
    rf"(?:{_HU_NAME_PART}|{_HU_NAME_PART_UC}))[ \t]+(?i:r[eé]sz[eé]re)\b"
)

# Doctor names: "Dr." prefix ("Dr. Fekete Éva", "Dr.Homonai", "dr.Badalay Rob")
# or suffix ("Fekete Éva Dr."). NER usually catches these but misses some near
# chunk boundaries; this is the deterministic backstop. Unlike labeled name
# fields, the name sits right next to "Dr." on the same line, so the separator
# excludes newlines — otherwise the pattern swallows the first word of the
# following sentence ("Dr.Homonai\n\nCsontszerkezeti ...").
_HU_NAME_PART_ANY = rf"(?:{_HU_NAME_PART}|{_HU_NAME_PART_UC})"
_HU_NAME_SEP_INLINE = r"[ \t\-–—.]+?"
_HU_NAME_INLINE_ONE_PLUS = (
    rf"{_HU_NAME_PART_ANY}(?:{_HU_NAME_SEP_INLINE}{_HU_NAME_PART_ANY}){{0,4}}"
)
_HU_NAME_INLINE_TWO_PLUS = (
    rf"{_HU_NAME_PART_ANY}(?:{_HU_NAME_SEP_INLINE}{_HU_NAME_PART_ANY}){{1,4}}"
)
_DR_PREFIX_NAME_RE = re.compile(rf"\b[Dd][Rr]\b\.?[ \t]*({_HU_NAME_INLINE_ONE_PLUS})")
_DR_SUFFIX_NAME_RE = re.compile(
    rf"({_HU_NAME_INLINE_TWO_PLUS})[ \t]+[Dd][Rr]\.?(?![A-Za-z])"
)
# Clinician title right after a multi-part name ("Kis Éva Optometrista",
# OCR-garbled signature blocks NER whiffs on). Requires 2+ name parts so a
# lone capitalized word before a title ("Konzulens orvos") never matches.
_TITLE_SUFFIX_NAME_RE = re.compile(
    rf"({_HU_NAME_INLINE_TWO_PLUS})[ \t]+"
    r"(?i:optometrista|kontaktol[oó]gus|szakorvos|adjunktus|f[oő]orvos|orvos"
    r"|rezidens|asszisztens|szakasszisztens|v[eé]d[oő]n[oő]|gy[oó]gytorn[aá]sz)\b"
)

# Doctor stamp/registry IDs: "EESZT: O43048", and short numeric IDs in parens
# directly after a name ("Kovácsné Kis Mária (36563)", "(azonosító: 220756)").
# The name itself is redacted separately; the ID re-identifies the doctor via
# the public EESZT registry, so it must go too.
_EESZT_ID_RE = re.compile(r"(?i)\bEESZT\s*:?\s*\(?\s*([A-Z]?\d{4,7})\b")
_NAME_PAREN_ID_RE = re.compile(
    rf"{_HU_NAME_PART}\s*\.?\s*\(\s*(?:azonos[ií]t[oó]\s*:?\s*)?([A-Z]?\d{{5,7}})\s*\)"
)
# Bare stamp ID in signature blocks: "Fekete Éva  O43048 adjunktus". The
# letter+5-digit EESZT stamp format directly after a name part.
_NAME_BARE_STAMP_RE = re.compile(rf"{_HU_NAME_PART}\s+([A-Z]\d{{5}})\b")

# Company identifiers: cégjegyzékszám (##-##-######) and adószám (########-#-##).
_COMPANY_REG_RE = re.compile(r"\b\d{2}-\d{2}-\d{6}\b")
_COMPANY_TAX_RE = re.compile(r"\b\d{8}-[1-5]-\d{2}\b")

# Medical record/log/document numbers: label-anchored values and the composite
# EESZT form <institution>-<year>-<serial>. Values allow inner spaces ("5 5 0 0"
# on dot-matrix lab prints), a slash ("12072/2021"), or a letter prefix
# (COVID immunity certificate "V14639234"). At least 4 digits so table row
# numbers ("Sorszám: 1") survive.
_RECORD_ID_LABELS = (
    r"(?:napl[oó](?:sor)?sz[aá]m|sorsz[aá]m|ambul[aá]ns\s*lap\s*sz[aá]m"
    r"|munkasz[aá]m|v[eé]detts[eé]gi\s*igazolv[aá]ny\s*sz[aá]m)a?"
)
_RECORD_ID_SEP = r"[\s_:.|·…\n]*[:\|]?[\s_.·…\n]*"
_RECORD_ID_FIELD_RE = re.compile(
    rf"(?i)(?<![a-záéíóöőúüű]){_RECORD_ID_LABELS}{_RECORD_ID_SEP}"
    rf"([A-Z]?\d(?:[\d /–-]{{0,16}}\d){{3,}})"
)
_RECORD_ID_COMPOSITE_RE = re.compile(r"\b\d{8,9}-(?:19|20)\d{2}-\d{7,8}\b")

# 9-digit institutional codes after these labels routinely pass the TAJ
# checksum; they identify the lab/department, not the patient.
_INSTITUTION_CODE_LABEL_RE = re.compile(r"(?i)(?:NNGYK|NEAK)\s*:?\s*\(?\s*$")

_BIRTH_CONTEXT_RE = re.compile(
    r"(?i)sz[uü]let[eé]si\s*(?:d[aá]tum|id[oő]|hely)"
    r"|sz[uü]l\.?\s*(?:d[aá]t|id[oő])?"
    r"|sz[uü]letett"
    r"|sz\.\s*d\."
    r"|sz\.\s*id[oő]?"
    r"|born"
    r"|d[aá]tum\s*:?\s*sz[uü]l"
    r"|sz[uü]l\.\s*d[aá]t"
)


def _is_birth_date(text: str, match_start: int) -> bool:
    context_start = max(0, match_start - 80)
    context = text[context_start:match_start]
    line_start = text.rfind("\n", 0, match_start) + 1
    line_context = text[line_start:match_start]
    if _BIRTH_CONTEXT_RE.search(line_context):
        return True
    # A different field label on the same line ("Vizsgálat dátuma: ...") marks
    # a non-birth date. A bare prefix without a label is usually the birth
    # place ("Debrecen, 1997.10.22") with the label on an earlier line, so it
    # still falls through to the wider context window.
    if ":" in line_context:
        return False
    return _BIRTH_CONTEXT_RE.search(context) is not None


def _validate_taj(d1: str, d2: str, d3: str) -> bool:
    digits = [int(c) for c in d1 + d2 + d3]
    if len(digits) != 9:
        return False
    weights = [3, 7, 3, 7, 3, 7, 3, 7]
    total = sum(digits[i] * weights[i] for i in range(8))
    return total % 10 == digits[8]


def _find_regex_pii(text: str) -> list[PiiSpan]:
    spans: list[PiiSpan] = []

    for m in _TAJ_RE.finditer(text):
        if _INSTITUTION_CODE_LABEL_RE.search(text[max(0, m.start() - 12) : m.start()]):
            continue
        context_start = max(0, m.start() - 60)
        context = text[context_start : m.start()]
        if _validate_taj(m.group(1), m.group(2), m.group(3)) or _TAJ_CONTEXT_RE.search(context):
            spans.append(PiiSpan(m.start(), m.end(), "TAJ", m.group()))

    for m in _PHONE_RE.finditer(text):
        spans.append(PiiSpan(m.start(), m.end(), "PHONE", m.group()))

    for m in _EMAIL_RE.finditer(text):
        spans.append(PiiSpan(m.start(), m.end(), "EMAIL", m.group()))

    for m in _DATE_NUMERIC_RE.finditer(text):
        if _is_birth_date(text, m.start()):
            spans.append(PiiSpan(m.start(), m.end(), "DATE_OF_BIRTH", m.group()))

    for m in _DATE_TEXT_RE.finditer(text):
        if _is_birth_date(text, m.start()):
            spans.append(PiiSpan(m.start(), m.end(), "DATE_OF_BIRTH", m.group()))

    for m in _ADDRESS_STREET_RE.finditer(text):
        spans.append(PiiSpan(m.start(), m.end(), "ADDRESS", m.group()))

    for m in _POSTAL_CITY_RE.finditer(text):
        if not any(s.start <= m.start() and s.end >= m.end() for s in spans):
            spans.append(PiiSpan(m.start(), m.end(), "ADDRESS", m.group()))

    for pattern in (_NAME_FIELD_RE, _NAME_TABLE_RE):
        for m in pattern.finditer(text):
            name = m.group(1).strip().rstrip(".")
            if name and len(name) > 3:
                name_start = m.start(1)
                name_end = name_start + len(name)
                if not any(s.start <= name_start and s.end >= name_end for s in spans):
                    spans.append(PiiSpan(name_start, name_end, "NAME", name))

    # Dr.-, title- and részére-anchored names: the anchor is strong evidence,
    # so even short single-part surnames ("Dr. Kui") count.
    for pattern in (
        _DR_PREFIX_NAME_RE,
        _DR_SUFFIX_NAME_RE,
        _TITLE_SUFFIX_NAME_RE,
        _NAME_RESZERE_RE,
    ):
        for m in pattern.finditer(text):
            name = m.group(1).strip().rstrip(".")
            if len(name) >= 2:
                name_start = m.start(1)
                name_end = name_start + len(name)
                if not any(s.start <= name_start and s.end >= name_end for s in spans):
                    spans.append(PiiSpan(name_start, name_end, "NAME", name))

    for m in _EESZT_ID_RE.finditer(text):
        spans.append(PiiSpan(m.start(1), m.end(1), "DOCTOR_ID", m.group(1)))

    for m in _NAME_PAREN_ID_RE.finditer(text):
        spans.append(PiiSpan(m.start(1), m.end(1), "DOCTOR_ID", m.group(1)))

    for m in _NAME_BARE_STAMP_RE.finditer(text):
        spans.append(PiiSpan(m.start(1), m.end(1), "DOCTOR_ID", m.group(1)))

    for pattern in (_COMPANY_REG_RE, _COMPANY_TAX_RE):
        for m in pattern.finditer(text):
            spans.append(PiiSpan(m.start(), m.end(), "COMPANY_ID", m.group()))

    for m in _RECORD_ID_FIELD_RE.finditer(text):
        spans.append(PiiSpan(m.start(1), m.end(1), "RECORD_ID", m.group(1)))

    for m in _RECORD_ID_COMPOSITE_RE.finditer(text):
        spans.append(PiiSpan(m.start(), m.end(), "RECORD_ID", m.group()))

    return spans


# Calibrated on the 76-document private corpus (2026-07-12): every observed
# span that ate a clinical word (Epistaxis, Kálium, Rowachol, Mounjaro
# fragments) scored <= 0.72, while dropping real-name spans only starts
# leaking at >= 0.8 ('Rádi Fan' 0.727, 'Szabóné' 0.768). 0.7 removed ~22% of
# NER spans with zero end-to-end leak change; do not raise it without
# re-running scripts from that session (score_calibration.py).
_NER_MIN_SCORE = 0.7


def _find_ner_pii(text: str, ner_pipeline) -> list[PiiSpan]:
    label_map = {"PER": "NAME", "LOC": "LOCATION", "ORG": "ORGANIZATION"}
    spans: list[PiiSpan] = []

    def run_chunk(chunk: str, offset: int, accept=None):
        # The model hard-caps at 512 tokens. Dense content (markdown tables,
        # lab values) tokenizes far heavier than prose, so an 800-char chunk
        # can overflow; split in half (with overlap) until it fits.
        token_count = ner_pipeline.count_tokens(chunk)
        if token_count > 512 and len(chunk) > 50:
            mid = len(chunk) // 2
            run_chunk(chunk[: mid + 50], offset, accept)
            run_chunk(chunk[mid:], offset + mid, accept)
            return
        for ent in ner_pipeline(chunk):
            mapped = label_map.get(ent["entity_group"])
            if not mapped:
                continue
            if ent["score"] < _NER_MIN_SCORE:
                continue
            abs_start = offset + ent["start"]
            abs_end = offset + ent["end"]
            if accept is not None and not accept(abs_start, abs_end):
                continue
            if not any(s.start == abs_start and s.end == abs_end for s in spans):
                spans.append(
                    PiiSpan(abs_start, abs_end, mapped, ent["word"], score=ent["score"])
                )

    chunk_size = 800
    overlap = 200
    stride = chunk_size - overlap

    boundaries: set[int] = set()
    pos = 0
    while pos < len(text):
        run_chunk(text[pos : pos + chunk_size], pos)
        if pos:
            boundaries.add(pos)
        chunk_end = pos + chunk_size
        if chunk_end < len(text):
            boundaries.add(chunk_end)
        pos += stride

    # Second pass, shifted by half a stride, heals entities that pass 1 cut
    # or context-starved at its chunk boundaries. Only entities near a pass-1
    # boundary are accepted: chunk-interior text already had one clean look,
    # so a pass-2-only hit there is far more likely tokenizer noise than PII
    # (observed: lab analyte names getting eaten). NER is a small fraction of
    # per-file time (conversion dominates), so the extra pass is cheap.
    window = 100

    def near_boundary(start: int, end: int) -> bool:
        return any(b - window <= end and start <= b + window for b in boundaries)

    if boundaries:
        pos = stride // 2
        while pos < len(text):
            run_chunk(text[pos : pos + chunk_size], pos, accept=near_boundary)
            pos += stride

    return spans


def _drop_isolated_midword_spans(
    text: str, ner_spans: list[PiiSpan], regex_spans: list[PiiSpan]
) -> list[PiiSpan]:
    """Drop NER spans that cut into a word with no supporting span nearby.

    Mid-word NER spans come in two kinds: fragments of real names (the rest
    of the name is covered by an adjacent NER fragment or a regex span) and
    tokenizer noise that eats clinical words ("Mo|unjaro", "Ro|wachol").
    Only short spans are candidates: the observed noise is always <= 4 chars,
    while longer mid-word fragments ("Rádi Fan|ni") are real names whose
    removal would leak — verified on the private corpus, where dropping
    longer isolated fragments exposed two real names.
    """

    def is_word(c: str) -> bool:
        return c.isalnum()

    kept: list[PiiSpan] = []
    for s in ner_spans:
        if s.end - s.start > 4:
            kept.append(s)
            continue
        mid_start = s.start > 0 and is_word(text[s.start - 1]) and is_word(text[s.start])
        mid_end = s.end < len(text) and is_word(text[s.end - 1]) and is_word(text[s.end])
        if not (mid_start or mid_end):
            kept.append(s)
            continue
        supported = any(
            o is not s and o.start - 2 <= s.end and s.start <= o.end + 2
            for o in (*ner_spans, *regex_spans)
        )
        if supported:
            kept.append(s)
    return kept


_BARE_STAMP_RE = re.compile(r"\b[A-Z]?\d{5,6}\b")


def _find_ids_near_names(text: str, spans: list[PiiSpan]) -> list[PiiSpan]:
    """Bare 5-6 digit stamp IDs adjacent to a detected name.

    Doctor stamp numbers float around the name in every layout variation:
    "(43048) Fekete Éva Dr.", "O79493 Dr. Homonai Eduárd", or on the line
    above/below in signature blocks. Any short ID within a small window of a
    NAME span identifies that (redacted) person, so it goes too.
    """
    window = 60
    name_spans = [s for s in spans if s.label == "NAME"]
    if not name_spans:
        return []
    extra: list[PiiSpan] = []
    for m in _BARE_STAMP_RE.finditer(text):
        near = any(
            s.start - window <= m.end() and m.start() <= s.end + window
            for s in name_spans
        )
        covered = any(s.start <= m.start() and s.end >= m.end() for s in spans)
        if near and not covered:
            extra.append(PiiSpan(m.start(), m.end(), "DOCTOR_ID", m.group()))
    return extra


def _merge_spans(spans: list[PiiSpan]) -> list[PiiSpan]:
    if not spans:
        return []
    spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
    merged = [spans[0]]
    for span in spans[1:]:
        prev = merged[-1]
        if span.start < prev.end:
            if span.end > prev.end:
                merged[-1] = PiiSpan(prev.start, span.end, prev.label, prev.text)
        else:
            merged.append(span)
    return merged


def _redact(text: str, spans: list[PiiSpan]) -> str:
    sorted_spans = sorted(spans, key=lambda s: s.start, reverse=True)
    result = text
    for span in sorted_spans:
        placeholder = PLACEHOLDER_MAP.get(span.label, f"[REDACTED_{span.label}]")
        result = result[:span.start] + placeholder + result[span.end :]
    return result


def _label_count_dict(spans: list[PiiSpan]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in spans:
        counts[s.label] = counts.get(s.label, 0) + 1
    return counts


def _label_counts(spans: list[PiiSpan]) -> str:
    counts = _label_count_dict(spans)
    return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))


# --- PDF conversion ---


def _is_windows() -> bool:
    return sys.platform == "win32"


def redact_filename(filename: str) -> str:
    stem = Path(filename).stem
    # Redact each " - "-delimited segment on its own so a single-word document
    # type suffix ("Lelet", "Vizsgálat") is not swallowed into the name match:
    # _HU_FULL_NAME needs at least two capitalized parts. Distinct documents
    # from the same date then keep distinct output names.
    pieces = re.split(r"(\s+[-–—]\s+)", stem)
    return "".join(
        piece if i % 2 else _redact_filename_segment(piece) for i, piece in enumerate(pieces)
    )


def _redact_filename_segment(name: str) -> str:
    for pattern in (_NAME_FIELD_RE, _NAME_TABLE_RE):
        for m in pattern.finditer(name):
            matched = m.group(1).strip().rstrip(".")
            if matched and len(matched) > 3:
                name = name.replace(matched, "[REDACTED_NAME]")
    name = re.sub(
        rf"(?<![A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű]){_HU_FULL_NAME_ANYCASE}(?![A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű])",
        "[REDACTED_NAME]",
        name,
    )
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name


def convert_pdf(pdf_path: str, converter) -> str:
    source = pdf_path
    if _is_windows():
        # docling-parse passes filesystem paths to native code as UTF-8 bytes.
        # Windows native path APIs do not reliably interpret those bytes, so
        # user directories and filenames containing Hungarian characters can
        # be rejected as invalid documents. A DocumentStream keeps the display
        # name while letting Python open the Unicode path safely.
        from docling.datamodel.base_models import DocumentStream

        path = Path(pdf_path)
        source = DocumentStream(name=path.name, stream=BytesIO(path.read_bytes()))

    result = converter.convert(source)
    return result.document.export_to_markdown()


# --- Docling loading ---


def build_docling_converter():
    from medical_redactor_onnx.register_docling import (
        install_docling_torch_free_shims,
        register_onnx_tableformer,
    )

    install_docling_torch_free_shims()
    register_onnx_tableformer()
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.object_detection_engine_options import (
        OnnxRuntimeObjectDetectionEngineOptions,
    )
    from docling.datamodel.pipeline_options import (
        LayoutObjectDetectionOptions,
        RapidOcrOptions,
        ThreadedPdfPipelineOptions,
    )
    from docling.document_converter import DocumentConverter
    from docling.document_converter import PdfFormatOption

    pipeline_options = ThreadedPdfPipelineOptions()
    pipeline_options.layout_options = LayoutObjectDetectionOptions.from_preset(
        "layout_heron_default",
        engine_options=OnnxRuntimeObjectDetectionEngineOptions(),
        create_orphan_clusters=True,
    )
    pipeline_options.ocr_options = RapidOcrOptions(backend="onnxruntime", lang=["english"])

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


# --- NER model loading ---


def load_ner_model():
    from medical_redactor_onnx.ner_onnx import OnnxNerPipeline
    from medical_redactor_onnx.paths import hubert_ner_dir

    return OnnxNerPipeline(hubert_ner_dir(require=True))


# --- Public API ---


def process_file_detailed(
    pdf_path: str,
    nlp,
    converter,
    log: Callable[[str], None] | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> tuple[str, dict[str, int]]:
    name = Path(pdf_path).name
    if log:
        log(f"Converting {name}...")
    if on_stage:
        on_stage("converting")

    markdown = convert_pdf(pdf_path, converter)

    if log:
        log(f"  {len(markdown)} chars extracted. Detecting PII...")
    if on_stage:
        on_stage("redacting")

    ner_spans = _find_ner_pii(markdown, nlp)
    regex_spans = _find_regex_pii(markdown)
    ner_spans = _drop_isolated_midword_spans(markdown, ner_spans, regex_spans)
    merged = _merge_spans(ner_spans + regex_spans)
    id_spans = _find_ids_near_names(markdown, merged)
    if id_spans:
        merged = _merge_spans(merged + id_spans)

    if log:
        log(f"  NER: {len(ner_spans)} hits, Regex: {len(regex_spans)} hits, merged: {len(merged)}")
        if merged:
            log(f"  PII breakdown: {_label_counts(merged)}")
        else:
            log("  WARNING: No PII detected at all")

    return _redact(markdown, merged), _label_count_dict(merged)


def process_file(
    pdf_path: str,
    nlp,
    converter,
    log: Callable[[str], None] | None = None,
) -> str:
    redacted, _counts = process_file_detailed(pdf_path, nlp, converter, log=log)
    return redacted


def _build_permutations(value: str) -> list[str]:
    parts = re.split(r"[\s\-–—.]+", value.strip())
    parts = [p for p in parts if p]
    if not parts:
        return [value]

    perms: set[str] = set()
    perms.add(value.strip())

    for combo in itertools.permutations(parts):
        perms.add(" ".join(combo))
        perms.add("-".join(combo))
        perms.add(". ".join(combo))
        perms.add("".join(combo))

    for i in range(len(parts)):
        for j in range(i + 1, len(parts) + 1):
            sub = parts[i:j]
            if len(sub) >= 1:
                perms.add(" ".join(sub))
                perms.add("-".join(sub))

    return sorted(perms, key=len, reverse=True)


# Accent-folding for manual redact: OCR frequently strips accents ("FEKETE"
# from "Fekete"), and IGNORECASE alone does not bridge that.
_ACCENT_CLASS: dict[str, str] = {}
for _group in ("aá", "eé", "ií", "oóöő", "uúüű"):
    for _ch in _group:
        _ACCENT_CLASS[_ch] = f"[{_group}]"


def _accent_insensitive_pattern(literal: str) -> str:
    return "".join(_ACCENT_CLASS.get(c.lower(), re.escape(c)) for c in literal)


def manual_redact_folder(output_dir: str, value: str, label: str = "NAME") -> tuple[int, int]:
    output_path = Path(output_dir)
    md_files = sorted(output_path.glob("*.md"))
    placeholder = f"[REDACTED_{label}]"
    perms = _build_permutations(value)
    pattern = re.compile(
        "|".join(_accent_insensitive_pattern(p) for p in perms), re.IGNORECASE
    )

    total_replacements = 0
    files_touched = 0

    for md in md_files:
        text = md.read_text(encoding="utf-8")
        new_text, count = pattern.subn(placeholder, text)
        if count > 0:
            md.write_text(new_text, encoding="utf-8")
            total_replacements += count
            files_touched += 1

    # also redact filenames
    for md in sorted(output_path.glob("*.md")):
        old_name = md.stem
        new_name = pattern.sub(placeholder, old_name)
        if new_name != old_name:
            new_path = md.parent / f"{new_name}.md"
            md.rename(new_path)

    return total_replacements, files_touched


def process_pdfs(
    pdf_paths: list[str],
    output_dir: str | None,
    stop_event: threading.Event | None = None,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
    on_file_event: Callable[[FileEvent], None] | None = None,
):
    # output_dir=None saves each .md next to its source PDF
    output_path = Path(output_dir) if output_dir else None
    if output_path:
        output_path.mkdir(parents=True, exist_ok=True)

    pdfs = [Path(p) for p in pdf_paths]

    if log:
        log(f"Processing {len(pdfs)} PDF(s). Loading Docling converter...")

    converter = build_docling_converter()

    if log:
        log("Loading Hungarian NER model...")

    nlp = load_ner_model()

    if log:
        log("Models ready.\n")

    success = 0
    # Redacted names can collide (two PDFs from the same date). Uniquify
    # within this run only; overwriting a previous run's output for the same
    # PDF stays intentional so reprocessing is idempotent.
    used_names: set[Path] = set()
    for i, pdf in enumerate(pdfs):
        if stop_event and stop_event.is_set():
            if log:
                log(f"\nStopped by user after {success} files.")
            return

        try:
            on_stage = None
            if on_file_event:
                on_stage = lambda stage, p=str(pdf): on_file_event(FileEvent(path=p, stage=stage))
            redacted, counts = process_file_detailed(
                str(pdf), nlp, converter, log=log, on_stage=on_stage
            )
            out_dir = output_path if output_path else pdf.parent
            base = redact_filename(pdf.name)
            out_file = out_dir / f"{base}.md"
            counter = 2
            while out_file in used_names:
                out_file = out_dir / f"{base} ({counter}).md"
                counter += 1
            used_names.add(out_file)
            out_file.write_text(redacted, encoding="utf-8")
            success += 1
            if log:
                log(f"  Saved: {out_file.name}\n")
            if on_file_event:
                on_file_event(FileEvent(
                    path=str(pdf), stage="done", counts=counts, output_name=out_file.name
                ))
        except Exception as e:
            if log:
                log(f"  ERROR processing {pdf.name}: {e}\n")
            if on_file_event:
                on_file_event(FileEvent(path=str(pdf), stage="failed", error=str(e)))

        if progress:
            progress(i + 1, len(pdfs))

    if log:
        log(f"Done. {success}/{len(pdfs)} files processed successfully.")
        log(f"Output: {output_path if output_path else 'next to the original PDFs'}")


def process_folder(
    input_dir: str,
    output_dir: str | None,
    stop_event: threading.Event | None = None,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
    on_file_event: Callable[[FileEvent], None] | None = None,
):
    input_path = Path(input_dir)

    pdfs = sorted(
        [p for p in input_path.iterdir() if p.suffix.lower() == ".pdf"],
        key=lambda p: p.name,
    )

    if not pdfs:
        if log:
            log("No PDF files found in the selected folder.")
        return

    process_pdfs(
        [str(p) for p in pdfs],
        output_dir,
        stop_event=stop_event,
        log=log,
        progress=progress,
        on_file_event=on_file_event,
    )
