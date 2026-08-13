"""
Launch posture: the operator's stored choice of launch flags (harness/launch_policy.py,
harness/launcher.py's Capability/PolicyOption).

Interfaces: `select`/`effective`/`describe`, and `capability_argv`/`launch_argv` for
what a posture contributes to a launch. Infrastructure: tmp_path for the store and the
ledger, injected clocks — nothing here reads the operator's real `~/.thalamus/launch`.
Scope: the rules that make this surface safe rather than merely present. The
load-bearing ones are that a lapsed posture reverts *on read* rather than needing a
sweep to have run, and that the defaults produce exactly the argv the launcher produced
before this module existed — a settings surface that changed behaviour by existing
would be a migration in disguise.

The lifetime rule is asymmetric on purpose and is tested as such: a loosening may be
given one, a tightening may not. A posture reverting toward *more* permission on a
timer is the forgotten-setting failure with its sign flipped.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from thalamus.harness import launch_policy as lp
from thalamus.harness.launcher import (
    LAUNCH_SHAPES,
    PERMISSION_POSTURE,
    capability_argv,
    launch_argv,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    return tmp_path / "policy.json"


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "policy.jsonl"


def pick(store, ledger, harness, value, **kw):
    return lp.select(harness, PERMISSION_POSTURE, value, store=store, ledger=ledger,
                     now=kw.pop("now", NOW), **kw)


class TestDefaultsAreUnchanged:
    """The surface must not change what a launch does merely by existing."""

    def test_an_empty_store_launches_exactly_as_before(self, store):
        assert launch_argv("claude", "qe", persona="thalamus-qe", selections={}) == [
            "claude", "--agent", "thalamus-qe", "--permission-mode", "auto",
        ]
        assert launch_argv("cursor", "qe", selections={}) == [
            "env", "THALAMUS_SCOPE=qe", "agent", "--trust",
        ]

    def test_every_harness_declares_its_postures(self):
        """A harness with no capability would render as a card with no controls,
        which reads as "no posture" rather than "nothing to choose here"."""
        for harness, shape in LAUNCH_SHAPES.items():
            keys = [c.key for c in shape.capabilities]
            assert PERMISSION_POSTURE in keys, harness
            assert len(keys) == len(set(keys)), f"{harness} declares a key twice"

    def test_a_default_is_always_a_real_option(self):
        for shape in LAUNCH_SHAPES.values():
            for capability in shape.capabilities:
                assert capability.option(capability.default) is not None


class TestLifetimes:
    def test_a_loose_posture_may_be_left_until_it_is_changed(self, store, ledger):
        """Offered, not required: the panel is passed through often enough that the
        setting is re-decided in the normal course of work."""
        row = pick(store, ledger, "cursor", "force")
        assert row["direction"] == lp.WIDEN and row["expires_at"] is None
        far = NOW + timedelta(days=400)
        assert lp.effective("cursor", store=store, now=far)[PERMISSION_POSTURE] == "force"

    def test_a_lifetime_off_the_offered_list_is_refused(self, store, ledger):
        """The lifetimes are a closed list for the same reason the postures are: a
        duration nothing can check is a value the panel cannot promise to honour."""
        with pytest.raises(lp.PolicyRefused, match="not one of the offered"):
            pick(store, ledger, "cursor", "force", ttl_hours=999)

    def test_tightening_takes_no_lifetime(self, store, ledger):
        """A posture reverting toward more permission on a timer is the forgotten
        setting with its sign flipped, so it is refused rather than ignored."""
        with pytest.raises(lp.PolicyRefused, match="does not take a lifetime"):
            pick(store, ledger, "claude", "manual", ttl_hours=24)

    def test_a_posture_at_the_default_takes_no_lifetime(self, store, ledger):
        with pytest.raises(lp.PolicyRefused, match="does not take a lifetime"):
            pick(store, ledger, "claude", "auto", ttl_hours=24)

    def test_stepping_down_but_still_above_default_still_expires(self, store, ledger):
        """`auto-review` is a narrowing from `force` and still above Cursor's default.
        Judging by direction alone would park the box permanently above its default
        with nothing recording that anything was still elevated."""
        pick(store, ledger, "cursor", "force", ttl_hours=24)
        row = pick(store, ledger, "cursor", "auto-review", ttl_hours=24)
        assert row["direction"] == lp.NARROW
        assert row["expires_at"] is not None


class TestLapsing:
    def test_a_lapsed_posture_reverts_on_read(self, store, ledger):
        """On a box where the console has been shut for a week, the expiry that
        matters is the one the next launch enforces — so reverting is a property of
        reading, not of a sweep that may never have run."""
        pick(store, ledger, "cursor", "force", ttl_hours=24)
        assert lp.effective("cursor", store=store, now=NOW)[PERMISSION_POSTURE] == "force"
        assert capability_argv("cursor", lp.effective("cursor", store=store, now=NOW)) \
            == ["--force"]

        later = NOW + timedelta(hours=25)
        assert lp.effective("cursor", store=store, now=later) == {}
        assert capability_argv("cursor", lp.effective("cursor", store=store, now=later)) == []

    def test_the_lapsed_choice_is_still_shown(self, store, ledger):
        """The panel has to say a posture lapsed; silently showing the default would
        make a reverted setting indistinguishable from one never chosen."""
        pick(store, ledger, "cursor", "force", ttl_hours=24)
        cap = lp.describe("cursor", store=store, now=NOW + timedelta(hours=25))[0]
        assert cap["value"] == "manual" and cap["lapsed"] is True
        assert cap["expires_at"] is None, "a lapsed deadline is not a live countdown"

    def test_a_live_choice_reports_its_deadline(self, store, ledger):
        pick(store, ledger, "cursor", "force", ttl_hours=24)
        cap = lp.describe("cursor", store=store, now=NOW)[0]
        assert cap["value"] == "force" and cap["lapsed"] is False
        assert cap["expires_at"] == (NOW + timedelta(hours=24)).isoformat()
        assert cap["is_default"] is False


class TestTheStoreIsNotTrusted:
    def test_an_unknown_value_falls_back_to_the_default(self, store):
        """The store is a file a future release may have written differently. A stale
        entry has to launch at the default, not stop the roster from starting."""
        store.write_text(json.dumps(
            {"version": 1, "harnesses": {"cursor": {PERMISSION_POSTURE: {"value": "yolo"}}}}))
        assert lp.effective("cursor", store=store, now=NOW) == {}
        assert launch_argv("cursor", "qe", selections=lp.effective("cursor", store=store)) \
            == ["env", "THALAMUS_SCOPE=qe", "agent", "--trust"]

    def test_an_unrankable_value_does_not_read_as_the_strictest_rung(self, store, ledger):
        """Ranking an unknown value 0 would make any change away from it look like a
        widening from the bottom — and, worse, make a change *to* the default look
        like a narrowing that needs no lifetime."""
        capability = LAUNCH_SHAPES["cursor"].capabilities[0]
        assert capability.rank("not-a-posture") == capability.default_rank

    def test_a_corrupt_store_is_the_default_not_a_crash(self, store):
        store.write_text("{not json")
        assert lp.effective("cursor", store=store, now=NOW) == {}

    def test_an_unknown_harness_or_capability_is_refused(self, store, ledger):
        with pytest.raises(lp.PolicyRefused):
            lp.select("codex", PERMISSION_POSTURE, "force", store=store, ledger=ledger)
        with pytest.raises(lp.PolicyRefused):
            lp.select("cursor", "sandbox", "on", store=store, ledger=ledger)


class TestTheLedger:
    def test_every_change_lands_a_row_carrying_its_direction(self, store, ledger):
        """"When did this box become permissive" has to be a question with an answer;
        access auditing that records escalations is the whole point (arXiv 2503.23278)."""
        pick(store, ledger, "cursor", "force", ttl_hours=24)
        pick(store, ledger, "claude", "manual")
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        assert [(r["harness"], r["from"], r["to"], r["direction"]) for r in rows] == [
            ("cursor", "manual", "force", lp.WIDEN),
            ("claude", "auto", "manual", lp.NARROW),
        ]
        assert rows[0]["ttl_hours"] == 24 and rows[0]["expires_at"]
        assert rows[1]["ttl_hours"] is None and rows[1]["expires_at"] is None

    def test_an_unwritable_ledger_does_not_lose_the_selection(self, store, tmp_path):
        """The row is the audit trail's problem. Refusing the change here would make a
        full disk look like a rejected posture."""
        blocked = tmp_path / "afile" / "policy.jsonl"
        blocked.parent.write_text("not a directory")
        pick(store, blocked, "cursor", "force", ttl_hours=24)
        assert lp.effective("cursor", store=store, now=NOW)[PERMISSION_POSTURE] == "force"


class TestWhatThePanelIsToldToShow:
    def test_every_option_above_the_default_carries_its_cost(self):
        """An option list without `drops` is the capability-declaration failure this
        surface exists to avoid — a setting shown by what it enables and not by what
        it gives up ("unsafe defaults exploited", arXiv 2503.23278 §5.1.3)."""
        for harness in LAUNCH_SHAPES:
            for cap in lp.describe(harness):
                for option in cap["options"]:
                    if option["above_default"]:
                        assert option["drops"], f"{harness}/{option['value']}"

    def test_the_server_decides_what_counts_as_widening(self, store, ledger):
        """The client reads `widening` rather than comparing ranks itself, so the two
        cannot disagree about which taps need a lifetime."""
        cap = lp.describe("cursor", store=store, now=NOW)[0]
        assert {o["value"]: o["widening"] for o in cap["options"]} == {
            "manual": False, "auto-review": True, "force": True,
        }

    def test_claude_offers_no_rung_above_its_default(self):
        """`bypassPermissions` removes the policy checks measured to stop prompt
        injection, so it is a decision-log change and not a tap: the surface must not
        be able to express a posture the contract argues against."""
        values = [o["value"] for o in lp.describe("claude")[0]["options"]]
        assert "bypassPermissions" not in values
        cap = LAUNCH_SHAPES["claude"].capabilities[0]
        assert cap.rank(cap.default) == len(cap.options) - 1
