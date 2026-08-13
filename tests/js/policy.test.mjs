// The launch-posture panel's pure helpers: how a lifetime is spelled, how long a loose
// posture has left, and which taps get the confirmation row.
import { extractFunction, evaluate, suite, check, done } from "./harness.mjs";

const src = ["ttlLabel", "expiryLabel", "loosens"]
  .map((n) => extractFunction(n)).join("\n");
const { ttlLabel, expiryLabel, loosens } =
  evaluate(src, ["ttlLabel", "expiryLabel", "loosens"]);

suite("ttlLabel");

check("an hour reads as an hour", ttlLabel(1) === "for 1 hour");
check("hours below a day stay hours", ttlLabel(8) === "for 8 hours");
// The server owns the list of lifetimes; the client only spells them, so a lifetime
// added server-side must render without a client change.
check("a day reads as a day, not 24 hours", ttlLabel(24) === "for 1 day");
check("multiple days pluralise", ttlLabel(48) === "for 2 days");
check("an unanticipated lifetime still spells", ttlLabel(3) === "for 3 hours");
// The no-expiry rung is a real choice, not a missing value, so it gets words that name
// what ends it rather than "none" or "off".
check("no lifetime names the action that ends it",
      ttlLabel(null) === "until I turn it off");
check("an absent lifetime reads the same as an explicit null",
      ttlLabel(undefined) === "until I turn it off");

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

suite("loosens");

// The server decides what counts as a widening and ships both flags; the client reads
// them rather than comparing ranks itself, so the two cannot disagree about which taps
// get the confirmation row.
check("a rung above the default that is also a step up gets the second row",
      loosens({ widening: true, above_default: true }) === true);
check("a step up that is still at or below the default does not",
      loosens({ widening: true, above_default: false }) === false);
check("returning to a looser-than-default rung we are already on does not",
      loosens({ widening: false, above_default: true }) === false);
check("tightening never does",
      loosens({ widening: false, above_default: false }) === false);
check("a missing option does not silently take the loosening path",
      loosens(undefined) === false);

done();
