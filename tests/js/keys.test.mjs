// Holding a key locked the console up. Printable characters were already coalesced
// into one `api/send` per 24ms window, but every named key was its own request and
// `queue` serialises them — three seconds on backspace built a chain of ~90 round
// trips, each spawning a `tmux send-keys`, still draining after the key came up.
//
// What these pin down is the coalescing *and* the ordering it must not break: a run
// of one key collapses to a count, a different key ends the run, and text and keys
// keep the order they were typed in.

import {
  readApp, extractFunction, extractRegion, evaluate,
  suite, check, done,
} from "./harness.mjs";

const src = readApp();
const source = [
  extractRegion("let keyBuf = \"\";", "// Named keys we forward", src),
  extractFunction("queue", src),
  extractFunction("flushKeys", src),
  extractFunction("typeChar", src),
  extractFunction("flushNamed", src),
  extractFunction("sendNamed", src),
].join("\n");

// Each harness run gets a fresh module scope, so state cannot leak between cases.
function load() {
  const sent = [];
  const api = evaluate(source, ["typeChar", "sendNamed", "flushKeys", "flushNamed"], {
    activeIdx: 1,
    post: async (path, body) => { sent.push({ path, ...body }); },
    KEY_COALESCE_MS: 5,
  });
  return { sent, ...api };
}
const settle = () => new Promise((r) => setTimeout(r, 40));

suite("keys — a held key is one request");
{
  const { sent, sendNamed } = load();
  for (let i = 0; i < 90; i++) sendNamed("backspace");   // ~3s of key repeat
  await settle();
  check("90 repeats do not become 90 requests", sent.length < 90, `sent=${sent.length}`);
  check("every request is a key request", sent.every((s) => s.path === "api/key"));
  check("the repeats are all accounted for",
    sent.reduce((n, s) => n + (s.count || 1), 0) === 90,
    JSON.stringify(sent));
  check("no request exceeds the cap", sent.every((s) => (s.count || 1) <= 64),
    JSON.stringify(sent));
}

suite("keys — coalescing preserves meaning");
{
  const { sent, sendNamed } = load();
  sendNamed("backspace"); sendNamed("backspace"); sendNamed("backspace");
  await settle();
  check("a short run is one request with a count",
    sent.length === 1 && sent[0].count === 3, JSON.stringify(sent));
}
{
  const { sent, sendNamed } = load();
  sendNamed("backspace"); sendNamed("backspace"); sendNamed("up"); sendNamed("backspace");
  await settle();
  check("a different key ends the run",
    sent.length === 3 &&
    sent[0].key === "backspace" && sent[0].count === 2 &&
    sent[1].key === "up" &&
    sent[2].key === "backspace", JSON.stringify(sent.map((s) => `${s.key}x${s.count}`)));
}
{
  const { sent, sendNamed } = load();
  sendNamed("enter");
  await settle();
  check("a single key still sends", sent.length === 1 && sent[0].key === "enter");
}

suite("keys — ordering with typed text");
{
  const { sent, typeChar, sendNamed } = load();
  typeChar("h"); typeChar("i");
  sendNamed("backspace");
  await settle();
  check("text queued before a key lands first",
    sent.length === 2 && sent[0].path === "api/send" && sent[0].text === "hi" &&
    sent[1].path === "api/key" && sent[1].key === "backspace",
    JSON.stringify(sent));
}
{
  const { sent, typeChar, sendNamed } = load();
  sendNamed("backspace"); sendNamed("backspace");
  typeChar("o"); typeChar("k");
  await settle();
  check("a held key lands before text typed after it",
    sent.length === 2 && sent[0].path === "api/key" && sent[0].count === 2 &&
    sent[1].path === "api/send" && sent[1].text === "ok",
    JSON.stringify(sent));
}

done();
