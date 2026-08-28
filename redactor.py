from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from enum import Enum

try:
    import spacy
except ImportError:
    spacy = None


class PIILabel(str, Enum):
    EMAIL = "EMAIL"
    PHONE_NUMBER = "PHONE_NUMBER"
    PERSON_NAME = "PERSON_NAME"
    STREET_ADDRESS = "STREET_ADDRESS"
    SSN = "SSN"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"


#data class for returning spans of detected PII in the text, frozen to make it immutable once created
@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: PIILabel

    def as_triple(self) -> tuple[int, int, str]:
        return (self.start, self.end, self.label.value)

#EMAIL

# Methodology:
#   1. Regex match on local@domain.tld

# Known Holes:
#   1. Misses obfuscated or nonstandard formats (e.g. "user at domain dot com"), not present in the given data but could exist in future datasets

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

def detect_email(text: str) -> list[Span]:
    return [Span(m.start(), m.end(), PIILabel.EMAIL) for m in _EMAIL_RE.finditer(text)]

#PHONE NUMBER

# Methodology:
#   1. Regex looks for patterns of 3 digit, 3 digit, 4 digit groups, requiring separators between groups (parens/dash/dot), optional country code

# Known Holes:
#   1. won't catch numbers with no separators, as these could be IDs or other numeric data. No such cases present in the given data but could exist in future datasets.

# Future Work:
#   1. Considered phonenumbers (libphonenumber) for broader and more accurate coverage (catch unseparated numbers), but it will reject correctly formatted numbers that are not actually assigned to a carrier. This will work in production but might cause some failures during testing for this very specific excerise. 

_PHONE_SHAPE_RE = re.compile(
    r"(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}"
)

def detect_phone_number(text: str) -> list[Span]:
    return [Span(m.start(), m.end(), PIILabel.PHONE_NUMBER) for m in _PHONE_SHAPE_RE.finditer(text)]


_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is None:
        if spacy is None:
            raise RuntimeError(
                "spaCy is required for PERSON_NAME detection. Install it with "
                "`pip install spacy` and `python -m spacy download en_core_web_md`."
            )
        _NLP = spacy.load("en_core_web_md")
    return _NLP


_TITLE_PREFIX_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Mx|Dr)\.?\s+$")
_NAME_SUFFIX_RE = re.compile(r"^,?\s*(?:Jr|Sr|II|III|IV|V)\.?\b")

#NAME

# Methodology:
#   1. spaCy en_core_web_md NER, PERSON entities (uses en_core_web_md, as it was tested to be most accurate for this task)
#   2. Widen match to include adjacent title (Dr., Mrs.) or suffix (III, Jr.)

# Known Holes:
#   1. Bare unlabeled single-token names inconsistently detected (very small false negative rate, but still present in simulated dataset)
#   2. Terse "Label: Value" record formatting still degrades type classification
#      in places 
#   3. Failures aren't rule-governed meaning the same word can pass/fail in near-identical contexts

# Future Work:
#   1. Confidence-based routing + human review queue
#   2. Fine-tune on labeled examples matching real document shapes
#   3. Classify document type upstream, change strategy per shape
#   4. Locally hosted, fine tuned LLM (in my testing, a small model (800 mb) was less accurate than spaCy, where a larger model (7.5 gb) was the same level of accuracy but much slower (1 minute per row))

def detect_person_name(text: str) -> list[Span]:

    nlp = _get_nlp()
    doc = nlp(text)
    spans: list[Span] = []

    for ent in doc.ents:

        #only saves if the entity is a PERSON, otherwise continues to next entity
        if ent.label_ != "PERSON":
            continue
        start, end = ent.start_char, ent.end_char

        #checks for prefix and suffix of the name, and expands the span to include them if they exist
        prefix_window = text[max(0, start - 20):start]
        title_match = _TITLE_PREFIX_RE.search(prefix_window)
        if title_match:
            start -= len(title_match.group())

        suffix_window = text[end:end + 10]
        suffix_match = _NAME_SUFFIX_RE.match(suffix_window)
        if suffix_match:
            end += len(suffix_match.group())

        spans.append(Span(start, end, PIILabel.PERSON_NAME))
    return spans

#ADDRESS

# Methodology:
#   1. Required core: number + up to 3 capitalized filler words + known street-suffix
#   2. Optional tail: unit/suite, city, state+zip (each independently optional)

# Known Holes:
#   1. Won't catch an address wrapped across two lines (as in testing, if I allowed it to look past a linebreak, it would consume additional non-address text and produce false positives)
#   2. Won't catch a street name with internal punctuation (e.g. "St. Mary's Lane") (same as 1, allowing punctuation would produce false positives as it would match past the end of an address in testing data)
#   3. Street suffix vocabulary is a fixed, finite list (e.g. "Lane", "Road", "Drive") and won't catch a nonstandard suffix (e.g. "Crescent") (same as 1, allowing arbitrary words would produce false positives as it would match past the end of an address in testing data)

# Future Work:
#   1. An locally hosted LLM would work here, but would require a large model (7.5 gb) to be accurate enough to avoid false positives, and would be slow (1 minute per row in my testing)
#   1. b. This could be alleviated with more powerful hardware (GPU accelleration) or a smaller model fine-tuned on labeled examples, but is outside the scope of this excersise.

_STREET_SUFFIXES = (
    r"Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Road|Rd|"
    r"Way|Court|Ct|Place|Pl|Circle|Cir|Terrace|Ter|Parkway|Pkwy|"
    r"Highway|Hwy|Trail|Trl|Square|Sq|Loop|Alley|Path"
)

_ADDRESS_CORE_RE = re.compile(
    rf"\d+[ \t]+(?:[A-Z][A-Za-z]*[ \t]+){{0,3}}(?:{_STREET_SUFFIXES})\.?\b"
)

_ADDRESS_TAIL_RE = re.compile(
    r"(?:,\s*(?:Apt|Suite|Ste|Unit|#)\.?\s*[A-Za-z0-9]+)?"
    r"(?:,\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)?"
    r"(?:,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?"
)

def detect_street_address(text: str) -> list[Span]:
    spans: list[Span] = []

    for m in _ADDRESS_CORE_RE.finditer(text):
        end = m.end()
        tail_match = _ADDRESS_TAIL_RE.match(text, end)
        if tail_match:
            end = tail_match.end()
        spans.append(Span(m.start(), end, PIILabel.STREET_ADDRESS))
    return spans

#SSN

# Methodology:
#   1. first pass looking for a dashed format (AAA-GG-SSSS) anywhere in the text
#   2. Validate against SSA-invalid ranges (area 000/666/900+, group 00, serial 0000)
#   3. Keyword-anchored pass for bare 9-digit runs near "SSN"/"Social Security Number"

# Known Holes:
#   1. Can't verify real issuance beyond structural validity
#   2. Bare-digit SSNs only caught when a keyword label is nearby

# Future Work:
#   - Broaden keyword list for more label phrasings

_SSN_RE = re.compile(r"(\d{3})-(\d{2})-(\d{4})")

#validates the area, group, and serial numbers of a social security number (SSN) to ensure they are not in invalid ranges
def _is_valid_ssn(area: str, group: str, serial: str) -> bool:
    return (
        area != "000"
        and area != "666"
        and int(area) < 900
        and group != "00"
        and serial != "0000"
    )


#searches for dashed-format social security numbers (SSNs) in the text and returns a list of spans for valid SSNs
def _detect_ssn_dashed(text: str) -> list[Span]:
    spans: list[Span] = []
    for m in _SSN_RE.finditer(text):
        area, group, serial = m.group(1), m.group(2), m.group(3)
        if _is_valid_ssn(area, group, serial):
            spans.append(Span(m.start(), m.end(), PIILabel.SSN))
    return spans


_SSN_KEYWORD_RE = re.compile(
    r"\b(?:ssn|social security(?:\s+number)?)\b\s*(?:on\s+file)?\s*[:\-]?\s*",
    re.IGNORECASE,
)
_SSN_BARE_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")
_SSN_WINDOW_CHARS = 15

#searches for bare 9-digit social security numbers (SSNs) in the text that are near keywords like "SSN" or "Social Security Number" and returns a list of spans for valid SSNs
def _detect_ssn_bare(text: str) -> list[Span]:
    spans: list[Span] = []
    for kw_match in _SSN_KEYWORD_RE.finditer(text):
        window_start = kw_match.end()
        window_end = window_start + _SSN_WINDOW_CHARS
        m = _SSN_BARE_RE.search(text, window_start, window_end)
        if m:
            digits = m.group()
            if _is_valid_ssn(digits[:3], digits[3:5], digits[5:]):
                spans.append(Span(m.start(), m.end(), PIILabel.SSN))
    return spans

def detect_ssn(text: str) -> list[Span]:
    return _detect_ssn_dashed(text) + _detect_ssn_bare(text)


_DOB_KEYWORD_RE = re.compile(
    r"\b(?:date of birth|birth\s*date|d\.?o\.?b\.?|born)\b\s*[:\-]?\s*",
    re.IGNORECASE,
)

_MONTH_NAMES = (
    "January|February|March|April|May|June|July|"
    "August|September|October|November|December"
)

_DATE_RE = re.compile(
    rf"\d{{1,2}}/\d{{1,2}}/\d{{2,4}}|(?:{_MONTH_NAMES})\s+\d{{1,2}},?\s+\d{{4}}",
    re.IGNORECASE,
)

_DOB_WINDOW_CHARS = 30

#DOB 

# Methodology:
#   1. Regex for birth-related keywords (DOB, Date of Birth, Birth Date, Born)
#   2. Search a short window after the keyword for a date (numeric or month-name)

# Known Holes:
#   1. Misses DOBs with no recognized label nearby (these are indistinguishable from other dates in the text, and are not present in the given data but could exist in future datasets)

# Future Work:
#   1. Broaden keyword list
#   2. Could grab all possible dates in the text, then pass their local context to a small LLM to determine if it's actually a birthdate. Again, this would be slow, but might catch some potential false negatives. None are present in the given dataset, but could easily appear in future datasets.

def detect_date_of_birth(text: str) -> list[Span]:
    spans: list[Span] = []
    for kw_match in _DOB_KEYWORD_RE.finditer(text):
        window_start = kw_match.end()
        window_end = window_start + _DOB_WINDOW_CHARS
        date_match = _DATE_RE.search(text, window_start, window_end)
        if date_match:
            spans.append(Span(date_match.start(), date_match.end(), PIILabel.DATE_OF_BIRTH))
    return spans


_DETECTORS = [
    detect_email,
    detect_phone_number,
    detect_person_name,
    detect_street_address,
    detect_ssn,
    detect_date_of_birth,
]

#trims whitespace from the start and end of a span, returning the new start and end indices. Useful in some cases where the space is pulled in accidentally
def _trim_whitespace(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


# no span should cross a line break, only really relevant to the name function, but applied to all for consistency. This is because spaCy NER will sometimes pull in a line break and the next line's text into a PERSON_NAME span, which is not desired behavior. This function clips the end of a span at the first newline character, if any.
def _clip_at_newline(text: str, start: int, end: int) -> int:
    newline_pos = text.find("\n", start, end)
    return newline_pos if newline_pos != -1 else end


# there was a small errorcase in simulated data, where names were being detected inside street addresses. For example "123 Main St, Austin, Tx" would detect Austin as a name. This eliminates those false positives.
def _drop_names_inside_addresses(spans: list[Span]) -> list[Span]:
    address_ranges = [(s.start, s.end) for s in spans if s.label == PIILabel.STREET_ADDRESS]
    return [
        s for s in spans
        if s.label != PIILabel.PERSON_NAME
        or not any(s.start < a_end and a_start < s.end for a_start, a_end in address_ranges)
    ]

#function that detects all PII in the text and returns a list of spans for each detected PII. It uses the individual detection functions for each type of PII and applies some post-processing to clean up the spans.
def detect(text: str) -> list[Span]:
    spans: list[Span] = []
    for detector in _DETECTORS:
        for span in detector(text):
            end = _clip_at_newline(text, span.start, span.end)
            start, end = _trim_whitespace(text, span.start, end)
            if start < end:
                spans.append(Span(start, end, span.label))
    return _drop_names_inside_addresses(spans)

#function that redacts all detected PII in the text by replacing it with a placeholder indicating the type of PII. It returns the redacted text and a list of spans for each detected PII.
def redact(text: str) -> tuple[str, list[Span]]:
    spans = sorted(detect(text), key=lambda s: (s.start, s.end))
    pieces: list[str] = []
    kept_spans: list[Span] = []
    last_end = 0
    for span in spans:
        if span.start < last_end:
            continue
        pieces.append(text[last_end:span.start])
        pieces.append(f"[{span.label.value}]")
        last_end = span.end
        kept_spans.append(span)
    pieces.append(text[last_end:])
    return "".join(pieces), kept_spans


def main() -> None:
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    redacted_text, spans = redact(text)
    print(json.dumps({
        "redacted_text": redacted_text,
        "spans": [list(span.as_triple()) for span in spans],
    }, indent=2))


if __name__ == "__main__":
    main()
