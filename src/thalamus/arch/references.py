"""Every name a comment points at, and whether the tree still holds it.

A comment that cites a sibling module or `reader.py:106` makes a claim with a
**resolvable referent**: the tree either holds that name or it does not, and no
judgement sits between the question and the answer. That is the whole of what this
reads. Claims whose referent is a measured number, a vendor's release, or a corpus
snapshot that no longer exists are outside it — the first needs a re-run, the second
has no oracle in this repo at any precision, and the third is correctly uncheckable.

**No annotation, deliberately.** The obvious design is a marker an author writes on
the references worth checking, and it makes coverage strictly worse: the sixteen
dangling references this was built after were found precisely because nobody had
marked anything. A recognizer over all comment text has coverage by construction; an
opt-in has coverage by memory. So there is nothing to write and nothing to migrate,
and the only thing an author can do wrong is spell a name that never existed.

**Report-only, and the gate is absent rather than defaulted off.** This channel makes
no `--gate` flag and fails no build. Precision is unmeasured, and a checker that acts
on an unmeasured precision has no denominator to be judged by later — an absorbed
false positive leaves no trace, so the number that decides whether to arm it stops
being computable the moment it arms. The shadow run comes first; the flag comes after
it, or not at all.

**Three outcomes, not two, because a non-resolving name is not always wrong.** This
repo argues about what it does not contain — "`Solution.worked` is written and never
read", "no analyzer computing the closure exists", "codex ships no analogous tool" —
and those sentences carry a name that *correctly* fails to resolve. Flagging them
would be bad enough; the repair is worse, because the obedient way to satisfy the
checker is to delete a true statement. So a non-resolving reference on a sentence
that asserts absence is reported in its own bucket and is never a finding. It is a
suppression the reader can audit, not one the recogniser hides.

**The gap report is complement-shaped.** A recognizer that lists what it understood
reads as complete over files it never opened — the defect `oracle_parses_whole.py`
exists for, where a gate declared eleven entries, parsed ten, and refused nothing. So
this reports the files it could not read, and every token that looked like a
reference and that no form consumed. A migration cannot claim coverage it does not
have, because the uncovered set is printed beside the covered one.

**Its own block and its own digest.** Like `DeadEndPolicy`, this contributes no edge
to the visibility matrix and stays out of `model.scan_id`, so adding the channel does
not move the import measurement's key and does not invalidate a committed model.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import io
import json
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from thalamus.arch.findings import DESIGN, UNDERSTANDING, Finding

# Surfaces read, and how prose is lifted out of each. A `.py` file's prose is its
# comment tokens and its docstrings — never a runtime string, because an argparse help
# string and a refusal message are read by a user rather than by a maintainer, and
# citing a path in one is a different act from citing it in a comment.
PY_SUFFIXES = (".py",)
LINE_COMMENT_SUFFIXES = {".sh": ("#",), ".js": ("//", "*", "/*"), ".mjs": ("//", "*", "/*")}
PROSE_SUFFIXES = (".md",)

# A reference this repo writes as `pkg/file.ext`, resolved relative to the package as
# well as to the repo, because a comment in `harness/` names a module the way an
# import would — `eval/rankers.py`, not `src/thalamus/eval/rankers.py`.
_PATH = re.compile(
    r"(?<![\w/.-])"
    r"((?:[a-z_][a-z0-9_.-]*/)+[a-z0-9_.-]+\.(?:py|sh|js|mjs|md|ya?ml|json|properties))"
    r"(?![\w/])"
)
# The same, carrying a line or a line range: `reader.py:106`, `cli.py:1767-1772`.
_PATH_LINE = re.compile(
    r"(?<![\w/.-])"
    r"([a-z_][a-z0-9_./-]*\.(?:py|sh|js|mjs|md))"
    r":(\d+)(?:\s*[-–]\s*(\d+))?"
    r"(?![\w])"
)
# A backticked bare filename — `routes.py`, `SKILL.md`. Resolved as a path, because
# that is what it is; the dotted-name regex would otherwise read `routes.py` as a
# symbol whose final segment is `py` and report every one of them missing.
#
# **Source extensions only, and the exclusion is the interesting half.** A bare
# `.json`/`.yaml`/`.jsonl` name is as often someone else's file as ours — `hooks.json`
# and `auth.json` are Cursor's, `pins.jsonl` and `settings.local.json` are written at
# runtime under `$HOME`, and none of them is a defect for being absent from the tree.
# The first cut judged them and produced nine findings that were all true statements
# about a file this repo does not contain and never claimed to. A source file named
# without a directory is ours; a data file named without one is anybody's.
_BARE_FILE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.-]*\.(?:py|sh|js|mjs|md))`")

# **Dotted names are recognised and deliberately not resolved.** The first cut of this
# channel resolved a backticked `a.b` against an index of every name defined under the
# roots, and on this tree that produced findings against `RETURNS.judged_terms`,
# `room.peer_roster` and `Trace.ranker_config` — graph properties and ontology terms
# whose referent is real and is simply not a Python definition. A form that cannot tell
# a missing symbol from a non-Python referent has no business emitting a finding, and
# the argument for this whole channel is that its class of claim is *exact*. So these
# are counted, listed under `--limits`, and judged by nothing.
_DOTTED = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`")

# Anything shaped enough like a reference to be worth accounting for. The complement
# report is the difference between what this matches and what the three forms above
# consume, so it is deliberately looser than all of them.
_CANDIDATE = re.compile(r"`[^`\n]{1,80}`|(?<![\w/])[\w.-]+/[\w./-]+\.\w{1,12}")

# Sentences that assert a referent's absence. Matched against the clause the reference
# sits in rather than the whole line, because "X is gone but `Y` is not" is two claims.
_ABSENCE = re.compile(
    r"\b(?:no|not|never|nothing|none|neither|nobody|cannot|can't|won't|"
    r"absent|missing|removed|deleted|gone|unbuilt|unwired|does not|do not|did not|"
    r"no longer|would be|would have|instead of|rather than|hypothetical)\b",
    re.IGNORECASE,
)

# Illustrative names this repo writes to explain a mechanism rather than to point at
# something. `src/foo.py` in a comment about path matching is an example, not a
# citation, and a checker that cannot tell them apart reports the prose as broken.
# Matched on any segment, not just the stem: `pkg/__init__.py` is a worked example in
# `extractor.py` and its stem is the perfectly real `__init__`.
# Quoted spans, removed before the absence reading. A negation inside a quotation is
# not the sentence's own. A comment that cites a module and then quotes a rule
# containing the word never is not asserting the module is absent, and reading it
# that way made a live dangling citation vanish into the audit bucket. A false
# suppression is worse than a false finding here: the finding gets argued with, the
# suppression is never seen.
_QUOTED = re.compile(r"\"[^\"\n]{0,200}\"|'[^'\n]{0,200}'")

_PLACEHOLDER_SEGMENTS = frozenset(
    {"foo", "bar", "baz", "qux", "x", "y", "example", "sample", "pkg", "mypkg", "somefile"}
)

# A path sitting inside a URL is a citation of somebody else's document.
# `cursor.com/docs/hooks.md` is a vendor doc this repo re-verified against, and
# reporting it as a missing file would be a checker mistaking the web for the tree.
_URLISH = re.compile(r"(?:https?://|\b[a-z0-9-]+\.(?:com|org|io|dev|net|ai)/)")

_EXCLUDE = ("*/node_modules/*", "*/gremlin-docs/*", "*/__pycache__/*", "*/.venv/*")


@dataclass(frozen=True)
class ReferenceExemption:
    """A reference the model accepts, and why. The reason is required, as everywhere."""

    reason: str
    path: str = ""
    target: str = ""

    def matches(self, reference: "Reference") -> bool:
        if self.path and not fnmatch.fnmatch(reference.file, self.path):
            return False
        if self.target and not fnmatch.fnmatch(reference.target, self.target):
            return False
        return bool(self.path or self.target)

    def block(self) -> dict[str, str]:
        return {"reason": self.reason, "path": self.path, "target": self.target}


@dataclass(frozen=True)
class ReferencePolicy:
    """The declared rules this census was taken under.

    `enabled` is off by default for the same reason `DeadEndPolicy`'s is: a channel
    that turns itself on changes every existing model file's report on the commit it
    lands, and the reader cannot tell the new channel from a new defect.
    """

    version: int = 1
    enabled: bool = False
    roots: tuple[str, ...] = ("src",)
    exclude: tuple[str, ...] = _EXCLUDE
    # Resolution roots tried in order for a package-relative path. `src/thalamus` is
    # here because that is what a bare `eval/rankers.py` means inside this package.
    search_roots: tuple[str, ...] = (".", "src", "src/thalamus")
    exemptions: tuple[ReferenceExemption, ...] = ()

    def block(self) -> dict[str, object]:
        return {
            "version": self.version,
            "enabled": self.enabled,
            "roots": list(self.roots),
            "exclude": list(self.exclude),
            "search_roots": list(self.search_roots),
            "exemptions": [item.block() for item in self.exemptions],
        }

    def digest(self) -> str:
        canonical = json.dumps(self.block(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_block(cls, block: dict) -> "ReferencePolicy":
        """Rebuild from a model file's `references:` mapping.

        An exemption without a reason raises rather than loading blank: the file is
        where the reason is authored, so defaulting it would unenforce the requirement
        exactly where it binds.
        """
        defaults = cls()
        exemptions = []
        for entry in block.get("exemptions") or ():
            reason = str(entry.get("reason", "")).strip()
            if not reason:
                raise ValueError(
                    "a references: exemption needs a reason — "
                    f"{entry.get('path') or entry.get('target')!r} has none"
                )
            exemptions.append(
                ReferenceExemption(
                    reason=reason,
                    path=str(entry.get("path", "")),
                    target=str(entry.get("target", "")),
                )
            )
        return cls(
            version=int(block.get("version", defaults.version)),
            enabled=bool(block.get("enabled", defaults.enabled)),
            roots=tuple(block.get("roots", defaults.roots)),
            exclude=tuple(block.get("exclude", defaults.exclude)),
            search_roots=tuple(block.get("search_roots", defaults.search_roots)),
            exemptions=tuple(exemptions),
        )


# What a reference turned out to be. `ASSERTED_ABSENT` is not a weaker `DANGLING`:
# it is the opposite reading of the same observation, and the two must never share a
# bucket, because the repair for one is the inverse of the repair for the other.
RESOLVED = "resolved"
DANGLING = "dangling"
ASSERTED_ABSENT = "asserted-absent"
EXEMPTED = "exempted"


@dataclass(frozen=True)
class Reference:
    """One citation lifted out of one line of prose."""

    file: str
    lineno: int
    target: str
    kind: str  # "path" | "path-line" | "symbol"
    clause: str
    status: str = DANGLING
    detail: str = ""
    # The clause, plus the line above it **only when the prose actually wrapped**.
    # Comments wrap mid-sentence and the negation governing a reference is regularly on
    # the line before — `ownership.py:6` reads "holds a manifest per expert and no" /
    # "`main.yaml`, so the scope...", and one line at a time turned that true sentence
    # into a finding. Joining unconditionally is worse: it imports the previous
    # *sentence's* negation, which suppressed a live dangling module citation because
    # the paragraph above it happened to end on the words not an escape hatch.
    # So the join needs both signals of a wrap — the line above does not end a sentence,
    # and the reference sits at the start of the line below.
    context: str = ""


@dataclass
class ReferenceCensus:
    """What the recognizer read, and — equally — what it did not."""

    references: list[Reference] = field(default_factory=list)
    # Files the policy selected, and the subset actually read. The difference is the
    # gap: a file that would not parse is named, never skipped into silence.
    files_selected: int = 0
    files_read: list[str] = field(default_factory=list)
    unreadable: list[tuple[str, str]] = field(default_factory=list)
    # Tokens that looked like a reference and that no form consumed. This is the
    # complement — the half a whitelist-shaped report leaves out.
    unconsumed: list[tuple[str, int, str]] = field(default_factory=list)
    # Backticked dotted names. Recognised so they are not reported as unconsumed,
    # resolved by nothing so they are never reported as wrong.
    dotted: list[tuple[str, int, str]] = field(default_factory=list)

    def by_status(self, status: str) -> list[Reference]:
        return [item for item in self.references if item.status == status]

    @property
    def coverage(self) -> str:
        return f"{len(self.files_read)}/{self.files_selected}"


def _clause_around(line: str, start: int, end: int) -> str:
    """The clause a reference sits in — the sentence fragment, not the whole line.

    Split on the punctuation that separates independent claims, so a line reading
    "`a` is gone; `b` is fine" does not let the first clause's negation excuse the
    second's reference.
    """
    left = max(
        (line.rfind(mark, 0, start) for mark in (";", " — ", " – ", ". ", ", but ", ", and ")),
        default=-1,
    )
    right_candidates = [
        index for index in (line.find(mark, end) for mark in (";", " — ", " – ", ". ")) if index != -1
    ]
    right = min(right_candidates) if right_candidates else len(line)
    return line[left + 1 : right]


def _py_prose(text: str) -> list[tuple[int, str]]:
    """Comment tokens and docstrings — never a runtime string literal."""
    out: list[tuple[int, str]] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                out.append((token.start[0], token.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        docstring = ast.get_docstring(node, clean=False)
        if not docstring:
            continue
        anchor = getattr(node, "lineno", 1)
        for offset, line in enumerate(docstring.splitlines()):
            out.append((anchor + offset, line))
    return out


def _line_prose(text: str, markers: tuple[str, ...]) -> list[tuple[int, str]]:
    return [
        (index, line)
        for index, line in enumerate(text.splitlines(), 1)
        if line.lstrip().startswith(markers)
    ]


def _prose(path: Path, text: str) -> list[tuple[int, str]]:
    if path.suffix in PY_SUFFIXES:
        return _py_prose(text)
    if path.suffix in LINE_COMMENT_SUFFIXES:
        return _line_prose(text, LINE_COMMENT_SUFFIXES[path.suffix])
    if path.suffix in PROSE_SUFFIXES:
        return list(enumerate(text.splitlines(), 1))
    return []


def _selected(repo: Path, policy: ReferencePolicy) -> list[Path]:
    suffixes = set(PY_SUFFIXES) | set(LINE_COMMENT_SUFFIXES) | set(PROSE_SUFFIXES)
    found: list[Path] = []
    for root in policy.roots:
        base = repo / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            relative = path.relative_to(repo).as_posix()
            if any(fnmatch.fnmatch(relative, pattern) for pattern in policy.exclude):
                continue
            found.append(path)
    return found


def _resolve_path(repo: Path, target: str, policy: ReferencePolicy) -> Path | None:
    for root in policy.search_roots:
        candidate = (repo / root / target) if root != "." else (repo / target)
        if candidate.is_file():
            return candidate
    # `policy.exclude` governs which files this reads prose *from*, never which files
    # may be a referent. A comment in the gremlin skill cites `gremlin-docs/index.md`,
    # which exists and is excluded from the walk; judging it missing would report the
    # policy's own scope as a defect in the tree.
    matches = [path for path in repo.glob(f"**/{target}") if path.is_file()]
    return matches[0] if matches else None


def _is_placeholder(target: str) -> bool:
    parts = Path(target).parts
    segments = {part.lower() for part in parts} | {Path(target).stem.lower()}
    return bool(segments & _PLACEHOLDER_SEGMENTS)


def census(repo: Path, policy: ReferencePolicy | None = None) -> ReferenceCensus:
    """Read every reference under the roots and decide what each one turned out to be."""
    policy = policy or ReferencePolicy()
    report = ReferenceCensus()
    paths = _selected(repo, policy)
    report.files_selected = len(paths)

    for path in paths:
        relative = path.relative_to(repo).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            report.unreadable.append((relative, str(exc)))
            continue
        report.files_read.append(relative)

        previous = ""
        for lineno, line in sorted(_prose(path, text)):
            consumed: list[tuple[int, int]] = []

            for match in _PATH_LINE.finditer(line):
                consumed.append(match.span())
                target, start, end = match.group(1), int(match.group(2)), match.group(3)
                resolved = _resolve_path(repo, target, policy)
                clause = _clause_around(line, *match.span())
                if resolved is None:
                    status, detail = DANGLING, "no such file"
                else:
                    highest = int(end) if end else start
                    total = len(resolved.read_text(encoding="utf-8", errors="replace").splitlines())
                    status, detail = (
                        (RESOLVED, "")
                        if highest <= total
                        else (DANGLING, f"file has {total} lines")
                    )
                report.references.append(
                    _classify(
                        Reference(relative, lineno, match.group(0), "path-line", clause,
                                  status, detail, _wrapped_context(previous, line, match.start(), clause)),
                        policy,
                    )
                )

            for match in _PATH.finditer(line):
                if any(start <= match.start() < end for start, end in consumed):
                    continue
                if _URLISH.search(line[max(0, match.start() - 30) : match.end()]):
                    consumed.append(match.span())
                    continue
                consumed.append(match.span())
                target = match.group(1)
                if _is_placeholder(target):
                    continue
                clause = _clause_around(line, *match.span())
                found = _resolve_path(repo, target, policy) is not None
                report.references.append(
                    _classify(
                        Reference(relative, lineno, target, "path", clause,
                                  RESOLVED if found else DANGLING,
                                  "" if found else "path does not exist",
                                  _wrapped_context(previous, line, match.start(), clause)),
                        policy,
                    )
                )

            for match in _BARE_FILE.finditer(line):
                if any(start <= match.start() < end for start, end in consumed):
                    continue
                consumed.append(match.span())
                target = match.group(1)
                if _is_placeholder(target):
                    continue
                clause = _clause_around(line, *match.span())
                found = _resolve_path(repo, target, policy) is not None
                report.references.append(
                    _classify(
                        Reference(relative, lineno, target, "bare-file", clause,
                                  RESOLVED if found else DANGLING,
                                  "" if found else "no file of this name in the tree",
                                  _wrapped_context(previous, line, match.start(), clause)),
                        policy,
                    )
                )

            # Recognised, counted, and judged by nothing — see `_DOTTED`.
            for match in _DOTTED.finditer(line):
                if any(start <= match.start() < end for start, end in consumed):
                    continue
                consumed.append(match.span())
                report.dotted.append((relative, lineno, match.group(1)))

            previous = line

            for match in _CANDIDATE.finditer(line):
                if any(
                    start <= match.start() < end or match.start() <= start < match.end()
                    for start, end in consumed
                ):
                    continue
                report.unconsumed.append((relative, lineno, match.group(0)))

    return report


def _wrapped_context(previous: str, line: str, start: int, clause: str) -> str:
    """The absence-reading context: the clause, and the line above it if prose wrapped.

    Both conditions, or neither. See `Reference.context` for what each one is holding
    off — a missed suppression and a false one, and the false one is the expensive
    direction because nobody ever sees it.
    """
    tail = previous.rstrip()
    if not tail or tail[-1] in ".!?:":
        return clause
    if start - (len(line) - len(line.lstrip())) > 4:
        return clause
    return f"{tail} {clause}"


def _unquoted(text: str) -> str:
    """Text with quoted spans removed, including one left open by a line wrap.

    The paired form alone is not enough. Comment prose wraps mid-quotation, so the
    clause this reads regularly holds an opening quote whose partner is two lines
    down — which is exactly the shape that hid a live citation from the report. An
    unmatched quote therefore swallows the rest of the string rather than nothing.
    """
    stripped = _QUOTED.sub(" ", text)
    opening = stripped.find('"')
    return stripped if opening == -1 else stripped[:opening]


def _classify(reference: Reference, policy: ReferencePolicy) -> Reference:
    """Apply the absence reading and the declared exemptions, in that order.

    Absence first, because an exemption is a decision someone made about a defect and
    an asserted absence was never one — recording the second as the first would put a
    true sentence on a list of tolerated wrongs.
    """
    if reference.status != DANGLING:
        return reference
    # The reference's own text is removed first. A module whose filename happens to
    # contain an absence word otherwise carries the cue inside the very token being
    # judged, and suppresses itself — silently, which is the failure direction this
    # channel can least afford.
    sentence = (reference.context or reference.clause).replace(reference.target, " ")
    if _ABSENCE.search(_unquoted(sentence)):
        return Reference(
            reference.file, reference.lineno, reference.target, reference.kind,
            reference.clause, ASSERTED_ABSENT,
            "the sentence asserts this does not exist", reference.context,
        )
    for exemption in policy.exemptions:
        if exemption.matches(reference):
            return Reference(
                reference.file, reference.lineno, reference.target, reference.kind,
                reference.clause, EXEMPTED, exemption.reason, reference.context,
            )
    return reference


def reference_findings(report: ReferenceCensus) -> list[Finding]:
    """Dangling references as findings, and the census's own reach as another.

    An asserted absence produces no finding at all — not a softened one. The whole
    point of separating it is that it is not a defect, and a finding is what a reader
    is asked to act on.
    """
    found = [
        Finding(
            description=(
                f"{reference.file}:{reference.lineno} cites {reference.target}, "
                f"which does not resolve ({reference.detail})."
            ),
            category=DESIGN,
            artifacts=(reference.file,),
        )
        for reference in report.by_status(DANGLING)
    ]
    for path, reason in report.unreadable:
        found.append(
            Finding(
                description=f"{path} could not be read, so its references are unmeasured: {reason}",
                category=UNDERSTANDING,
                artifacts=(path,),
            )
        )
    return found


def render(report: ReferenceCensus, limits: bool = False) -> str:
    """The report. Covered and uncovered on the same page, never one without the other."""
    lines: list[str] = []
    dangling = report.by_status(DANGLING)
    absent = report.by_status(ASSERTED_ABSENT)
    exempted = report.by_status(EXEMPTED)
    lines.append(
        f"{len(report.references)} reference(s) over {report.coverage} file(s): "
        f"{len(report.by_status(RESOLVED))} resolved, {len(dangling)} dangling, "
        f"{len(absent)} asserted-absent, {len(exempted)} exempted"
    )
    # Rendered from the findings rather than from the references, so the sentence a
    # reader sees is the same object a caller would act on. Two formatters over one
    # observation is how a report and a gate drift into disagreeing about it.
    for finding in reference_findings(report):
        lines.append(f"  {finding.category:<11} {finding.description}")
    for reference in exempted:
        lines.append(
            f"  exempted   {reference.file}:{reference.lineno}  {reference.target} "
            f"— {reference.detail}"
        )
    # Always printed, never behind the flag. A reader who is told 4 things resolved
    # and not told 900 tokens went unread has been told the wrong thing.
    lines.append(
        f"{len(report.unconsumed)} candidate(s) no form consumed, "
        f"{len(report.dotted)} dotted name(s) recognised and not resolved, "
        f"{len(report.unreadable)} file(s) unreadable"
    )
    if limits:
        for path, lineno, raw in report.unconsumed[:200]:
            lines.append(f"  unconsumed {path}:{lineno}  {raw}")
        if len(report.unconsumed) > 200:
            lines.append(f"  ... {len(report.unconsumed) - 200} more")
        for path, lineno, raw in report.dotted[:100]:
            lines.append(f"  dotted     {path}:{lineno}  {raw} — no oracle, not judged")
        if len(report.dotted) > 100:
            lines.append(f"  ... {len(report.dotted) - 100} more")
        for path, reason in report.unreadable:
            lines.append(f"  unreadable {path}  — {reason}")
        for reference in absent:
            lines.append(
                f"  absent     {reference.file}:{reference.lineno}  {reference.target} "
                f"— not a finding: {reference.clause.strip()[:70]}"
            )
    lines.append(
        "Report only: this channel fails no build. A gate is withheld until a shadow "
        "run measures its precision, because a false positive nobody records cannot "
        "be counted afterwards."
    )
    return "\n".join(lines)
