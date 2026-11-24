"""The plugins installed beside the console must load together and agree where they meet.

Thalamus is a core and four plugins that all arrive through one extension point
(`thalamus.plugins`): `console`, `ingest`, `measure` (pulse), `reflex`, plus `arch`. Each
is unit-tested alone, and CI's `installs-alone` job proves each *can* run without the
others. What neither proves is the opposite — that with all of them installed in one
interpreter they do not step on each other, and that the few places where one plugin
reads another's state still mean the same thing on both sides. Those places are the whole
of this case: they are where a change in one package breaks a sibling that nobody opened.

Everything runs as the real `thalamus` CLI or a fresh interpreter under the rig's HOME and
PATH (`_console_integ`), against a real console where one is needed.

**Case 1 — `console-extractor-setting-reaches-ingest-and-the-harness-sets-agree`.** The
console writes `~/.thalamus/extractor/policy.json`; `thalamus-ingest` reads it through the
core's `extractor_policy.resolve(pass_="ingest")`, and its `--harness` help says that is
what it does ("the console's ingestion setting, else its distillation setting"). Asserted
over real POSTs: with nothing set, ingest resolves to the floor (`claude`); after the
console sets *distillation* to codex, ingest resolves to it with the distillation setting
as the stated reason; after the console sets *ingestion* to claude, ingest resolves to that
while distillation keeps codex; setting ingestion back to "follow distillation" returns it
to codex. And the set of harnesses `thalamus ingest --harness`, `thalamus extract
--extract-with`, the core's `HARNESSES` and the console's option list offer is one set —
a harness added to one surface and not another is a choice the operator can make where it
will be refused or ignored.

**Case 2 — `plugins-coexist-load-clean-wire-hooks-and-report-no-drift`.** In one
interpreter with every plugin installed: no plugin reports a load or registration failure
on the real `thalamus --help` (a command name two plugins both claim is refused by argparse
and reported as exactly this); every command and `eval` subcommand the plugins add answers
`--help` with rc 0 and no stderr; every plugin hook script is accepted by core
(`Hook.refusal() == ""`), is executable, parses under `bash -n`, and is wired once (the same
`(event, script)` twice would run the hook twice); every capability row the plugins
contribute is a legal `(label, outcome, detail)` and none says `drift` or `malformed`; and
the console's and pulse's PWA manifests resolve to disjoint scopes with distinct ids, with
every icon the console's manifest names actually served — two installed PWAs that share a
scope replace each other on a phone.

**Controls.** Each assertion over "what the plugins add" is preceded by a count that must be
non-zero, derived by diffing the real CLI against the same CLI with the plugin manager
emptied — so "no command failed `--help`" cannot be true of an empty set, and a plugin that
stopped loading shrinks the set visibly instead of passing.

**Shown capable of going red** (copies under `QE_CONSOLE_SRC`, run 2026-11-24). Case 1:
filter `"local"` out of `extractor_policy_view()`'s options in a copy of `server.py` and
it reports `console options=['claude','codex','cursor']` against the other three
surfaces' four. Case 2: copy the console and reflex `src` trees into one directory,
`chmod -x` `thalamus_reflex/hooks/claude-code/reflex.sh`, and it names that script
(`executable=False`). A command-name collision (rename the console's `room` parser to
`ingest`) is not a red here: argparse then aborts the console's own registration, the rig
refuses to start and the case is MALFORMED — which is the right loudness for it, and why
the registration-failure assertion is on `thalamus --help` and not on the rig.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from urllib.parse import urljoin

from ..model import Case, FailureClass, Finding, Substrate, Tier
from . import _console_integ as C
from ._console_rig import REPO_ROOT

_SELF = "tests/qe/cases/console_integ_plugins.py"
_CMD = re.compile(r"^ {4}([a-z][a-z0-9-]*)\s{2,}\S", re.M)


def _f(summary, witness, site, cls=FailureClass.INVARIANT_FALSIFIED):
    return Finding(cls, summary, witness=witness, site=site)


def _resolve(rig, pass_, source="claude"):
    r = C.py(rig, "import json; from thalamus.harness import extractor_policy as p; "
                  f"x = p.resolve(pass_={pass_!r}, source_harness={source!r}); "
                  "print(json.dumps([x.harness, x.model, x.reason]))")
    if r.returncode != 0:
        return None, r.stderr[-300:]
    return json.loads(r.stdout), ""


def _choices(text: str) -> set[str]:
    m = re.search(r"\{([a-z,]+)\}", text)
    return set(m.group(1).split(",")) if m else set()


def run_extractor() -> Finding | None:
    site = "src/thalamus/harness/extractor_policy.py::resolve"
    with C.integ_rig() as rig:
        def post(pass_, harness, model=""):
            return rig.post("/api/extractor-policy",
                            {"pass": pass_, "harness": harness, "model": model})

        got, err = _resolve(rig, "ingest")
        if got is None or got[0] != "claude":
            return _f("with no setting, ingest does not resolve to the floor harness",
                      f"{got} {err}", site)
        if post("distill", "codex", "gpt-5.6-luna").status != 200:
            return _f("fixture: the console refused a legal distillation setting", "",
                      _SELF, FailureClass.COLLAPSED_SENTINEL)
        got, err = _resolve(rig, "ingest")
        if not got or got[:2] != ["codex", "gpt-5.6-luna"] or "distillation" not in got[2]:
            return _f("the console's distillation setting did not reach the ingest "
                      "resolution", f"resolved={got} {err}", site)
        if post("ingest", "claude", "sonnet").status != 200:
            return _f("fixture: the console refused a legal ingestion setting", "", _SELF,
                      FailureClass.COLLAPSED_SENTINEL)
        got, _ = _resolve(rig, "ingest")
        dist, _ = _resolve(rig, "distill", "cursor")
        if (not got or got[:2] != ["claude", "sonnet"] or "ingestion" not in got[2]
                or not dist or dist[:2] != ["codex", "gpt-5.6-luna"]):
            return _f("setting ingestion moved it wrongly, or moved distillation",
                      f"ingest={got} distill={dist}", site)
        if post("ingest", "", "").status != 200:
            return _f("fixture: the console refused 'follow distillation'", "", _SELF,
                      FailureClass.COLLAPSED_SENTINEL)
        got, _ = _resolve(rig, "ingest")
        if not got or got[:2] != ["codex", "gpt-5.6-luna"]:
            return _f("resetting ingestion to 'follow distillation' did not make ingest "
                      "follow distillation again", f"ingest={got}", site)

        # the harness sets
        sets = {}
        for label, args, pat in (("thalamus ingest --harness", ("ingest", "--help"),
                                  r"--harness \{[a-z,]+\}"),
                                 ("thalamus extract --extract-with", ("extract", "--help"),
                                  r"--extract-with \{[a-z,]+\}")):
            out = C.thalamus(rig, *args).stdout
            m = re.search(pat, out)
            sets[label] = _choices(m.group(0)) if m else set()
        core = C.py(rig, "from thalamus.harness import extractor_policy as p; "
                         "print(','.join(sorted(p.HARNESSES)))")
        sets["core HARNESSES"] = set(core.stdout.strip().split(",")) - {""}
        view = rig.get("/api/extractor-policy").json()["passes"]
        for p in view:
            sets[f"console options ({p['pass']})"] = {o["value"] for o in p["options"]} - {""}
        if not sets["core HARNESSES"] or any(not v for v in sets.values()):
            return _f("a harness set could not be read, so agreement proves nothing",
                      repr(sets), _SELF, FailureClass.COLLAPSED_SENTINEL)
        if len({frozenset(v) for v in sets.values()}) != 1:
            return _f("the extractor harness offered differs between surfaces",
                      "; ".join(f"{k}={sorted(v)}" for k, v in sets.items()), site)
        return None


_HOOKS = r'''
import json, os
from thalamus import plugins
P = plugins.load()
hooks = [(h.harness, h.event, str(h.script), h.refusal(), os.access(h.script, os.X_OK))
         for h in P.hooks()]
print(json.dumps({"eps": sorted(n for n, _ in P.manager.list_name_plugin()),
                  "failures": [f.report() for f in P.failures],
                  "hooks": hooks, "rows": P.capability_rows()}))
'''

_CORE_ONLY = r'''
import sys, pluggy
from thalamus import plugins
m = pluggy.PluginManager(plugins.GROUP)
m.add_hookspecs(plugins.Spec)
plugins._loaded = plugins.Plugins(m, [])
sys.argv = ["thalamus"] + sys.argv[1:]
from thalamus import cli
cli.main()
'''

_OUTCOMES = {"confirmed", "drift", "malformed", "unprobeable", "unavailable"}


def _core_only(rig, *args):
    return subprocess.run([sys.executable, "-c", _CORE_ONLY, *args],
                          env=C.child_env(rig), capture_output=True, text=True,
                          cwd=str(rig.root), timeout=60)


def run_coexist() -> Finding | None:
    with C.integ_rig() as rig:
        full = C.thalamus(rig, "--help")
        if full.returncode != 0 or "failed to" in full.stderr:
            return _f("thalamus --help with every plugin installed reports a plugin "
                      "failure", f"rc={full.returncode} stderr={full.stderr[-400:]!r}",
                      "src/thalamus/plugins.py::Plugins.register_commands")
        base = _core_only(rig, "--help")
        added = sorted(set(_CMD.findall(full.stdout)) - set(_CMD.findall(base.stdout)))
        if base.returncode != 0 or len(added) < 4:
            return _f("fixture: the plugin-added command set could not be derived",
                      f"core-only rc={base.returncode} {base.stderr[-200:]!r}; added={added}",
                      _SELF, FailureClass.COLLAPSED_SENTINEL)
        eval_full = C.thalamus(rig, "eval", "--help")
        eval_base = _core_only(rig, "eval", "--help")
        added_eval = sorted(set(_CMD.findall(eval_full.stdout))
                            - set(_CMD.findall(eval_base.stdout)))
        if not added_eval:
            return _f("fixture: no plugin adds an `eval` subcommand to the CLI",
                      eval_full.stdout[-300:], _SELF, FailureClass.COLLAPSED_SENTINEL)
        for argv in [(c, "--help") for c in added] + [("eval", c, "--help")
                                                      for c in added_eval]:
            r = C.thalamus(rig, *argv)
            if r.returncode != 0 or r.stderr.strip() or not r.stdout.strip():
                return _f("a plugin-added command does not answer --help cleanly",
                          f"thalamus {' '.join(argv)}: rc={r.returncode} "
                          f"stderr={r.stderr[-300:]!r}", "src/thalamus/plugins.py")

        p = C.py(rig, _HOOKS)
        if p.returncode != 0:
            return _f("fixture: the plugin inspection interpreter failed",
                      p.stderr[-400:], _SELF, FailureClass.COLLAPSED_SENTINEL)
        info = json.loads(p.stdout)
        if info["failures"]:
            return _f("a plugin failed when loaded beside the others",
                      "; ".join(info["failures"]), "src/thalamus/plugins.py")
        if sorted(info["eps"]) != ["arch", "console", "ingest", "measure", "reflex"]:
            return _f("fixture: not every plugin is installed in this interpreter",
                      f"loaded={info['eps']}", _SELF, FailureClass.COLLAPSED_SENTINEL)
        if not info["hooks"]:
            return _f("fixture: no plugin hook was seen, so hook wiring is unexamined",
                      "hooks=[]", _SELF, FailureClass.COLLAPSED_SENTINEL)
        seen = set()
        for harness, event, script, refusal, executable in info["hooks"]:
            key = (harness, event, script)
            if refusal or not executable:
                return _f("a plugin hook that `thalamus init` would wire is refused or "
                          "not executable",
                          f"{event} {script}: refusal={refusal!r} executable={executable}",
                          script)
            if key in seen:
                return _f("one hook is wired twice, so it would run twice per event",
                          f"{event} {script}", "src/thalamus/plugins.py::Plugins.hooks")
            seen.add(key)
            syntax = subprocess.run(["bash", "-n", script], capture_output=True, text=True)
            if syntax.returncode != 0:
                return _f("a plugin hook script does not parse", f"{script}: "
                          f"{syntax.stderr[-300:]!r}", script)
        labels = set()
        for label, outcome, detail in info["rows"]:
            if outcome not in _OUTCOMES or outcome in ("drift", "malformed") or label in labels:
                return _f("a plugin capability row is illegal, duplicated, or reports "
                          "drift", f"({label!r}, {outcome!r}, {detail!r})",
                          "src/thalamus/plugins.py::Plugins.capability_rows")
            labels.add(label)
        if not labels:
            return _f("fixture: no capability rows reached the report", "rows=[]", _SELF,
                      FailureClass.COLLAPSED_SENTINEL)

        # two PWAs behind one proxy
        console_dir = REPO_ROOT / "packages" / "thalamus-console" / "src" / \
            "thalamus_console" / "static"
        pulse_dir = REPO_ROOT / "packages" / "thalamus-measure" / "src" / \
            "thalamus_measure" / "pulse" / "static"
        mounts = {"console": ("/console/", console_dir), "pulse": ("/pulse/", pulse_dir)}
        scopes, ids = {}, {}
        for name, (mount, directory) in mounts.items():
            m = json.loads((directory / "manifest.webmanifest").read_text())
            scopes[name] = urljoin(mount, m.get("scope", "./"))
            ids[name] = urljoin(mount, m.get("id", m.get("start_url", "./")))
            if not scopes[name].endswith("/"):
                scopes[name] += "/"
        if (scopes["console"].startswith(scopes["pulse"])
                or scopes["pulse"].startswith(scopes["console"])
                or ids["console"] == ids["pulse"]):
            return _f("the console's and pulse's installable-app manifests overlap — "
                      "installing one replaces the other", f"scopes={scopes} ids={ids}",
                      "packages/thalamus-measure/src/thalamus_measure/pulse/static/"
                      "manifest.webmanifest")
        manifest = json.loads((console_dir / "manifest.webmanifest").read_text())
        for icon in manifest["icons"]:
            r = rig.get("/" + icon["src"])
            if r.status != 200 or not r.headers.get("Content-Type", "").startswith("image/"):
                return _f("an icon the console's manifest names is not served",
                          f"/{icon['src']}: {r.status} {r.headers.get('Content-Type')}",
                          "packages/thalamus-console/src/thalamus_console/server.py::STATIC")
        return None


_SUB = (Substrate.NEEDS_TMUX,)
_CLS = (FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL)

EXTRACTOR = Case(
    name="console-extractor-setting-reaches-ingest-and-the-harness-sets-agree",
    tier=Tier.FAST, substrate=_SUB, classes=_CLS,
    summary="what the console writes for distillation and ingestion is what the ingest "
            "plugin resolves, and every surface offers the same extractor harnesses",
    run=run_extractor,
)
COEXIST = Case(
    name="plugins-coexist-load-clean-wire-hooks-and-report-no-drift",
    tier=Tier.FAST, substrate=_SUB, classes=_CLS,
    summary="with every plugin installed none fails to load, every added command and hook "
            "is well-formed and wired once, no capability row reports drift, and the "
            "console and pulse manifests do not overlap",
    run=run_coexist,
)

CASES = (EXTRACTOR, COEXIST)
