"""The spoken-register transform, checked against the classes a listener acts on.

The gold cases are the six sentences homelab used to benchmark the engines, so
what these assert and what was actually listened to are the same sentences.
"""

from thalamus.console.speech import (
    TRUNCATION_TAIL,
    KIND_ACRONYM,
    KIND_HASH,
    KIND_IDENTIFIER,
    KIND_NUMBER,
    KIND_VERSION,
    protected_tokens,
    spoken_update,
    to_speakable,
)


def _spoken(raw: str) -> str:
    return to_speakable(raw)


class TestPathsAreDroppedNotSpelled:
    """A path identifies a file; it is not read out character by character."""

    def test_deep_path_becomes_parent_and_stem(self):
        assert _spoken("The handler lives in src/thalamus/console/server.py.") == (
            "The handler lives in console server."
        )

    def test_no_slash_is_ever_spoken(self):
        spoken = _spoken("Edit src/thalamus/console/static/app.js and static/sw.js now.")
        assert "slash" not in spoken
        assert "dot" not in spoken

    def test_bare_filename_loses_its_extension(self):
        assert "app" in _spoken("Rename it in app.js.")
        assert "js" not in _spoken("Rename it in app.js.").lower().split()

    def test_parent_directory_survives_to_disambiguate(self):
        # Many projects hold several server.py; the parent is what tells them apart.
        assert "console server" in _spoken("See src/thalamus/console/server.py")


class TestIdentifiersAreSplitNotSpelled:
    def test_snake_case_becomes_words(self):
        assert _spoken("Call consult_answer to close it.") == "Call consult answer to close it."

    def test_camel_case_becomes_words(self):
        assert "camel case" in _spoken("Rename camelCase in the same pass.")

    def test_constant_case_spells_its_short_caps_run(self):
        assert "poll M S" in _spoken("Rename POLL_MS in the client.")

    def test_dotted_call_becomes_words(self):
        assert "consultation assemble brief" in _spoken("Patch consultation._assemble_brief now.")


class TestAcronymsAreSpelled:
    def test_bare_acronym(self):
        assert "T T S" in _spoken("The TTS engine is warm.")

    def test_several_in_one_sentence(self):
        spoken = _spoken("The TTS engine speaks over the PWA and we measure RTF via MCP.")
        assert "T T S" in spoken
        assert "P W A" in spoken
        assert "R T F" in spoken
        assert "M C P" in spoken

    def test_plural_keeps_its_s(self):
        assert "P W As" in _spoken("Two PWAs are installed.")


class TestNumbersSurviveExactly:
    def test_counts_are_left_as_digits(self):
        spoken = _spoken("There are 17 citations across 4 sessions.")
        assert "17" in spoken
        assert "4" in spoken

    def test_decimal_is_not_mangled_into_a_version(self):
        assert "1.55" in _spoken("It took about 1.55 seconds.")

    def test_line_number_survives(self):
        assert "396" in _spoken("The handler is near line 396.")


class TestVersionsAndHashes:
    def test_version_is_spoken_digit_by_digit(self):
        assert "v zero point four point two" in _spoken("Bumped to v0.4.2 today.")

    def test_commit_hash_is_spelled(self):
        assert "E zero eight A zero nine A" in _spoken("Commit e08a09a landed.")

    def test_iso_date_becomes_a_month_and_ordinal(self):
        assert "August eleventh" in _spoken("Shipped on 2026-08-11.")

    def test_ordinary_hex_word_is_not_spelled(self):
        # No digit, so not a hash — "deface" must stay a word.
        assert "deface" in _spoken("Do not deface it.")


class TestScreenOnlyMaterialIsDropped:
    def test_fenced_block_is_not_spoken(self):
        raw = "Here is the fix:\n\n```python\nx = compute(1, 2, 3)\n```\n\nIt passes."
        spoken = _spoken(raw)
        assert "compute" not in spoken
        assert "It passes." in spoken

    def test_unterminated_fence_is_still_dropped(self):
        assert "secret" not in _spoken("Look:\n\n```\nsecret = 1\n")

    def test_markdown_emphasis_and_links_are_unwrapped(self):
        assert _spoken("This is **bold** and a [link](http://x.y).") == (
            "This is bold and a link."
        )

    def test_heading_and_bullet_markers_go(self):
        spoken = _spoken("## Findings\n\n- first thing\n- second thing")
        assert "#" not in spoken
        assert "-" not in spoken
        assert "First thing" in spoken

    def test_tool_narration_opening_is_cut(self):
        assert _spoken("I'll now run the tests.").startswith("Run the tests")
        assert _spoken("Okay, the suite is green.").startswith("The suite is green")


class TestProtectedTokenExtraction:
    def test_runs_on_the_raw_turn_and_finds_each_class(self):
        raw = (
            "Commit e08a09a bumped POLL_MS to v0.4.2 on 2026-08-11, "
            "with 17 citations and the TTS path."
        )
        kinds = {token.kind for token in protected_tokens(raw)}
        assert kinds >= {
            KIND_HASH,
            KIND_IDENTIFIER,
            KIND_VERSION,
            KIND_NUMBER,
            KIND_ACRONYM,
        }

    def test_tokens_inside_a_fence_are_not_protected(self):
        # Fenced code is never spoken, so protecting it would fail every utterance.
        raw = "Done.\n\n```\nTIMEOUT_MS = 9999\n```\n"
        assert not any(t.literal == "9999" for t in protected_tokens(raw))

    def test_a_date_is_not_also_harvested_as_bare_numbers(self):
        tokens = protected_tokens("Shipped on 2026-08-11.")
        assert not any(t.literal == "2026" for t in tokens)


class TestTheLengthBudget:
    def test_a_short_update_is_untouched(self):
        update = spoken_update("All 940 tests pass.")
        assert update.text == "All 940 tests pass."
        assert update.faithful

    def test_a_long_update_is_cut_at_a_sentence_and_says_so(self):
        raw = " ".join(f"Sentence number {n} says something." for n in range(1, 200))
        update = spoken_update(raw, budget=300)
        assert update.text.endswith("The rest is in the console.")
        # Cut at a sentence, not mid-phrase.
        body = update.text.replace(TRUNCATION_TAIL.strip(), "").strip()
        assert body.endswith(".")

    def test_trimming_is_not_reported_as_a_fidelity_failure(self):
        # The contract covers what was chosen to be said. A number dropped by a
        # deliberate cut is not the corruption the gate exists to catch, and
        # reporting it as one would withhold every long update.
        raw = "First fact is 11. " + " ".join(
            f"Filler sentence {n} carries no value." for n in range(60)
        ) + " Final fact is 99."
        update = spoken_update(raw, budget=200)
        assert update.faithful, [t.literal for t in update.missing]
        assert "99" not in update.text

    def test_what_survives_the_cut_is_still_protected(self):
        update = spoken_update("There are 17 citations. " + "Padding sentence. " * 100,
                               budget=120)
        assert "17" in update.text
        assert update.faithful

    def test_a_budget_landing_mid_number_does_not_split_it(self):
        raw = "The count is 12345678 and then some more words follow here."
        update = spoken_update(raw, budget=20)
        assert "1234" not in update.text or "12345678" in update.text


class TestTheContract:
    def test_a_clean_turn_is_faithful(self):
        raw = (
            "Commit e08a09a bumped the version to v0.4.2 on 2026-08-11. "
            "There are 17 citations across 4 sessions, about 1.55 seconds each. "
            "Call consult_answer in src/thalamus/console/server.py near line 396."
        )
        update = spoken_update(raw)
        assert update.faithful, [t.literal for t in update.missing]

    def test_every_gold_case_is_faithful(self):
        for raw in [
            "Call consult_answer with the ticket id to close the exchange.",
            "The handler lives in src/thalamus/console/server.py near line 396.",
            "Rename POLL_MS in app.js and camelCase in the same pass.",
            "The TTS engine speaks over the PWA and we measure RTF via MCP.",
            "Commit e08a09a bumped the version to v0.4.2 on 2026-08-11.",
            "There are 17 citations across 4 sessions, about 1.55 seconds each.",
        ]:
            update = spoken_update(raw)
            assert update.faithful, f"{raw!r} lost {[t.literal for t in update.missing]}"

    def test_a_dropped_number_is_caught(self):
        # The failure the contract exists for: plausible speech, wrong content.
        tokens = protected_tokens("There are 17 citations.")
        from thalamus.console.speech import verify_protected

        missing = verify_protected("There are some citations.", tokens)
        assert [t.literal for t in missing] == ["17"]

    def test_underscore_emphasis_does_not_weld_an_identifier(self):
        # Markdown emphasis and snake_case compete for the same character. Treating
        # `._assemble_brief` as emphasis yields "assemblebrief" — fluent audio
        # naming a function that does not exist, with nothing for the ear to catch.
        spoken = _spoken("Patch consultation._assemble_brief now.")
        assert "assemble brief" in spoken
        assert "assemblebrief" not in spoken

    def test_real_underscore_emphasis_still_unwraps(self):
        assert _spoken("That is _emphatic_ prose.") == "That is emphatic prose."

    def test_verification_ignores_punctuation_and_case(self):
        tokens = protected_tokens("Call consult_answer now.")
        from thalamus.console.speech import verify_protected

        assert not verify_protected("CONSULT ANSWER -- now!", tokens)
