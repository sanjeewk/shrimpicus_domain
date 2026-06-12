(function () {
  const root = document.querySelector(".field");
  if (!root) return;

  const flowersEl = document.getElementById("flowers");
  const counter = document.getElementById("flowerCount");
  const slider = document.getElementById("flowerSlider");
  const number = document.getElementById("flowerNumber");
  const reset  = document.getElementById("flowerReset");
  const audioBtn = document.getElementById("audioToggle");

  const baseCount = parseInt(root.dataset.doneCount || "0", 10) || 0;
  const stored = parseInt(localStorage.getItem("shrimpicus.flowerCount"), 10);
  let current = Number.isFinite(stored) ? stored : baseCount;

  syncControls(current);
  render(current);

  if (slider) slider.addEventListener("input", (e) => onChange(parseInt(e.target.value, 10)));
  if (number) number.addEventListener("input", (e) => onChange(parseInt(e.target.value, 10)));
  if (reset)  reset.addEventListener("click", () => onChange(baseCount));

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

  function render(n) {
    flowersEl.innerHTML = "";
    const w = flowersEl.clientWidth || root.clientWidth;
    const h = flowersEl.clientHeight || root.clientHeight;
    const groundTop = h * 0.62;
    const groundBottom = h - 18;
    for (let i = 0; i < n; i++) {
      flowersEl.appendChild(makeDaisy(i, w, groundTop, groundBottom));
    }
  }

  function makeDaisy(seed, w, yTop, yBot) {
    const rng = mulberry32(0x9e37 ^ (seed * 0x45d9f3b + 0x7f4a7c15));
    const x = rng() * w;
    const y = yTop + rng() * (yBot - yTop);
    const scale = 0.7 + rng() * 0.7;
    const swayDur = (3 + rng() * 3.5).toFixed(2) + "s";
    const swayDelay = (rng() * -3).toFixed(2) + "s";
    const tilt = (rng() * 8 - 4).toFixed(1);

    const wrap = document.createElement("span");
    wrap.className = "daisy";
    wrap.style.left = x + "px";
    wrap.style.top = y + "px";
    wrap.style.transform = `translate(-50%, -100%) scale(${scale}) rotate(${tilt}deg)`;
    wrap.style.zIndex = String(Math.floor(y));
    wrap.style.setProperty("--sway-dur", swayDur);
    wrap.style.setProperty("--sway-delay", swayDelay);
    wrap.innerHTML = daisySvg();
    return wrap;
  }

  function daisySvg() {
    return `
      <svg viewBox="0 0 22 44" shape-rendering="crispEdges">
        <rect x="10" y="20" width="2" height="22" fill="#3a8a2e"/>
        <rect x="11" y="22" width="1" height="22" fill="#2d6a23"/>
        <rect x="6"  y="28" width="4" height="2" fill="#4ea234"/>
        <rect x="7"  y="26" width="2" height="2" fill="#4ea234"/>
        <rect x="12" y="32" width="4" height="2" fill="#4ea234"/>
        <rect x="13" y="30" width="2" height="2" fill="#4ea234"/>
        <rect x="9"  y="6"  width="4" height="2" fill="#ffffff"/>
        <rect x="9"  y="14" width="4" height="2" fill="#ffffff"/>
        <rect x="5"  y="10" width="2" height="4" fill="#ffffff"/>
        <rect x="15" y="10" width="2" height="4" fill="#ffffff"/>
        <rect x="7"  y="8"  width="2" height="2" fill="#ffffff"/>
        <rect x="13" y="8"  width="2" height="2" fill="#ffffff"/>
        <rect x="7"  y="14" width="2" height="2" fill="#ffffff"/>
        <rect x="13" y="14" width="2" height="2" fill="#ffffff"/>
        <rect x="9"  y="10" width="4" height="4" fill="#ffd23f"/>
        <rect x="10" y="11" width="2" height="2" fill="#b8860b"/>
      </svg>
    `;
  }

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  window.addEventListener("resize", debounce(() => render(current), 200));

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  /* ---------- chiptune via WebAudio ---------- */

  let audioCtx = null;
  let masterGain = null;
  let stopFn = null;

  if (audioBtn) {
    audioBtn.addEventListener("click", () => {
      const isOn = audioBtn.getAttribute("aria-pressed") === "true";
      if (isOn) stopAudio(); else startAudio();
    });
  }

  function startAudio() {
    if (!audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      audioCtx = new Ctx();
      masterGain = audioCtx.createGain();
      masterGain.gain.value = 0.06;
      masterGain.connect(audioCtx.destination);
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    stopFn = scheduleLoop(audioCtx, masterGain);
    audioBtn.setAttribute("aria-pressed", "true");
    audioBtn.querySelector(".field__audio-text").textContent = "MUSIC: ON";
  }

  function stopAudio() {
    if (stopFn) { stopFn(); stopFn = null; }
    audioBtn.setAttribute("aria-pressed", "false");
    audioBtn.querySelector(".field__audio-text").textContent = "MUSIC: OFF";
  }

  function scheduleLoop(ctx, out) {
    const bpm = 96;
    const beat = 60 / bpm;
    const scale = [0, 2, 4, 7, 9, 12, 14, 16];
    const root = 220;
    const melody = [0, 2, 4, 5, 4, 2, 0, 2, 4, 5, 7, 5, 4, 2, 4, 0];
    const bass   = [-12, -12, -7, -7, -10, -10, -5, -5];

    let active = true;
    let nextTime = ctx.currentTime + 0.05;
    let step = 0;

    const tick = () => {
      if (!active) return;
      while (nextTime < ctx.currentTime + 0.4) {
        const i = step % melody.length;
        playNote(ctx, out, "square", root * Math.pow(2, scale[melody[i] % scale.length] / 12) * (melody[i] >= 12 ? 2 : 1), nextTime, beat * 0.45, 0.18);
        if (step % 2 === 0) {
          const j = (step / 2) % bass.length;
          playNote(ctx, out, "triangle", root * Math.pow(2, bass[j] / 12), nextTime, beat * 0.9, 0.25);
        }
        nextTime += beat * 0.5;
        step++;
      }
      requestAnimationFrame(tick);
    };
    tick();

    return () => { active = false; };
  }

  function playNote(ctx, out, type, freq, time, dur, vol) {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    g.gain.setValueAtTime(0, time);
    g.gain.linearRampToValueAtTime(vol, time + 0.01);
    g.gain.exponentialRampToValueAtTime(0.001, time + dur);
    osc.connect(g).connect(out);
    osc.start(time);
    osc.stop(time + dur + 0.05);
  }
})();
