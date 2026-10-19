"""The surfaces this plugin adds to core: the eval loop's readers under `thalamus eval`
and the `thalamus pulse` dashboard.

Registered through core's hooks (`thalamus.plugins`). `register_commands` runs on every
`thalamus` invocation, so this module builds parsers and nothing else. It imports two
parser defaults from `profile` and `withholding`; the handlers in `commands.py` import
every other report only when its command runs.
"""

from __future__ import annotations

from pathlib import Path

from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.plugins import hookimpl
from thalamus.substrate.writer import DEFAULT_URL
from thalamus_measure import commands
from thalamus_measure.profile import DEFAULT_REPEAT as PROFILE_REPEAT
from thalamus_measure.withholding import DRAWS as WITHHOLD_DRAWS


@hookimpl
def register_commands(subparsers, groups) -> None:
    eval_sub = groups["eval"]

    eval_report_parser = eval_sub.add_parser(
        "report", help="Per-scope retrieval-utility numbers from landed traces"
    )
    eval_report_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_report_parser.add_argument(
        "--scope", default=MAIN_SCOPE, help="Scope to report on (default: main)"
    )
    eval_report_parser.add_argument(
        "--top", type=int, default=5, help="How many most-ignored nodes to list"
    )
    eval_report_parser.add_argument(
        "--since",
        default=None,
        help="Only count traces at or after this ISO date/datetime (UTC), e.g. 2026-07-18",
    )
    eval_report_parser.add_argument(
        "--until",
        default=None,
        help="Only count traces at or before this ISO date/datetime (UTC); a bare date "
        "covers the whole day",
    )
    eval_report_parser.set_defaults(plugin_run=commands.report)

    eval_uses_parser = eval_sub.add_parser(
        "uses",
        help="Attribution subgraphs: who cited what, whether it compounds, and what "
        "the served stamp can speak about",
    )
    eval_uses_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_uses_parser.add_argument(
        "--scope",
        default=None,
        help="Narrow to subgraphs rooted in this scope (default: every scope — an "
        "attribution subgraph may reach another scope's knowledge, and filtering by "
        "the target would hide exactly those edges)",
    )
    eval_uses_parser.add_argument(
        "--since",
        default=None,
        help="Only count sessions at or after this ISO date/datetime (UTC)",
    )
    eval_uses_parser.add_argument(
        "--until",
        default=None,
        help="Only count sessions at or before this ISO date/datetime (UTC); a bare "
        "date covers the whole day",
    )
    eval_uses_parser.set_defaults(plugin_run=commands.uses)

    eval_pins_parser = eval_sub.add_parser(
        "pins",
        help="Pin-quality routing signal: per-expert pinned vs consulted utility "
        "from priced traces (the pin or the expert — the data says which)",
    )
    eval_pins_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_pins_parser.add_argument(
        "--pins-file", type=Path, default=None, help="Pin ledger (default: ~/.thalamus/pins/pins.jsonl)"
    )
    eval_pins_parser.set_defaults(plugin_run=commands.pins)

    eval_gremlin_parser = eval_sub.add_parser(
        "gremlin",
        help="Gremlin fluency metrics: guard rescue rate, rejection classes, recipe reuse",
    )
    eval_gremlin_parser.add_argument(
        "--traces", type=Path, default=None, help="Trace tap dir (default: ~/.thalamus/traces)"
    )
    eval_gremlin_parser.add_argument(
        "--guards", type=Path, default=None, help="Guard event dir (default: ~/.thalamus/guards)"
    )
    eval_gremlin_parser.set_defaults(plugin_run=commands.gremlin)

    eval_recipes_parser = eval_sub.add_parser(
        "recipes",
        help="Smoke-run every stored gremlin recipe read-only (rolling freshness signal)",
    )
    eval_recipes_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_recipes_parser.add_argument(
        "--staged", action="store_true",
        help="Show queries the PostToolUse hook staged for RECIPES.md instead of "
             "smoke-running the store",
    )
    eval_recipes_parser.set_defaults(plugin_run=commands.recipes)

    eval_profile_parser = eval_sub.add_parser(
        "profile",
        help="Gremlin query cost: what each traversal shape costs in wall time, and "
        "where a single query spends it step by step",
    )
    eval_profile_parser.add_argument(
        "--profiles", type=Path, default=None,
        help="Span ledger directory (default: ~/.thalamus/profiles)",
    )
    eval_profile_parser.add_argument(
        "--top", type=int, default=10, help="How many costliest shapes to list"
    )
    eval_profile_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_profile_parser.add_argument(
        "--query",
        default="",
        help="Step-profile one read-only gremlin-lang traversal instead of reading the "
        "ledger. Server-side per-step metrics via TinkerPop's profile(); profiling "
        "impedes the traversal, so read the steps against each other.",
    )
    eval_profile_parser.add_argument(
        "--corpus",
        action="store_true",
        help="Step-profile every gremlin-lang recipe the skills store, slowest first",
    )
    eval_profile_parser.add_argument(
        "--repeat", type=int, default=PROFILE_REPEAT,
        help=f"Timed runs per query for --query/--corpus (default: {PROFILE_REPEAT})",
    )
    eval_profile_parser.set_defaults(plugin_run=commands.profile)

    eval_withholding_parser = eval_sub.add_parser(
        "withholding",
        help="The randomized-withholding ledger as an outcome: do withheld nodes come back?",
    )
    eval_withholding_parser.add_argument(
        "--url", default=DEFAULT_URL, help="Gremlin endpoint"
    )
    eval_withholding_parser.add_argument(
        "--scope", default="main",
        help="Scope to analyse (default: main, 80%% of the corpus). "
             "Pass '' for the pooled exploratory read across every scope.",
    )
    eval_withholding_parser.add_argument(
        "--draws", type=int, default=WITHHOLD_DRAWS,
        help=f"Permutation draws (default: {WITHHOLD_DRAWS}); the attainable "
             "two-sided p floor is 1/(draws+1)",
    )
    eval_withholding_parser.set_defaults(plugin_run=commands.withholding)

    # The live telemetry dashboard.
    pulse_parser = subparsers.add_parser(
        "pulse",
        help="Serve the live telemetry dashboard over the eval loop's measurements",
    )
    pulse_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    pulse_parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address (default: localhost)"
    )
    pulse_parser.add_argument(
        "--port", type=int, default=8379, help="Port (default: 8379; /pulse via tailscale serve)"
    )
    pulse_parser.set_defaults(plugin_run=commands.pulse)
