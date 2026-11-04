// Numbered scene transitions for the picker reel (tools/transition_reel.py), in the film's palette.
// Each: { name, d: seconds, fn(c), opaque?: false }. c gives tl, T, D, A, B (.tw wrappers of the
// outgoing and incoming scene), ai, bi (their .inner) and the helpers below. Single paused
// timeline, explicit from-states, seeded randomness only: seek-safe.
const GROUND = "#14120f", INK = "#f3eee4", MUTED = "#a39b8e", RULE = "#2a2622", SIGNAL = "#ff5b24";
const HEAT = ["#6a3a22", "#a3431f", "#d9501f", "#ff5b24"];
const ADD = "#8fd694", DEL = "#f2777a";
const W = 1080, H = 1350;

function seeded(seed) { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; }

function ctx(tl, T, D, A, B) {
  const film = document.getElementById("film");
  const c = { tl, T, D, A, B, ai: A.querySelector(".inner"), bi: B.querySelector(".inner") };
  // the outgoing scene: an explicit from-state, not applied until the transition starts
  c.out = (el, from, to, at = 0, dur = D) => tl.fromTo(el, from, { ...to, duration: dur, immediateRender: false }, T + at);
  c.in = (el, from, to, at = 0, dur = D) => tl.fromTo(el, from, { ...to, duration: dur }, T + at);
  // hide the incoming scene, show it at a moment (for covers)
  c.swap = (at = D / 2) => tl.fromTo(B, { opacity: 0 }, { opacity: 1, duration: 0.001 }, T + at);
  c.ov = (css, html = "") => {
    const el = document.createElement("div");
    el.style.cssText = "position:absolute;z-index:5000;visibility:hidden;" + css;
    el.innerHTML = html;
    film.appendChild(el);
    tl.set(el, { visibility: "visible" }, T);
    tl.set(el, { visibility: "hidden" }, T + D + 0.001);
    return el;
  };
  // an animated CSS mask on the incoming scene, driven by a seek-safe proxy
  c.mask = (paint, ease = "power2.inOut", dur = D) => {
    paint(0);
    const p = { v: 0 };
    tl.fromTo(p, { v: 0 }, { v: 1, duration: dur, ease, onUpdate: () => paint(p.v) }, T);
  };
  c.setMask = (el, image, size) => {
    el.style.webkitMaskImage = image; el.style.maskImage = image;
    if (size) { el.style.webkitMaskSize = size; el.style.maskSize = size; }
  };
  // any rectangle size: same fill-then-clear as cells, for grids that are not square
  c.tiles = (w, h, order, colour, stagger = 0.42) => {
    const cols = Math.ceil(W / w - 0.001), rows = Math.ceil(H / h - 0.001), list = [];
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) list.push({ x, y, el: c.ov(`left:${x * w}px;top:${y * h}px;width:${w + 1}px;height:${h + 1}px;background:${colour(x, y)};opacity:0`) });
    const max = Math.max(...list.map((k) => order(k.x, k.y)));
    list.forEach((k) => {
      const f = order(k.x, k.y) / (max || 1);
      tl.fromTo(k.el, { opacity: 0 }, { opacity: 1, duration: 0.001 }, T + f * D * stagger);
      tl.to(k.el, { opacity: 0, duration: 0.001 }, T + D * (1 - stagger) + f * D * stagger);
    });
    c.swap(D / 2);
  };
  // a full-frame grid of cells that fill, then clear, with the swap between
  c.cells = (size, order, colour, stagger = 0.42) => {
    const cols = Math.ceil(W / size), rows = Math.ceil(H / size);
    const list = [];
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      list.push({ x, y, el: c.ov(`left:${x * size}px;top:${y * size}px;width:${size + 1}px;height:${size + 1}px;background:${colour(x, y, cols, rows)};opacity:0`) });
    }
    const max = Math.max(...list.map((k) => order(k.x, k.y, cols, rows)));
    list.forEach((k) => {
      const f = order(k.x, k.y, cols, rows) / (max || 1);
      tl.fromTo(k.el, { opacity: 0 }, { opacity: 1, duration: 0.001 }, T + f * D * stagger);
      tl.to(k.el, { opacity: 0, duration: 0.001 }, T + D * (1 - stagger) + f * D * stagger);
    });
    c.swap(D * stagger + (D * (1 - 2 * stagger)) / 2);
  };
  return c;
}

const heatAt = (seed) => { const r = seeded(seed); const m = new Map(); return (x, y) => { const k = x * 1000 + y; if (!m.has(k)) m.set(k, HEAT[Math.floor(r() * 4)]); return m.get(k); }; };
const randOrder = (seed) => { const r = seeded(seed); const m = new Map(); return (x, y) => { const k = x * 1000 + y; if (!m.has(k)) m.set(k, r()); return m.get(k); }; };

const GREEN = ["#0e4429", "#006d32", "#26a641", "#39d353"];
const ADDBG = "#22352a", DELBG = "#3d2425";
const LANG = { HTML: "#e34c26", Python: "#3572a5", JavaScript: "#f1e05a", TypeScript: "#3178c6", other: "#6e7681" };
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
const heatFrom = (seed, cols) => { const r = seeded(seed); const m = new Map(); return (x, y) => { const k = x * 1000 + y; if (!m.has(k)) m.set(k, cols[Math.floor(r() * 4)]); return m.get(k); }; };
// the real calendar as colours: no contributions is the empty square, the rest by quartile of active days
const dayLevels = (cal) => {
  const on = cal.map((d) => d[1]).filter((v) => v > 0).sort((a, b) => a - b);
  const q = [0.25, 0.5, 0.75].map((f) => on[Math.floor(on.length * f)]);
  return cal.map(([, v]) => (v === 0 ? RULE : HEAT[v <= q[0] ? 0 : v <= q[1] ? 1 : v <= q[2] ? 2 : 3]));
};
// a 5-wide mirrored block pattern seeded from the handle, in the manner of a default avatar
const identicon = (user, rows) => {
  let seed = 7; for (const ch of user) seed = (seed * 31 + ch.charCodeAt(0)) % 2147483646 + 1;
  const r = seeded(seed), out = [];
  for (let y = 0; y < rows; y++) out.push([r() > 0.5, r() > 0.5, r() > 0.5]);
  return out;
};

const TRANSITIONS = [
  // ---- straight handoffs
  { name: "Hard cut", d: 0, fn: () => {} },
  { name: "Cut, 0.1 s fade (the tight test)", d: 0.1, fn: (c) => c.in(c.B, { opacity: 0 }, { opacity: 1, ease: "power1.out" }) },
  { name: "Crossfade, quick", d: 0.25, fn: (c) => c.in(c.B, { opacity: 0 }, { opacity: 1, ease: "none" }) },
  { name: "Crossfade, slow", d: 0.5, fn: (c) => c.in(c.B, { opacity: 0 }, { opacity: 1, ease: "sine.inOut" }) },
  { name: "Dip through ground (the calm film)", d: 0.65, fn: (c) => {
    c.out(c.A, { opacity: 1 }, { opacity: 0, ease: "power1.in" }, 0, c.D * 0.5);
    c.in(c.B, { opacity: 0 }, { opacity: 1, ease: "power1.out" }, c.D * 0.5, c.D * 0.5);
  } },
  { name: "Blur crossfade", d: 0.45, fn: (c) => {
    c.out(c.A, { filter: "blur(0px)" }, { filter: "blur(14px)", ease: "power2.in" });
    c.in(c.B, { opacity: 0, filter: "blur(14px)" }, { opacity: 1, filter: "blur(0px)", ease: "power2.out" });
  } },
  { name: "Focus pull", d: 0.55, fn: (c) => {
    c.out(c.A, { scale: 1, filter: "blur(0px)" }, { scale: 1.06, filter: "blur(22px)", ease: "sine.in" });
    c.in(c.B, { opacity: 0, scale: 0.97, filter: "blur(22px)" }, { opacity: 1, scale: 1, filter: "blur(0px)", ease: "sine.out" });
  } },

  // ---- only the content moves, the page stays
  { name: "Content lifts, next rises", d: 0.4, opaque: false, fn: (c) => {
    c.out(c.ai, { y: 0, opacity: 1 }, { y: -50, opacity: 0, ease: "power2.in" }, 0, c.D * 0.55);
    c.in(c.bi, { y: 50, opacity: 0 }, { y: 0, opacity: 1, ease: "power3.out" }, c.D * 0.4, c.D * 0.6);
  } },
  { name: "Content slides across", d: 0.4, opaque: false, fn: (c) => {
    c.out(c.ai, { x: 0, opacity: 1 }, { x: -120, opacity: 0, ease: "power2.in" }, 0, c.D * 0.55);
    c.in(c.bi, { x: 120, opacity: 0 }, { x: 0, opacity: 1, ease: "power3.out" }, c.D * 0.4, c.D * 0.6);
  } },
  { name: "Lines stagger out", d: 0.5, opaque: false, fn: (c) => {
    c.tl.fromTo([...c.ai.children], { y: 0, opacity: 1 }, { y: -36, opacity: 0, duration: 0.2, ease: "power2.in", stagger: 0.05, immediateRender: false }, c.T);
    c.in(c.bi, { opacity: 0 }, { opacity: 1, ease: "none" }, c.D * 0.6, c.D * 0.4);
  } },
  { name: "Shrink back, next comes forward", d: 0.4, opaque: false, fn: (c) => {
    c.out(c.ai, { scale: 1, opacity: 1 }, { scale: 0.92, opacity: 0, ease: "power2.in" }, 0, c.D * 0.5);
    c.in(c.bi, { scale: 1.06, opacity: 0 }, { scale: 1, opacity: 1, ease: "power3.out" }, c.D * 0.4, c.D * 0.6);
  } },

  // ---- pushes
  { name: "Push left", d: 0.4, fn: (c) => {
    c.out(c.A, { xPercent: 0 }, { xPercent: -100, ease: "power3.inOut" });
    c.in(c.B, { xPercent: 100 }, { xPercent: 0, ease: "power3.inOut" });
  } },
  { name: "Push up", d: 0.4, fn: (c) => {
    c.out(c.A, { yPercent: 0 }, { yPercent: -100, ease: "power3.inOut" });
    c.in(c.B, { yPercent: 100 }, { yPercent: 0, ease: "power3.inOut" });
  } },
  { name: "Push with overshoot", d: 0.55, fn: (c) => {
    c.out(c.A, { xPercent: 0 }, { xPercent: -100, ease: "power3.in" }, 0, c.D * 0.6);
    c.in(c.B, { xPercent: 100 }, { xPercent: 0, ease: "back.out(1.3)" });
  } },
  { name: "Whip pan", d: 0.3, fn: (c) => {
    c.out(c.A, { xPercent: 0, filter: "blur(0px)" }, { xPercent: -100, filter: "blur(16px)", ease: "expo.in" });
    c.in(c.B, { xPercent: 100, filter: "blur(16px)" }, { xPercent: 0, filter: "blur(0px)", ease: "expo.out" });
  } },
  { name: "Parallax slide", d: 0.5, fn: (c) => {
    c.out(c.A, { xPercent: 0, opacity: 1 }, { xPercent: -30, opacity: 0.3, ease: "power3.inOut" });
    c.in(c.B, { xPercent: 100 }, { xPercent: 0, ease: "power3.inOut" });
  } },
  { name: "Card stacks on top", d: 0.45, fn: (c) => {
    c.out(c.A, { scale: 1, opacity: 1 }, { scale: 0.9, opacity: 0.25, ease: "power2.inOut" });
    c.in(c.B, { yPercent: 100 }, { yPercent: 0, ease: "power3.out" });
  } },
  { name: "Top card lifts off", d: 0.45, aTop: true, fn: (c) => {
    c.out(c.A, { yPercent: 0 }, { yPercent: -100, ease: "power3.in" });
    c.in(c.B, { scale: 0.93, opacity: 0.3 }, { scale: 1, opacity: 1, ease: "power2.out" });
  } },
  { name: "Squeeze", d: 0.45, fn: (c) => {
    c.A.style.transformOrigin = "0 50%"; c.B.style.transformOrigin = "100% 50%";
    c.out(c.A, { scaleX: 1 }, { scaleX: 0, ease: "power3.inOut" });
    c.in(c.B, { scaleX: 0 }, { scaleX: 1, ease: "power3.inOut" });
  } },
  { name: "Terminal scroll", d: 0.42, fn: (c) => {
    c.out(c.A, { yPercent: 0 }, { yPercent: -100, ease: "steps(9)" });
    c.in(c.B, { yPercent: 100 }, { yPercent: 0, ease: "steps(9)" });
  } },

  // ---- scale and space
  { name: "Zoom through", d: 0.4, fn: (c) => {
    c.out(c.A, { scale: 1, opacity: 1 }, { scale: 1.6, opacity: 0, ease: "power3.in" });
    c.in(c.B, { scale: 0.75, opacity: 0 }, { scale: 1, opacity: 1, ease: "power3.out" });
  } },
  { name: "Zoom out", d: 0.45, aTop: true, fn: (c) => {
    c.out(c.A, { scale: 1, opacity: 1 }, { scale: 0.6, opacity: 0, ease: "power3.in" });
    c.in(c.B, { scale: 1.2 }, { scale: 1, ease: "power3.out" });
  } },
  { name: "Card flip", d: 0.55, fn: (c) => {
    c.A.parentElement.style.perspective = "1800px"; c.B.parentElement.style.perspective = "1800px";
    c.out(c.A, { rotationY: 0, opacity: 1 }, { rotationY: -90, ease: "power2.in" }, 0, c.D / 2);
    c.tl.set(c.A, { opacity: 0 }, c.T + c.D / 2);
    c.in(c.B, { rotationY: 90, opacity: 0 }, { rotationY: 0, opacity: 1, ease: "power2.out" }, c.D / 2, c.D / 2);
  } },
  { name: "Gravity drop", d: 0.5, aTop: true, fn: (c) => {
    c.out(c.A, { yPercent: 0, rotation: 0 }, { yPercent: 120, rotation: 5, ease: "power3.in" });
  } },

  // ---- wipes and masks
  { name: "Wipe, hard edge", d: 0.35, fn: (c) => c.in(c.B, { clipPath: "inset(0 0 0 100%)" }, { clipPath: "inset(0 0 0 0%)", ease: "power3.inOut" }) },
  { name: "Wipe, orange edge", d: 0.4, fn: (c) => {
    c.in(c.B, { clipPath: "inset(0 0 0 100%)" }, { clipPath: "inset(0 0 0 0%)", ease: "power3.inOut" });
    const bar = c.ov(`left:0;top:0;width:14px;height:${H}px;background:${SIGNAL}`);
    c.tl.fromTo(bar, { x: W }, { x: -14, duration: c.D, ease: "power3.inOut" }, c.T);
  } },
  { name: "Diagonal wipe", d: 0.4, fn: (c) => c.in(c.B, { clipPath: "polygon(130% 0%, 130% 0%, 100% 100%, 100% 100%)" }, { clipPath: "polygon(-30% 0%, 130% 0%, 100% 100%, -60% 100%)", ease: "power3.inOut" }) },
  { name: "Circle iris", d: 0.5, fn: (c) => c.in(c.B, { clipPath: "circle(0% at 50% 45%)" }, { clipPath: "circle(90% at 50% 45%)", ease: "power2.inOut" }) },
  { name: "Clock wipe", d: 0.6, fn: (c) => c.mask((v) => {
    const a = v * 360;
    c.setMask(c.B, v >= 1 ? "none" : `conic-gradient(#000 ${a}deg, transparent ${a}deg)`);
  }, "power1.inOut") },
  { name: "Barn doors", d: 0.4, fn: (c) => c.in(c.B, { clipPath: "inset(0 50% 0 50%)" }, { clipPath: "inset(0 0% 0 0%)", ease: "power3.inOut" }) },
  { name: "Orange line opens", d: 0.55, fn: (c) => {
    const line = c.ov(`left:0;top:${H / 2 - 3}px;width:${W}px;height:6px;background:${SIGNAL};transform-origin:0 50%`);
    c.tl.fromTo(line, { scaleX: 0, opacity: 1 }, { scaleX: 1, duration: c.D * 0.45, ease: "power3.inOut" }, c.T);
    c.tl.to(line, { opacity: 0, duration: 0.08 }, c.T + c.D - 0.08);
    c.in(c.B, { clipPath: "inset(50% 0 50% 0)" }, { clipPath: "inset(0% 0 0% 0)", ease: "power3.out" }, c.D * 0.45, c.D * 0.55);
  } },
  { name: "Scanline", d: 0.5, fn: (c) => {
    c.in(c.B, { clipPath: "inset(0 0 100% 0)" }, { clipPath: "inset(0 0 0% 0)", ease: "none" });
    const line = c.ov(`left:0;top:0;width:${W}px;height:4px;background:${SIGNAL};box-shadow:0 0 30px ${SIGNAL}`);
    c.tl.fromTo(line, { y: 0 }, { y: H, duration: c.D, ease: "none" }, c.T);
  } },
  { name: "Horizontal slats", d: 0.45, fn: (c) => c.mask((v) => {
    const p = (v * 100).toFixed(1);
    c.setMask(c.B, v >= 1 ? "none" : `linear-gradient(#000 ${p}%, transparent ${p}%)`, "100% 90px");
  }) },
  { name: "Vertical slats", d: 0.45, fn: (c) => c.mask((v) => {
    const p = (v * 100).toFixed(1);
    c.setMask(c.B, v >= 1 ? "none" : `linear-gradient(to right, #000 ${p}%, transparent ${p}%)`, "90px 100%");
  }) },

  // ---- colour panels and light
  { name: "Orange panel sweeps", d: 0.5, fn: (c) => {
    const p = c.ov(`left:0;top:0;width:${W}px;height:${H}px;background:${SIGNAL}`);
    c.tl.fromTo(p, { xPercent: 100 }, { xPercent: 0, duration: c.D / 2, ease: "power3.in" }, c.T);
    c.tl.to(p, { xPercent: -100, duration: c.D / 2, ease: "power3.out" }, c.T + c.D / 2);
    c.swap();
  } },
  { name: "Heat panels, staggered", d: 0.6, fn: (c) => {
    HEAT.forEach((col, k) => {
      const p = c.ov(`left:0;top:0;width:${W}px;height:${H}px;background:${col}`);
      c.tl.fromTo(p, { yPercent: 100 }, { yPercent: 0, duration: 0.22, ease: "power3.in" }, c.T + k * 0.03);
      c.tl.to(p, { yPercent: -100, duration: 0.22, ease: "power3.out" }, c.T + 0.3 + (3 - k) * 0.03);
    });
    c.swap(0.28);
  } },
  { name: "Staggered blocks", d: 0.55, fn: (c) => c.cells(270, (x, y) => x + y, () => RULE) },
  { name: "Overexposure", d: 0.45, fn: (c) => {
    c.out(c.A, { filter: "brightness(1)" }, { filter: "brightness(6)", ease: "power2.in" }, 0, c.D / 2);
    c.in(c.B, { opacity: 0, filter: "brightness(6)" }, { opacity: 1, filter: "brightness(1)", ease: "power2.out" }, c.D / 2, c.D / 2);
  } },
  { name: "Light leak", d: 0.6, fn: (c) => {
    const p = c.ov(`left:-700px;top:-500px;width:2500px;height:2400px;background:radial-gradient(closest-side, ${SIGNAL}, rgba(255,91,36,0.55) 45%, rgba(255,91,36,0) 100%)`);
    c.tl.fromTo(p, { xPercent: 55, opacity: 0 }, { xPercent: -25, opacity: 1, duration: c.D * 0.6, ease: "sine.in" }, c.T);
    c.tl.to(p, { xPercent: -60, opacity: 0, duration: c.D * 0.4, ease: "sine.out" }, c.T + c.D * 0.6);
    c.swap();
  } },
  { name: "Chromatic split", d: 0.35, opaque: false, fn: (c) => {
    c.out(c.ai, { opacity: 1, filter: "drop-shadow(0px 0 0 rgba(255,40,60,0)) drop-shadow(0px 0 0 rgba(40,220,255,0))" }, { opacity: 0, filter: "drop-shadow(28px 0 0 rgba(255,40,60,0.9)) drop-shadow(-28px 0 0 rgba(40,220,255,0.9))", ease: "power2.in" }, 0, c.D * 0.6);
    c.in(c.bi, { opacity: 0, filter: "drop-shadow(28px 0 0 rgba(255,40,60,0.9)) drop-shadow(-28px 0 0 rgba(40,220,255,0.9))" }, { opacity: 1, filter: "drop-shadow(0px 0 0 rgba(255,40,60,0)) drop-shadow(0px 0 0 rgba(40,220,255,0))", ease: "power2.out" }, c.D * 0.4, c.D * 0.6);
  } },
  { name: "Glitch", d: 0.3, fn: (c) => {
    const r = seeded(7);
    for (let k = 0; k < 6; k++) {
      const t = c.T + (k * c.D) / 6;
      const top = Math.floor(r() * 60), bottom = Math.floor(r() * 30);
      const el = k < 3 ? c.A : c.B;
      c.tl.set(el, { x: (r() - 0.5) * 90, clipPath: k < 3 ? `inset(${top}% 0 ${bottom}% 0)` : `inset(${bottom}% 0 ${top}% 0)` }, t);
    }
    c.tl.set(c.B, { x: 0, clipPath: "inset(0% 0 0% 0)" }, c.T + c.D);
    c.tl.fromTo(c.B, { opacity: 0 }, { opacity: 1, duration: 0.001 }, c.T + c.D / 2);
  } },

  // ---- made for this film: its own data marks
  { name: "Contribution grid, left to right", d: 0.6, fn: (c) => c.cells(90, (x) => x, heatAt(11)) },
  { name: "Contribution grid, random", d: 0.6, fn: (c) => c.cells(90, randOrder(23), heatAt(13)) },
  { name: "Contribution squares grow", d: 0.5, fn: (c) => c.mask((v) => {
    const a = (50 * (1 - v)).toFixed(1), b = (50 * (1 + v)).toFixed(1);
    if (v >= 1) { c.setMask(c.B, "none"); c.B.style.webkitMaskComposite = c.B.style.maskComposite = ""; return; }
    const g = (dir) => `linear-gradient(${dir}, transparent ${a}%, #000 ${a}%, #000 ${b}%, transparent ${b}%)`;
    c.setMask(c.B, `${g("to right")}, ${g("to bottom")}`, "90px 90px");
    c.B.style.webkitMaskComposite = "source-in"; c.B.style.maskComposite = "intersect";
  }) },
  { name: "Punchcard dots", d: 0.5, fn: (c) => c.mask((v) => {
    const r = (v * 66).toFixed(1);
    c.setMask(c.B, v >= 1 ? "none" : `radial-gradient(circle, #000 ${r}px, transparent ${r}px)`, "90px 90px");
  }) },
  { name: "Bar chart wipe", d: 0.6, fn: (c) => {
    const n = 12, w = W / n;
    const hs = [0.75, 0.5, 1, 0.65, 0.9, 0.4, 0.8, 1, 0.55, 0.95, 0.6, 0.85];
    for (let k = 0; k < n; k++) {
      const col = c.ov(`left:${k * w}px;bottom:0;width:${w + 1}px;height:${H}px;background:${HEAT[k % 4]};transform-origin:50% 100%`);
      c.tl.fromTo(col, { scaleY: 0 }, { scaleY: 1, duration: 0.2 + 0.08 * hs[k], ease: "power3.in" }, c.T + k * 0.008);
      c.tl.to(col, { yPercent: -100, duration: 0.2, ease: "power3.out" }, c.T + 0.34 + k * 0.004);
    }
    c.swap(0.33);
  } },
  { name: "Diff rows", d: 0.65, fn: (c) => {
    const rows = 22, h = H / rows, r = seeded(31);
    for (let k = 0; k < rows; k++) {
      const add = r() > 0.42;
      const el = c.ov(`left:0;top:${k * h}px;width:${W}px;height:${h + 1}px;background:${add ? "#22352a" : "#3d2425"};color:${add ? ADD : DEL};font:700 34px JBMono,monospace;line-height:${h}px;padding-left:84px;box-sizing:border-box;transform-origin:0 50%`, add ? "+" : "-");
      c.tl.fromTo(el, { scaleX: 0 }, { scaleX: 1, duration: 0.14, ease: "power3.out" }, c.T + (k / rows) * 0.2);
      c.tl.to(el, { xPercent: add ? 100 : -100, duration: 0.18, ease: "power3.in" }, c.T + 0.36 + (k / rows) * 0.1);
    }
    c.swap(0.34);
  } },
  { name: "Terminal clear", d: 0.6, fn: (c) => {
    const p = c.ov(`left:0;top:0;width:${W}px;height:${H}px;background:${GROUND};font:500 44px JBMono,monospace;color:${INK};padding:96px 84px;box-sizing:border-box`,
      `<span style="color:${MUTED}">~ $</span> <span class="t" style="display:inline-block;clip-path:inset(0 100% 0 0)">git log -1</span>`);
    c.tl.fromTo(p, { opacity: 0 }, { opacity: 1, duration: 0.001 }, c.T);
    c.tl.fromTo(p.querySelector(".t"), { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.3, ease: "steps(10)" }, c.T + 0.03);
    c.tl.to(p, { opacity: 0, duration: 0.001 }, c.T + c.D - 0.02);
    c.swap(c.D - 0.04);
  } },

  // ---- GitHub marks, second batch (#19364821): he picked 42, 43, 46, 47, so full-frame covers built
  // from what GitHub draws. DATA is the story's real numbers, passed in by the reel.
  // contribution graph
  { name: "Your real 2026, day by day", d: 0.8, fn: (c) => {
    const lv = dayLevels(DATA.calendar);
    c.cells(67.5, (x, y, cols) => y * cols + x, (x, y, cols) => lv[y * cols + x] || RULE);
  } },
  { name: "Your real 2026, week columns", d: 0.8, fn: (c) => {
    const lv = dayLevels(DATA.calendar), off = (new Date(DATA.calendar[0][0] + "T00:00:00Z").getUTCDay());
    const cols = Math.ceil((lv.length + off) / 7), w = W / cols, h = H / 7;
    const at = (x, y) => lv[x * 7 + y - off] || RULE;
    c.tiles(w, h, (x) => x, at);
  } },
  { name: "Contribution grid, GitHub green", d: 0.6, fn: (c) => c.cells(90, (x) => x, heatFrom(11, GREEN)) },
  { name: "Grid rain", d: 0.85, fn: (c) => {
    const r = seeded(41), colour = heatAt(17), size = 90;
    for (let x = 0; x < 12; x++) { const j = r() * 0.08; for (let y = 0; y < 15; y++) {
      const el = c.ov(`left:${x * size}px;top:${y * size}px;width:${size + 1}px;height:${size + 1}px;background:${colour(x, y)}`);
      c.tl.fromTo(el, { y: -1500 }, { y: 0, duration: 0.2, ease: "power2.in" }, c.T + j + ((14 - y) / 14) * 0.2);
      c.tl.to(el, { y: 1500, duration: 0.22, ease: "power2.in" }, c.T + 0.54 + j + ((14 - y) / 14) * 0.06);
    } }
    c.swap(0.5);
  } },
  { name: "Streak snake eats the grid", d: 0.95, fn: (c) => {
    const size = 135, cols = 8, rows = 10, L = 9;
    const cell = (i) => { const y = Math.floor(i / cols), k = i % cols; return [y % 2 ? cols - 1 - k : k, y]; };
    const seg = [];
    for (let k = 0; k < L; k++) seg.push(c.ov(`left:0;top:0;width:${size - 14}px;height:${size - 14}px;border-radius:14px;background:${k === 0 ? SIGNAL : HEAT[Math.max(0, 3 - Math.floor(k / 2.5))]}`));
    c.mask((v) => {
      const p = v * (cols * rows + L);
      let d = "";
      for (let i = 0; i < Math.floor(p - L); i++) { const [x, y] = cell(Math.min(i, cols * rows - 1)); d += `M${x * size} ${y * size}h${size + 1}v${size + 1}h-${size + 1}z`; }
      c.B.style.clipPath = v >= 1 ? "none" : `path("${d || "M0 0"}")`;
      seg.forEach((el, k) => {
        const i = Math.floor(p) - k;
        if (i < 0 || i >= cols * rows) { el.style.opacity = 0; return; }
        const [x, y] = cell(i);
        el.style.opacity = 1; el.style.transform = `translate(${x * size + 7}px,${y * size + 7}px)`;
      });
    }, "none");
  } },
  { name: "Heat ripple from the middle", d: 0.7, fn: (c) => {
    const dist = (x, y, cols, rows) => Math.hypot(x - (cols - 1) / 2, y - (rows - 1) / 2);
    c.cells(90, dist, (x, y, cols, rows) => HEAT[3 - Math.floor(dist(x, y, cols, rows) / 2.2) % 4]);
  } },
  { name: "Contribution tiles flip", d: 0.85, fn: (c) => {
    const size = 135, colour = heatAt(29);
    for (let y = 0; y < 10; y++) for (let x = 0; x < 8; x++) {
      const f = (x + y) / 16;
      const el = c.ov(`left:${x * size}px;top:${y * size}px;width:${size + 1}px;height:${size + 1}px;background:${colour(x, y)}`);
      c.tl.fromTo(el, { rotationY: -90, transformPerspective: 900 }, { rotationY: 0, duration: 0.16, ease: "power2.out" }, c.T + f * 0.28);
      c.tl.to(el, { rotationY: 90, duration: 0.16, ease: "power2.in" }, c.T + 0.46 + f * 0.22);
    }
    c.swap(0.45);
  } },
  { name: "Grid heats up, level by level", d: 0.85, fn: (c) => {
    const r = randOrder(37), size = 90;
    for (let y = 0; y < 15; y++) for (let x = 0; x < 12; x++) {
      const f = r(x, y) * 0.14;
      const el = c.ov(`left:${x * size}px;top:${y * size}px;width:${size + 1}px;height:${size + 1}px;opacity:0`);
      c.tl.fromTo(el, { opacity: 0, backgroundColor: HEAT[0] }, { opacity: 1, duration: 0.001 }, c.T + f);
      HEAT.slice(1).forEach((col, k) => c.tl.set(el, { backgroundColor: col }, c.T + f + (k + 1) * 0.09));
      c.tl.to(el, { opacity: 0, duration: 0.001 }, c.T + 0.6 + r(y + 40, x) * 0.24);
    }
    c.swap(0.5);
  } },

  // diffs
  { name: "Real diff of your year", d: 0.95, fn: (c) => {
    const rows = DATA.stats.flatMap(([k, v]) => [["-", `${k}: 0`], ["+", `${k}: ${v}`]]), h = H / rows.length;
    rows.forEach(([s, text], k) => {
      const add = s === "+";
      const el = c.ov(`left:0;top:${k * h}px;width:${W}px;height:${h + 1}px;background:${add ? ADDBG : DELBG};color:${add ? ADD : DEL};font:600 38px JBMono,monospace;line-height:${h}px;padding-left:60px;box-sizing:border-box;white-space:pre;clip-path:inset(0 100% 0 0)`, `${s}  ${esc(text)}`);
      c.tl.fromTo(el, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.14, ease: "power3.out" }, c.T + (k / rows.length) * 0.22);
      c.tl.to(el, { xPercent: add ? 100 : -100, duration: 0.2, ease: "power3.in" }, c.T + 0.66 + (k / rows.length) * 0.09);
    });
    c.swap(0.5);
  } },
  { name: "Split diff closes", d: 0.8, fn: (c) => {
    const n = DATA.stats.length, h = H / n;
    for (let k = 0; k < n; k++) {
      const [key, v] = DATA.stats[k];
      [[0, DELBG, DEL, `- ${key}: 0`, -100], [W / 2, ADDBG, ADD, `+ ${key}: ${v}`, 100]].forEach(([left, bg, col, text, from]) => {
        const el = c.ov(`left:${left}px;top:${k * h}px;width:${W / 2 + 1}px;height:${h + 1}px;background:${bg};color:${col};font:500 32px JBMono,monospace;line-height:${h}px;padding-left:26px;box-sizing:border-box;white-space:nowrap;overflow:hidden`, esc(text));
        c.tl.fromTo(el, { xPercent: from }, { xPercent: 0, duration: 0.2, ease: "power3.out" }, c.T + (k / n) * 0.14);
        c.tl.to(el, { xPercent: from, duration: 0.2, ease: "power3.in" }, c.T + 0.5 + (k / n) * 0.1);
      });
    }
    c.swap(0.42);
  } },
  { name: "Hunk header splits red and green", d: 0.85, fn: (c) => {
    const n = 11, h = (H - 90) / (n * 2), top = H / 2 - 45;
    for (let k = 0; k < n; k++) {
      [[top - (k + 1) * h, DELBG, DEL, "-"], [top + 90 + k * h, ADDBG, ADD, "+"]].forEach(([y, bg, col, s]) => {
        const el = c.ov(`left:0;top:${y}px;width:${W}px;height:${h + 1}px;background:${bg};color:${col};font:700 30px JBMono,monospace;line-height:${h}px;padding-left:60px;box-sizing:border-box`, s);
        c.tl.fromTo(el, { scaleY: 0 }, { scaleY: 1, duration: 0.07, ease: "none" }, c.T + 0.1 + (k / n) * 0.3);
        c.tl.to(el, { xPercent: s === "+" ? 100 : -100, duration: 0.2, ease: "power3.in" }, c.T + 0.56 + ((n - k) / n) * 0.09);
      });
    }
    const bar = c.ov(`left:0;top:${top}px;width:${W}px;height:91px;background:#1c2a3a;color:#8fb8e0;font:600 36px JBMono,monospace;line-height:90px;padding-left:60px;box-sizing:border-box;z-index:5001`, "@@ -1,11 +1,11 @@");
    c.tl.fromTo(bar, { scaleX: 0, transformOrigin: "0 50%" }, { scaleX: 1, duration: 0.1, ease: "power3.out" }, c.T);
    c.tl.to(bar, { opacity: 0, duration: 0.05 }, c.T + 0.66);
    c.swap(0.46);
  } },
  { name: "All red, then all green", d: 0.85, fn: (c) => {
    const n = 22, h = H / n;
    for (let k = 0; k < n; k++) {
      const f = k / n;
      const red = c.ov(`left:0;top:${k * h}px;width:${W}px;height:${h + 1}px;background:${DELBG};color:${DEL};font:700 34px JBMono,monospace;line-height:${h}px;padding-left:60px;box-sizing:border-box;transform-origin:0 50%`, "-");
      c.tl.fromTo(red, { scaleX: 0 }, { scaleX: 1, duration: 0.12, ease: "power3.out" }, c.T + f * 0.16);
      const add = c.ov(`left:0;top:${k * h}px;width:${W}px;height:${h + 1}px;background:${ADDBG};color:${ADD};font:700 34px JBMono,monospace;line-height:${h}px;padding-left:60px;box-sizing:border-box;transform-origin:0 50%`, "+");
      c.tl.fromTo(add, { scaleX: 0 }, { scaleX: 1, duration: 0.12, ease: "power3.out" }, c.T + 0.24 + f * 0.16);
      c.tl.set(red, { opacity: 0 }, c.T + 0.5);
      c.tl.to(add, { xPercent: 100, duration: 0.2, ease: "power3.in" }, c.T + 0.56 + f * 0.09);
    }
    c.swap(0.5);
  } },
  { name: "Your lines, added against removed", d: 0.95, fn: (c) => {
    const a = DATA.added / (DATA.added + DATA.removed), split = H * a;
    const big = "font:800 170px Bricolage,sans-serif;font-stretch:75%;display:flex;align-items:center;justify-content:center;";
    const g = c.ov(`left:0;top:0;width:${W}px;height:${split + 1}px;background:${ADDBG};color:${ADD};${big}`, `+${DATA.added.toLocaleString("en-US")}`);
    const r = c.ov(`left:0;top:${split}px;width:${W}px;height:${H - split}px;background:${DELBG};color:${DEL};${big}`, `-${DATA.removed.toLocaleString("en-US")}`);
    c.tl.fromTo(g, { xPercent: -100 }, { xPercent: 0, duration: 0.24, ease: "power3.out" }, c.T);
    c.tl.fromTo(r, { xPercent: 100 }, { xPercent: 0, duration: 0.24, ease: "power3.out" }, c.T + 0.04);
    c.tl.to(g, { yPercent: -100, duration: 0.24, ease: "power3.in" }, c.T + 0.68);
    c.tl.to(r, { yPercent: 100, duration: 0.24, ease: "power3.in" }, c.T + 0.68);
    c.swap(0.3);
  } },

  // charts from the data
  { name: "Your real months, then full height", d: 0.9, fn: (c) => {
    const n = 12, w = W / n, max = Math.max(...DATA.months);
    DATA.months.forEach((v, k) => {
      const f = Math.max(0.05, Math.sqrt(v / max));
      const el = c.ov(`left:${k * w}px;bottom:0;width:${w + 1}px;height:${H}px;background:${v === max ? SIGNAL : HEAT[Math.min(2, Math.floor(f * 3))]};transform-origin:50% 100%`);
      const lab = c.ov(`left:${k * w}px;bottom:18px;width:${w}px;text-align:center;font:600 38px JBMono,monospace;color:${INK};z-index:5001`, "JFMAMJJASOND"[k]);
      c.tl.fromTo(el, { scaleY: 0 }, { scaleY: f, duration: 0.22, ease: "power3.out" }, c.T + k * 0.008);
      c.tl.to(el, { scaleY: 1, duration: 0.18, ease: "power3.in" }, c.T + 0.36 + k * 0.006);
      c.tl.to(el, { yPercent: -100, duration: 0.2, ease: "power3.out" }, c.T + 0.64 + k * 0.004);
      c.tl.to(lab, { opacity: 0, duration: 0.05 }, c.T + 0.62);
    });
    c.swap(0.62);
  } },
  { name: "Your year's sparkline floods", d: 0.9, fn: (c) => {
    const w = DATA.weeks, max = Math.max(...w), pts = w.map((v, k) => [(k / (w.length - 1)) * W, H - 120 - Math.sqrt(v / max) * (H - 300)]);
    const line = pts.map((p) => p.map((x) => x.toFixed(1)).join(",")).join(" ");
    const s = c.ov(`left:0;top:0;width:${W}px;height:${H}px`, `<svg width="${W}" height="${H}" style="position:absolute;inset:0"><polygon points="0,${H} ${line} ${W},${H}" fill="${HEAT[0]}" /><polyline points="${line}" fill="none" stroke="${SIGNAL}" stroke-width="10" stroke-linejoin="round"/></svg>`);
    c.tl.fromTo(s, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.34, ease: "power1.inOut" }, c.T);
    const p = c.ov(`left:0;top:0;width:${W}px;height:${H}px;background:${HEAT[0]}`);
    c.tl.fromTo(p, { yPercent: 100 }, { yPercent: 0, duration: 0.2, ease: "power3.in" }, c.T + 0.36);
    c.tl.set(s, { opacity: 0 }, c.T + 0.57);
    c.tl.to(p, { yPercent: -100, duration: 0.24, ease: "power3.out" }, c.T + 0.64);
    c.swap(0.6);
  } },
  { name: "Your language bar opens", d: 0.95, fn: (c) => {
    const box = c.ov(`left:0;top:0;width:${W}px;height:${H}px`);
    const total = DATA.languages.reduce((a, r) => a + r[1], 0);
    let x = 0;
    DATA.languages.forEach(([name, v], k) => {
      const w = (v / total) * W, col = LANG[name] || LANG.other;
      const s = document.createElement("div");
      s.style.cssText = `position:absolute;left:${x}px;top:0;width:${w + 1}px;height:${H}px;background:${col};color:${name === "JavaScript" ? GROUND : "#fff"};font:800 74px Bricolage,sans-serif;font-stretch:75%;writing-mode:vertical-rl;display:flex;align-items:center;justify-content:center`;
      s.textContent = name; box.appendChild(s);
      c.tl.to(s, { yPercent: k % 2 ? 100 : -100, duration: 0.22, ease: "power3.in" }, c.T + 0.68 + k * 0.012);
      x += w;
    });
    c.tl.fromTo(box, { clipPath: "inset(49% 100% 49% 0%)" }, { clipPath: "inset(49% 0% 49% 0%)", duration: 0.24, ease: "power3.out" }, c.T);
    c.tl.to(box, { clipPath: "inset(0% 0% 0% 0%)", duration: 0.2, ease: "power3.inOut" }, c.T + 0.3);
    c.swap(0.52);
  } },
  { name: "Your real punchcard swells", d: 0.9, fn: (c) => {
    const g = DATA.punchcard, max = Math.max(...g.flat()), cw = W / 7, ch = H / 24, D = 260;
    g.forEach((row, x) => row.forEach((v, y) => {
      const level = v === 0 ? HEAT[0] : HEAT[Math.min(3, Math.floor((v / max) * 4))];
      const el = c.ov(`left:${(x + 0.5) * cw - D / 2}px;top:${(y + 0.5) * ch - D / 2}px;width:${D}px;height:${D}px;border-radius:50%;background:${level}`);
      c.tl.fromTo(el, { scale: 0 }, { scale: 0.03 + (v / max) * 0.2, duration: 0.2, ease: "back.out(1.6)" }, c.T);
      c.tl.to(el, { scale: 1, duration: 0.2, ease: "power2.in" }, c.T + 0.28 + ((max - v) / max) * 0.06);
      c.tl.to(el, { scale: 0, duration: 0.2, ease: "power2.in" }, c.T + 0.66 + (v / max) * 0.04);
    }));
    c.swap(0.6);
  } },

  // git
  { name: "Git graph rails", d: 0.95, fn: (c) => {
    const n = 6, w = W / n, col = [SIGNAL, ADD, "#8fb8e0", HEAT[2], DEL, "#c9a6ff"];
    const curve = (a, b, y) => `M${(a + 0.5) * w} ${y} C${(a + 0.5) * w} ${y + 120} ${(b + 0.5) * w} ${y + 90} ${(b + 0.5) * w} ${y + 210}`;
    const links = [[0, 1, 150, 0], [1, 2, 620, 1], [3, 2, 300, 3], [4, 3, 840, 4], [5, 4, 480, 5]];
    const svg = c.ov(`left:0;top:0;width:${W}px;height:${H}px;z-index:5002`, `<svg width="${W}" height="${H}">${links.map(([a, b, y, k]) => `<path d="${curve(a, b, y)}" fill="none" stroke="${col[k]}" stroke-width="12"/>`).join("")}</svg>`);
    c.tl.fromTo(svg, { clipPath: "inset(0 0 100% 0)" }, { clipPath: "inset(0 0 0% 0)", duration: 0.34, ease: "power1.inOut" }, c.T);
    c.tl.to(svg, { opacity: 0, duration: 0.03 }, c.T + 0.42);
    const r = seeded(53);
    col.forEach((colr, k) => {
      const rail = c.ov(`left:${k * w}px;top:0;width:${w + 1}px;height:${H}px;background:${colr};transform-origin:50% 0;clip-path:inset(0 46.5% 0 46.5%)`);
      c.tl.fromTo(rail, { scaleY: 0 }, { scaleY: 1, duration: 0.3, ease: "power1.inOut" }, c.T + k * 0.012);
      c.tl.fromTo(rail, { clipPath: "inset(0 46.5% 0 46.5%)" }, { clipPath: "inset(0 0% 0 0%)", duration: 0.14, ease: "power3.in", immediateRender: false }, c.T + 0.38);
      c.tl.to(rail, { clipPath: "inset(0 50% 0 50%)", duration: 0.2, ease: "power3.out" }, c.T + 0.68 + k * 0.008);
      for (let d = 0; d < 5; d++) {
        const dot = c.ov(`left:${(k + 0.5) * w - 21}px;top:${100 + d * 250 + r() * 90}px;width:42px;height:42px;border-radius:50%;background:${GROUND};border:10px solid ${colr};box-sizing:border-box;z-index:5003`);
        c.tl.fromTo(dot, { scale: 0 }, { scale: 1, duration: 0.08, ease: "back.out(2)" }, c.T + 0.05 + d * 0.06);
        c.tl.to(dot, { opacity: 0, duration: 0.03 }, c.T + 0.42);
      }
    });
    c.swap(0.55);
  } },
  { name: "Branch opens, merges past the frame", d: 0.85, fn: (c) => {
    const svg = c.ov(`left:0;top:0;width:${W}px;height:${H}px;z-index:5001`, `<svg width="${W}" height="${H}"><path class="a" fill="none" stroke="${SIGNAL}" stroke-width="10"/><path class="b" fill="none" stroke="${ADD}" stroke-width="10"/><circle class="o" r="26" fill="${GROUND}" stroke="${SIGNAL}" stroke-width="10"/><circle class="p" r="26" fill="${GROUND}" stroke="${ADD}" stroke-width="10"/></svg>`);
    const pa = svg.querySelector(".a"), pb = svg.querySelector(".b"), o = svg.querySelector(".o"), q = svg.querySelector(".p");
    const edge = (A, s) => { const out = []; for (let i = 0; i <= 40; i++) { const y = (i / 40) * H; out.push([W / 2 + s * A * (0.35 + 0.65 * Math.sin((Math.PI * i) / 40)), y]); } return out; };
    c.mask((v) => {
      const draw = Math.min(1, v / 0.3), A = Math.max(0, (v - 0.3) / 0.7) ** 2.2 * 2100;
      const l = edge(A, -1), r = edge(A, 1), str = (e) => e.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" L");
      c.B.style.clipPath = v >= 1 ? "none" : `polygon(${[...l, ...r.reverse()].map((p) => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(",")})`;
      r.reverse();
      const clipDraw = `inset(0 0 ${(100 - draw * 100).toFixed(1)}% 0)`;
      svg.style.clipPath = clipDraw;
      pa.setAttribute("d", "M" + str(l)); pb.setAttribute("d", "M" + str(r));
      [o, q].forEach((dot, k) => { dot.setAttribute("cx", (k ? r : l)[20][0]); dot.setAttribute("cy", H / 2); });
    }, "none");
  } },
  { name: "git log rush", d: 0.85, fn: (c) => {
    const n = DATA.log.length, h = H / n;
    for (let k = 0; k < n; k++) {
      const [hash, msg] = DATA.log[k];
      const el = c.ov(`left:0;top:${k * h}px;width:${W}px;height:${h + 1}px;background:${GROUND};color:${INK};font:500 34px JBMono,monospace;line-height:${h}px;padding-left:50px;box-sizing:border-box;white-space:pre;overflow:hidden`, `<span style="color:${SIGNAL}">${esc(hash)}</span>  ${esc(msg)}`);
      c.tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.001 }, c.T + (k / n) * 0.42);
      c.tl.to(el, { y: -H, duration: 0.26, ease: "steps(9)" }, c.T + 0.58);
    }
    c.swap(0.46);
  } },
  { name: "Merge button goes purple", d: 0.95, fn: (c) => {
    const pill = c.ov(`left:${W / 2 - 300}px;top:${H / 2 - 62}px;width:600px;height:124px;border-radius:62px;background:#238636;color:#fff;font:700 48px Bricolage,sans-serif;display:flex;align-items:center;justify-content:center`, `<span class="a" style="position:absolute">Merge pull request</span><span class="b" style="position:absolute;opacity:0">Merged</span>`);
    c.tl.fromTo(pill, { scale: 0 }, { scale: 1, duration: 0.14, ease: "back.out(2)" }, c.T);
    c.tl.set(pill, { backgroundColor: "#8957e5" }, c.T + 0.28);
    c.tl.set(pill.querySelector(".a"), { opacity: 0 }, c.T + 0.28);
    c.tl.set(pill.querySelector(".b"), { opacity: 1 }, c.T + 0.28);
    c.tl.to(pill.querySelector(".b"), { opacity: 0, duration: 0.05 }, c.T + 0.42);
    c.tl.to(pill, { scale: 14, duration: 0.2, ease: "power3.in" }, c.T + 0.42);
    c.tl.to(pill, { y: -2400, duration: 0.2, ease: "power3.in" }, c.T + 0.74);
    c.swap(0.62);
  } },

  // Actions
  { name: "CI checks pass", d: 0.95, fn: (c) => {
    const names = DATA.jobs, n = names.length, h = H / n;
    const tick = `<svg width="46" height="46" viewBox="0 0 16 16" style="position:absolute;left:44px;top:${(h - 46) / 2}px"><path d="M3 8.5l3.2 3.2L13 4.6" fill="none" stroke="${ADD}" stroke-width="2.4"/></svg>`;
    const dot = `<div class="w" style="position:absolute;left:44px;top:${(h - 46) / 2}px;width:46px;height:46px;border-radius:50%;border:8px solid #d29922;box-sizing:border-box;background:${GROUND}"></div>`;
    names.forEach((name, k) => {
      const el = c.ov(`left:0;top:${k * h}px;width:${W}px;height:${h + 1}px;background:#1a1815;color:${INK};font:500 40px JBMono,monospace;line-height:${h}px;padding-left:120px;box-sizing:border-box;border-bottom:2px solid ${RULE}`, `${tick}${dot}${esc(name)}`);
      c.tl.fromTo(el, { xPercent: 100 }, { xPercent: 0, duration: 0.14, ease: "power3.out" }, c.T + (k / n) * 0.16);
      c.tl.set(el.querySelector(".w"), { opacity: 0 }, c.T + 0.3 + (k / n) * 0.26);
      c.tl.set(el, { backgroundColor: ADDBG }, c.T + 0.3 + (k / n) * 0.26);
      c.tl.to(el, { xPercent: -100, duration: 0.18, ease: "power3.in" }, c.T + 0.68 + (k / n) * 0.09);
    });
    c.swap(0.34);
  } },
  { name: "Run spinner, tick, iris", d: 0.95, fn: (c) => {
    const cx = W / 2, cy = H * 0.45, R = 70;
    const spin = c.ov(`left:${cx - R}px;top:${cy - R}px;width:${R * 2}px;height:${R * 2}px;border-radius:50%;border:14px solid #d29922;border-right-color:transparent;box-sizing:border-box`);
    c.tl.fromTo(spin, { rotation: 0 }, { rotation: 540, duration: 0.3, ease: "none" }, c.T);
    c.tl.set(spin, { opacity: 0 }, c.T + 0.3);
    const disc = c.ov(`left:0;top:0;width:${W}px;height:${H}px;background:#2da44e;opacity:0`);
    const tick = c.ov(`left:${cx - R}px;top:${cy - R}px;width:${R * 2}px;height:${R * 2}px;z-index:5001;opacity:0`, `<svg width="${R * 2}" height="${R * 2}" viewBox="0 0 16 16"><path d="M3.2 8.5l3.2 3.2L13 4.6" fill="none" stroke="#fff" stroke-width="2.2"/></svg>`);
    c.tl.set(tick, { opacity: 1 }, c.T + 0.3);
    c.tl.set(disc, { opacity: 1 }, c.T + 0.3);
    c.tl.to(tick, { opacity: 0, duration: 0.04 }, c.T + 0.5);
    const paint = (r0, r1) => { const m = `radial-gradient(circle at ${cx}px ${cy}px, ${r0 > 0 ? `transparent ${r0}px,` : ""} #000 ${r0}px, #000 ${r1}px, transparent ${r1}px)`; disc.style.webkitMaskImage = m; disc.style.maskImage = m; };
    paint(0, R);
    const p = { a: R, b: 0 };
    c.tl.fromTo(p, { a: R }, { a: 1500, duration: 0.2, ease: "power3.in", onUpdate: () => paint(p.b, p.a) }, c.T + 0.42);
    c.tl.fromTo(p, { b: 0 }, { b: 1500, duration: 0.3, ease: "power2.inOut", immediateRender: false, onUpdate: () => paint(p.b, p.a) }, c.T + 0.64);
    c.swap(0.63);
  } },
  { name: "Actions job timeline", d: 0.9, fn: (c) => {
    const n = 15, h = H / n, r = seeded(61), col = ["#2da44e", ADD, "#8fb8e0", "#2f6fbd", HEAT[2]];
    for (let k = 0; k < n; k++) {
      const a = r() * 62, len = 18 + r() * 34, b = Math.max(0, 100 - a - len);
      const el = c.ov(`left:0;top:${k * h}px;width:${W}px;height:${h + 1}px;background:${col[k % col.length]}`);
      c.tl.fromTo(el, { clipPath: `inset(0 ${100 - a}% 0 ${a}%)` }, { clipPath: `inset(0 ${b}% 0 ${a}%)`, duration: 0.2, ease: "power2.out" }, c.T + (k / n) * 0.14);
      c.tl.to(el, { clipPath: "inset(0 0% 0 0%)", duration: 0.16, ease: "power3.in" }, c.T + 0.36 + (k / n) * 0.05);
      c.tl.to(el, { xPercent: k % 2 ? 100 : -100, duration: 0.2, ease: "power3.in" }, c.T + 0.66 + (k / n) * 0.04);
    }
    c.swap(0.58);
  } },

  // the rest of the site
  { name: "Your identicon", d: 0.8, fn: (c) => {
    const size = 216, cols = 5, rows = 7, on = identicon(DATA.user, rows);
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const f = (Math.abs(x - 2) + y) / 8;
      const el = c.ov(`left:${x * size}px;top:${y * size}px;width:${size + 1}px;height:${size + 1}px;background:${on[y][Math.min(x, 4 - x)] ? SIGNAL : "#efe9de"}`);
      c.tl.fromTo(el, { scale: 0 }, { scale: 1, duration: 0.14, ease: "back.out(1.4)" }, c.T + f * 0.2);
      c.tl.to(el, { scale: 0, duration: 0.14, ease: "power3.in" }, c.T + 0.5 + (1 - f) * 0.16);
    }
    c.swap(0.42);
  } },
  { name: "Page load bar", d: 0.5, fn: (c) => {
    const bar = c.ov(`left:0;top:0;width:${W}px;height:8px;background:#2f81f7;transform-origin:0 50%`);
    c.tl.fromTo(bar, { scaleX: 0 }, { scaleX: 0.72, duration: 0.3, ease: "power2.out" }, c.T);
    c.tl.to(bar, { scaleX: 1, duration: 0.1, ease: "power2.in" }, c.T + 0.3);
    c.tl.to(bar, { opacity: 0, duration: 0.08 }, c.T + 0.41);
    c.swap(0.38);
  } },
  { name: "Release tag sweeps", d: 0.75, fn: (c) => {
    const notch = 300, w = W + notch + 40;
    const p = c.ov(`left:0;top:0;width:${w}px;height:${H}px;background:${SIGNAL};color:${GROUND};clip-path:polygon(0 50%,${notch}px 0,100% 0,100% 100%,${notch}px 100%);font:800 300px Bricolage,sans-serif;font-stretch:75%;display:flex;align-items:center;padding-left:${notch + 60}px;box-sizing:border-box`, `<span style="position:absolute;left:150px;top:${H / 2 - 44}px;width:88px;height:88px;border-radius:50%;background:${GROUND}"></span>v${DATA.year}`);
    c.tl.fromTo(p, { x: W }, { x: -notch + 20, duration: 0.3, ease: "power3.in" }, c.T);
    c.tl.to(p, { x: -w - 20, duration: 0.3, ease: "power3.out" }, c.T + 0.42);
    c.swap(0.34);
  } },
  { name: "Star iris", d: 0.75, fn: (c) => {
    const cx = W / 2, cy = H * 0.45;
    const svg = c.ov(`left:0;top:0;width:${W}px;height:${H}px`, `<svg width="${W}" height="${H}"><polygon fill="none" stroke="${SIGNAL}" stroke-width="16" stroke-linejoin="round"/></svg>`);
    const poly = svg.querySelector("polygon");
    const star = (R) => { const pts = []; for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + (i * Math.PI) / 5, r = i % 2 ? R * 0.42 : R; pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]); } return pts; };
    c.mask((v) => {
      const pts = star(v * 3000);
      c.B.style.clipPath = v >= 1 ? "none" : `polygon(${pts.map((p) => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(",")})`;
      poly.setAttribute("points", pts.map((p) => p.map((x) => x.toFixed(1)).join(",")).join(" "));
    }, "power2.in");
  } },
];
