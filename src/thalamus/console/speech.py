"""Spoken-register transform: assistant prose in, text meant for the ear out.

This is not a screen reader. Verbatim fidelity is deliberately traded for
listenability — prose written for the eye is rewritten, and material that only
makes sense on a screen (fenced code, diffs, full paths) is dropped rather than
transliterated. Reading `src/thalamus/console/server.py` aloud as "source slash
thalamus slash console slash server dot pie" is accurate and unlistenable; the
ear wants "the console server".

What is *not* traded away is a protected set: numbers, counts, versions, commit
hashes, identifiers and acronyms. Those carry the meaning a listener would act
on, and audio has no rewind — a corrupted number produces perfectly plausible
speech with no cue that anything broke, which makes it the one error class a
listener cannot detect or recover from. So protection is a contract, not a
best effort: tokens are extracted from the *raw* turn before any rewriting, and
the finished utterance is checked against them. An utterance that dropped one
is rejected rather than spoken.

Extract-then-verify follows Herman (Zhao, Cohen & Webber, "Reducing Quantity
Hallucinations in Abstractive Summarization", Findings of EMNLP 2020), which
verifies quantity entities against the source and re-ranks on the result. The
acceptable-vs-unrecoverable split the protected set encodes is Sproat & Jaitly's
("RNN Approaches to Text Normalization: A Challenge", arXiv:1611.00068), whose
finding — that a neural normalizer scoring well overall still "occasionally
predicts wildly inappropriate" output, and that a finite-state filter is what
reins it in — is why the protected classes below are matched by explicit
patterns rather than left to the engine's own front end.

The verbalizations here target espeak-ng (piper's front end), which splits
snake_case and camelCase correctly on its own. They are still applied
explicitly, because the engine downstream is not guaranteed to be piper and at
least one alternative silently deletes tokens its G2P cannot parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Semiotic classes in the sense of Sproat's taxonomy, extended with the two the
# taxonomy has no room for — identifiers and paths — because it was built for
# ordinary written text and this input is a coding agent's turn output.
KIND_NUMBER = "number"
KIND_VERSION = "version"
KIND_HASH = "hash"
KIND_IDENTIFIER = "identifier"
KIND_ACRONYM = "acronym"

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

_ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth", 21: "twenty-first", 22: "twenty-second",
    23: "twenty-third", 24: "twenty-fourth", 25: "twenty-fifth",
    26: "twenty-sixth", 27: "twenty-seventh", 28: "twenty-eighth",
    29: "twenty-ninth", 30: "thirtieth", 31: "thirty-first",
}

_DIGIT_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

# A fenced block is screen material: it is dropped whole rather than spoken.
_FENCE_RE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_INDENTED_BLOCK_RE = re.compile(r"(?:^[ \t]*\n)(?:^(?: {4}|\t).*\n?)+", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# A version is a `v` prefix or three-plus dotted numeric parts; two dotted parts
# without the prefix is left alone, since "1.55 seconds" is a decimal, not a
# version, and speaking it as "one point five five" is what a listener expects.
_VERSION_RE = re.compile(r"\bv(\d+(?:\.\d+)+)\b|\b(\d+\.\d+\.\d+(?:\.\d+)*)\b")
# Git short hashes. Requires a digit so ordinary hex-looking words ("decade",
# "deadbeef" is admittedly a real hash, "faced") are not spelled out.
_HASH_RE = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}s?\b")
_PATH_RE = re.compile(r"(?<![\w/.])(?:~|\.{1,2})?/[\w.\-/]*\w|\b[\w\-]+(?:/[\w.\-]*[\w\-])+")
_DOTTED_FILE_RE = re.compile(r"\b[\w\-]+\.(?:py|js|md|json|yaml|yml|toml|txt|sh|html|css|mjs|jsonl|wav|mp3|onnx|service)\b")
_SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_CONST_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_CAMEL_RE = re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]*)+\b")
_DOTTED_CALL_RE = re.compile(r"\b[a-z_][\w]*(?:\.[a-z_][\w]*)+\b")

# Markdown that carries nothing audible.
_HEADING_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*{1,3})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
# Underscore emphasis only where an identifier cannot be. An underscore run
# flanked by word characters is `snake_case`, and unwrapping it welds the parts
# together into a name no listener can map back to the code — plausible speech
# carrying the wrong identifier, which is the class this module exists to stop.
_US_EMPHASIS_RE = re.compile(r"(?<!\w)(_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)", re.DOTALL)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^\s*>\s?", re.MULTILINE)
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)

# Tool narration reads as chatter in an update. These openings are cut when they
# begin a sentence, leaving the substance that follows.
# Only first-person openings and interjections — never bare ordering words like
# "first" or "next", which begin ordinary content ("first thing" must survive).
_NARRATION_RE = re.compile(
    r"^(?:ok(?:ay)?|alright|sure|great)\b[ ,]*"
    r"|^(?:let me|let's|i'll|i will|i'm going to|i am going to|i've|i have)\b[ ,]*"
    r"(?:now|then|next|just)?[ ,]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProtectedToken:
    """A token the utterance may not lose, and how it may legitimately sound.

    `spoken_forms` is every realization that counts as having survived, so the
    verifier accepts "seventeen" or "17" for a count but nothing else.
    """

    kind: str
    literal: str
    spoken_forms: tuple[str, ...]

    def satisfied_by(self, spoken: str) -> bool:
        haystack = _fold(spoken)
        return any(_fold(form) in haystack for form in self.spoken_forms)


@dataclass
class SpokenUpdate:
    """The result of the transform, carrying its own audit."""

    text: str
    protected: tuple[ProtectedToken, ...] = ()
    missing: tuple[ProtectedToken, ...] = field(default=())

    @property
    def faithful(self) -> bool:
        return not self.missing


def _fold(value: str) -> str:
    """Compare on words alone — punctuation and case are the engine's business."""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _spell(value: str) -> str:
    """Character-by-character, digits as words. For hashes and short acronyms."""
    out = []
    for char in value:
        if char in _DIGIT_WORDS:
            out.append(_DIGIT_WORDS[char])
        elif char.isalpha():
            out.append(char.upper())
    return " ".join(out)


def _split_identifier(name: str) -> str:
    """snake_case, camelCase and CONSTANT_CASE into spaced words.

    An all-caps run is spelled rather than pronounced, so POLL_MS becomes
    "poll M S" and not a word no listener would map back to the constant.
    """
    parts: list[str] = []
    for chunk in name.split("_"):
        if not chunk:
            continue
        for piece in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", chunk):
            if piece.isupper() and len(piece) <= 3 and not piece.isdigit():
                parts.append(_spell(piece))
            else:
                parts.append(piece.lower())
    return " ".join(parts)


def _speak_path(path: str) -> str:
    """A path becomes the shortest phrase that still identifies the file.

    Full paths are dropped, not transliterated: the listener wants to know
    *which file*, and "the console server" answers that where "source slash
    thalamus slash console slash server dot pie" only spells it.
    """
    cleaned = path.strip().strip(".,;:!?)（）\"'")
    cleaned = re.sub(r"^[~.]*/", "", cleaned)
    segments = [seg for seg in cleaned.split("/") if seg]
    if not segments:
        return ""
    tail = segments[-1]
    stem = tail.rsplit(".", 1)[0] if "." in tail else tail
    # The parent directory disambiguates same-named files (many `server.py`);
    # anything above it is noise to a listener who knows the project.
    keep = segments[-2:-1] + [stem] if len(segments) > 1 else [stem]
    return " ".join(_split_identifier(part) for part in keep if part).strip()


def _speak_version(raw: str) -> str:
    body = raw[1:] if raw[:1].lower() == "v" else raw
    spoken = " point ".join(
        " ".join(_DIGIT_WORDS.get(ch, ch) for ch in part) for part in body.split(".")
    )
    return f"v {spoken}" if raw[:1].lower() == "v" else spoken


def _speak_date(year: str, month: str, day: str) -> str:
    try:
        month_name = _MONTHS[int(month) - 1]
        day_word = _ORDINALS[int(day)]
    except (ValueError, IndexError, KeyError):
        return f"{year}-{month}-{day}"
    return f"{month_name} {day_word}"


def protected_tokens(raw: str) -> tuple[ProtectedToken, ...]:
    """Extract what the utterance may not lose, from the RAW turn.

    Order matters: this runs *before* any rewriting. Running it on the finished
    summary would only confirm the summary is consistent with itself, which is
    not the property wanted — a token deleted during compression would never
    appear in either side of that comparison.
    """
    found: dict[tuple[str, str], ProtectedToken] = {}

    def add(kind: str, literal: str, forms: tuple[str, ...]) -> None:
        found.setdefault((kind, literal), ProtectedToken(kind, literal, forms))

    text = _FENCE_RE.sub(" ", raw)

    for match in _ISO_DATE_RE.finditer(text):
        year, month, day = match.groups()
        add(KIND_NUMBER, match.group(0), (_speak_date(year, month, day), match.group(0)))

    masked = _ISO_DATE_RE.sub(" ", text)

    for match in _VERSION_RE.finditer(masked):
        literal = match.group(0)
        add(KIND_VERSION, literal, (_speak_version(literal), literal))

    versionless = _VERSION_RE.sub(" ", masked)

    for match in _HASH_RE.finditer(versionless):
        literal = match.group(0)
        add(KIND_HASH, literal, (_spell(literal), literal))

    hashless = _HASH_RE.sub(" ", versionless)

    for match in _NUMBER_RE.finditer(hashless):
        literal = match.group(0)
        add(KIND_NUMBER, literal, (literal,))

    for pattern in (_CONST_RE, _SNAKE_RE, _CAMEL_RE):
        for match in pattern.finditer(text):
            literal = match.group(0)
            add(KIND_IDENTIFIER, literal, (_split_identifier(literal), literal))

    for match in _ACRONYM_RE.finditer(text):
        literal = match.group(0).rstrip("s")
        if len(literal) < 2:
            continue
        add(KIND_ACRONYM, literal, (_spell(literal), literal))

    return tuple(found.values())


def to_speakable(raw: str) -> str:
    """Rewrite one turn's prose into something meant to be heard.

    Screen-only material is dropped whole; the classes a listener needs are
    verbalized explicitly rather than left to the engine's front end.
    """
    text = _FENCE_RE.sub(" ", raw)
    text = _INDENTED_BLOCK_RE.sub(" ", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _RULE_RE.sub(" ", text)
    text = _HEADING_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _EMPHASIS_RE.sub(r"\2", text)
    text = _US_EMPHASIS_RE.sub(r"\2", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)

    text = _ISO_DATE_RE.sub(lambda m: _speak_date(*m.groups()), text)
    text = _VERSION_RE.sub(lambda m: _speak_version(m.group(0)), text)
    text = _HASH_RE.sub(lambda m: _spell(m.group(0)), text)

    text = _PATH_RE.sub(lambda m: _speak_path(m.group(0)), text)
    text = _DOTTED_FILE_RE.sub(lambda m: _speak_path(m.group(0)), text)
    text = _DOTTED_CALL_RE.sub(lambda m: _split_identifier(m.group(0).replace(".", "_")), text)

    for pattern in (_CONST_RE, _SNAKE_RE, _CAMEL_RE):
        text = pattern.sub(lambda m: _split_identifier(m.group(0)), text)

    text = _ACRONYM_RE.sub(
        lambda m: _spell(m.group(0).rstrip("s")) + ("s" if m.group(0).endswith("s") else ""),
        text,
    )

    lines = []
    for line in text.splitlines():
        stripped = _NARRATION_RE.sub("", line.strip())
        if stripped:
            lines.append(stripped[0].upper() + stripped[1:] if stripped else stripped)
    text = " ".join(lines)

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def verify_protected(
    spoken: str, tokens: tuple[ProtectedToken, ...]
) -> tuple[ProtectedToken, ...]:
    """Every protected token, or the utterance does not go out."""
    return tuple(token for token in tokens if not token.satisfied_by(spoken))


def spoken_update(raw: str) -> SpokenUpdate:
    """The whole transform, carrying the audit that says whether to speak it."""
    tokens = protected_tokens(raw)
    text = to_speakable(raw)
    return SpokenUpdate(text=text, protected=tokens, missing=verify_protected(text, tokens))
