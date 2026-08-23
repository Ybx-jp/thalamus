"""Which CLI and model run an extraction pass (harness/extractor_policy.py).

Interfaces: `resolve`/`effective`/`select`/`describe`, and `agents.AgentCLI.models`,
the closed list the panel offers from. Infrastructure: tmp_path for the store and the
ledger, `monkeypatch` over `shutil.which` for availability — nothing here reads the
operator's real `~/.thalamus/extractor` or asks the real PATH.

Scope: the rules that make it safe to point a pass at a second vendor. Three are
load-bearing and are tested as behaviour rather than as return values. The first is that
an empty store extracts exactly as before this module existed — a settings surface that
changed what a pass does merely by existing would be a migration in disguise. The second
is that an unavailable CLI is refused at selection *and* dropped on read: the failure it
would otherwise cause happens inside the detached job SessionEnd forks, so it reaches a
log nobody opens rather than a person. The third is the split the module exists for —
ingestion is one model call per chunk and distillation is one per session, so a choice
about the expensive one must not be forced through a decision about the cheap one, and a
choice about the cheap one must still cover both until ingestion is set on its own.
"""

import json
from datetime import datetime, timezone

import pytest

from thalamus.harness import agents
from thalamus.harness import extractor_policy as ep

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    return tmp_path / "policy.json"


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "policy.jsonl"


@pytest.fixture
def all_installed(monkeypatch):
    """Every declared CLI on PATH, so availability is a variable and not the weather."""
    monkeypatch.setattr(agents.shutil, "which", lambda binary: f"/usr/bin/{binary}")


def pick(store, ledger, harness, model="", *, pass_="distill", **kw):
    return ep.select(harness, model, pass_=pass_, store=store, ledger=ledger,
                     now=kw.pop("now", NOW), **kw)


def distilled(store, source="claude", **kw):
    return ep.resolve(pass_="distill", source_harness=source, store=store, **kw)


def ingested(store, **kw):
    return ep.resolve(pass_="ingest", store=store, **kw)


class TestTheDeclaredModelLists:
    """The panel offers a closed list, so the list has to be one."""

    def test_every_cli_declares_models_and_its_default_is_among_them(self):
        for harness, cli in agents.AGENT_CLIS.items():
            assert cli.models, f"{harness} declares no models to choose between"
            assert cli.default_model in cli.models, (
                f"{harness} defaults to `{cli.default_model}`, which is not on the "
                f"list a surface would offer"
            )

    def test_cursor_does_not_resell_anthropic_models(self):
        """Routing a pass to Cursor to reach Claude is the opposite of the point.

        Cursor's live catalog carries ~40 entries, most of them other vendors' models.
        A panel offering those would let "extract somewhere other than Claude" select
        Claude, which is the one outcome the setting exists to avoid.
        """
        assert not [m for m in agents.cli_for("cursor").models if "claude" in m]


class TestNothingChangesUntilSomethingIsChosen:
    def test_an_empty_store_follows_the_session(self, store):
        got = distilled(store, "claude")
        assert (got.harness, got.model) == ("claude", agents.default_model("claude"))
        got = distilled(store, "cursor")
        assert (got.harness, got.model) == ("cursor", agents.default_model("cursor"))

    def test_an_empty_store_ingests_through_claude(self, store):
        """Ingestion has no session to follow, so its floor is what it did before."""
        got = ingested(store)
        assert (got.harness, got.model) == ("claude", agents.default_model("claude"))
        assert got.reason == "the default"

    def test_an_unreadable_store_follows_the_session(self, store):
        store.write_text("{ not json")
        assert distilled(store).harness == "claude"
        assert ingested(store).harness == "claude"

    def test_an_empty_store_describes_itself_as_deferring(self, store):
        for key in ep.PASS_KEYS:
            view = ep.describe(key, store=store)
            assert view["value"] == {"harness": "", "model": ""}
            assert view["unusable"] == ""


class TestChoosingAnExtractor:
    def test_a_chosen_harness_runs_every_harness_s_sessions(self, store, ledger, all_installed):
        pick(store, ledger, "codex")
        for source in agents.HARNESSES:
            got = distilled(store, source)
            assert got.harness == "codex"
            assert got.reason == "the distillation setting"

    def test_no_model_means_the_chosen_cli_s_own_default(self, store, ledger, all_installed):
        pick(store, ledger, "codex")
        assert distilled(store).model == agents.default_model("codex")

    def test_a_chosen_model_is_used(self, store, ledger, all_installed):
        pick(store, ledger, "codex", "gpt-5.4-mini")
        assert distilled(store).model == "gpt-5.4-mini"

    def test_choosing_the_default_again_is_a_real_choice(self, store, ledger, all_installed):
        pick(store, ledger, "codex")
        row = pick(store, ledger, ep.INHERIT)
        assert distilled(store).harness == "claude"
        # It has to land a ledger row like any other change: reverting is exactly the
        # act someone reading the ledger later is trying to date.
        assert row["from_harness"] == "codex" and row["to_harness"] == ""

    def test_the_flag_outranks_the_policy(self, store, ledger, all_installed):
        pick(store, ledger, "codex")
        got = distilled(store, harness="claude")
        assert got.harness == "claude"
        assert got.reason == "--extract-with"

    def test_the_ingest_flag_reports_its_own_name(self, store, ledger, all_installed):
        """`--extract-with` and `--harness` mean the same thing on two commands.

        The reason line is printed for a reader working out what produced a bad batch of
        claims, and naming the flag the command does not have sends him to the wrong help.
        """
        assert ingested(store, harness="codex").reason == "--harness"

    def test_an_explicit_model_outranks_the_policy_s(self, store, ledger, all_installed):
        pick(store, ledger, "codex", "gpt-5.4-mini")
        assert distilled(store, model="gpt-5.6-sol").model == "gpt-5.6-sol"


class TestTheTwoPassesAreTwoBudgets:
    """The split this module exists for: one model call per session, one per chunk."""

    def test_ingestion_follows_distillation_until_it_is_set(self, store, ledger, all_installed):
        pick(store, ledger, "codex", "gpt-5.4-mini")
        got = ingested(store)
        assert (got.harness, got.model) == ("codex", "gpt-5.4-mini")
        assert got.reason == "the distillation setting"

    def test_ingestion_can_be_moved_without_moving_distillation(
        self, store, ledger, all_installed
    ):
        """The whole ask: a paper is chunked, so an ingest is the spend worth moving,
        and moving it must not drag the SessionEnd pass along with it."""
        pick(store, ledger, "codex", pass_="ingest")
        assert ingested(store).harness == "codex"
        assert ingested(store).reason == "the ingestion setting"
        assert distilled(store, "claude").harness == "claude"
        assert distilled(store, "claude").reason == "the session's own harness"

    def test_distillation_can_be_moved_without_moving_ingestion(
        self, store, ledger, all_installed
    ):
        pick(store, ledger, "cursor", pass_="ingest")
        pick(store, ledger, "codex", pass_="distill")
        assert ingested(store).harness == "cursor"
        assert distilled(store).harness == "codex"

    def test_stepping_ingestion_back_to_deferring_returns_it_to_distillation(
        self, store, ledger, all_installed
    ):
        pick(store, ledger, "codex", pass_="distill")
        pick(store, ledger, "cursor", pass_="ingest")
        pick(store, ledger, ep.INHERIT, pass_="ingest")
        assert ingested(store).harness == "codex"

    def test_a_pass_this_build_does_not_have_is_a_refusal_not_a_crash(self, store):
        with pytest.raises(ep.UnknownPass):
            ep.describe("summarise", store=store)


class TestRefusals:
    def test_an_uninstalled_cli_is_refused(self, store, ledger, monkeypatch):
        monkeypatch.setattr(agents.shutil, "which", lambda binary: None)
        with pytest.raises(ep.ExtractorRefused) as exc:
            pick(store, ledger, "codex")
        assert "PATH" in str(exc.value)
        assert not store.exists()

    def test_a_model_the_cli_does_not_offer_is_refused(self, store, ledger, all_installed):
        with pytest.raises(ep.ExtractorRefused) as exc:
            pick(store, ledger, "codex", "gpt-4")
        # The refusal has to point at the escape hatch, or it reads as "this model is
        # unreachable" rather than "this panel does not carry it".
        assert "--model" in str(exc.value)

    def test_an_unknown_harness_is_refused(self, store, ledger, all_installed):
        with pytest.raises(ep.ExtractorRefused):
            pick(store, ledger, "gemini")

    def test_deferring_takes_no_model(self, store, ledger, all_installed):
        """There is no one CLI for the slug to belong to, so it cannot be honoured."""
        with pytest.raises(ep.ExtractorRefused):
            pick(store, ledger, ep.INHERIT, "sonnet")


class TestAnExtractorThatDisappears:
    """Refusing at selection is not enough: a box loses a CLI after the choice is made."""

    def test_it_is_dropped_on_read_rather_than_by_a_sweep(self, store, ledger, monkeypatch):
        monkeypatch.setattr(agents.shutil, "which", lambda binary: f"/usr/bin/{binary}")
        pick(store, ledger, "codex")
        monkeypatch.setattr(agents.shutil, "which",
                            lambda binary: None if binary == "codex" else f"/usr/bin/{binary}")
        got = distilled(store)
        assert got.harness == "claude", "a lost CLI must not stop memory accumulating"
        assert got.reason == "the session's own harness"

    def test_a_lost_ingest_cli_falls_through_to_distillation_not_to_nothing(
        self, store, ledger, monkeypatch
    ):
        """Dropping the unusable selection returns the pass to what it would do unset,
        which for ingestion is the distillation setting — not the `claude` floor."""
        monkeypatch.setattr(agents.shutil, "which", lambda binary: f"/usr/bin/{binary}")
        pick(store, ledger, "codex", pass_="distill")
        pick(store, ledger, "cursor", pass_="ingest")
        monkeypatch.setattr(agents.shutil, "which",
                            lambda binary: None if binary == "agent" else f"/usr/bin/{binary}")
        assert ingested(store).harness == "codex"

    def test_the_choice_is_kept_and_the_panel_says_why_it_is_not_running(
        self, store, ledger, monkeypatch
    ):
        monkeypatch.setattr(agents.shutil, "which", lambda binary: f"/usr/bin/{binary}")
        pick(store, ledger, "codex")
        monkeypatch.setattr(agents.shutil, "which",
                            lambda binary: None if binary == "codex" else f"/usr/bin/{binary}")
        view = ep.describe("distill", store=store)
        assert view["stored"]["harness"] == "codex"
        assert view["value"]["harness"] == ""
        assert "PATH" in view["unusable"]


class TestTheLedger:
    def test_every_change_lands_a_row(self, store, ledger, all_installed):
        pick(store, ledger, "codex")
        pick(store, ledger, "codex", "gpt-5.4-mini")
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        assert [(r["from_harness"], r["to_harness"], r["to_model"]) for r in rows] == [
            ("", "codex", ""), ("codex", "codex", "gpt-5.4-mini"),
        ]
        assert all(r["actor"] == "console" for r in rows)

    def test_a_row_names_the_pass_it_changed(self, store, ledger, all_installed):
        """One ledger holds both passes, and it is read after the fact to find out what
        extracted a given week's claims. A row that did not say which pass it moved
        would make the record unreadable exactly when it is being read."""
        pick(store, ledger, "codex", pass_="ingest")
        pick(store, ledger, "cursor", pass_="distill")
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        assert [r["pass"] for r in rows] == ["ingest", "distill"]

    def test_a_change_to_one_pass_leaves_the_other_alone_on_disk(
        self, store, ledger, all_installed
    ):
        pick(store, ledger, "codex", "gpt-5.4-mini", pass_="distill")
        pick(store, ledger, "cursor", pass_="ingest")
        held = json.loads(store.read_text())["passes"]
        assert held["distill"] == {"harness": "codex", "model": "gpt-5.4-mini"}
        assert held["ingest"] == {"harness": "cursor", "model": ""}

    def test_a_refused_change_lands_no_row(self, store, ledger, all_installed):
        with pytest.raises(ep.ExtractorRefused):
            pick(store, ledger, "codex", "gpt-4")
        assert not ledger.exists()


class TestWhatThePanelIsTold:
    def test_a_cli_that_does_not_price_its_run_says_so(self, store, all_installed):
        view = ep.describe("distill", store=store)
        by_value = {o["value"]: o for o in view["options"]}
        assert by_value["claude"]["drops"] == ""
        for harness in ("codex", "cursor"):
            # The saving is real and the measurement of it is what goes away. A panel
            # showing the first without the second sells a saving it cannot substantiate.
            assert "eval cost" in by_value[harness]["drops"]

    def test_an_uninstalled_cli_is_offered_and_marked_rather_than_hidden(
        self, store, monkeypatch
    ):
        monkeypatch.setattr(agents.shutil, "which",
                            lambda binary: None if binary == "codex" else f"/usr/bin/{binary}")
        by_value = {o["value"]: o for o in ep.describe("distill", store=store)["options"]}
        assert by_value["codex"]["available"] is False
        assert by_value["claude"]["available"] is True

    def test_every_harness_and_the_deferring_default_are_offered(self, store, all_installed):
        for key in ep.PASS_KEYS:
            values = [o["value"] for o in ep.describe(key, store=store)["options"]]
            assert values == [ep.INHERIT, *agents.HARNESSES]

    def test_each_pass_names_what_deferring_means_for_it(self, store, all_installed):
        """"follow the session" and "follow distillation" are the same stored value on
        two passes. A panel that could not tell them apart would offer the operator a
        blank where the answer is."""
        labels = {ep.describe(k, store=store)["options"][0]["label"] for k in ep.PASS_KEYS}
        assert labels == {"follow the session", "follow distillation"}

    def test_a_deferring_ingest_card_names_what_it_will_actually_run(
        self, store, ledger, all_installed
    ):
        """The label alone names a rule, not an outcome, and the outcome is the whole
        question — an operator weighing his allowance cannot act on "follow distillation"."""
        pick(store, ledger, "codex", "gpt-5.4-mini", pass_="distill")
        view = ep.describe("ingest", store=store)
        assert view["value"]["harness"] == ""
        assert view["resolved"]["harness"] == "codex"
        assert view["resolved"]["model"] == "gpt-5.4-mini"

    def test_a_deferring_distill_card_resolves_to_nothing_because_there_is_nothing(
        self, store, all_installed
    ):
        """No session has ended, so no CLI can be named — and naming one anyway would
        assert a fact about a run that has not happened."""
        assert ep.describe("distill", store=store)["resolved"] == {}
