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
];
