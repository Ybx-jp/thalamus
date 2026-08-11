// The tap-to-listen control. Two things here are load-bearing and neither is
// obvious from reading the handler.
//
// A mobile browser grants audio playback to an element the user just activated.
// That grant is lost across an `await`, so the src must be assigned and `play()`
// called in the same turn as the click — fetching the audio first and playing the
// result is the natural way to write it and the phone silently refuses it. These
// tests pin the ordering by recording when `play()` happened relative to the
// assignment, which is the only observable difference between the two shapes.
//
// The second is that the button is a toggle: the same tap that starts a long
// utterance has to be able to stop it, or a five-minute update owns the device.

import {
  readApp, extractFunction, extractRegion, evaluate,
  suite, check, contains, done,
} from "./harness.mjs";

const src = readApp();
const source = [
  extractFunction("sayUrl", src),
  extractFunction("setSayState", src),
  extractFunction("stopSaying", src),
  extractFunction("speakActiveWindow", src),
].join("\n");

function load(activeIdx = 3) {
  const events = [];
  const classes = new Set();
  const sayAudio = {
    _src: "",
    get src() { return this._src; },
    set src(v) { this._src = v; events.push({ type: "src", value: v }); },
    play() { events.push({ type: "play", src: this._src }); return Promise.resolve(); },
    pause() { events.push({ type: "pause" }); },
  };
  const els = {
    sayToggle: {
      textContent: "say",
      classList: {
        toggle: (name, on) => { on ? classes.add(name) : classes.delete(name); },
        has: (name) => classes.has(name),
      },
    },
  };
  // `saying` is module state in app.js. Injected as a parameter it becomes a
  // binding the extracted functions share and mutate exactly as they do in the
  // browser, which is the behaviour under test — the toggle is that flag.
  const api = evaluate(
    source + "\nfunction _saying(){ return saying; }",
    ["sayUrl", "setSayState", "stopSaying", "speakActiveWindow", "_saying"],
    { els, sayAudio, activeIdx, encodeURIComponent, saying: false },
  );
  return { api, events, els, classes };
}

suite("say: the url");
{
  const { api } = load();
  check("is relative, so it survives whatever path the proxy mounts",
    !api.sayUrl(3).startsWith("/") && !api.sayUrl(3).startsWith("http"));
  contains("carries the window index", api.sayUrl(7), "index=7");
  contains("encodes a negative index rather than splicing it raw",
    api.sayUrl(-1), "index=-1");
}

suite("say: user activation is not spent before play()");
{
  const { api, events } = load(2);
  api.speakActiveWindow();
  const order = events.map((e) => e.type);
  check("assigns src then plays, with nothing between",
    order[0] === "src" && order[1] === "play", `got: ${order.join(",")}`);
  check("plays the url it just assigned",
    events[1].src === api.sayUrl(2), `got: ${events[1].src}`);
  check("no fetch happens first — only two events in the click turn",
    events.length === 2, `got ${events.length}: ${order.join(",")}`);
}

suite("say: the toggle stops what it started");
{
  const { api, events, els } = load(1);
  api.speakActiveWindow();
  check("reads as speaking after the first tap", els.sayToggle.textContent === "stop",
    `got: ${els.sayToggle.textContent}`);
  api.speakActiveWindow();
  check("second tap pauses rather than starting a second utterance",
    events.filter((e) => e.type === "pause").length === 1,
    `got: ${events.map((e) => e.type).join(",")}`);
  check("only ever started once", events.filter((e) => e.type === "play").length === 1);
  check("reads as idle again", els.sayToggle.textContent === "say");
}

suite("say: nothing to speak");
{
  const { api, events } = load(null);
  api.speakActiveWindow();
  check("a window-less console does not request audio", events.length === 0,
    `got: ${events.map((e) => e.type).join(",")}`);
}

suite("say: failure is visible");
{
  const { api, els, classes } = load(4);
  api.setSayState("err");
  check("marks the control bad", classes.has("bad"));
  check("and does not also claim to be speaking", !classes.has("on"));
}

done();
