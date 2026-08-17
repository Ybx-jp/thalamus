"""A tracked configuration file must not name a real host or carry a real secret.

`deploy/penpot/.env.example` said on its own second line that it was the tracked template
and *must never carry a real secret*. It shipped carrying this machine's real tailnet host
on `PENPOT_PUBLIC_URI` — the one line in the file that was not a `REPLACE-ME` (`c9a0082`).
The repository is public. A tag cut before that commit would have published it, and a
published host identifier is not retractable: the file can be edited, the git history and
every clone cannot.

**The `.example` suffix was incidental to the file that failed.** That deployment lives in
a different repository now and took the last `.example` file with it, but nothing about the
leak needed the suffix: what publishes a host is any configuration file this repository
tracks, and several are still here as worked examples — `config/mcp/designer.json` names a
server URL, `config/gremlin-server.yaml` a bind address. So the scan covers every tracked
file under `config/`, plus any `.example` or `.env.*` file anywhere, which is the class that
returns the moment a deployment does.

The property is narrow on purpose, because the obvious wide version is wrong. "Every value
in a config file is a placeholder" goes red on `PENPOT_FLAGS=enable-registration ...`, which
is a real value and *should* be — feature flags are the documentation. What must not be a
real value is the value of a key whose name says it carries a credential or an address.
Keying on the *name* rather than on the value's shape is what lets the check fire on a real
hostname, which no credential-pattern scanner recognises, because a hostname is not a
credential. `scan_for_secrets` would not have caught this one.

**Names are matched by segment, not by substring.** `PENPOT_PUBLIC_URI` and `graphLocation`
both split on separators and case boundaries, so `uri` is found in the first while `author`
never reads as `auth` in the second — a substring test over prose-heavy YAML manifests
raises exactly that false positive. Words that name a credential and nothing else — secret,
password, token, credential — match anywhere in the key, since those need no boundary.

**Acceptable values are defined positively**: empty, an explicit marker (`REPLACE-ME`, an
`<angle-bracketed>` span, `CHANGEME`/`YOUR-`, `${...}`), or an address that identifies
nothing — `localhost`, `127.0.0.0/8`, `0.0.0.0`, `::1`. The loopback carve-out is the only
exception and it is enumerable: those addresses name no machine and no network, so they
cannot leak one. Everything else is a real value. A negative definition — "does not look
like a secret" — is the check that passed the tailnet host, since a hostname looks exactly
like documentation.

**Two controls, both running, and one of them has already fired.** The acceptance gate is
exercised against a synthetic real host on every run, because a gate that has drifted into
always-true would clear the very line this case exists for. And the scan must reach at least
one key of the kind this case is about, or a repository whose config was renamed, moved or
emptied reports the same clean pass as a correct one — which is what happened when the
Penpot deployment left: the file class emptied, and the control reported the collapse
instead of a green.

**Shown capable of going red.** Point `config/mcp/designer.json`'s `url` at
`https://penpot.some-tailnet.ts.net/mcp` and the case reports `invariant-falsified` naming
the file, the key and the value; restore the loopback address and it returns green. Run
against the tree as it stood at `c9a0082^`, it reports the leak that shipped.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]

# Key-name segments whose value is a credential or an address. Matched on the key name,
# because the leak was a hostname and a hostname has no distinguishing shape.
_SENSITIVE_SEGMENTS = frozenset({
    "key", "apikey", "token", "secret", "password", "passwd", "credential",
    "auth", "uri", "url", "host", "hostname", "endpoint", "addr", "address",
    "email", "username",
})

# These name a credential and nothing else, so they need no segment boundary to be
# unambiguous — `MYSECRETVALUE` is as much a hit as `MY_SECRET_VALUE`.
_UNAMBIGUOUS = ("secret", "password", "passwd", "credential", "apikey", "token")

# Separators and camelCase boundaries. `PENPOT_PUBLIC_URI` -> uri; `graphLocation` -> graph,
# location; `author` stays one segment and never reads as `auth`.
_SEGMENT = re.compile(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])")

# What an acceptable placeholder looks like, stated positively.
_PLACEHOLDER = re.compile(r"(?i)(REPLACE[-_]ME|CHANGE[-_]?ME|YOUR[-_]|<[^>]+>|\$\{[^}]+\})")

# Addresses that identify no machine and no network, so they cannot leak one.
_LOCAL_HOSTS = frozenset({"localhost", "0.0.0.0", "::", "::1", "[::1]", "127.0.0.1"})
_LOOPBACK_V4 = re.compile(r"^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

# `KEY=value` (env files, java properties) and `key: value` / `"key": "value"` (YAML, JSON).
_ENV = re.compile(r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_.]*)\s*=\s*(?P<value>.*)$")
_MAPPING = re.compile(
    r"""^\s*"?(?P<key>[A-Za-z_][A-Za-z0-9_.\-]*)"?\s*:\s*(?P<value>.*?)\s*,?\s*$""")

# YAML block-scalar and container openers: the line declares a key and holds no value, so
# there is nothing on it to leak.
_NO_VALUE = frozenset({"", ">", ">-", ">+", "|", "|-", "|+", "{", "[", "{}", "[]", "null", "~"})


def _is_sensitive(key: str) -> bool:
    segments = {s.lower() for s in _SEGMENT.split(key) if s}
    if segments & _SENSITIVE_SEGMENTS:
        return True
    low = key.lower()
    return any(word in low for word in _UNAMBIGUOUS)


def _host_of(value: str) -> str:
    """The host a value names, or the value itself when it names none.

    Textual rather than `urlsplit`, because half the values in this class are bare hosts
    and a bare host parses as a path.
    """
    text = value.split("://", 1)[-1]
    text = text.split("/", 1)[0].split("@")[-1]
    if text.startswith("["):                      # bracketed IPv6, port optional
        return text.split("]", 1)[0] + "]"
    return text.rsplit(":", 1)[0] if text.count(":") == 1 else text


def _identifies_nothing(value: str) -> bool:
    host = _host_of(value).lower()
    return host in _LOCAL_HOSTS or bool(_LOOPBACK_V4.match(host))


def _acceptable(value: str) -> bool:
    """The whole gate: empty, an explicit marker, or an address that identifies nothing."""
    stripped = value.strip().strip("\"'")
    if not stripped:
        return True                      # nothing to leak
    if _PLACEHOLDER.search(stripped):
        return True
    return _identifies_nothing(stripped)


def _tracked_config() -> list[Path]:
    """Tracked configuration files. Enumerated from git, not from a hand list."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=str(_REPO),
                         capture_output=True, text=True, check=False)
    names = [n for n in out.stdout.split("\0") if n]
    return [_REPO / n for n in names
            if n.startswith("config/")
            or n.endswith(".example") or n.endswith(".example.env")
            or Path(n).name.startswith(".env.")]


def run() -> Finding | None:
    # CONTROL, and it runs: the gate must still be able to say "this is a real value".
    if _acceptable("https://penpot.some-real-tailnet.ts.net"):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the acceptance gate admits a real hostname, so it cannot detect the "
                    "value this case exists for and its green means nothing",
            witness="_acceptable('https://penpot.some-real-tailnet.ts.net') is True",
            site="tests/qe/cases/published_config.py:_acceptable",
        )

    files = _tracked_config()
    if not files:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no tracked configuration file was found, so 'no config names a real "
                    "host' and 'no config was read' are the same result",
            witness=f"git ls-files under {_REPO} matched nothing under config/ and no "
                    f".example file",
            site="tests/qe/cases/published_config.py:_tracked_config",
        )

    checked, leaks = 0, []
    for path in files:
        try:
            text = path.read_text(errors="replace")
        except OSError as exc:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="a tracked configuration file could not be read, so it was not "
                        "checked and the clean result does not cover it",
                witness=f"{path}: {type(exc).__name__}: {exc}",
                site="tests/qe/cases/published_config.py",
            )
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            match = _ENV.match(line) or _MAPPING.match(line)
            if not match or not _is_sensitive(match.group("key")):
                continue
            value = match.group("value").split(" #")[0].strip()
            if value in _NO_VALUE:
                continue
            checked += 1
            if not _acceptable(value):
                rel = path.relative_to(_REPO)
                leaks.append(f"{rel}:{number} {match.group('key')}={value[:60]}")

    # CONTROL: the scan must have reached a key of the kind this case is about.
    if checked == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no credential- or address-named key was found in any tracked "
                    "configuration file, so this case would pass a config whose keys were "
                    "all renamed out of its reach",
            witness=f"{len(files)} file(s) read, 0 assignments matched a sensitive key name",
            site="tests/qe/cases/published_config.py:_SENSITIVE_SEGMENTS",
        )

    if not leaks:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a tracked configuration file carries a real value on a line naming a "
            "credential or a host — this repository is public, and a tag publishes it to "
            "every clone, where editing the file afterwards does not take it back"
        ),
        witness=f"{len(leaks)} of {checked} sensitive-named assignment(s): "
                + "; ".join(leaks[:6])
                + (f" (+{len(leaks) - 6} more)" if len(leaks) > 6 else ""),
        site="tracked configuration under config/ and *.example",
    )


CASE = Case(
    name="published-config-names-no-real-host-or-secret",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="every credential- or address-named key in a tracked configuration file must "
            "hold a placeholder or an address that identifies nothing",
    run=run,
)
