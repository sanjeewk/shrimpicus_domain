(function () {
  "use strict";

  const root = document.querySelector(".field");
  if (!root) return;

  const flowersEl = document.getElementById("flowers");
  const dogLayer = document.getElementById("dogLayer");
  const counter = document.getElementById("flowerCount");
  const slider = document.getElementById("flowerSlider");
  const number = document.getElementById("flowerNumber");
  const reset = document.getElementById("flowerReset");
  const dogToggle = document.getElementById("dogToggle");

  const MAX_RENDERED = 400;

  /* single pastel-pink daisy palette (all flowers same colour for now) */
  const PETAL = "#ffb3d9";
  const PETAL_HI = "#ffd0e8";
  const CENTER = "#ffe066";
  const STEM = "#5a9838";
  const STEM_HI = "#6cb84e";

  /* ---------- SVG symbol library (defined once, referenced many times) ---------- */

  function injectDefs() {
    const ns = "http://www.w3.org/2000/svg";
    const sprite = document.createElementNS(ns, "svg");
    sprite.setAttribute("aria-hidden", "true");
    sprite.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
    sprite.innerHTML = `
      <symbol id="fl-daisy" viewBox="0 0 16 24">
        <!-- stem -->
        <rect x="7" y="11" width="2" height="13" fill="${STEM}"/>
        <!-- leaf -->
        <rect x="9" y="15" width="4" height="2" fill="${STEM_HI}"/>
        <rect x="10" y="14" width="3" height="1" fill="${STEM_HI}"/>
        <rect x="4" y="18" width="3" height="2" fill="${STEM_HI}"/>
        <rect x="3" y="17" width="2" height="1" fill="${STEM_HI}"/>
        <!-- petals (round blob around centre 8,6) -->
        <rect x="7" y="2"  width="2" height="1" fill="${PETAL}"/>
        <rect x="6" y="3"  width="4" height="1" fill="${PETAL}"/>
        <rect x="3" y="4"  width="10" height="1" fill="${PETAL}"/>
        <rect x="2" y="5"  width="12" height="1" fill="${PETAL}"/>
        <rect x="2" y="6"  width="12" height="1" fill="${PETAL}"/>
        <rect x="2" y="7"  width="12" height="1" fill="${PETAL}"/>
        <rect x="2" y="8"  width="12" height="1" fill="${PETAL}"/>
        <rect x="3" y="9"  width="10" height="1" fill="${PETAL}"/>
        <rect x="6" y="10" width="4" height="1" fill="${PETAL}"/>
        <rect x="7" y="11" width="2" height="1" fill="${PETAL}"/>
        <!-- petal highlights -->
        <rect x="3" y="4" width="2" height="1" fill="${PETAL_HI}"/>
        <rect x="2" y="5" width="1" height="1" fill="${PETAL_HI}"/>
        <rect x="11" y="6" width="1" height="1" fill="${PETAL_HI}"/>
        <!-- centre -->
        <rect x="6" y="5" width="4" height="4" fill="${CENTER}"/>
        <rect x="7" y="6" width="1" height="1" fill="#fff4b0"/>
      </symbol>
      <symbol id="dog" viewBox="0 0 32 20">
        <!-- tail -->
        <rect class="dog-tail" x="3" y="6" width="3" height="3" fill="#e8a44c"/>
        <rect class="dog-tail" x="2" y="5" width="2" height="2" fill="#e8a44c"/>
        <!-- body -->
        <rect x="6" y="8" width="16" height="6" fill="#e8a44c"/>
        <rect x="5" y="8" width="2" height="3" fill="#e8a44c"/>
        <!-- belly -->
        <rect x="6" y="13" width="16" height="2" fill="#fff3df"/>
        <!-- head -->
        <rect x="20" y="7" width="7" height="6" fill="#e8a44c"/>
        <!-- muzzle -->
        <rect x="26" y="10" width="4" height="3" fill="#fff3df"/>
        <!-- ear -->
        <rect x="21" y="5" width="3" height="3" fill="#c97a2e"/>
        <!-- collar -->
        <rect x="19" y="12" width="4" height="1" fill="#d72638"/>
        <rect x="20" y="13" width="1" height="1" fill="#ffe066"/>
        <!-- eye + nose -->
        <rect x="24" y="9" width="1" height="1" fill="#3a2a1a"/>
        <rect x="29" y="11" width="1" height="1" fill="#3a2a1a"/>
        <!-- legs -->
        <rect class="dog-leg dog-leg--a" x="8"  y="14" width="2" height="5" fill="#e8a44c"/>
        <rect class="dog-leg dog-leg--b" x="12" y="14" width="2" height="5" fill="#d98b3a"/>
        <rect class="dog-leg dog-leg--c" x="16" y="14" width="2" height="5" fill="#e8a44c"/>
        <rect class="dog-leg dog-leg--d" x="20" y="14" width="2" height="5" fill="#d98b3a"/>
      </symbol>
    `;
    document.body.appendChild(sprite);
  }

  injectDefs();

  /* ---------- state ---------- */

  const baseCount = parseInt(root.dataset.doneCount || "0", 10) || 0;
  const stored = parseInt(localStorage.getItem("shrimpicus.flowerCount"), 10);
  let current = Number.isFinite(stored) ? stored : baseCount;
  let petalLayer = null;

  /* ---------- rendering ---------- */

  function render(n) {
    flowersEl.innerHTML = "";
    petalLayer = null;
    const w = flowersEl.clientWidth || root.clientWidth;
    const h = flowersEl.clientHeight || root.clientHeight;
    const visual = Math.min(n, MAX_RENDERED);

    // dense staggered grid (Stardew-style planted rows)
    const cellW = 30;
    const cellH = 26;
    const cols = Math.max(1, Math.floor((w + cellW / 2) / cellW));
    const startY = h - 10;           // start at front (bottom)
    const minTopY = h * 0.06;        // don't climb past the ledge

    let placed = 0;
    let row = 0;
    while (placed < visual) {
      const rowY = startY - row * cellH;
      if (rowY < minTopY) break;
      const offset = (row % 2) ? cellW / 2 : 0;
      // slight per-row depth so front rows read bigger
      const depthFactor = (startY - rowY) / (startY - minTopY || 1); // 0 front → 1 back
      for (let c = 0; c < cols && placed < visual; c++) {
        const rng = mulberry32(0x9e37 ^ (placed * 0x45d9f3b + 0x7f4a7c15));
        const jx = (rng() * 2 - 1) * 4;   // ±4px horizontal jitter
        const jy = (rng() * 2 - 1) * 3;   // ±3px vertical jitter
        const x = c * cellW + offset + jx;
        const y = rowY + jy;
        // back rows smaller, front rows bigger
        const scale = 1.25 - depthFactor * 0.55;

        const el = document.createElement("span");
        el.className = "flower";
        el.style.left = x + "px";
        el.style.top = y + "px";
        el.style.setProperty("--scale", scale.toFixed(3));
        el.style.setProperty("--sway-dur", (3 + rng() * 3.5).toFixed(2) + "s");
        el.style.setProperty("--sway-delay", (rng() * -4).toFixed(2) + "s");
        el.style.zIndex = String(Math.floor(y));
        el.innerHTML = `<svg viewBox="0 0 16 24"><use href="#fl-daisy"/></svg>`;
        el.addEventListener("click", onFlowerClick);
        flowersEl.appendChild(el);
        placed++;
      }
      row++;
    }
  }

  /* ---------- interaction ---------- */

  function onFlowerClick(e) {
    const el = e.currentTarget;
    el.classList.remove("is-bloom");
    void el.offsetWidth;
    el.classList.add("is-bloom");
    spawnPetals(el);
    chime();
  }

  function spawnPetals(el) {
    if (!petalLayer) {
      petalLayer = document.createElement("div");
      petalLayer.className = "field__petals";
      flowersEl.appendChild(petalLayer);
    }
    const rect = el.getBoundingClientRect();
    const layerRect = petalLayer.getBoundingClientRect();
    const cx = rect.left + rect.width / 2 - layerRect.left;
    const cy = rect.top + rect.height * 0.30 - layerRect.top;
    const count = 7;
    for (let i = 0; i < count; i++) {
      const p = document.createElement("span");
      p.className = "petal";
      const ang = (Math.PI * 2 * i) / count + Math.random() * 0.6;
      const dist = 22 + Math.random() * 30;
      p.style.left = cx + "px";
      p.style.top = cy + "px";
      p.style.setProperty("--dx", (Math.cos(ang) * dist).toFixed(1) + "px");
      p.style.setProperty("--dy", (Math.sin(ang) * dist - 10).toFixed(1) + "px");
      p.style.setProperty("--rot", (Math.random() * 540 - 270).toFixed(0) + "deg");
      petalLayer.appendChild(p);
      setTimeout(() => p.remove(), 1100);
    }
  }

  /* ---------- audio: soft chime ---------- */

  let audioCtx = null;
  function chime() {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === "suspended") audioCtx.resume();
      const notes = [523.25, 659.25, 783.99, 1046.5];
      const f = notes[Math.floor(Math.random() * notes.length)];
      const t = audioCtx.currentTime;
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.type = "square";
      o.frequency.value = f;
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(0.06, t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
      o.connect(g).connect(audioCtx.destination);
      o.start(t);
      o.stop(t + 0.55);
    } catch (_) {}
  }

  /* ---------- dog ---------- */

  let dogEl = null;
  let dogState = { active: false, x: -80, y: 0, dir: 1, target: null, raf: null, phase: "rest", phaseUntil: 0 };

  function ensureDog() {
    if (dogEl) return;
    const wrap = document.createElement("div");
    wrap.className = "dog";
    wrap.innerHTML = `<svg viewBox="0 0 32 20"><use href="#dog"/></svg>`;
    dogLayer.appendChild(wrap);
    dogEl = wrap;
  }

  function setDogEnabled(on) {
    if (on) {
      ensureDog();
      dogState.active = true;
      if (!dogState.raf) tickDog();
    } else {
      dogState.active = false;
      if (dogEl) {
        dogEl.classList.add("is-leaving");
        setTimeout(() => {
          if (dogEl && !dogState.active) { dogEl.remove(); dogEl = null; }
        }, 1400);
      }
    }
  }

  function tickDog() {
    if (!dogState.active || !dogEl) { dogState.raf = null; return; }
    const now = performance.now();
    const w = dogLayer.clientWidth || root.clientWidth;
    const h = dogLayer.clientHeight || root.clientHeight;

    if (dogState.phase === "rest" && now >= dogState.phaseUntil) {
      dogState.target = 30 + Math.random() * (w - 60);
      dogState.dir = dogState.target > dogState.x ? 1 : -1;
      dogState.phase = "run";
      dogEl.classList.remove("is-sniff");
      dogEl.classList.add("is-run");
    } else if (dogState.phase === "run") {
      const speed = 2.0;
      const dx = dogState.target - dogState.x;
      if (Math.abs(dx) <= speed) {
        dogState.x = dogState.target;
        dogState.phase = "sniff";
        dogState.phaseUntil = now + 800 + Math.random() * 1500;
        dogEl.classList.remove("is-run");
        dogEl.classList.add("is-sniff");
      } else {
        dogState.x += Math.sign(dx) * speed;
      }
    } else if (dogState.phase === "sniff" && now >= dogState.phaseUntil) {
      if (Math.random() < 0.18) {
        dogState.target = Math.random() < 0.5 ? -100 : w + 100;
        dogState.dir = dogState.target > dogState.x ? 1 : -1;
        dogState.phase = "run";
        dogEl.classList.remove("is-sniff");
        dogEl.classList.add("is-run");
      } else {
        dogState.phase = "rest";
        dogState.phaseUntil = now + 300 + Math.random() * 800;
        dogEl.classList.remove("is-run", "is-sniff");
      }
    }

    const yBand = h * 0.25 + (Math.sin(dogState.x * 0.013) * 0.5 + 0.5) * h * 0.60;
    dogState.y = yBand;
    dogEl.style.transform = `translate(${dogState.x}px, ${dogState.y}px) scaleX(${dogState.dir})`;
    dogEl.style.zIndex = String(500 + Math.floor(dogState.y));

    dogState.raf = requestAnimationFrame(tickDog);
  }

  /* ---------- debug wiring ---------- */

  function onChange(n) {
    if (!Number.isFinite(n) || n < 0) n = 0;
    if (n > 2000) n = 2000;
    current = n;
    localStorage.setItem("shrimpicus.flowerCount", String(n));
    syncControls(n);
    render(n);
  }

  function syncControls(n) {
    if (slider && parseInt(slider.value, 10) !== Math.min(n, 500)) slider.value = String(Math.min(n, 500));
    if (number && parseInt(number.value, 10) !== n) number.value = String(n);
    if (counter) counter.textContent = String(n);
  }

  /* ---------- boot ---------- */

  syncControls(current);
  render(current);
  setDogEnabled(!!(dogToggle && dogToggle.checked));

  if (slider) slider.addEventListener("input", (e) => onChange(parseInt(e.target.value, 10)));
  if (number) number.addEventListener("input", (e) => onChange(parseInt(e.target.value, 10)));
  if (reset) reset.addEventListener("click", () => onChange(baseCount));
  if (dogToggle) dogToggle.addEventListener("change", (e) => setDogEnabled(e.target.checked));

  window.addEventListener("resize", debounce(() => render(current), 200));

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }
})();
