"""Run bounded expert work through the executor declared by its manifest.

This is deliberately a different surface from `pin` and `spawn`. Those create an
interactive session in one of the editor harnesses. A delegated expert can instead be
a served model with no TUI, hooks, tools, or transcript. Its manifest owns that routing
decision, and callers cannot override it at the command line.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thalamus.contract.manifest import load_manifest
from thalamus.harness.extraction import ExtractionRun, run_extraction


class DelegationError(RuntimeError):
    pass


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


def run(
    scope: str,
    *,
    instructions_path: Path,
    input_paths: list[Path],
    output_path: Path,
    timeout: int = 900,
) -> DelegationRun:
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

    prompt = build_prompt(scope, instructions, inputs)
    result = run_extraction(prompt, harness=manifest.executor, timeout=timeout)
    if not result.text.strip():
        raise DelegationError(f"`{manifest.executor}` returned an empty answer")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.write_text(result.text.rstrip() + "\n", encoding="utf-8")
    temporary.replace(output_path)

    from thalamus.harness.agents import default_model

    return DelegationRun(
        output=output_path,
        harness=manifest.executor,
        model=default_model(manifest.executor),
        usage=result,
    )
