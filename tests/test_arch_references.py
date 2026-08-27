"""The class-A reference channel: what it judges, and what it refuses to judge.

Interfaces: thalamus.arch.references (census, reference_findings, render,
ReferencePolicy, ReferenceExemption).

Half of these are suppression tests, and that is the point. The channel's risk is not
that it misses a dangling name — it is that it reports a true sentence as a defect, or
that it silently swallows a real one. Both failures were live during the build and both
have a case here.
"""

from __future__ import annotations

import pytest

from thalamus.arch import references as refs


def _tree(root, files: dict[str, str]):
    for name, body in files.items():
        path = root / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return refs.ReferencePolicy(enabled=True, roots=("src",))


def test_a_path_the_tree_does_not_hold_is_a_finding(tmp_path):
    policy = _tree(tmp_path, {"a.py": "# see mod/other.py for the rest\n"})
    report = refs.census(tmp_path, policy)
    dangling = report.by_status(refs.DANGLING)
    assert [item.target for item in dangling] == ["mod/other.py"]
    assert len(refs.reference_findings(report)) == 1


def test_a_path_the_tree_holds_is_not(tmp_path):
    policy = _tree(tmp_path, {"a.py": "# see mod/here.py\n", "mod/here.py": "x = 1\n"})
    report = refs.census(tmp_path, policy)
    assert report.by_status(refs.DANGLING) == []
    assert refs.reference_findings(report) == []


def test_a_sentence_asserting_absence_is_not_a_finding(tmp_path):
    """The repo argues about what it does not contain, and those names must not resolve.

    Flagging one is bad; the compliant repair is worse, because the cheapest way to
    satisfy the checker is to delete the true statement.
    """
    policy = _tree(tmp_path, {"a.py": "# no mod/other.py exists anywhere in this tree\n"})
    report = refs.census(tmp_path, policy)
    assert report.by_status(refs.DANGLING) == []
    assert [item.target for item in report.by_status(refs.ASSERTED_ABSENT)] == ["mod/other.py"]
    assert refs.reference_findings(report) == []


def test_a_negation_inside_a_quotation_does_not_suppress(tmp_path):
    """Regression: a quoted rule containing "never" is not the sentence's own claim.

    This hid a live dangling citation during the build — the reference was real, the
    negation belonged to a quoted maxim, and the report showed nothing.
    """
    policy = _tree(
        tmp_path,
        {"a.py": '# mod/other.py established the shape: "n/a with a reason, never dropped"\n'},
    )
    report = refs.census(tmp_path, policy)
    assert [item.target for item in report.by_status(refs.DANGLING)] == ["mod/other.py"]


def test_a_previous_sentences_negation_does_not_suppress(tmp_path):
    """Regression: the line above ends a sentence, so its negation is not in scope.

    The first cut joined the previous prose line unconditionally and inherited whatever
    negation happened to be there, which is the same false suppression by another route.
    """
    policy = _tree(
        tmp_path,
        {"a.py": "# a reason is a first-class answer and not an escape hatch.\n"
                 "# mod/other.py established the shape.\n"},
    )
    report = refs.census(tmp_path, policy)
    assert [item.target for item in report.by_status(refs.DANGLING)] == ["mod/other.py"]


def test_a_genuine_line_wrap_does_suppress(tmp_path):
    """The other direction: prose wrapped mid-sentence, so the negation does govern.

    The line above does not end a sentence and the reference opens the line below —
    both signals of a wrap, and only both together.
    """
    policy = _tree(
        tmp_path,
        {"a.py": "# config/experts/ holds a manifest per expert and no\n"
                 "# mod/other.py, so the boundary has nowhere to declare itself\n"},
    )
    report = refs.census(tmp_path, policy)
    assert report.by_status(refs.DANGLING) == []
    assert [item.target for item in report.by_status(refs.ASSERTED_ABSENT)] == ["mod/other.py"]


def test_a_bare_data_filename_is_not_judged(tmp_path):
    """`hooks.json` is Cursor's and `pins.jsonl` is written at runtime under $HOME.

    A source file named without a directory is ours; a data file named without one is
    anybody's, and the tree's not holding it is not a defect.
    """
    policy = _tree(tmp_path, {"a.py": "# the harness writes `hooks.json` and `pins.jsonl`\n"})
    report = refs.census(tmp_path, policy)
    assert report.by_status(refs.DANGLING) == []


def test_a_path_inside_a_url_is_not_judged(tmp_path):
    policy = _tree(tmp_path, {"a.py": "# re-verified against cursor.com/docs/hooks.md today\n"})
    report = refs.census(tmp_path, policy)
    assert report.by_status(refs.DANGLING) == []


def test_a_dotted_name_is_recognised_and_never_judged(tmp_path):
    """Graph properties and ontology terms are real referents that are not definitions.

    The form cannot tell a missing symbol from a non-Python referent, so it resolves
    nothing and says so, rather than emitting a finding it cannot stand behind.
    """
    policy = _tree(tmp_path, {"a.py": "# `RETURNS.judged_terms` rides on the edge\n"})
    report = refs.census(tmp_path, policy)
    assert refs.reference_findings(report) == []
    assert [name for _, _, name in report.dotted] == ["RETURNS.judged_terms"]


def test_an_illustrative_placeholder_is_not_judged(tmp_path):
    policy = _tree(tmp_path, {"a.py": "# `.../src/cli.py` matches src/foo.py but not i.py\n"})
    report = refs.census(tmp_path, policy)
    assert all(item.target != "src/foo.py" for item in report.by_status(refs.DANGLING))


def test_a_runtime_string_is_not_prose(tmp_path):
    """An argparse help string citing a path is read by a user, not by a maintainer."""
    policy = _tree(tmp_path, {"a.py": 'parser.add_argument("--x", help="see mod/other.py")\n'})
    report = refs.census(tmp_path, policy)
    assert report.references == []


def test_the_report_names_what_it_could_not_consume(tmp_path):
    """Complement-shaped: a recognizer that lists only what it understood reads complete.

    The uncovered set is printed beside the covered one, always — never behind the flag.
    """
    policy = _tree(tmp_path, {"a.py": "# `some prose in backticks` and mod/other.py\n"})
    report = refs.census(tmp_path, policy)
    assert report.unconsumed
    assert "candidate(s) no form consumed" in refs.render(report)


def test_an_unreadable_file_is_a_finding_not_a_silence(tmp_path):
    policy = _tree(tmp_path, {"a.py": "# fine\n"})
    (tmp_path / "src" / "bad.py").write_bytes(b"\xff\xfe# \x00not utf-8\n")
    report = refs.census(tmp_path, policy)
    assert report.unreadable
    assert any(f.category == "understanding" for f in refs.reference_findings(report))


def test_an_exemption_needs_a_reason(tmp_path):
    with pytest.raises(ValueError, match="needs a reason"):
        refs.ReferencePolicy.from_block({"exemptions": [{"path": "src/a.py"}]})


def test_an_exempted_reference_is_not_a_finding_and_says_why(tmp_path):
    policy = _tree(tmp_path, {"a.py": "# see mod/other.py for the rest\n"})
    policy = refs.ReferencePolicy(
        enabled=True,
        roots=("src",),
        exemptions=(refs.ReferenceExemption(reason="moved to the companion repo",
                                            target="mod/other.py"),),
    )
    report = refs.census(tmp_path, policy)
    exempted = report.by_status(refs.EXEMPTED)
    assert [item.detail for item in exempted] == ["moved to the companion repo"]
    assert refs.reference_findings(report) == []


def test_absence_is_read_before_an_exemption(tmp_path):
    """A true sentence must never land on a list of tolerated wrongs."""
    policy = refs.ReferencePolicy(
        enabled=True,
        roots=("src",),
        exemptions=(refs.ReferenceExemption(reason="whatever", target="mod/other.py"),),
    )
    _tree(tmp_path, {"a.py": "# there is no mod/other.py in this tree\n"})
    report = refs.census(tmp_path, policy)
    assert [item.status for item in report.references] == [refs.ASSERTED_ABSENT]


def test_the_policy_digest_covers_the_block(tmp_path):
    base = refs.ReferencePolicy(enabled=True)
    assert base.digest() == refs.ReferencePolicy(enabled=True).digest()
    assert base.digest() != refs.ReferencePolicy(enabled=True, roots=("src", "tests")).digest()


def test_a_reference_whose_own_name_is_an_absence_word_still_reports(tmp_path):
    """Regression: `gone.py` carries an absence cue inside the token being judged.

    Found by a fixture that happened to be named that way. The reference's own text is
    removed before the sentence is read, or a module suppresses itself by being called
    something unlucky — and self-suppression is invisible, which is the direction this
    channel can least afford to fail in.
    """
    policy = _tree(tmp_path, {"a.py": "# see mod/gone.py for the rest\n"})
    report = refs.census(tmp_path, policy)
    assert [item.target for item in report.by_status(refs.DANGLING)] == ["mod/gone.py"]


def test_the_policy_round_trips_through_its_block():
    policy = refs.ReferencePolicy(
        enabled=True,
        exemptions=(refs.ReferenceExemption(reason="because", path="src/a.py"),),
    )
    assert refs.ReferencePolicy.from_block(policy.block()) == policy
