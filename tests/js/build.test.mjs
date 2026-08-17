// The staleness bar, and what it is allowed to decide.
//
// The server composes `reason` and reduces `stale`; the client prints the one and
// branches on the other. That split is the point of these tests: a client that ranked
// `behind` against `process_stale` itself would be a second policy about one fact, and
// the two would drift the first time the server's order changed.
//
// The dismissal is the other half. "Keyed to the commit" is the spec's phrase, but a
// sha-keyed dismissal silences the bar permanently in the exact case it exists for —
// the checkout sits still while the remote moves ahead, so the sha never changes and
// the bar never comes back. The key has to move when the next merge lands.

import {
  readApp, extractFunction, evaluate,
  suite, check, done,
} from "./harness.mjs";

const src = readApp();

const env = evaluate(extractFunction("buildBarState", src), ["buildBarState"], {});
const { buildBarState } = env;

const behind = (n = 1) => ({
  vcs: true, stale: true, sha: "f4de40b", branch: "master", behind: n, ahead: 0,
  process_stale: false, dirty: false, upstream: "origin/master",
  reason: `the checkout is ${n} commit${n === 1 ? "" : "s"} behind origin/master`,
});
const clean = () => ({
  vcs: true, stale: false, sha: "f4de40b", branch: "master", behind: 0, ahead: 0,
  process_stale: false, dirty: false, upstream: "origin/master", reason: "",
});

suite("the bar shows exactly when the server says the console is out of date");
{
  check("a clean checkout raises nothing", buildBarState(clean(), null).show === false);
  check("a stale checkout raises the bar", buildBarState(behind(), null).show === true);
  check("no payload at all raises nothing", buildBarState(null, null).show === false);
  check("a wheel install raises nothing",
        buildBarState({ vcs: false, stale: true, reason: "x" }, null).show === false);
}

suite("the sentence is the server's, verbatim");
{
  const info = behind(3);
  check("it prints `reason` unchanged", buildBarState(info, null).text === info.reason);

  const stale = { ...behind(2), process_stale: true,
                  reason: "this process is running code older than the checkout; " +
                          "the checkout is 2 commits behind origin/master" };
  check("both conditions print as the server joined them",
        buildBarState(stale, null).text === stale.reason);

  // The client must not be the thing that decides which half leads. If it ever ranks
  // them it will do so by rewriting this string, so pinning the string pins the split.
  check("it does not re-order the two conditions",
        buildBarState(stale, null).text.indexOf("older than the checkout") <
        buildBarState(stale, null).text.indexOf("behind origin/master"));

  check("a stale payload with no reason still says something",
        buildBarState({ vcs: true, stale: true, sha: "abc1234", behind: 1 }, null).text !== "");
}

suite("dismissal survives a reload and does not survive the next merge");
{
  const one = behind(1);
  const key = buildBarState(one, null).key;
  check("dismissing hides it", buildBarState(one, key).show === false);
  check("an unrelated key does not hide it",
        buildBarState(one, "something-else").show === true);

  // The case the sha alone gets wrong: the checkout has not moved, so `sha` is
  // identical, but another merge landed upstream.
  const two = behind(2);
  check("the same sha one commit further behind raises it again",
        two.sha === one.sha && buildBarState(two, key).show === true);

  // ...and the other axis: nothing moved upstream, but the process fell behind the
  // tree, which is a different condition with the same sha and the same `behind`.
  const alsoStale = { ...one, process_stale: true,
                      reason: "this process is running code older than the checkout" };
  check("the same sha newly process-stale raises it again",
        buildBarState(alsoStale, key).show === true);

  check("re-dismissing the new state hides it again",
        buildBarState(two, buildBarState(two, null).key).show === false);
}

suite("✕ dismisses the state that is on screen");
{
  // The defect this pins, found by clicking the real control in a browser: the
  // handler derived its own key from a module variable the renderer never wrote, so
  // dismissing stored nothing and the next poll raised the bar straight back. It
  // looked exactly like a dismissal that worked, because the bar did go away — until
  // 1.2 seconds later. The renderer must publish the key it drew.
  const store = new Map();
  const localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k),
  };
  const bar = { hidden: true };
  const msg = { textContent: "" };
  const els = { buildBar: bar, buildMsg: msg };

  // `buildBarKey` is the client's own module-scope variable; it is declared here
  // because an extracted function has no module around it, and both the renderer and
  // the dismiss handler below are the shipped source, unmodified.
  const env = evaluate(
    "let buildBarKey = '';\n" +
    extractFunction("buildBarState", src) + "\n" +
    extractFunction("renderBuildBar", src) + "\n" +
    extractFunction("dismissBuildBar", src),
    ["renderBuildBar", "dismissBuildBar"],
    { els, localStorage, BUILD_DISMISS_KEY: "plane-build-dismissed", deployInFlight: false },
  );

  env.renderBuildBar(behind(2));
  check("the bar is up", bar.hidden === false);

  env.dismissBuildBar();
  check("dismissing stores a key", store.get("plane-build-dismissed") !== undefined);
  check("the stored key is the one the render produced",
        store.get("plane-build-dismissed") === buildBarState(behind(2), null).key);

  env.renderBuildBar(behind(2));
  check("the same state stays down after a dismissal", bar.hidden === true);

  env.renderBuildBar(behind(3));
  check("the next merge raises it again", bar.hidden === false);
}

suite("the key is stable for one unchanged state");
{
  const a = buildBarState(behind(1), null).key;
  const b = buildBarState(behind(1), null).key;
  check("two reads of the same state agree", a === b && a !== "");
  check("a clean checkout yields no key", buildBarState(clean(), null).key === "");
}

done();
