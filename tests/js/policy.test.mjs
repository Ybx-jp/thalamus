// The launch-posture panel's pure helpers: how a lifetime is spelled, how long a loose
// posture has left, and which taps need a lifetime at all.
import { extractFunction, evaluate, suite, check, done } from "./harness.mjs";

const src = ["ttlLabel", "expiryLabel", "needsLifetime"]
  .map((n) => extractFunction(n)).join("\n");
const { ttlLabel, expiryLabel, needsLifetime } =
  evaluate(src, ["ttlLabel", "expiryLabel", "needsLifetime"]);

suite("ttlLabel");

check("an hour reads as an hour", ttlLabel(1) === "1 hour");
check("hours below a day stay hours", ttlLabel(8) === "8 hours");
// The server owns the list of lifetimes; the client only spells them, so a lifetime
// added server-side must render without a client change.
check("a day reads as a day, not 24 hours", ttlLabel(24) === "1 day");
check("multiple days pluralise", ttlLabel(48) === "2 days");
check("an unanticipated lifetime still spells", ttlLabel(3) === "3 hours");

suite("expiryLabel");

const NOW = Date.UTC(2026, 7, 13, 12, 0, 0);
const at = (mins) => new Date(NOW + mins * 60000).toISOString();

check("a posture with no deadline says nothing", expiryLabel(null, NOW) === "");
check("minutes are shown below the hour", expiryLabel(at(45), NOW) === "reverts in 45m");
// "reverts in 0h" on a posture that is still live reads as already expired.
check("an almost-lapsed posture does not read as 0h",
      expiryLabel(at(5), NOW) === "reverts in 5m");
check("hours are shown above the hour", expiryLabel(at(200), NOW) === "reverts in 3h");
check("a passed deadline reads as lapsed", expiryLabel(at(-1), NOW) === "lapsed");
check("the exact deadline reads as lapsed", expiryLabel(at(0), NOW) === "lapsed");

suite("needsLifetime");

// The server decides what counts as a widening and ships both flags; the client reads
// them rather than comparing ranks itself, so the two cannot disagree about which taps
// have to be given a lifetime.
check("a rung above the default that is also a step up needs one",
      needsLifetime({ widening: true, above_default: true }) === true);
check("a step up that is still at or below the default does not",
      needsLifetime({ widening: true, above_default: false }) === false);
check("returning to a looser-than-default rung we are already on does not",
      needsLifetime({ widening: false, above_default: true }) === false);
check("tightening never does",
      needsLifetime({ widening: false, above_default: false }) === false);
check("a missing option is not a licence to skip the lifetime",
      needsLifetime(undefined) === false);

done();
