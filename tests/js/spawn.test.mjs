// The spawn sheet's room and harness chips.
import { extractFunction, evaluate, suite, check, contains, done } from "./harness.mjs";

const { spawnRoomChoices } = evaluate(extractFunction("spawnRoomChoices"),
                                      ["spawnRoomChoices"]);
const harnessSrc = ["spawnHarnessChoices", "pickHarness", "harnessCaveat"]
  .map((n) => extractFunction(n)).join("\n");
const { spawnHarnessChoices, pickHarness, harnessCaveat } =
  evaluate(harnessSrc, ["spawnHarnessChoices", "pickHarness", "harnessCaveat"]);

suite("spawnRoomChoices");

const wins = [{ room: "atlas" }, { room: null }, { room: "atlas" }, { room: "beta" }];

check("known rooms are listed",
      JSON.stringify(spawnRoomChoices(["alpha"], [], "")) === '["alpha"]');

check("a room with live windows but no config-dir entry still lists",
      spawnRoomChoices([], wins, "").join(",") === "atlas,beta");

check("known and live are unioned without duplicates",
      spawnRoomChoices(["atlas"], wins, "").join(",") === "atlas,beta");

// The reported bug: a name typed into `+ new` exists in neither source yet.
const fresh = spawnRoomChoices(["alpha"], wins, "newroom");
check("a freshly typed room appears in the list", fresh.includes("newroom"),
      `got: ${fresh}`);
check("...without displacing the rooms that already existed",
      fresh.join(",") === "alpha,atlas,beta,newroom", `got: ${fresh}`);

check("choosing an existing room does not duplicate it",
      spawnRoomChoices(["alpha"], wins, "atlas").join(",") === "alpha,atlas,beta");

check("solo (the empty choice) adds nothing",
      spawnRoomChoices(["alpha"], [], "").length === 1);

check("missing sources are tolerated",
      spawnRoomChoices(undefined, undefined, "x").join(",") === "x");

suite("the harness row");

const OFFERED = [{ harness: "claude", persona: true },
                 { harness: "cursor", persona: false }];

check("the harnesses the server named are the chips",
      spawnHarnessChoices(OFFERED).map((h) => h.harness).join(",") === "claude,cursor");

// Version skew, not paranoia: the static files are served off disk while server.py
// is whatever the last restart loaded, so a client newer than the server is the
// normal state for a while after every edit.
check("a server that names no harness still offers the default",
      spawnHarnessChoices([]).map((h) => h.harness).join(",") === "claude");
check("...and so does one that sends no field at all",
      spawnHarnessChoices(undefined).map((h) => h.harness).join(",") === "claude");
check("junk entries are dropped rather than rendered as blank chips",
      spawnHarnessChoices([null, {}, { harness: "cursor" }])
        .map((h) => h.harness).join(",") === "cursor");

check("the first harness offered is the default", pickHarness(OFFERED, null) === "claude");
check("a chosen harness is kept", pickHarness(OFFERED, "cursor") === "cursor");
// Otherwise the chip stays lit and the spawn is refused with `unknown harness`
// after the tap — which on a phone reads as the button having failed for no reason.
check("a harness the server no longer offers falls back",
      pickHarness([{ harness: "claude", persona: true }], "cursor") === "claude");
check("the fallback holds when the server named nothing",
      pickHarness([], "cursor") === "claude");

check("a harness whose pin carries a persona says nothing",
      harnessCaveat(OFFERED, "claude") === "");
const caveat = harnessCaveat(OFFERED, "cursor");
contains("a harness with no persona flag names itself", caveat, "cursor");
contains("...and says what the scope still does", caveat, "holds its boundary");
contains("...and what it does not", caveat, "will not think like the expert");
check("an unknown harness is not described",
      harnessCaveat(OFFERED, "no-such-harness") === "");

done();
