// The cast: illustrated SVG characters with a small rig (body, eyes, lids, brows, mouth, paws, prop)
// so they can breathe, blink, follow the pointer, type, talk, celebrate and frown.

export type CastId = keyof typeof CAST_DEF;
const CAST_DEF = {
  scanner: { kind: "device", name: "Scanner", role: "Ranks the whole Binance spot market", base: "#8fe3d6", light: "#c9f4ec", dark: "#2a8f80" },
  prices: { kind: "device", name: "Prices", role: "Binance candles, funding, open interest", base: "#8fb8ff", light: "#cfe0ff", dark: "#3f63b0" },
  headlines: { kind: "device", name: "Headlines", role: "CoinDesk, Cointelegraph, Decrypt, The Block", base: "#ffc978", light: "#ffe4ba", dark: "#b47a1c" },
  book: { kind: "device", name: "Book", role: "Account, open trades, past lessons", base: "#c9b5ff", light: "#e6dcff", dark: "#6d55c4" },
  technical: { kind: "critter", name: "Tech", role: "Chart analyst", base: "#7cc4ff", light: "#c4e6ff", dark: "#2f6fae", prop: "tablet", extra: "glasses" },
  news: { kind: "critter", name: "News", role: "News and macro analyst", base: "#ffcf6e", light: "#ffeab8", dark: "#b07a12", prop: "paper", extra: "phones" },
  bull: { kind: "critter", name: "Bull", role: "Argues for buying", base: "#6fdc9b", light: "#bff3d4", dark: "#23864c", extra: "horns" },
  bear: { kind: "critter", name: "Bear", role: "Argues against", base: "#f3a08f", light: "#ffd3ca", dark: "#a8513f", extra: "ears" },
  pm: { kind: "critter", name: "PM", role: "Portfolio manager, decides", base: "#b9a3ff", light: "#e1d7ff", dark: "#5f45c0", prop: "clipboard", extra: "tie" },
  risk: { kind: "robot", name: "Risk", role: "Rule engine, plain Python", base: "#b3bfd1", light: "#e1e7f0", dark: "#4f5d73", extra: "shield" },
  exchange: { kind: "robot", name: "Exchange", role: "Sends orders to Binance", base: "#f4d35e", light: "#fbeaa8", dark: "#a8860f", extra: "dial" },
};

export const CAST: Record<string, any> = CAST_DEF;

export const ABOUT: Record<string, string> = {
  scanner: "A data feed. Goes through every coin on Binance with enough volume and picks the few that moved most against Bitcoin or traded far above their usual volume. Those join your watchlist and gold for the day.",
  prices: "Not a character, a data feed. Pulls 4-hour, daily and weekly candles from Binance and turns them into averages, momentum, typical move size and key price levels.",
  headlines: "A data feed. Collects the last 36 hours of crypto headlines and sorts them by coin.",
  book: "The account's notebook: money available, open trades, recent results, and lessons the desk wrote after past trades.",
  technical: "Reads only the numbers from the Prices feed. Says which way each chart leans and where the important levels are. Never looks at news.",
  news: "Reads the headlines and checks the economic calendar with at most three web searches. Reports facts and dates, no trade ideas.",
  bull: "Reads both analysts and makes the best case for buying. If there isn't one, it has to say so.",
  bear: "Reads both analysts and makes the best case for staying out or selling. Looks hardest at crowding and upcoming events.",
  pm: "Weighs the bull against the bear and writes the trade plan: entry, stop, target, confidence. Never chooses the size.",
  risk: "Not AI. Plain Python rules decide the size so a loss costs 1% of the account, and throw out any plan that breaks a rule.",
  exchange: "Sends only the plans you approved to Binance, always with the stop already attached on the exchange.",
};

const BEAN = "M0 -44 C27 -44 41 -24 41 4 C41 33 24 48 0 48 C-24 48 -41 33 -41 4 C-41 -24 -27 -44 0 -44 Z";

function eyes(c: any, robot: boolean) {
  if (robot) {
    return [-12, 12].map((x) => `
      <g class="eye" transform="translate(${x} -14)">
        <g class="pupil"><rect x="-4.5" y="-6.5" width="9" height="13" rx="4.5" class="led"/></g>
        <rect class="lid" x="-7" y="-9" width="14" height="18" fill="#1b2130"/>
      </g>`).join("");
  }
  return [-13, 13].map((x) => `
    <g class="eye" transform="translate(${x} -12)">
      <ellipse rx="8.6" ry="9.6" fill="#fff" stroke="${c.dark}" stroke-width="1.6"/>
      <g class="pupil"><circle r="4.7" fill="#1a1c23"/><circle cx="1.7" cy="-1.9" r="1.6" fill="#fff"/></g>
      <ellipse class="lid" rx="9.4" ry="10.4" fill="${c.base}"/>
    </g>`).join("");
}

function closedEyes(c: any, robot: boolean) {
  const col = robot ? "#7ef0ff" : c.dark;
  return `
    <g class="eyes-closed" stroke="${col}" stroke-width="2.4" fill="none" stroke-linecap="round">
      <path d="M-20 -11 Q-13 -6 -6 -11"/><path d="M6 -11 Q13 -6 20 -11"/>
    </g>
    <g class="eyes-happy" stroke="${col}" stroke-width="2.6" fill="none" stroke-linecap="round">
      <path d="M-20 -9 Q-13 -18 -6 -9"/><path d="M6 -9 Q13 -18 20 -9"/>
    </g>`;
}

function mouth(c: any, robot: boolean, y = 8) {
  const col = robot ? "#7ef0ff" : c.dark;
  return `
    <g class="mouth" transform="translate(0 ${y})" stroke="${col}" stroke-width="2.4" stroke-linecap="round" fill="none">
      <path class="m-smile" d="M-7 -1 Q0 6 7 -1"/>
      <path class="m-open" d="M-6 -2 Q0 9 6 -2 Q0 1 -6 -2 Z" fill="${robot ? "#7ef0ff" : "#4a2430"}"/>
      <path class="m-frown" d="M-7 4 Q0 -3 7 4"/>
      <path class="m-rest" d="M-3 0 Q0 2 3 0"/>
    </g>`;
}

function brows(c: any) {
  return `<g class="brows" stroke="${c.dark}" stroke-width="2.4" stroke-linecap="round" fill="none">
      <path class="brow l" d="M-20 -27 Q-13 -31 -6 -27"/><path class="brow r" d="M6 -27 Q13 -31 20 -27"/>
    </g>`;
}

const BEHIND: Record<string, (c: any, fill: string) => string> = {
  horns: (c) => `<g stroke="${c.dark}" stroke-width="2" fill="#fbf3dc">
      <path d="M-26 -30 C-40 -34 -46 -50 -40 -62 C-36 -52 -28 -46 -16 -40 Z"/>
      <path d="M26 -30 C40 -34 46 -50 40 -62 C36 -52 28 -46 16 -40 Z"/></g>`,
  ears: (c, fill) => `<g stroke="${c.dark}" stroke-width="2.2">
      <circle cx="-28" cy="-34" r="13" fill="${fill}"/><circle cx="-28" cy="-34" r="6.5" fill="${c.light}" stroke="none"/>
      <circle cx="28" cy="-34" r="13" fill="${fill}"/><circle cx="28" cy="-34" r="6.5" fill="${c.light}" stroke="none"/></g>`,
  phones: (_c) => `<path d="M-38 -6 C-40 -50 40 -50 38 -6" fill="none" stroke="#2c3140" stroke-width="5" stroke-linecap="round"/>`,
};

const FRONT: Record<string, (c: any) => string> = {
  glasses: (_c) => `<g fill="none" stroke="#1d2230" stroke-width="2.2">
      <rect x="-24" y="-23" width="21" height="20" rx="8"/><rect x="3" y="-23" width="21" height="20" rx="8"/>
      <path d="M-3 -14 h6"/></g>`,
  phones: () => `<g fill="#2c3140"><rect x="-46" y="-20" width="11" height="22" rx="5"/><rect x="35" y="-20" width="11" height="22" rx="5"/></g>`,
  horns: (c) => `<g><ellipse cx="0" cy="7" rx="15" ry="10" fill="${c.light}" stroke="${c.dark}" stroke-width="1.8"/>
      <ellipse cx="-5" cy="6" rx="2" ry="2.6" fill="${c.dark}"/><ellipse cx="5" cy="6" rx="2" ry="2.6" fill="${c.dark}"/></g>`,
  ears: (c) => `<g><ellipse cx="0" cy="5" rx="12" ry="9" fill="${c.light}" stroke="${c.dark}" stroke-width="1.8"/>
      <ellipse cx="0" cy="1.5" rx="4.2" ry="3" fill="#3a2a2a"/></g>`,
  tie: () => `<path d="M0 22 l-6 -6 h12 z M0 22 l-5 18 l5 6 l5 -6 z" fill="#2b2f44"/>`,
};

const PROPS: Record<string, (c: any) => string> = {
  tablet: (_c) => `<g class="prop" transform="translate(0 30)">
      <rect x="-23" y="-15" width="46" height="31" rx="5" fill="#1b2130" stroke="#0d1018" stroke-width="1.5"/>
      <polyline class="screen-line" points="-17,8 -9,2 -3,5 4,-4 10,-1 17,-9" fill="none" stroke="#5ff0a3" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
    </g>`,
  paper: () => `<g class="prop" transform="translate(0 31)">
      <path d="M-25 -14 L23 -17 L25 15 L-23 17 Z" fill="#fdfaf2" stroke="#c9bfa8" stroke-width="1.4"/>
      <rect x="-19" y="-11" width="22" height="5" rx="1" fill="#2c3140"/>
      <g stroke="#b9b09a" stroke-width="1.6"><path d="M-19 -1 H18"/><path d="M-19 4 H18"/><path d="M-19 9 H8"/></g>
    </g>`,
  clipboard: () => `<g class="prop" transform="translate(0 31)">
      <rect x="-20" y="-17" width="40" height="34" rx="4" fill="#a8763e" stroke="#7a5228" stroke-width="1.4"/>
      <rect x="-16" y="-12" width="32" height="26" rx="2" fill="#fffdf7"/>
      <rect x="-8" y="-20" width="16" height="7" rx="2" fill="#7d8597"/>
      <g class="ticks" stroke="#23864c" stroke-width="2" fill="none" stroke-linecap="round">
        <path d="M-11 -5 l2.5 2.5 l4.5 -5"/><path d="M-11 4 l2.5 2.5 l4.5 -5"/></g>
      <g stroke="#cfc6b3" stroke-width="1.6"><path d="M-1 -4 H12"/><path d="M-1 5 H12"/></g>
    </g>`,
};

function paws(c: any, fill: string, hasProp: boolean) {
  const y = hasProp ? 22 : 30;
  return `<g class="paws" fill="${fill}" stroke="${c.dark}" stroke-width="2">
      <ellipse class="paw l" cx="-24" cy="${y}" rx="8" ry="6.5"/>
      <ellipse class="paw r" cx="24" cy="${y}" rx="8" ry="6.5"/></g>`;
}

function overlays(top = -66) {
  return `
    <g class="dots" transform="translate(0 ${top})"><circle cx="-10" r="3.6"/><circle r="3.6"/><circle cx="10" r="3.6"/></g>
    <g class="zzz" transform="translate(30 -52)"><text>z</text><text x="9" y="-9" font-size="10">z</text></g>
    <g class="badge ok" transform="translate(36 34)"><circle r="11"/><path d="M-4.5 0 l3 3.2 l6 -6.6"/></g>
    <g class="badge no" transform="translate(36 34)"><circle r="11"/><path d="M-4 -4 l8 8 M4 -4 l-8 8"/></g>`;
}

function critter(id: string, c: any, flat: boolean) {
  const fill = flat ? c.base : `url(#g-${id})`;
  const behind = BEHIND[c.extra]?.(c, fill) || "";
  const front = FRONT[c.extra]?.(c) || "";
  const mouthY = c.extra === "horns" ? 18 : c.extra === "ears" ? 14 : 8;
  return `
    <ellipse class="shadow" cx="0" cy="52" rx="34" ry="6"/>
    <g class="hop"><g class="breathe">
      ${behind}
      <path class="skin" d="${BEAN}" fill="${fill}" stroke="${c.dark}" stroke-width="2.4"/>
      <ellipse cx="0" cy="24" rx="23" ry="17" fill="${c.light}" opacity=".55"/>
      <g class="face">
        <ellipse cx="-26" cy="4" rx="5.5" ry="3.2" fill="#ff6f86" opacity=".32"/>
        <ellipse cx="26" cy="4" rx="5.5" ry="3.2" fill="#ff6f86" opacity=".32"/>
        ${eyes(c, false)}${closedEyes(c, false)}${brows(c)}
        ${front}
        ${mouth(c, false, mouthY)}
      </g>
      ${PROPS[c.prop]?.(c) || ""}
      ${paws(c, fill, !!c.prop)}
    </g></g>
    ${overlays()}`;
}

function robot(id: string, c: any, flat: boolean) {
  const fill = flat ? c.base : `url(#g-${id})`;
  const belly = c.extra === "shield"
    ? `<path d="M0 12 l14 5 v9 c0 9 -7 14 -14 17 c-7 -3 -14 -8 -14 -17 v-9 z" fill="${c.light}" stroke="${c.dark}" stroke-width="2"/>
       <path d="M-5 27 l4 4 l7 -8" stroke="${c.dark}" stroke-width="2.4" fill="none" stroke-linecap="round"/>`
    : `<circle cx="0" cy="26" r="13" fill="${c.light}" stroke="${c.dark}" stroke-width="2"/>
       <g class="dial" transform="translate(0 26)"><path d="M0 -9 V-3" stroke="${c.dark}" stroke-width="2.6" stroke-linecap="round"/>
       <circle r="2.6" fill="${c.dark}"/></g>`;
  return `
    <ellipse class="shadow" cx="0" cy="52" rx="34" ry="6"/>
    <g class="hop"><g class="breathe">
      <path d="M0 -42 V-56" stroke="${c.dark}" stroke-width="3" stroke-linecap="round"/>
      <circle class="bulb" cx="0" cy="-59" r="5.5"/>
      <rect class="skin" x="-38" y="-42" width="76" height="90" rx="16" fill="${fill}" stroke="${c.dark}" stroke-width="2.4"/>
      <rect x="-45" y="-12" width="8" height="20" rx="3" fill="${c.dark}"/><rect x="37" y="-12" width="8" height="20" rx="3" fill="${c.dark}"/>
      <g class="face">
        <rect x="-29" y="-33" width="58" height="38" rx="10" fill="#1b2130" stroke="${c.dark}" stroke-width="2"/>
        ${eyes(c, true)}${closedEyes(c, true)}
        ${mouth(c, true, -2)}
      </g>
      ${belly}
    </g></g>
    ${overlays(-78)}`;
}

function device(id: string, c: any, flat: boolean) {
  const fill = flat ? c.base : `url(#g-${id})`;
  const art = ({
    prices: `<g transform="translate(-20 6)">${[[0, 10, -12, 4], [10, 4, -16, 2], [20, 8, -20, -6], [30, -2, -26, -12], [40, -8, -30, -16]]
      .map(([x, a, hi, b], i) => `<path d="M${x} ${hi} V${Math.max(a, b) + 8}" stroke="#1b2130" stroke-width="1.6"/>
        <rect class="bar" style="--i:${i}" x="${x - 3.5}" y="${Math.min(a, b) - 4}" width="7" height="${Math.abs(a - b) + 8}" rx="1.5" fill="${i === 1 ? "#ff6b6b" : "#2fbf71"}"/>`).join("")}</g>`,
    scanner: `<g transform="translate(0 4)"><circle r="19" fill="#f4fffc" stroke="${c.dark}" stroke-width="1.6"/>
        <circle r="11" fill="none" stroke="${c.dark}" stroke-opacity=".35" stroke-width="1.2"/><circle r="3" fill="${c.dark}"/>
        <g class="sweep"><path d="M0 0 L0 -19 A19 19 0 0 1 16.5 -9.5 Z" fill="${c.dark}" fill-opacity=".22"/><path d="M0 0 L0 -19" stroke="${c.dark}" stroke-width="1.6"/></g>
        <circle class="bar" style="--i:0" cx="9" cy="-6" r="2.4" fill="#2fbf71"/><circle class="bar" style="--i:1" cx="-8" cy="9" r="2.4" fill="#ff6b6b"/></g>`,
    headlines: `<g transform="translate(-22 -12)"><rect width="44" height="34" rx="3" fill="#fffdf6" stroke="${c.dark}" stroke-width="1.4"/>
        <rect x="5" y="5" width="20" height="6" rx="1" fill="#2c3140"/><g class="bar-lines" stroke="#b9b09a" stroke-width="1.8">
        <path class="bar" style="--i:0" d="M5 17 H39"/><path class="bar" style="--i:1" d="M5 23 H39"/><path class="bar" style="--i:2" d="M5 29 H27"/></g></g>`,
    book: `<g transform="translate(-20 -14)"><rect width="40" height="40" rx="4" fill="#fffdf6" stroke="${c.dark}" stroke-width="1.4"/>
        <rect width="7" height="40" rx="2" fill="${c.dark}"/><g stroke="#b9b09a" stroke-width="1.8">
        <path class="bar" style="--i:0" d="M13 10 H34"/><path class="bar" style="--i:1" d="M13 18 H34"/><path class="bar" style="--i:2" d="M13 26 H28"/></g></g>`,
  } as Record<string, string>)[id];
  return `
    <ellipse class="shadow" cx="0" cy="44" rx="34" ry="5"/>
    <g class="hop"><g class="breathe">
      <rect class="skin" x="-40" y="-34" width="80" height="72" rx="18" fill="${fill}" stroke="${c.dark}" stroke-width="2.2"/>
      ${art}
    </g></g>
    <g class="badge ok" transform="translate(36 -32)"><circle r="11"/><path d="M-4.5 0 l3 3.2 l6 -6.6"/></g>
    <g class="badge no" transform="translate(36 -32)"><circle r="11"/><path d="M-4 -4 l8 8 M4 -4 l-8 8"/></g>`;
}

export function figure(id: string, { flat = false } = {}) {
  const c = CAST[id];
  if (c.kind === "device") return device(id, c, flat);
  if (c.kind === "robot") return robot(id, c, flat);
  return critter(id, c, flat);
}

export function gradients() {
  return Object.entries(CAST).map(([id, c]) => `
    <radialGradient id="g-${id}" cx="35%" cy="25%" r="85%">
      <stop offset="0" stop-color="${c.light}"/><stop offset=".55" stop-color="${c.base}"/>
      <stop offset="1" stop-color="${c.base}" stop-opacity=".95"/>
    </radialGradient>`).join("");
}

// A standalone avatar for lists and the drawer.
export function portrait(id: string, { size = 40, mood = "awake" } = {}) {
  const vb = CAST[id].kind === "device" ? "-48 -44 96 96" : "-52 -70 104 128";
  return `<svg class="portrait char is-${mood}" data-kind="${CAST[id].kind}" viewBox="${vb}" width="${size}" height="${size}" aria-hidden="true">${figure(id, { flat: true })}</svg>`;
}

// ---------- the rig in motion ----------
const SPRING = "linear(0, 0.22 4%, 0.72 10%, 1.06 17%, 1.17 22%, 1.13 28%, 0.99 37%, 0.95 43%, 0.99 55%, 1.01 66%, 1)";

export class Rig {
  root: SVGElement;
  calm: MediaQueryList;
  chars: SVGGElement[];
  pointer: { x: number; y: number } | null = null;
  talkTimers = new Map<string, number>();
  raf: number | null = null;
  alive = true;
  constructor(root: SVGElement, { calm }: { calm: MediaQueryList }) {
    this.root = root;
    this.calm = calm;
    this.chars = [...root.querySelectorAll<SVGGElement>(".char[data-id]")];
    this.pointer = null;
    this.talkTimers = new Map();
    this.#blinkLoop();
    addEventListener("pointermove", this.onMove, { passive: true });
    document.addEventListener("pointerleave", this.onLeave);
  }

  onMove = (e: PointerEvent) => {
    this.pointer = { x: e.clientX, y: e.clientY };
    if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = null; this.#look(); });
  };

  onLeave = () => { this.pointer = null; this.#look(); };

  destroy() {
    this.alive = false;
    removeEventListener("pointermove", this.onMove);
    document.removeEventListener("pointerleave", this.onLeave);
    for (const t of this.talkTimers.values()) clearInterval(t);
  }

  get(id: string) { return this.root.querySelector<SVGGElement>(`.char[data-id="${id}"]`); }

  mood(id: string, mood: string) {
    const g = this.get(id);
    if (!g) return;
    const before = g.dataset.mood;
    if (before === mood) return;
    g.classList.remove("is-idle", "is-working", "is-done", "is-alert", "is-awake");
    g.classList.add(`is-${mood}`);
    g.dataset.mood = mood;
    const label = g.querySelector(".status");
    if (label) label.textContent = ({ idle: "asleep", working: "working", done: "done", alert: "objected", awake: "ready" } as Record<string, string>)[mood];
    if (!this.calm.matches && (mood === "done" || mood === "alert") && before === "working") this.#hop(g, mood === "alert");
  }

  talk(id: string, ms: number) {
    const g = this.get(id);
    if (!g || this.calm.matches) return;
    clearInterval(this.talkTimers.get(id));
    g.classList.add("is-talking");
    let open = false;
    const t = window.setInterval(() => { open = !open; g.classList.toggle("mouth-open", open); }, 120);
    this.talkTimers.set(id, t);
    setTimeout(() => { clearInterval(t); g.classList.remove("is-talking", "mouth-open"); }, ms);
  }

  #hop(g: SVGGElement, shake: boolean) {
    const target = g.querySelector(".hop")!;
    const frames = shake
      ? [{ transform: "translateX(0)" }, { transform: "translateX(-5px)" }, { transform: "translateX(5px)" }, { transform: "translateX(-3px)" }, { transform: "translateX(0)" }]
      : [{ transform: "translateY(0) scale(1, 1)" }, { transform: "translateY(2px) scale(1.06, .92)", offset: 0.15 }, { transform: "translateY(-16px) scale(.96, 1.05)", offset: 0.45 }, { transform: "translateY(0) scale(1, 1)" }];
    target.animate(frames, { duration: shake ? 420 : 720, easing: shake ? "ease-in-out" : SPRING });
  }

  #blinkLoop() {
    for (const g of this.chars) {
      const blink = () => {
        if (!this.alive) return;
        if (!this.calm.matches && !document.hidden && !g.classList.contains("is-idle")) {
          for (const lid of g.querySelectorAll(".lid")) {
            lid.animate([{ transform: "scaleY(0)" }, { transform: "scaleY(1)" }, { transform: "scaleY(0)" }], { duration: 170, easing: "ease-in-out" });
          }
        }
        setTimeout(blink, 2200 + Math.random() * 4200);
      };
      setTimeout(blink, 600 + Math.random() * 3000);
    }
  }

  #look() {
    for (const g of this.chars) {
      const face = g.querySelector(".face") || g;
      const pupils = g.querySelectorAll<SVGGElement>(".pupil");
      if (!this.pointer || this.calm.matches) {
        for (const p of pupils) p.style.transform = "";
        g.style.removeProperty("--lean");
        continue;
      }
      const r = face.getBoundingClientRect();
      const dx = this.pointer.x - (r.left + r.width / 2);
      const dy = this.pointer.y - (r.top + r.height / 2);
      const d = Math.hypot(dx, dy) || 1;
      const k = Math.min(1, d / 160);
      const robot = g.dataset.kind === "robot";
      const mx = (robot ? 2.6 : 3.6) * k, my = (robot ? 2 : 3.4) * k;
      for (const p of pupils) p.style.transform = `translate(${(dx / d) * mx}px, ${(dy / d) * my}px)`;
      g.style.setProperty("--lean", `${Math.max(-4, Math.min(4, dx / 120))}deg`);
    }
  }
}
