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
