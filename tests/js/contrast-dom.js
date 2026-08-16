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

/** The 8 corners a float channel triple can land on once quantized to 8 bits. */
function corners(rgb) {
  const out = [];
  for (let i = 0; i < 8; i++) {
    out.push(rgb.map((v, k) => (i >> k & 1) ? Math.ceil(v) : Math.floor(v)));
  }
  return out;
}

/**
 * The worst ratio the screen could plausibly paint, rather than the prettiest.
 *
 * A composite lands between two 8-bit values and the rounding model decides which.
 * Measured on `#4db6a6` at .5 over `--panel`, three defensible implementations give
 * 2.714, 2.733 and 2.751 — and across an alpha sweep the spread reaches **0.0344**,
 * which is wider than the headroom on the two tightest pairs this surface has
 * (`--faint` on `--panel` at 4.53, the composer at 4.51 before it was lifted).
 *
 * So near the floor the checker's arithmetic decides the verdict instead of the
 * design. A legibility floor exists to protect a reader, so the tie goes to the
 * reader: take the minimum over both operands' quantizations. Being wrong here in
 * the optimistic direction means passing something the screen fails, which is the
 * one error a checker must not make.
 */
function paintedRatio(fgFloat, bgFloat) {
  let worst = Infinity;
  for (const f of corners(fgFloat)) {
    for (const b of corners(bgFloat)) worst = Math.min(worst, ratio(f, b));
  }
  return worst;
}

// THE COST OF BEING CONSERVATIVE, stated so it is known rather than rediscovered by
// whoever next wants to relax this.
//
// Being pessimistic means a composited pair can fail while the screen would have
// passed it. Swept over 13 hues against `--bg`, `--panel` and `--panel-hi`, alpha
// .05–.99, the penalty **near the floor** — the only place it can turn a pass into a
// failure — reaches **0.056**. So a composited pair wants about **4.556** measured to
// be safe from a false failure.
//
// No attaining example is given, deliberately. The maximum sits on a flat ridge: the
// top six points are six different hue/ground/alpha combinations spanning 0.0026, so
// naming one hue invites the next reader to check that hue, find a smaller penalty,
// and conclude the header is wrong — when they have only found a different point on
// the same ridge. Two independent sweeps put the maximum at different hues and agreed
// on its value to 0.0014.
//
// Two numbers that are *not* that one, because both mislead:
//   • ~0.09 is the global maximum penalty, and it occurs at ratios near 8:1 where a
//     large absolute movement cannot cross any threshold. Quoting it overstates, and
//     it is the number someone would reach for in good faith to argue this check is
//     too strict.
//   • ~0.05 measured over a single hue and ground understates, by sampling a
//     population of one.
// The figure that bounds false failures is the maximum *among pairs already near the
// floor*. Both of the others are true numbers about the wrong population.
//
// The trade is asymmetric and that is what justifies it: the remedy for a false
// failure is about one percent more contrast, which this design has twice concluded
// costs it nothing — and the remedy for a false pass is a reader who cannot read.
//
// The eight corners are not merely adequate, they are exact. Relative luminance is
// monotonically increasing in every channel and the ratio is monotonic in luminance,
// so the minimum is always attained by pushing the lighter operand down on *all*
// channels and the darker up on *all* — a uniform corner, and both are already in
// the set. Mixed corners such as `[49,105,100]` are unrealisable (a browser rounds
// one colour's three channels by one rule) and can never be the extremum, so
// including them is free. Verified: min-over-64 equals min-over-4-uniform on every
// point of the sweep, zero mismatches. qe proposed narrowing this to the realisable
// models, measured it, and found the refinement changes nothing.

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
    const r = paintedRatio(painted, bg);
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
    const g = ground(leaf);
    const r = paintedRatio(over(parse(getComputedStyle(leaf).color).slice(0, 3), g, alpha), g);
    if (near(r, 1.0, 0.05)) fail.push("alpha trap: comparing a colour to itself");

    // Round against yourself. The optimistic model is what a checker reaches for
    // and it is the one error that matters: passing what the screen fails.
    const fg = [77, 182, 166], panel = [22, 27, 34];   // #4db6a6 over --panel
    const half = over(fg, panel, 0.5);
    if (!(paintedRatio(half, panel) <= ratio(half, panel))) {
      fail.push("quantization is optimistic: the float value is being reported");
    }
    if (!near(paintedRatio(half, panel), 2.714, 0.005)) {
      fail.push(`worst-corner ratio drifted: ${paintedRatio(half, panel).toFixed(3)}`);
    }
  } finally {
    probe.remove();
  }
  return fail;
}

// Browser console: `selfCheck()` first, then `report()`.
if (typeof window !== "undefined") {
  // `contrastMeasured` is the denominator, and it is exported because a verdict
  // without one is not a verdict: zero failures over zero elements is byte-identical
  // to a clean surface. Any caller quoting a clean `report()` states this alongside it.
  Object.assign(window, { contrastReport: report, contrastSelfCheck: selfCheck,
                          contrastRatio: ratio, contrastGround: ground,
                          contrastMeasured: (root) => textBearing(root).length });
}
