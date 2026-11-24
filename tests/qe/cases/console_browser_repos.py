"""The repos view, judged against the design board before it is built.

Written from the Penpot file *Thalamus console — living design space*
(`_console_spec.PENPOT_FILE`), page 1, frames 01–59 with the index at `00a` and the
redlines at `08`. Nothing of the view is on master, so every case declares
`CONSOLE_UNBUILT_REPOS` and SKIPS until `_console_spec` sees a served route or page; the
oracle exists first so the view is built against it, not fitted to it afterwards.

**Locating.** By accessible role and the board's own words — `get_by_role("button",
name=/repos/i)` for frame 01's "REPOS ❯" entry control, the repo's name for its row,
`/commit/i`, `/push/i` for the sheets' controls — never by a class a builder might pick.
A step that cannot find its control returns a collapsed sentinel naming the page text,
so a rename reads as "the instrument cannot reach it", not as a pass.

**The four rules, each from the board's own text:**

1. `commit-gate` — index note: *"A disabled control that does nothing — the commit
   primary at zero staged, the push primary before the gate — has no target, because
   doing nothing is its correct behaviour."* At zero staged (frame 10/11) the commit
   primary is disabled **and a tap on it sends no request and makes no commit**; with a
   file staged outside the UI (`git add`) the same control is enabled (the control that
   "disabled" is a state and not the control's permanent look).
2. `no-force-push` — index note: *"force-push absent rather than gated."* Neither the
   push sheet on a feature branch (frame 17) nor on the protected `master` (frame 06)
   offers, names or describes a force push anywhere on the page. Control: the sheet
   is open (a push control is present), so an empty search is over a real page.
3. `unanswerable-count` — redlines: *"unanswerable count: — plus a sentence. never 0.
   (git exits 128 with no upstream.)"* The rig's `alpha` has no upstream. Its row shows
   `—` and a sentence, and shows no `0` as an ahead/behind count. Control: `beta` has an
   upstream and one unpushed commit; its row shows the count `1`.
4. `redlines` — row min-height 60 px; secondary control target 44×44 px; *"success
   colour: forbidden — no --ok, no green, no check glyph, no 'clean' badge"*. Measured on
   the rendered DOM (bounding boxes, computed colours), over a view with a dirty repo and
   a clean one. Controls: the colour scanner flags an injected green element and the
   glyph scanner an injected `✓`, so "none found" is over a scanner that can see; and a
   floor of rows/targets measured.
"""

from __future__ import annotations

import os
import re
import subprocess
import time

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_browser import browser, collapsed, finding, wait_text
from ._console_rig import console_rig

_ENV_KEYS = ("PATH", "LANG")


def _git(rig, repo, *args: str) -> str:
    env = {k: os.environ[k] for k in _ENV_KEYS if k in os.environ}
    env.update(HOME=str(rig.home), GIT_CONFIG_NOSYSTEM="1")
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=qe", "-c",
                        "user.email=qe@invalid", *args], env=env, capture_output=True,
                       text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"git {args} in {repo}: {r.stderr}")
    return r.stdout


def _seed(rig) -> None:
    """alpha: dirty, no upstream, nothing staged. beta: clean, upstream, one unpushed."""
    alpha, beta = rig.repos[0], rig.repos[1]
    (alpha / "README.md").write_text("# alpha\nunstaged edit\n")
    remote = rig.root / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(remote)], check=True,
                   capture_output=True)
    _git(rig, beta, "remote", "add", "origin", str(remote))
    _git(rig, beta, "push", "-q", "-u", "origin", "master")
    (beta / "ahead.txt").write_text("one unpushed commit\n")
    _git(rig, beta, "add", "ahead.txt")
    _git(rig, beta, "commit", "-q", "-m", "ahead of upstream")


def _enter(page, base: str) -> Finding | None:
    """Roster -> the repos list (frame 01 -> 02)."""
    page.goto(base + "/")
    entry = page.get_by_role("button", name=re.compile(r"repos", re.I))
    if not entry.count():
        return collapsed("the roster has no button named for REPOS (frame 01), so the "
                         "repos view cannot be entered",
                         f"roster text={page.inner_text('body')[:240]!r}")
    entry.first.click()
    if not wait_text(page, "alpha", 8):
        return collapsed("the repos list did not show the rig's repo `alpha` (frame 02)",
                         f"text={page.inner_text('body')[:300]!r}")
    return None


def _open_repo(page, name: str) -> Finding | None:
    row = page.get_by_role("button", name=re.compile(re.escape(name)))
    if not row.count():
        return collapsed(f"no control named for the repo {name!r} in the repos list",
                         f"text={page.inner_text('body')[:300]!r}")
    row.first.click()
    time.sleep(0.5)
    return None


def _button(page, pattern: str):
    return page.get_by_role("button", name=re.compile(pattern, re.I))


def run_commit_gate() -> Finding | None:
    with console_rig() as rig:
        _seed(rig)
        alpha = rig.repos[0]
        with browser(rig.base) as (page, _w):
            posts: list[str] = []
            page.on("request", lambda r: r.method == "POST" and posts.append(r.url))
            for step in (lambda: _enter(page, rig.base), lambda: _open_repo(page, "alpha")):
                r = step()
                if r:
                    return r
            commit = _button(page, r"^commit\b|commit\.\.\.|^commit$")
            if not commit.count():
                return collapsed("no commit control on the opened repo (frames 10/11)",
                                 f"text={page.inner_text('body')[:300]!r}")
            commit.first.click()
            time.sleep(0.5)
            primary = _button(page, r"^commit")
            if not primary.count():
                return collapsed("the commit sheet shows no primary commit control",
                                 f"text={page.inner_text('body')[:300]!r}")
            btn = primary.last
            before = _git(rig, alpha, "rev-list", "--count", "HEAD").strip()
            disabled = btn.is_disabled() or btn.get_attribute("aria-disabled") == "true"
            if not disabled:
                return finding(
                    FailureClass.FAILED_OPEN,
                    "the commit primary is enabled with nothing staged (frame 10)",
                    f"staged files=0; button={btn.evaluate('e => e.outerHTML')[:200]}")
            posts.clear()
            btn.dispatch_event("click")
            time.sleep(0.8)
            after = _git(rig, alpha, "rev-list", "--count", "HEAD").strip()
            if posts or after != before:
                return finding(
                    FailureClass.FAILED_OPEN,
                    "tapping the disabled commit primary at zero staged did something "
                    "(the board: doing nothing is its correct behaviour)",
                    f"POSTs after tap={posts}; commits {before} -> {after}")
            # Control: staged outside the UI, the same sheet's primary becomes enabled.
            _git(rig, alpha, "add", "README.md")
            page.reload()
            for step in (lambda: _enter(page, rig.base), lambda: _open_repo(page, "alpha")):
                r = step()
                if r:
                    return r
            _button(page, r"^commit").first.click()
            time.sleep(0.5)
            btn2 = _button(page, r"^commit").last
            if btn2.is_disabled() or btn2.get_attribute("aria-disabled") == "true":
                return collapsed("with a file staged the commit primary is still "
                                 "disabled, so 'disabled at zero' is not shown to be "
                                 "a state of the staged count",
                                 f"button={btn2.evaluate('e => e.outerHTML')[:200]}")
    return None


def run_no_force_push() -> Finding | None:
    with console_rig() as rig:
        _seed(rig)
        beta = rig.repos[1]
        with browser(rig.base) as (page, _w):
            for branch in ("feature", "master"):
                _git(rig, beta, "checkout", "-q", "-B" if branch == "feature" else "master",
                     *(["feature"] if branch == "feature" else []))
                page.goto(rig.base + "/")
                r = _enter(page, rig.base) or _open_repo(page, "beta")
                if r:
                    return r
                push = _button(page, r"push")
                if not push.count():
                    return collapsed(f"no push control on beta@{branch} (frames 06/17)",
                                     f"text={page.inner_text('body')[:300]!r}")
                push.first.click()
                time.sleep(0.5)
                text = page.inner_text("body")
                html = page.content()
                if not _button(page, r"push").count():
                    return collapsed("the push sheet is not open, so an empty search for "
                                     "'force' is over the wrong page", f"text={text[:300]!r}")
                if re.search(r"force|--force|-f\b", text, re.I) \
                        or re.search(r"force", html, re.I):
                    return finding(
                        FailureClass.FAILED_OPEN,
                        "the push sheet names a force push (the board: absent rather "
                        "than gated)",
                        f"beta on {branch}: matches="
                        f"{re.findall(r'.{0,40}force.{0,40}', text, re.I)[:3]}")
    return None


def run_unanswerable_count() -> Finding | None:
    with console_rig() as rig:
        _seed(rig)
        with browser(rig.base) as (page, _w):
            r = _enter(page, rig.base)
            if r:
                return r
            rows = {name: page.get_by_role("button", name=re.compile(name))
                    for name in ("alpha", "beta")}
            texts = {n: (loc.first.inner_text() if loc.count() else "")
                     for n, loc in rows.items()}
            if not texts["beta"]:
                return collapsed("no row for beta", f"text={page.inner_text('body')[:300]!r}")
            if not re.search(r"\b1\b", texts["beta"]):
                return collapsed("beta's row does not show its one unpushed commit, so "
                                 "the control that counts are rendered at all is absent",
                                 f"beta row={texts['beta']!r}")
            a = texts["alpha"]
            bad = []
            if "—" not in a:
                bad.append("no `—` for the unanswerable count")
            if re.search(r"(ahead|behind)\W{0,3}0\b|\b0\W{0,3}(ahead|behind)|[↑↓⇡⇣]\s*0\b",
                         a, re.I):
                bad.append("a 0 is shown for a count git cannot answer (exit 128)")
            sentence = [ln for ln in a.splitlines() if len(ln.split()) >= 4]
            if not sentence:
                bad.append("no sentence beside the dash")
            if bad:
                return finding(FailureClass.COLLAPSED_SENTINEL,
                               "the unanswerable ahead/behind count is not rendered as "
                               "`—` plus a sentence",
                               f"alpha (no upstream) row={a!r}: " + "; ".join(bad))
    return None


_MEASURE = """() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const green = (c) => {
    const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?/);
    if (!m) return false;
    const [r, g, b, a] = [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]];
    return a > 0 && g > r + 30 && g > b + 30;
  };
  const out = {rows: [], targets: [], green: [], glyph: []};
  const rows = document.querySelectorAll('[role="button"], a, li, [role="listitem"], button');
  for (const e of document.querySelectorAll('button, [role="button"], a[href]')) {
    if (!vis(e)) continue;
    const r = e.getBoundingClientRect();
    out.targets.push({name: (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 30),
                      w: Math.round(r.width), h: Math.round(r.height),
                      big: r.height >= 40 && r.width > 200});
  }
  for (const e of document.querySelectorAll('body *')) {
    if (!vis(e)) continue;
    const cs = getComputedStyle(e);
    for (const p of ['color', 'backgroundColor', 'borderTopColor', 'fill', 'stroke'])
      if (green(cs[p]) && !(p === 'borderTopColor' && cs.borderTopWidth === '0px'))
        out.green.push(e.tagName + ' ' + p + '=' + cs[p]);
    if (e.children.length === 0 && /[✓✔☑]/.test(e.textContent)) out.glyph.push(e.textContent.trim().slice(0, 30));
  }
  out.text = document.body.innerText;
  return out;
}"""


def run_redlines() -> Finding | None:
    with console_rig() as rig:
        _seed(rig)
        with browser(rig.base) as (page, _w):
            r = _enter(page, rig.base)
            if r:
                return r
            time.sleep(0.5)
            m = page.evaluate(_MEASURE)
            # Controls: the scanners can see what they look for.
            page.evaluate("""() => { const d = document.createElement('div');
              d.id = '__qe_probe'; d.style.cssText = 'color:rgb(40,200,60);width:10px;height:10px';
              d.textContent = '✓'; document.body.appendChild(d); }""")
            probe = page.evaluate(_MEASURE)
            page.evaluate("document.getElementById('__qe_probe').remove()")
            if not (any("color=rgb(40, 200, 60)" in g for g in probe["green"]) and probe["glyph"]):
                return collapsed("the colour or glyph scanner did not flag an injected "
                                 "green check, so its silence means nothing",
                                 f"green={probe['green'][:3]} glyph={probe['glyph'][:3]}")
            rows = [t for t in m["targets"] if t["big"]]
            if len(rows) < 2:
                return collapsed("fewer than two repo rows were measurable (frame 02)",
                                 f"targets={m['targets'][:8]}")
            bad = []
            for t in rows:
                if t["h"] < 60:
                    bad.append(f"row {t['name']!r} is {t['h']}px tall (min 60)")
            for t in m["targets"]:
                if not t["big"] and (t["w"] < 44 or t["h"] < 44):
                    bad.append(f"control {t['name']!r} is {t['w']}x{t['h']} (min 44x44)")
            if m["green"]:
                bad.append(f"green found: {m['green'][:3]}")
            if m["glyph"]:
                bad.append(f"check glyph found: {m['glyph'][:3]}")
            if re.search(r"\bclean\b", m["text"], re.I):
                bad.append("a 'clean' badge: " + repr(
                    re.findall(r".{0,30}\bclean\b.{0,30}", m["text"], re.I)[:2]))
            if bad:
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "the repos list breaks a redline of board frame 08",
                               "; ".join(bad[:6]))
    return None


_SUBSTRATE = (Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT,
              Substrate.CONSOLE_UNBUILT_REPOS)

CASE_COMMIT = Case(
    name="browser-repos-commit-primary-disabled-at-zero-staged-and-inert",
    tier=Tier.BROWSER, substrate=_SUBSTRATE,
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
    summary="at zero staged the commit primary is disabled and a tap sends no request and "
            "makes no commit; with a file staged it is enabled (board frames 10/11)",
    run=run_commit_gate,
)
CASE_FORCE = Case(
    name="browser-repos-force-push-is-absent-not-gated",
    tier=Tier.BROWSER, substrate=_SUBSTRATE,
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
    summary="no push sheet, on a feature branch or the protected one, names or offers a "
            "force push (board index: absent rather than gated)",
    run=run_no_force_push,
)
CASE_COUNT = Case(
    name="browser-repos-unanswerable-count-is-a-dash-and-a-sentence-never-zero",
    tier=Tier.BROWSER, substrate=_SUBSTRATE,
    classes=(FailureClass.COLLAPSED_SENTINEL,),
    summary="a repo with no upstream shows `—` and a sentence for ahead/behind, never 0; "
            "a repo with an upstream shows its count (board redlines, frame 08)",
    run=run_unanswerable_count,
)
CASE_REDLINES = Case(
    name="browser-repos-list-measured-redlines-row-60-target-44-no-success-colour",
    tier=Tier.BROWSER, substrate=_SUBSTRATE,
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="repos rows are at least 60px, secondary targets 44x44, and nothing green, "
            "no check glyph and no 'clean' badge is rendered (board frame 08)",
    run=run_redlines,
)

CASES = (CASE_COMMIT, CASE_FORCE, CASE_COUNT, CASE_REDLINES)
