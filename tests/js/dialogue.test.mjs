// The room dialogue composer. What matters here is what the client does NOT decide.
//
// The pane composer types into a window the operator is watching, where answering a
// permission prompt on purpose is a primary use. The dialogue addresses members
// nobody is looking at, so the Enter after the text could answer a prompt the sender
// never saw — and the whole defence against that lives in the server's pre-flight.
// A client that duplicated any part of that rule would be a second policy about who
// is safe to type into, and two policies drift.
//
// So these tests pin two things: the client forwards and renders rather than judging,
// and a refusal reaches the operator verbatim instead of becoming a generic failure.

import {
  readApp, extractFunction, evaluate,
  suite, check, contains, lacks, done,
} from "./harness.mjs";

const src = readApp();
const source = [
  extractFunction("openDialogue", src),
  extractFunction("closeDialogue", src),
  extractFunction("runDialogue", src),
].join("\n");

function load({ ok = true, data = {} } = {}) {
  const posts = [];
  const els = {
    dialogue: { hidden: true },
    dialogueRoom: { textContent: "" },
    dialogueText: { value: "", focus() {} },
    dialoguePartial: { checked: false },
    dialogueGo: { disabled: false },
    dialogueCheck: { disabled: false },
    dialogueLog: { hidden: true, textContent: "" },
  };
  const api = evaluate(
    source + "\nfunction _room(){ return dialogueRoom; }",
    ["openDialogue", "closeDialogue", "runDialogue", "_room"],
    {
      els,
      dialogueRoom: null,
      postJson: async (path, body) => { posts.push({ path, body }); return { ok, data }; },
      poll: () => {},
      setTimeout: (fn) => fn(),
    },
  );
  return { api, els, posts };
}

suite("dialogue: opening targets one room");
{
  const { api, els } = load();
  api.openDialogue("alpha");
  check("shows the panel", els.dialogue.hidden === false);
  check("names the room it will address", els.dialogueRoom.textContent === "alpha");
  check("starts disabled — an empty message still costs every recipient a turn",
    els.dialogueGo.disabled === true);
  check("clears any previous result", els.dialogueLog.textContent === "");
}

{
  const { api, els } = load();
  api.openDialogue("");
  check("a falsy room opens nothing: `any` and `solo` name no addressable room",
    els.dialogue.hidden === true);
}

suite("dialogue: the request is a forward, not a decision");
{
  const { api, els, posts } = load({ ok: true, data: { note: "2/2 delivered" } });
  api.openDialogue("alpha");
  els.dialogueText.value = "  stand up  ";
  els.dialoguePartial.checked = true;
  await api.runDialogue(false);

  check("posts exactly once", posts.length === 1, `got ${posts.length}`);
  check("to the dispatch endpoint", posts[0].path === "api/dispatch");
  check("carrying the room", posts[0].body.room === "alpha");
  check("with the message trimmed", posts[0].body.message === "stand up");
  check("and the partial flag as the operator set it", posts[0].body.partial === true);
  check("dryRun false on a real say", posts[0].body.dryRun === false);
  contains("renders the server's own note", els.dialogueLog.textContent, "2/2 delivered");
}

suite("dialogue: check-only is a dry run on the server");
{
  const { api, els, posts } = load({ ok: true, data: { note: "would deliver to 2" } });
  api.openDialogue("alpha");
  els.dialogueText.value = "ping";
  await api.runDialogue(true);
  check("asks the server for the dry run", posts[0].body.dryRun === true);
  check("does not decide reachability itself — one request, no filtering",
    posts.length === 1);
}

suite("dialogue: a refusal reaches the operator verbatim");
{
  const refusal =
    "refusing the whole fan-out: 1 of 3 target(s) cannot be delivered to — " +
    "`alpha-homelab` is `waiting`";
  const { api, els } = load({ ok: false, data: { error: refusal } });
  api.openDialogue("alpha");
  els.dialogueText.value = "ping";
  await api.runDialogue(false);

  contains("names the target that refused", els.dialogueLog.textContent, "alpha-homelab");
  contains("and why", els.dialogueLog.textContent, "waiting");
  lacks("without flattening it to a generic failure",
    els.dialogueLog.textContent, "unknown error");
  check("re-enables the button so the operator can fix and retry",
    els.dialogueGo.disabled === false);
}

suite("dialogue: an empty message never reaches the server");
{
  const { api, posts } = load();
  api.openDialogue("alpha");
  await api.runDialogue(false);
  check("nothing posted for an empty box", posts.length === 0);
}

{
  const { api, posts } = load();
  api.openDialogue("alpha");
  await api.runDialogue(false);
  check("nor for whitespace only", posts.length === 0);
}

suite("dialogue: the client holds no view of who is reachable");
{
  // The guard against re-implementing the pre-flight. If any of these appear in the
  // dialogue's own source, the client has started deciding what only the server may.
  for (const forbidden of ["waiting", "idle", "busy", "pane", "send-keys"]) {
    lacks(`no \`${forbidden}\` reasoning in the client`, source, forbidden);
  }
}

done();
