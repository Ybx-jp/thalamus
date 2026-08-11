// The spawn sheet's room chips.
import { extractFunction, evaluate, suite, check, done } from "./harness.mjs";

const { spawnRoomChoices } = evaluate(extractFunction("spawnRoomChoices"),
                                      ["spawnRoomChoices"]);

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

done();
