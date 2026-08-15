// Composited contrast over a rendered console, measured in a real browser.
//
// NOT wired into any test run. It needs a live page and a browser, which is a CI
// decision rather than something to slip into a suite three people verify against.
// Paste into the console's devtools, or drive it through a browser automation tool
// against a console started on a spare port. `report()` returns the failures.
//
// It exists because every static check we built is blind to the value that actually
// reaches the screen. Three defect classes were found on this surface in one day,
// each invisible to the checker that caught the previous one:
//
//   1. a flat token below the floor            — caught by a token scan
//   2. a single `opacity` composite            — invisible to that; the declared
//                                                 colour measured 7.05:1 while the
//                                                 surface received 2.72:1
//   3. `opacity` compounding down a chain      — invisible to both; three rules,
//                                                 none wrong alone, multiplied to
//                                                 0.4284 and painted 2.15:1
//
// Class 3 is why this is worth a browser. `.rd-side` × `.rd-thinking` × `.rd-name`
// is a colour that exists in no file and is reachable only when a subagent thinks.
//
// The two traps, both of which have already been fallen into once here:
//
//   ALPHA. `getComputedStyle(el).backgroundColor` is frequently `rgba(…, 0)` or a
//   partial alpha. Reading it as opaque yields 1.0:1 for legible text — a pass that
//   means nothing, because it is comparing a colour to itself. Alpha must be
//   composited down the ancestor chain to an opaque base, and `opacity` folded in on
//   the way, including onto the ancestors' own backgrounds.
//
//   THRESHOLD. 3:1 applies only at ≥24px, or ≥18.66px bold. Hardcoding 4.5 hides the
//   rule and misjudges the day a heading arrives; hardcoding 3 lets body text through.
//
// COVERAGE IS PER VIEW, and this is the limitation to state before quoting a clean
// run. It measures what is on screen. A first run against the roster measured 61
// elements and found nothing below floor — while covering none of the `.rd-*` read
// view, which is exactly where defect class 3 lived, because those elements were not
// rendered. So a clean report is a claim about the views visited and nothing else.
// Drive it across the roster, an opened row, a terminal band, a session mirror and
// the read view, and report the element count with the verdict: a report of zero
// failures over zero elements is indistinguishable from a passing surface.

const OPAQUE_BASE = [14, 17, 22];        // --bg, the page's own ground

const lin = (c) => {
  c /= 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};
const luminance = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);

function ratio(fg, bg) {
  const a = luminance(fg), b = luminance(bg);
  const hi = Math.max(a, b), lo = Math.min(a, b);
  return (hi + 0.05) / (lo + 0.05);
}

/** `rgb(…)` / `rgba(…)` → [r, g, b, a]. */
function parse(css) {
  const m = String(css).match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const v = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
  return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1];
}

const over = (fg, bg, alpha) => fg.map((c, i) => c * alpha + bg[i] * (1 - alpha));

/**
 * The opaque colour actually painted behind `el`.
 *
 * Walks to the root collecting backgrounds, then composites them bottom-up onto an
 * opaque base. Each background's alpha is multiplied by the `opacity` of its own
 * element and of every element above it, because `opacity` dims an element's
 * background along with its text.
 */
function ground(el) {
  const layers = [];
  let opacityAbove = 1;
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    const cs = getComputedStyle(n);
    const own = parseFloat(cs.opacity);
    const bg = parse(cs.backgroundColor);
    if (bg && bg[3] > 0) {
      layers.push({ rgb: bg.slice(0, 3), alpha: bg[3] * own * opacityAbove });
    }
    opacityAbove *= own;
  }
  let painted = OPAQUE_BASE;
  for (let i = layers.length - 1; i >= 0; i--) {
    painted = over(layers[i].rgb, painted, Math.min(1, layers[i].alpha));
  }
  return painted;
}

/**
 * The effective alpha of `el`'s own ink: its colour's alpha times the `opacity` of
 * itself and every ancestor.
 *
 * This product is the whole of defect class 3. No single rule is wrong; the element
 * carrying `.rd-side` also carries `.rd-thinking`, and wraps `.rd-name`.
 */
function inkAlpha(el) {
  let alpha = parse(getComputedStyle(el).color)?.[3] ?? 1;
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    alpha *= parseFloat(getComputedStyle(n).opacity);
  }
  return alpha;
}

/** WCAG 1.4.3: large text is ≥24px, or ≥18.66px at bold or heavier. */
function floorFor(el) {
  const cs = getComputedStyle(el);
  const px = parseFloat(cs.fontSize);
  const weight = parseInt(cs.fontWeight, 10) || 400;
  const large = px >= 24 || (px >= 18.66 && weight >= 700);
  return large ? 3.0 : 4.5;
}

function path(el) {
  const bits = [];
  for (let n = el; n && n.nodeType === 1 && bits.length < 4; n = n.parentElement) {
    bits.unshift(n.tagName.toLowerCase() +
      (n.className && typeof n.className === "string"
        ? "." + n.className.trim().split(/\s+/).join(".") : ""));
  }
  return bits.join(" > ");
}

/** Elements holding visible text of their own, rather than only wrapping it. */
function textBearing(root = document.body) {
  return [...root.querySelectorAll("*")].filter((el) => {
    if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return false;
    const own = [...el.childNodes].some(
      (n) => n.nodeType === 3 && n.textContent.trim().length);
    return own;
  });
}

/** Every text element below its floor, worst first. */
function report(root = document.body) {
  const out = [];
  for (const el of textBearing(root)) {
    const colour = parse(getComputedStyle(el).color);
    if (!colour) continue;
    const alpha = inkAlpha(el);
    const bg = ground(el);
    const painted = over(colour.slice(0, 3), bg, Math.min(1, alpha));
    const r = ratio(painted, bg);
    const floor = floorFor(el);
    if (r < floor) {
      out.push({
        where: path(el),
        text: el.textContent.trim().slice(0, 40),
        ratio: +r.toFixed(2),
        floor,
        effectiveAlpha: +alpha.toFixed(4),
      });
    }
  }
  return out.sort((a, b) => a.ratio - b.ratio);
}

/**
 * Test of the test. A checker that computes the wrong number passes everything
 * forever, and this one has two documented ways to be silently wrong.
 *
 * Returns [] when sound. Run it before trusting a clean `report()` — a clean report
 * from a broken checker is the most expensive output here.
 */
function selfCheck() {
  const fail = [];
  const near = (a, b, eps = 0.02) => Math.abs(a - b) < eps;

  if (!near(ratio([255, 255, 255], [0, 0, 0]), 21)) fail.push("white/black is not 21:1");
  if (!near(ratio([0, 0, 0], [0, 0, 0]), 1)) fail.push("black/black is not 1:1");

  const probe = document.createElement("div");
  probe.style.cssText = "position:fixed;left:-9999px;background:#161b22;opacity:.72";
  const mid = document.createElement("div");
  mid.style.cssText = "opacity:.7";
  const leaf = document.createElement("span");
  leaf.style.cssText = "opacity:.85;color:#e07a9c";
  leaf.textContent = "thinking";
  mid.appendChild(leaf);
  probe.appendChild(mid);
  document.body.appendChild(probe);
  try {
    const alpha = inkAlpha(leaf);
    // .72 x .7 x .85 — the real compounding that painted 2.15:1.
    if (!near(alpha, 0.4284, 0.001)) {
      fail.push(`opacity does not compound: got ${alpha.toFixed(4)}, want 0.4284`);
    }
    // A transparent background must not be read as opaque, which is the alpha trap:
    // reading it as the element's own colour yields exactly 1.0:1.
    const r = ratio(over(parse(getComputedStyle(leaf).color).slice(0, 3),
                         ground(leaf), alpha), ground(leaf));
    if (near(r, 1.0, 0.05)) fail.push("alpha trap: comparing a colour to itself");
  } finally {
    probe.remove();
  }
  return fail;
}

// Browser console: `selfCheck()` first, then `report()`.
if (typeof window !== "undefined") {
  Object.assign(window, { contrastReport: report, contrastSelfCheck: selfCheck,
                          contrastRatio: ratio, contrastGround: ground });
}
