// The spawn sheet: what kind of window it opens, and the room and harness chips.
import { extractFunction, evaluate, suite, check, contains, done } from "./harness.mjs";

const { spawnRoomChoices } = evaluate(extractFunction("spawnRoomChoices"),
                                      ["spawnRoomChoices"]);
const kindSrc = ["spawnKindChoices", "pickKind", "spawnReady", "kindNote"]
  .map((n) => extractFunction(n)).join("\n");
const { spawnKindChoices, pickKind, spawnReady, kindNote } =
  evaluate(kindSrc, ["spawnKindChoices", "pickKind", "spawnReady", "kindNote"]);
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

suite("the kind row: one sheet opens two different things");

// A shell chip whose POST would 404 is a button that does nothing, which is the
// failure this console is least able to explain on a phone. `static/` is served off
// disk while server.py is whatever the last restart loaded, so a client newer than
// its server is the normal state for a while after every edit.
check("a server that says it can open a shell is offered one",
      spawnKindChoices({ shell: true }).join(",") === "session,shell");
check("a server that has not restarted yet is not",
      spawnKindChoices({ scopes: [] }).join(",") === "session");
check("and neither is one that could not be asked at all",
      spawnKindChoices(undefined).join(",") === "session");

check("the first kind is the default", pickKind({ shell: true }, null) === "session");
check("a chosen kind is kept", pickKind({ shell: true }, "shell") === "shell");
check("a kind the server no longer offers falls back",
      pickKind({}, "shell") === "session");

// The two kinds share the directory picker and nothing else.
check("a session needs its expert as well as somewhere to stand",
      spawnReady("session", null, "/home/op/code/alpha") === false);
check("...and is ready once it has both",
      spawnReady("session", "architect", "/home/op/code/alpha") === true);
check("a shell needs only somewhere to stand",
      spawnReady("shell", null, "/home/op/code/alpha") === true);
check("...and not even a shell can open nowhere",
      spawnReady("shell", null, null) === false);

contains("the shell note says there is no memory in it", kindNote("shell"), "no memory");
contains("the session note still says the directory is the subject",
         kindNote("session"), "distilled memory");

done();
