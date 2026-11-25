// Shared by the jobs and board pages. Nothing here knows what a job is: it fetches
// through the console's /api/jobs/ proxy, builds DOM without ever parsing a string as
// HTML, and maps a source-sent tone onto a class. Every word the pages show arrives
// from the jobs source already composed; these helpers print it.
"use strict";

const SURFACE_TIMEOUT_MS = 15000;

// A fresh AbortController per request: a signal is single-use, and a hoisted one
// would wedge every later request after the first timeout.
function surfaceFetch(url, opts) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), SURFACE_TIMEOUT_MS);
  return fetch(url, Object.assign({}, opts, { signal: ctl.signal }))
    .finally(() => clearTimeout(timer));
}

// GET a jobs-source path. Resolves to the parsed body; rejects with an Error whose
// message is the source's own `error` field when it sent one, so the page can print
// the reason rather than a status code.
async function api(path) {
  const res = await surfaceFetch("api/jobs/" + path);
  return apiBody(res);
}

async function apiPost(path, body) {
  const res = await surfaceFetch("api/jobs/" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return apiBody(res);
}

async function apiBody(res) {
  let data = null;
  try { data = await res.json(); } catch (_) { data = null; }
  if (!res.ok) {
    const err = new Error((data && data.error) || ("HTTP " + res.status));
    err.status = res.status;
    throw err;
  }
  return data || {};
}

// h("div.card.wide", {onclick}, child, "text", [more]) — the only DOM builder. Strings
// become text nodes, always; there is no path from data to markup.
function h(spec, attrs, ...kids) {
  const [tag, ...classes] = spec.split(".");
  const el = document.createElement(tag || "div");
  if (classes.length) el.className = classes.join(" ");
  if (attrs && (typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs))) {
    kids.unshift(attrs);
    attrs = null;
  }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className += (el.className ? " " : "") + v;
    else if (k === "text") el.textContent = v;
    else if (k === "style" && typeof v === "object") {
      // setProperty, not Object.assign: a custom property ("--scope") assigned as a
      // field on CSSStyleDeclaration is silently dropped.
      for (const [prop, val] of Object.entries(v)) {
        if (prop.startsWith("--")) el.style.setProperty(prop, val);
        else el.style[prop] = val;
      }
    }
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  }
  appendKids(el, kids);
  return el;
}

function appendKids(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}

// A scope's identity hue — the roster's, verbatim (pinned to app.js by
// tests/test_console_surface.py), so a scope is one colour on every console page. It
// marks which scope a row belongs to and means nothing about how the row is doing; a
// status is always a tone beside a word.
const MAIN_HUE = "#9a8cff";                                        // violet
const PALETTE = ["#e0a45c", "#4db6a6", "#6db3f2", "#e07a9c",       // amber, teal, sky, rose
                 "#8fce6b", "#c79bf0"];                            // moss, orchid
function hashHue(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (Math.imul(h, 31) + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
// A row with no scope gets the hairline grey: it belongs to nobody, which is not a hue.
function scopeHue(name) {
  if (!name) return "var(--muted)";
  return name === "main" ? MAIN_HUE : hashHue(name);
}

const TONES = ["ok", "faint", "danger", "pending", "muted", "accent"];

// The class for a source-sent tone. An unknown tone renders as muted rather than as
// nothing, so a source newer than this page still shows its word.
function toneClass(tone) {
  return "tone-" + (TONES.indexOf(tone) >= 0 ? tone : "muted");
}

// A status as the source sent it: the word, in its tone's colour. Null renders nothing.
function statusWord(status, extra) {
  if (!status || !status.word) return null;
  return h("span." + toneClass(status.tone) + (extra ? "." + extra : ""), status.word);
}

let toastTimer = 0;
function toast(msg) {
  let el = document.getElementById("s-toast");
  if (!el) {
    el = h("div.s-toast", { id: "s-toast", role: "status", hidden: true });
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

// A labelled switch. `onchange(checked)` may return a promise; while it is pending
// the input is disabled, and a rejection puts the knob back and toasts the reason.
function switchEl(checked, label, onchange) {
  const input = h("input", { type: "checkbox", role: "switch", "aria-label": label });
  input.checked = !!checked;
  input.addEventListener("change", async () => {
    input.disabled = true;
    try { await onchange(input.checked); }
    catch (e) { input.checked = !input.checked; toast(e.message); }
    finally { input.disabled = false; }
  });
  return h("label.s-switch", input, h("span.track"), h("span.knob"));
}

function errorBox(e) {
  return h("div.s-err", { role: "alert" }, e && e.message ? e.message : String(e));
}

// The three ratings a finding takes (N5): the value the source stores, and the button's
// word. "Not worth it" is true but not worth telling him; "Incorrect" is wrong on the facts.
const RATINGS = [["useful", "Useful"], ["not_useful", "Not worth it"], ["wrong", "Incorrect"]];

// A finding row, one renderer for B1's inbox, D2 and J5 (N5 "Finding row"). Every word is
// the source's: `meta` ("Career discovery · blind spot · still open"), the `title` the
// job wrote, the `observation`, the `source` link's text. With a title the observation
// is the body, clamped to two lines; with none it is the headline, clamped to three.
// `runHref(id)` is where an "evidence" link goes: the source names the run whose evidence
// the finding cites, and each page knows its own route to it. An external source opens
// in a new tab. `onRated(value)` runs after a rating is stored.
function findingCard(item, runHref, onRated) {
  const buttons = h("div.f-rate", { role: "group", "aria-label": "Rate this finding" });
  const paintRatings = (current) => {
    buttons.replaceChildren(...RATINGS.map(([value, word]) => {
      const on = current === value;
      return h("button.f-rate-btn" + (on ? ".on" : ""), { type: "button", "aria-pressed": on ? "true" : "false",
        onclick: async () => {
          if (item.label === value) return;
          const all = Array.from(buttons.children);
          all.forEach((b) => { b.disabled = true; });
          try {
            await apiPost("findings/" + encodeURIComponent(item.id) + "/label", { label: value });
            item.label = value;
            paintRatings(value);
            if (onRated) onRated(value);
          } catch (err) {
            all.forEach((b) => { b.disabled = false; });
            toast(err.message);
          }
        } }, word);
    }));
  };
  paintRatings(item.label);
  const src = item.source;
  let link = h("span.f-src");
  if (src && src.url) {
    link = h("a.f-src", { href: src.url, target: "_blank", rel: "noopener noreferrer" }, src.text + " ›");
  } else if (src && src.run) {
    link = h("a.f-src", { href: runHref(src.run) }, src.text + " ›");
  }
  return h("div.f-item",
    item.meta ? h("div.f-meta", item.meta) : null,
    item.title ? h("div.f-title", item.title) : h("div.f-headline", item.observation),
    item.title && item.observation ? h("div.f-body", item.observation) : null,
    h("div.f-foot", link, buttons));
}
