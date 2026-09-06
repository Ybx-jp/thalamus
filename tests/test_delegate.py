"""Executor-bound experts route through their manifest, never the caller."""

import pytest

from thalamus.contract.manifest import ExpertManifest
from thalamus.harness import delegate
from thalamus.harness.extraction import ExtractionRun


def manifest(executor: str | None = "local") -> ExpertManifest:
    return ExpertManifest(
        scope="ghoul",
        name="Constrained reader",
        domain="Reading under a hard context budget.",
        executor=executor,
    )


def test_build_prompt_embeds_only_declared_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(delegate, "load_manifest", lambda scope: manifest())
    source = tmp_path / "slice.md"

    prompt = delegate.build_prompt(
        "ghoul",
        "Return claims only.",
        [(source, "the bounded corpus")],
    )

    assert "Constrained reader" in prompt
    assert "Return claims only." in prompt
    assert str(source) in prompt
    assert "the bounded corpus" in prompt
    assert "no filesystem or tools" in prompt


def test_run_uses_manifest_executor_and_writes_atomically(monkeypatch, tmp_path):
    routed: dict[str, object] = {}
    monkeypatch.setattr(delegate, "load_manifest", lambda scope: manifest())

    def fake_run(prompt, *, harness, timeout):
        routed.update(prompt=prompt, harness=harness, timeout=timeout)
        return ExtractionRun(text="answer", input_tokens=12, output_tokens=3)

    monkeypatch.setattr(delegate, "run_extraction", fake_run)
    instructions = tmp_path / "instructions.md"
    source = tmp_path / "slice.md"
    output = tmp_path / "nested" / "answer.md"
    instructions.write_text("Do the bounded task.")
    source.write_text("Only this.")

    result = delegate.run(
        "ghoul",
        instructions_path=instructions,
        input_paths=[source],
        output_path=output,
        timeout=41,
    )

    assert routed["harness"] == "local"
    assert routed["timeout"] == 41
    assert "Only this." in str(routed["prompt"])
    assert output.read_text() == "answer\n"
    assert not (output.parent / ".answer.md.tmp").exists()
    assert result.harness == "local"


def test_run_refuses_a_scope_without_an_executor(monkeypatch, tmp_path):
    monkeypatch.setattr(delegate, "load_manifest", lambda scope: manifest(None))
    instructions = tmp_path / "instructions.md"
    source = tmp_path / "slice.md"
    instructions.write_text("instructions")
    source.write_text("source")

    with pytest.raises(delegate.DelegationError, match="declares no executor"):
        delegate.run(
            "ghoul",
            instructions_path=instructions,
            input_paths=[source],
            output_path=tmp_path / "answer.md",
        )


def test_run_refuses_no_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(delegate, "load_manifest", lambda scope: manifest())
    instructions = tmp_path / "instructions.md"
    instructions.write_text("instructions")

    with pytest.raises(delegate.DelegationError, match="at least one --input"):
        delegate.run(
            "ghoul",
            instructions_path=instructions,
            input_paths=[],
            output_path=tmp_path / "answer.md",
        )


def test_a_prompt_past_the_executor_window_is_refused_before_the_call(monkeypatch, tmp_path):
    """The control, ahead of the spend.

    The transport prices the prompt with the server's own tokenizer and refuses a
    truncated one, but only after the prompt has been built and a prefill paid for.
    A delegation that cannot fit is knowable from the file sizes alone.
    """
    monkeypatch.setattr(delegate, "load_manifest", lambda scope: manifest())

    def refuse(*a, **k):
        raise AssertionError("an over-budget delegation must not reach the executor")

    monkeypatch.setattr(delegate, "run_extraction", refuse)
    budget = delegate.prompt_char_budget("local")
    instructions = tmp_path / "instructions.md"
    source = tmp_path / "slice.md"
    instructions.write_text("Enumerate every claim.")
    source.write_text("x" * (budget + 1))

    with pytest.raises(delegate.DelegationError, match="over by") as err:
        delegate.run(
            "ghoul",
            instructions_path=instructions,
            input_paths=[source],
            output_path=tmp_path / "answer.md",
        )
    # Which file to cut, not just that something has to be.
    assert "slice.md" in str(err.value)


def test_a_plan_prices_a_delegation_without_spending_anything(monkeypatch, tmp_path):
    """What `--check` reports. No model call, so it costs a read of the inputs."""
    monkeypatch.setattr(delegate, "load_manifest", lambda scope: manifest())
    instructions = tmp_path / "instructions.md"
    source = tmp_path / "slice.md"
    instructions.write_text("Enumerate every claim.")
    source.write_text("a bounded corpus")

    prepared = delegate.plan(
        "ghoul", instructions_path=instructions, input_paths=[source]
    )

    assert prepared.fits
    assert prepared.chars == len(prepared.prompt)
    assert prepared.tokens < prepared.chars
    assert prepared.budget == delegate.prompt_char_budget("local")
    assert dict((path.name, size) for path, size in prepared.sizes) == {
        "instructions.md": len("Enumerate every claim."),
        "slice.md": len("a bounded corpus"),
    }


def test_an_executor_with_no_declared_ceiling_has_nothing_to_fit(monkeypatch, tmp_path):
    """A frontier row declares no `context_window`, and that is not a budget of zero."""
    monkeypatch.setattr(
        delegate, "load_manifest", lambda scope: manifest(executor="claude")
    )
    instructions = tmp_path / "instructions.md"
    source = tmp_path / "slice.md"
    instructions.write_text("Enumerate every claim.")
    source.write_text("x" * 500_000)

    prepared = delegate.plan(
        "ghoul", instructions_path=instructions, input_paths=[source]
    )

    assert prepared.budget is None
    assert prepared.fits
