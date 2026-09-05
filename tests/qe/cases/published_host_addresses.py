"""No tracked file in this public repository may carry an address that names a machine.

`published_config.py` already holds this rule and holds it well — for configuration
files, keyed on the *name* of the key an address sits under. That scoping is what let
the same rule be broken somewhere else: on 2026-08-20 a VM harness under `tests/qe/vm/`
was pushed carrying the operator's LAN address and tailnet address in a Python module's
`PROBE_TARGETS` dict and in a README table. No key name said "host". It was source, not
config. The branch was deleted from the remote thirteen minutes later and the harness
now lives in a private repository.

The instructive part is not the leak, it is what was already in place. The probe itself
deliberately carried no addresses — a probe with one box's IPs baked in is wrong on every
other machine and looks correct while testing nothing — and a passing check asserted
exactly that about exactly that file. The rule was right, the check was real, and its
scope was one file narrower than the rule it enforced. A check whose scope is narrower
than its rule reads as coverage and is not.

So this case is scoped to the rule instead of to a file class: **every** tracked file,
whatever its type, whatever the surrounding syntax.

## Two halves, because the identity of a machine has two sources

**What this machine currently holds.** The addresses on its interfaces and its hostname,
read at runtime. This is the strongest half — it needs no guess about which ranges are
sensitive, it flags the operator's actual tailnet address rather than the shape of one,
and it follows the box when the box changes. It also keeps this file honest: no address
of the machine under protection is written down here, because the case asks the kernel
instead of carrying a copy. A leak detector that has to name the secret to find it is
one more place the secret lives.

Its limit is stated rather than hidden: it can only see identity the machine holds *now*.
An address that has since changed is invisible to it, and it is blind on any other
machine, which is why the second half exists.

**Shapes that name somebody's machine wherever they appear.** RFC1918's 192.168/16 and
172.16/12, RFC6598's 100.64/10 — the range Tailscale assigns from, where a hit is close
to proof — and `*.ts.net` hostnames that are not obviously placeholders.

## What is deliberately not matched, and why

**10/8.** Measured over this tree: every occurrence is third-party. TinkerPop's vendored
documentation writes `spark@10.0.0.1` in three files, and `uv.lock` pins a package version
that reads as an address (`10.4.0.35`). A rule that fires on those would be muted within a
week, and muting is worse than the narrower rule. This machine's own 10/8 addresses are
still covered, by the runtime half, which is the half that can tell them apart.

**Loopback, `0.0.0.0`, and the broadcast address** name no machine. **RFC5737's
documentation ranges** (`192.0.2/24`, `198.51.100/24`, `203.0.113/24`) are the correct
thing to write in an example and must stay writable.

## The home directory, in scope and in two spellings

A home directory is not a reachable address, but it names the operator's account and it
breaks on every other machine, so it is held to the same rule. The tree was cleaned to
placeholders first — `/home/op` and `/home/u` are what worked examples use — so the
rule starts green and is enforceable rather than exempted.

It is matched in two spellings because the cleanup that preceded it found the second the
hard way. Grepping for the path form left five occurrences of the *flattened* form
behind: Claude Code names a project directory by punching `/`, `.` and `_` in the cwd
down to `-`, so `$HOME` also appears as `-home-<user>`, which no search for a slash will
ever return. Both spellings are derived from `Path.home()` at runtime, for the same
reason the addresses are: this file names neither.

## Shown capable of going red, against the defect as it shipped

The mutation cannot live in the case, because the case's subject is the tracked tree and
a fixture inside it would be the very thing it forbids. Repeat it in four commands:

    mkdir -p tests/qe/vm
    printf 'PROBE_TARGETS = {"HOST_LAN_IP": "<this box LAN>"}\\n' > tests/qe/vm/seed.py
    git add tests/qe/vm/seed.py        # tracked is the trigger; untracked is invisible
    uv run python tests/qe/run.py --tier fast

Run on 2026-08-20 with the two real addresses the original carried, it reported four
occurrences in one file — each address found twice, once by the runtime half and once by
the shape half, which is the redundancy working rather than a double count. `git rm
--cached` and delete the file afterwards.

## The controls, both running

A leak case that finds nothing is indistinguishable from a leak case that looked nowhere,
so neither "no hits" nor "scan completed" is trusted on its own.

A box without `ip(8)` fails this case rather than skipping it, which is a departure from
the suite's rule that absent substrate yields SKIPPED. The rule does not apply: `ip` is
not substrate here, because the case still means something without it — the static half
runs. What its absence does is *narrow* the check while leaving its green unchanged, and
that is the exact shape of the defect this case descends from. Narrowing is the thing
being guarded against, so it is reported as a failure and not as a skip. The detector is run
against a synthetic body built at runtime, and the scan must have decoded a plausible
number of files. The runtime half additionally reports when it learned no identity at
all — on a box without `ip`, that half contributes nothing, and saying so is the
difference between a narrower check and a check that quietly became a no-op.
"""

from __future__ import annotations

import re
import socket
import subprocess
from pathlib import Path

from qe.model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]

#: Ranges whose appearance names somebody's private network. Written as patterns rather
#: than as addresses so this file carries none of what it hunts.
_SHAPES = (
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b"),
)

_TAILNET_HOST = re.compile(r"\b[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*\.ts\.net\b", re.I)

#: A `*.ts.net` name is allowed when its own text says it stands for something. These are
#: the markers this tree already uses in its worked examples.
_PLACEHOLDER_MARKERS = ("some-", "example", "your-", "replace", "changeme", "my-tailnet")

#: RFC5737. The correct addresses to write in documentation, and none of the shapes above
#: overlap them; listed so the exemption is a decision on the page rather than an accident
#: of which ranges were chosen.
_DOC_RANGES = ("192.0.2.", "198.51.100.", "203.0.113.")

#: Home directories that name nobody. These are the placeholders this tree's worked
#: examples use, and a checkout running as one of them must not flag every example.
_PLACEHOLDER_HOMES = frozenset({"op", "u", "user", "someone", "dev", "x", "root", ""})

#: Loopback and the wildcard name no machine.
_NAMES_NOTHING = re.compile(r"^(?:127\.\d{1,3}\.\d{1,3}\.\d{1,3}|0\.0\.0\.0"
                            r"|255\.255\.255\.255|::1?)$")

#: Files whose content is not ours to police. Vendored upstream documentation and the
#: resolver's lock file both carry address-shaped text that no edit here should change.
_NOT_OURS = ("src/thalamus/harness/skills/gremlin-python/gremlin-docs/", "uv.lock")


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=str(_REPO),
                         capture_output=True, text=True, check=False)
    return [n for n in out.stdout.split("\0") if n]


def _flatten(path: str) -> str:
    """Claude Code's project-directory spelling of a path: `/`, `.` and `_` all to `-`."""
    return re.sub(r"[/._]", "-", path)


def _machine_identity() -> tuple[set[str], list[str]]:
    """Addresses this machine holds and the name it answers to, read at runtime.

    Returns the identity and a list of reasons any part could not be learned. The reasons
    are reported rather than swallowed: a half that learned nothing finds nothing, and
    that must not read as a clean scan.
    """
    identity: set[str] = set()
    gaps: list[str] = []

    for family in ("-4", "-6"):
        proc = subprocess.run(["ip", "-o", family, "addr", "show"],
                              capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            gaps.append(f"ip {family} addr failed: {proc.stderr.strip()[:80]}")
            continue
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                addr = parts[3].split("/")[0]
                if not _NAMES_NOTHING.match(addr):
                    identity.add(addr)

    home = Path.home()
    if home.name in _PLACEHOLDER_HOMES:
        gaps.append(f"home directory {home.name!r} is a placeholder name, so a real "
                    "home could not be distinguished from a worked example")
    else:
        # Both spellings. Claude Code names a project directory by punching `/`, `.`
        # and `_` down to `-`, so $HOME appears flattened too and no search for a
        # slash finds it. Missing that spelling is measured, not theorised: the
        # cleanup this case was written alongside left five flattened occurrences
        # behind after the path form was grepped clean.
        text = str(home)
        identity.add(text)
        identity.add(_flatten(text))

    host = socket.gethostname().strip()
    if host and host not in ("localhost", ""):
        identity.add(host)
    else:
        gaps.append("gethostname() returned nothing usable")

    if not identity:
        gaps.append("no interface address and no hostname were learned")
    return identity, gaps


def _exempt(path: str) -> bool:
    return any(path == n or path.startswith(n) for n in _NOT_OURS)


def _placeholder_tailnet(host: str) -> bool:
    lowered = host.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def scan_text(path: str, body: str, identity: set[str]) -> list[str]:
    """Every reason this file names a machine. Empty means it names none."""
    hits: list[str] = []

    for value in sorted(identity):
        if value in body:
            hits.append(f"{path}: holds this machine's own {value!r}")

    for pattern in _SHAPES:
        for match in sorted(set(pattern.findall(body))):
            if any(match.startswith(doc) for doc in _DOC_RANGES):
                continue
            hits.append(f"{path}: private-range address {match!r}")

    for match in sorted(set(_TAILNET_HOST.findall(body))):
        if not _placeholder_tailnet(match):
            hits.append(f"{path}: tailnet hostname {match!r}")

    return hits


def run() -> Finding | None:
    identity, gaps = _machine_identity()

    # CONTROL 1, and it runs on every invocation: the detector must see an address in a
    # body that has one. The address is assembled here rather than written, so this file
    # stays free of the thing it hunts — which is also the property the case asserts of
    # every other file, and a case exempting itself from its own rule is not one.
    # The host must carry none of `_PLACEHOLDER_MARKERS`, or the exemption swallows the
    # control and this reports a detector that cannot see tailnet hostnames at all.
    synthetic_addr = ".".join(("192", "168", "251", "7"))
    synthetic_host = "a-real-box." + "tailnet-alpha" + ".ts.net"
    proof = scan_text("<control>", f"host={synthetic_addr} url=https://{synthetic_host}/",
                      set())
    if len(proof) < 2:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the detector did not flag a synthetic private address and tailnet "
                    "host, so it cannot see the class of value this case exists for and "
                    "a clean scan would mean nothing",
            witness=f"scan_text on a body carrying both returned {len(proof)} hit(s)",
            site="tests/qe/cases/published_host_addresses.py:scan_text",
        )

    # CONTROL 1b: the identity half must see a home directory in BOTH spellings. The
    # shape patterns cannot catch a home path at all, so this half is the only thing
    # standing behind the home rule, and the flattened spelling is the one a grep for
    # `/home/...` silently misses. A synthetic home is used, so this file still names
    # no real one.
    synthetic_home = "/home/" + "notarealoperator"
    home_proof = scan_text(
        "<control>",
        f"cwd={synthetic_home}/code and dir={_flatten(synthetic_home)}-code",
        {synthetic_home, _flatten(synthetic_home)},
    )
    if len(home_proof) < 2:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the detector did not flag a home directory in both its path and "
                    "its flattened spelling, so the half that enforces the home rule "
                    "is not doing it and a clean scan would mean nothing",
            witness=f"scan_text on a body carrying both spellings returned "
                    f"{len(home_proof)} hit(s), expected 2",
            site="tests/qe/cases/published_host_addresses.py:_flatten",
        )

    # CONTROL 2: a documentation address must remain writable, or the rule stops being
    # "no real machine" and becomes "no addresses", which authors route around.
    if scan_text("<control>", "connect to " + "192.0.2." + "10", set()):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the detector flags RFC5737 documentation addresses, so correct "
                    "examples cannot be written and the rule will be worked around",
            witness="scan_text flagged a 192.0.2.0/24 address",
            site="tests/qe/cases/published_host_addresses.py:_DOC_RANGES",
        )

    leaks: list[str] = []
    read = 0
    undecodable = 0
    for name in _tracked():
        if _exempt(name):
            continue
        path = _REPO / name
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            undecodable += 1
            continue
        read += 1
        leaks.extend(scan_text(name, body, identity))

    # CONTROL 3: the scan must have reached the tree. A checkout that moved, a git that
    # returned nothing, or a working directory this case guessed wrong would all produce
    # zero hits and read as clean.
    if read < 50:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the scan decoded implausibly few tracked files, so 'no file names "
                    "a machine' is a statement about the scan and not about the tree",
            witness=f"{read} file(s) decoded, {undecodable} undecodable, "
                    f"repo root guessed as {_REPO}",
            site="tests/qe/cases/published_host_addresses.py:_tracked",
        )

    # CONTROL 4: the runtime half is the one that catches an address no shape covers.
    # If it learned nothing it silently degrades this case to the static half, and a
    # degraded check that reports the same green as a working one is the failure this
    # whole suite is about.
    if gaps:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="this machine's own identity could not be read, so the half of the "
                    "scan that catches an address outside the known shapes did not run",
            witness="; ".join(gaps),
            site="tests/qe/cases/published_host_addresses.py:_machine_identity",
        )

    if not leaks:
        return None

    return Finding(
        failure_class=FailureClass.BOUNDARY_LEAK,
        summary=(
            "a tracked file names a real machine — this repository is public, and a push "
            "publishes it to every clone and every fork, where deleting the branch "
            "afterwards does not take it back"
        ),
        witness=f"{len(leaks)} occurrence(s) across {read} tracked file(s): "
                + "; ".join(leaks[:6])
                + (f" (+{len(leaks) - 6} more)" if len(leaks) > 6 else ""),
        site="the tracked tree",
    )


CASE = Case(
    name="published-tree-names-no-real-machine",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="no tracked file carries an address or hostname that identifies a real "
            "machine, checked against this box's live identity and against the private "
            "ranges, over every tracked file rather than over a file class",
    run=run,
)
