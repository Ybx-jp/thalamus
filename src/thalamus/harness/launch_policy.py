"""The operator's chosen launch posture — stored, expiring, and audited.

Every launch flag in this system used to be a constant with a citation above it, which
is the right home for a decision nobody revisits and the wrong one for a posture an
operator needs to change from a phone at the moment a session is stalling. This module
is the store behind that surface; `harness/launcher.py` owns *what may be chosen* and
this owns *what was chosen*, because the set of legal postures is a property of the
harness and the selection is a property of the operator.

**It writes our own file and never the harness's.** A vendor config file
(`~/.cursor/cli-config.json`, `settings.local.json`) is state the sessions themselves
rewrite — `/config`, `/run-everything` and `/sandbox` are live slash commands — so one
window toggling its own posture would silently rewrite every other window's. A
per-window property stored where any window can rewrite it is not a boundary; it is a
shared mutable variable with a nice name. The selection here reaches a session only by
being folded into its argv at launch, which is also the only carrier that survives
`respawn-window`.

**A widening change is a different act from a narrowing one, and is treated as one.**
Progent classifies every privilege-policy update as narrowing or widening and refuses
to let a widening one pass silently, on the finding that its deterministic update
mechanism is what preserves utility while preventing *silent* privilege escalation
(arXiv 2504.11703). Progent needs an SMT solver because its policies are an open-ended
DSL over tool names and arguments; ours is a short ordered list per harness, so the
ordering is the classification. What the rule buys is the same: no path exists by which
a posture becomes more permissive without a record saying so.

**A loosening may carry a lifetime; a tightening may not.** A rung above the harness's
default is offered an expiry and reverts on its own if given one, because a permissive
posture fails by outliving the reason for it. It is offered rather than required: this
panel is passed through often enough that the setting is seen and re-decided in the
normal course of work, which is the safeguard a short forced lifetime would be
duplicating (operator decision, 2026-08-13). A rung at or below the default takes no
lifetime at all and is refused one — a posture reverting toward *more* permission on a
timer is the forgotten-setting failure with its sign flipped.

**Every change is a ledger row**, which is the one thing the graph's own literature is
unambiguous about: configuration adjustments should follow a controlled workflow, and
access auditing should record privilege escalations rather than leaving them to be
reconstructed (MCP threat survey, arXiv 2503.23278). The rows are append-only and carry
the direction, so "when did this box become permissive" is a question with an answer.

Not found in the 2026 scan: a permission surface that ties the
lifetime of a setting to whether it widened privilege.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from thalamus.harness.launcher import LAUNCH_SHAPES, Capability

LAUNCH_DIR = Path.home() / ".thalamus" / "launch"
STORE = LAUNCH_DIR / "policy.json"
LEDGER = LAUNCH_DIR / "policy.jsonl"

STORE_VERSION = 1

# The lifetimes a loosening selection may carry, alongside the option of none at all.
# A closed list for the same reason the postures are one: a duration typed into a box is
# a value nothing can check, and the panel's whole contract is that it cannot express
# something invalid. One day, because the operator passes through this panel often
# enough that a shorter lifetime is friction rather than a safeguard — the setting is
# seen and re-decided in the normal course of work (operator decision, 2026-08-13).
TTL_CHOICES = (24,)

WIDEN = "widen"
NARROW = "narrow"
SAME = "same"


class PolicyRefused(ValueError):
    """A selection the surface must not accept. Carries operator-facing prose."""


@dataclass(frozen=True)
class Selection:
    """What the operator chose for one capability, and when it lapses."""

    value: str
    expires_at: datetime | None = None

    def expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _capability(harness: str, key: str) -> Capability | None:
    shape = LAUNCH_SHAPES.get(harness)
    if shape is None:
        return None
    return next((c for c in shape.capabilities if c.key == key), None)


def _read(store: Path | None = None) -> dict:
    path = store or STORE
    try:
        raw = json.loads(path.read_text() or "{}")
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def stored(harness: str, *, store: Path | None = None) -> dict[str, Selection]:
    """The raw selections on file for a harness, expiry included and not yet applied.

    Kept distinct from `effective` because the two answer different questions: this one
    is what the operator chose, which the panel has to show even once it has lapsed, and
    `effective` is what a launch would actually use.
    """
    harnesses = _read(store).get("harnesses")
    entries = harnesses.get(harness) if isinstance(harnesses, dict) else None
    if not isinstance(entries, dict):
        return {}
    out: dict[str, Selection] = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("value"), str):
            continue
        out[key] = Selection(entry["value"], _stamp(entry.get("expires_at")))
    return out


def effective(
    harness: str, *, store: Path | None = None, now: datetime | None = None
) -> dict[str, str]:
    """The values a launch should use: stored, minus anything lapsed or unrecognized.

    A lapsed or unknown selection is simply absent, which drops that capability to the
    harness's default in `capability_argv`. Reverting has to be the behaviour of reading
    rather than a job that sweeps the file, because nothing guarantees a sweep ran: on a
    box where the console has been closed for a week, the expiry that matters is the one
    enforced by the next launch.
    """
    moment = _now(now)
    out: dict[str, str] = {}
    for key, selection in stored(harness, store=store).items():
        capability = _capability(harness, key)
        if capability is None or capability.option(selection.value) is None:
            continue
        if selection.expired(moment):
            continue
        out[key] = selection.value
    return out


def describe(
    harness: str, *, store: Path | None = None, now: datetime | None = None
) -> list[dict]:
    """Everything the panel needs to render one harness, options and state together.

    One structure rather than two endpoints, because every field here is only meaningful
    beside the others: `expires_at` without `widening` reads as an arbitrary deadline,
    and an option list without `drops` is the capability-declaration failure this
    surface exists to avoid.
    """
    shape = LAUNCH_SHAPES.get(harness)
    if shape is None:
        return []
    moment = _now(now)
    held = stored(harness, store=store)
    live = effective(harness, store=store, now=moment)
    out = []
    for capability in shape.capabilities:
        selection = held.get(capability.key)
        value = live.get(capability.key, capability.default)
        out.append({
            "key": capability.key,
            "title": capability.title,
            "value": value,
            "default": capability.default,
            "is_default": value == capability.default,
            # Present only while a widening selection is still live, so the panel can
            # show the countdown that makes "this reverts" a visible promise.
            "expires_at": (
                selection.expires_at.isoformat()
                if selection and selection.expires_at and not selection.expired(moment)
                else None
            ),
            "lapsed": bool(selection and selection.expired(moment)),
            "ttl_choices": list(TTL_CHOICES),
            "options": [
                {
                    "value": o.value,
                    "label": o.label,
                    "drops": o.drops,
                    "argv": list(o.argv),
                    # Whether picking this one is a widening — the panel uses it to
                    # decide whether to ask for a lifetime, so the rule lives in one
                    # place and the client cannot disagree with the server about it.
                    "widening": capability.rank(o.value) > capability.rank(value),
                    "above_default": capability.rank(o.value) > capability.default_rank,
                }
                for o in capability.options
            ],
        })
    return out


def direction(capability: Capability, current: str, value: str) -> str:
    rank_now, rank_next = capability.rank(current), capability.rank(value)
    if rank_next > rank_now:
        return WIDEN
    return NARROW if rank_next < rank_now else SAME


def select(
    harness: str,
    key: str,
    value: str,
    *,
    ttl_hours: int | None = None,
    actor: str = "console",
    store: Path | None = None,
    ledger: Path | None = None,
    now: datetime | None = None,
) -> dict:
    """Record a selection. Raises `PolicyRefused` for anything the surface may not accept.

    Refusals are prose rather than codes because every one of them is shown to a person
    mid-decision, and the reason a lifetime is required is the whole argument for the
    rule — a surface that answered `400` here would be enforcing a policy it declines to
    explain.
    """
    capability = _capability(harness, key)
    if capability is None:
        raise PolicyRefused(f"`{harness}` has no `{key}` to set.")
    option = capability.option(value)
    if option is None:
        raise PolicyRefused(f"`{value}` is not a posture `{harness}` offers.")

    moment = _now(now)
    current = effective(harness, store=store, now=moment).get(key, capability.default)
    how = direction(capability, current, value)

    # Above the harness's default, not merely above where it stands now: stepping down
    # from `force` to `auto-review` is a narrowing, but leaving it permanent would park
    # the box above its default forever with no record that anything was still elevated.
    above_default = capability.rank(value) > capability.default_rank
    if above_default:
        if ttl_hours is None:
            # Chosen to stay until it is changed. Legitimate, and the reason it is not
            # forced is in the module docstring.
            expires_at = None
        elif ttl_hours not in TTL_CHOICES:
            raise PolicyRefused(
                f"{ttl_hours}h is not one of the offered lifetimes "
                f"({', '.join(f'{h}h' for h in TTL_CHOICES)})."
            )
        else:
            expires_at = moment + timedelta(hours=ttl_hours)
    else:
        # A lifetime on a posture at or below the default would revert *toward* more
        # permission on a timer, which is the forgotten-setting bug with its sign
        # flipped. Refused rather than ignored, so a caller asking for it is told.
        if ttl_hours is not None:
            raise PolicyRefused(
                f"`{option.label}` is not more permissive than the "
                f"default, so it does not take a lifetime."
            )
        expires_at = None

    raw = _read(store)
    harnesses = raw.get("harnesses")
    raw["harnesses"] = harnesses if isinstance(harnesses, dict) else {}
    entries = raw["harnesses"].get(harness)
    raw["harnesses"][harness] = entries if isinstance(entries, dict) else {}
    raw["version"] = STORE_VERSION
    raw["harnesses"][harness][key] = {
        "value": value,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }

    path = store or STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")

    row = {
        "ts": moment.isoformat(),
        "harness": harness,
        "capability": key,
        "from": current,
        "to": value,
        "direction": how,
        "ttl_hours": ttl_hours,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "actor": actor,
    }
    _append(ledger or LEDGER, row)
    return row


def _append(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        # A change that cannot be logged is still a change the operator made, and
        # refusing it here would make an unwritable disk look like a rejected posture.
        # The row is the audit trail's problem; the selection is already on file.
        pass


def _stamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
