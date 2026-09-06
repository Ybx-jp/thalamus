"""Run bounded expert work through the executor declared by its manifest.

This is deliberately a different surface from `pin` and `spawn`. Those create an
interactive session in one of the editor harnesses. A delegated expert can instead be
a served model with no TUI, hooks, tools, or transcript. Its manifest owns that routing
decision, and callers cannot override it.

A served model is also the one route here with a hard context ceiling, so this surface
owns the budget the ceiling implies: the prompt is priced against the executor's window
before anything is sent, and a delegation that does not fit is refused with the
arithmetic rather than handed over to be truncated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thalamus.contract.manifest import load_manifest
from thalamus.harness.extraction import (
    ExtractionRun,
    estimate_prompt_tokens,
    prompt_char_budget,
    run_extraction,
)


class DelegationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DelegationPlan:
    """What a delegation will cost its executor, before it is sent.

    Held as a value rather than checked inline so `--check` can report the same
    numbers the refusal would, without spending a model call to find them out.
    """

    scope: str
    harness: str
    prompt: str
    budget: int | None
    sizes: list[tuple[Path, int]]

    @property
    def chars(self) -> int:
        return len(self.prompt)

    @property
    def tokens(self) -> int:
        return estimate_prompt_tokens(self.prompt)

    @property
    def fits(self) -> bool:
        """True on an executor that declares no ceiling; there is nothing to fit."""
        return self.budget is None or self.chars <= self.budget

    def refusal(self) -> str:
        budget = self.budget or 0
        largest = ", ".join(
            f"{path.name} {size:,}"
            for path, size in sorted(self.sizes, key=lambda row: -row[1])
        )
        return (
            f"delegation to `{self.harness}` is {self.chars:,} chars (~{self.tokens:,} "
            f"tokens) against a {budget:,}-char budget — over by "
            f"{self.chars - budget:,}. The budget is this executor's context "
            f"window less the room an answer needs; a prompt past it is truncated by "
            f"the server, which reports nothing about having done so. Inputs by size: "
            f"{largest}. Split them and delegate each part."
        )


@dataclass(frozen=True)
class DelegationRun:
    output: Path
    harness: str
    model: str
    usage: ExtractionRun


def build_prompt(scope: str, instructions: str, inputs: list[tuple[Path, str]]) -> str:
    manifest = load_manifest(scope)
    sections = [
        f"You are the {manifest.name} expert (scope `{manifest.scope}`).",
        f"Domain: {manifest.domain}",
        "You have no filesystem or tools. Every allowed input is included below. "
        "Do not assume or request any material outside those inputs.",
        "# Instructions",
        instructions.strip(),
    ]
    for index, (path, content) in enumerate(inputs, start=1):
        sections.extend(
            (
                f"# Input {index}: {path}",
                f"<<<BEGIN INPUT {index}>>>",
                content,
                f"<<<END INPUT {index}>>>",
            )
        )
    return "\n\n".join(sections).rstrip() + "\n"


def plan(
    scope: str,
    *,
    instructions_path: Path,
    input_paths: list[Path],
) -> DelegationPlan:
    """Read the files, build the prompt, and price it against the executor's window."""
    manifest = load_manifest(scope)
    if not manifest.executor:
        raise DelegationError(
            f"expert `{scope}` declares no executor; use an interactive pinned "
            "session rather than inventing a route"
        )
    if not input_paths:
        raise DelegationError("delegation needs at least one --input")

    try:
        instructions = instructions_path.read_text(encoding="utf-8")
        inputs = [(path, path.read_text(encoding="utf-8")) for path in input_paths]
    except OSError as exc:
        raise DelegationError(str(exc)) from exc

    return DelegationPlan(
        scope=scope,
        harness=manifest.executor,
        prompt=build_prompt(scope, instructions, inputs),
        budget=prompt_char_budget(manifest.executor),
        sizes=[(instructions_path, len(instructions))]
        + [(path, len(content)) for path, content in inputs],
    )


def run(
    scope: str,
    *,
    instructions_path: Path,
    input_paths: list[Path],
    output_path: Path,
    timeout: int = 900,
) -> DelegationRun:
    prepared = plan(
        scope, instructions_path=instructions_path, input_paths=input_paths
    )
    # The control, ahead of the spend. The transport's own guards price the prompt
    # with the server's tokenizer and refuse a truncated or unanswerable one, but they
    # can only do it after the prompt has been built and a prefill has been paid for.
    if not prepared.fits:
        raise DelegationError(prepared.refusal())

    result = run_extraction(prepared.prompt, harness=prepared.harness, timeout=timeout)
    if not result.text.strip():
        raise DelegationError(f"`{prepared.harness}` returned an empty answer")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.write_text(result.text.rstrip() + "\n", encoding="utf-8")
    temporary.replace(output_path)

    from thalamus.harness.agents import default_model

    return DelegationRun(
        output=output_path,
        harness=prepared.harness,
        model=default_model(prepared.harness),
        usage=result,
    )
