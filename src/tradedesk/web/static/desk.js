const NS = "http://www.w3.org/2000/svg";
const calm = matchMedia("(prefers-reduced-motion: reduce)");

const NODES = {
  prices: { x: 90, y: 95, kind: "machine", name: "Prices", role: "candles, funding, OI" },
  headlines: { x: 90, y: 265, kind: "machine", name: "Headlines", role: "news feeds" },
  book: { x: 90, y: 435, kind: "machine", name: "Book", role: "positions, lessons" },
  technical: { x: 330, y: 150, kind: "critter", name: "Tech", role: "chart read", extra: "glasses" },
  news: { x: 330, y: 380, kind: "critter", name: "News", role: "macro read", extra: "hat" },
  bull: { x: 560, y: 120, kind: "critter", name: "Bull", role: "long case", extra: "horns" },
  bear: { x: 560, y: 405, kind: "critter", name: "Bear", role: "against", extra: "ears" },
  pm: { x: 750, y: 262, kind: "critter", name: "PM", role: "decides", extra: "tie" },
  risk: { x: 915, y: 150, kind: "robot", name: "Risk", role: "rules in code" },
  exchange: { x: 915, y: 390, kind: "robot", name: "Exchange", role: "Binance orders" },
};

const EDGES = [
  ["prices", "technical"], ["book", "technical"], ["headlines", "news"],
  ["technical", "bull"], ["technical", "bear"], ["news", "bull"], ["news", "bear"],
  ["book", "bull"], ["book", "bear"],
  ["technical", "pm"], ["news", "pm"], ["bull", "pm"], ["bear", "pm"], ["book", "pm"],
  ["pm", "risk"], ["risk", "exchange"],
];

const START = {
  technical: "Reading the charts and funding",
  news: "Going through the headlines and the macro calendar",
  bull: "Looking for a reason to buy",
  bear: "Looking for what could go wrong",
  pm: "Weighing both sides",
  risk: "Measuring every idea against the rules",
};
const said = (ev) => (ev.kind === "start" && START[ev.actor]) || ev.title;

const LABELS = { desk: "Desk", ...Object.fromEntries(Object.entries(NODES).map(([k, v]) => [k, v.name])) };

const $ = (sel) => document.querySelector(sel);
const state = { run: null, latest: null, lastId: 0, events: [], live: false };

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, method = "GET") {
  const res = await fetch(path, { method, headers: method === "GET" ? {} : { "X-Desk": "1" } });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

const fmt = (n, d = 2) => n == null ? "n/a" : Math.abs(n) >= 1000
  ? n.toLocaleString("en-US", { maximumFractionDigits: 0 })
  : Number(n).toPrecision(Math.max(4, d + 1)).replace(/\.?0+$/, "");
const money = (n) => (n >= 0 ? "+" : "") + Number(n).toFixed(2);
const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function face() {
  return `
    <path class="mouth shut-eyes" d="M-15 -4 q5 4 10 0 M5 -4 q5 4 10 0"/>
    <g class="open-eyes"><circle class="eye" cx="-9" cy="-5" r="4"/><circle class="eye" cx="9" cy="-5" r="4"/></g>
    <path class="mouth smile" d="M-8 9 q8 7 16 0"/>`;
}

const EXTRAS = {
  glasses: `<g fill="none" stroke="#1d1d1f" stroke-width="2"><circle cx="-9" cy="-5" r="8"/><circle cx="9" cy="-5" r="8"/><path d="M-1 -5 h2"/></g>`,
  hat: `<path d="M-24 -24 L0 -50 L24 -24 Z" fill="#fffaf0" stroke="#1d1d1f33" stroke-width="2"/><path d="M-10 -32 h20 M-6 -38 h12" stroke="#1d1d1f55" stroke-width="2"/>`,
  horns: `<path d="M-20 -24 q-16 -6 -14 -26 q6 14 20 14 z M20 -24 q16 -6 14 -26 q-6 14 -20 14 z" fill="#f6efdc" stroke="#1d1d1f33" stroke-width="2"/>`,
  ears: "",
  tie: `<path d="M0 26 l-11 -7 v14 z M0 26 l11 -7 v14 z" fill="#1d1d1f" opacity="0.75"/>`,
};

function nodeMarkup(id, n) {
  const color = `var(--c-${id})`;
  let body;
  if (n.kind === "machine") {
    body = `<rect class="body" x="-40" y="-30" width="80" height="60" rx="10" fill="${color}"/>
      <g transform="translate(-24 18)">${[16, 26, 12, 30, 20].map((h, i) =>
        `<rect class="screen-bar" x="${i * 10}" y="${-h}" width="6" height="${h}" rx="2"/>`).join("")}</g>`;
  } else if (n.kind === "robot") {
    body = `<path d="M0 -34 v-12" stroke="#1d1d1f88" stroke-width="3"/><circle cx="0" cy="-48" r="5" fill="var(--flow)"/>
      <rect class="body" x="-34" y="-34" width="68" height="68" rx="12" fill="${color}"/>${face()}`;
  } else {
    const ears = n.extra === "ears"
      ? `<circle cx="-24" cy="-25" r="12" fill="${color}" class="body"/><circle cx="24" cy="-25" r="12" fill="${color}" class="body"/>` : "";
    const behind = n.extra === "horns" ? EXTRAS.horns : ears;
    const front = n.extra === "horns" || n.extra === "ears" ? "" : EXTRAS[n.extra] || "";
    body = `${behind}<circle class="body" r="34" fill="${color}"/>${face()}${front}`;
  }
  return `<g class="bob">${body}
      <g class="dots" transform="translate(0 -60)"><circle cx="-9" r="3.5"/><circle r="3.5"/><circle cx="9" r="3.5"/></g>
      <text class="zzz" x="26" y="-32">z z</text>
      <g class="badge ok" transform="translate(30 -28)"><circle r="10"/><path d="M-4 0 l3 3 l5 -6"/></g>
      <g class="badge no" transform="translate(30 -28)"><circle r="10"/><path d="M-4 -4 l8 8 M4 -4 l-8 8"/></g>
    </g>
    <text class="name" y="${n.kind === "machine" ? 52 : 58}">${n.name}</text>
    <text class="role" y="${n.kind === "machine" ? 68 : 74}">${n.role}</text>`;
}

function edgePath(a, b) {
  const p = NODES[a], q = NODES[b];
  if (Math.abs(q.x - p.x) < 60) {
    const s = Math.sign(q.y - p.y);
    return `M${p.x} ${p.y + s * 50} L${q.x} ${q.y - s * 62}`;
  }
  const dx = (q.x - p.x) / 2;
  return `M${p.x + 44} ${p.y} C${p.x + 44 + dx} ${p.y}, ${q.x - 44 - dx} ${q.y}, ${q.x - 46} ${q.y}`;
}

function drawFloor() {
  const edges = $("#edges"), nodes = $("#nodes");
  for (const [a, b] of EDGES) {
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", edgePath(a, b));
    path.setAttribute("class", "edge");
    path.setAttribute("marker-end", "url(#arrow)");
    path.dataset.from = a;
    path.dataset.to = b;
    edges.append(path);
  }
  for (const [id, n] of Object.entries(NODES)) {
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", "node idle");
    g.setAttribute("transform", `translate(${n.x} ${n.y})`);
    g.setAttribute("tabindex", "0");
    g.setAttribute("role", "button");
    g.setAttribute("aria-label", `${n.name}, ${n.role}. Show output`);
    g.dataset.actor = id;
    g.innerHTML = nodeMarkup(id, n);
    g.addEventListener("click", () => showDetail(id));
    g.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showDetail(id); }
    });
    nodes.append(g);
  }
}

function setNode(actor, mood) {
  const g = document.querySelector(`.node[data-actor="${actor}"]`);
  if (!g) return;
  g.classList.remove("idle", "working", "done", "alert");
  g.classList.add(mood);
  g.querySelector(".smile")?.setAttribute("d", mood === "alert" ? "M-8 14 q8 -7 16 0" : "M-8 9 q8 7 16 0");
  for (const e of document.querySelectorAll(`.edge[data-to="${actor}"]`)) {
    e.classList.toggle("flow", mood === "working");
  }
}

function resetFloor() {
  for (const id of Object.keys(NODES)) setNode(id, "idle");
  $("#bubbles").replaceChildren();
}

function sendPacket(from, to) {
  if (calm.matches) return;
  const path = document.querySelector(`.edge[data-from="${from}"][data-to="${to}"]`);
  if (!path) return;
  const dot = document.createElementNS(NS, "circle");
  dot.setAttribute("r", "6");
  dot.setAttribute("class", "packet");
  $("#packets").append(dot);
  const total = path.getTotalLength();
  const start = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - start) / 900);
    const p = path.getPointAtLength(total * k);
    dot.setAttribute("cx", p.x);
    dot.setAttribute("cy", p.y);
    if (k < 1) requestAnimationFrame(step);
    else dot.remove();
  };
  requestAnimationFrame(step);
}

function bubble(actor, text) {
  const n = NODES[actor];
  if (!n || !text) return;
  const box = $("#bubbles");
  box.querySelector(`[data-actor="${actor}"]`)?.remove();
  const b = el("div", { class: "bubble", "data-actor": actor }, text.length > 90 ? `${text.slice(0, 88)}…` : text);
  b.style.left = `${(n.x / 1000) * 100}%`;
  b.style.top = `${(n.y / 520) * 100}%`;
  box.append(b);
  setTimeout(() => b.classList.add("fade"), 9000);
  setTimeout(() => b.remove(), 9500);
}

function apply(ev, animate) {
  const a = ev.actor;
  if (a === "desk" && ev.kind === "start") resetFloor();
  if (ev.kind === "start" && NODES[a]) {
    setNode(a, "working");
    if (animate) for (const r of ev.refs) if (NODES[r]) sendPacket(r, a);
    if (animate && a === "risk") sendPacket("pm", "risk");
  } else if (NODES[a]) {
    if (["reject", "error"].includes(ev.kind)) {
      const g = document.querySelector(`.node[data-actor="${a}"]`);
      if (!g.classList.contains("done")) setNode(a, "alert");
    } else {
      setNode(a, "done");
    }
    if (animate && a === "exchange") sendPacket("risk", "exchange");
  }
  if (animate) bubble(a, said(ev));
}

function feedItem(ev) {
  const li = el("li", { class: ev.kind });
  const dot = el("span", { class: `dot ${NODES[ev.actor]?.kind === "robot" ? "square" : ""}`, "aria-hidden": "true" },
    (LABELS[ev.actor] || ev.actor).slice(0, 2));
  dot.style.background = NODES[ev.actor] ? `var(--c-${ev.actor})` : "var(--accent)";
  const box = el("div");
  const head = el("div");
  head.append(el("span", { class: "who" }, LABELS[ev.actor] || ev.actor), el("time", { class: "when", datetime: ev.ts }, clock(ev.ts)));
  box.append(head, el("p", { class: "title" }, said(ev)));
  if (ev.html) {
    const d = el("details");
    d.append(el("summary", {}, "Read it"));
    const body = el("div", { class: "prose" });
    body.innerHTML = ev.html;
    d.append(body);
    box.append(d);
  }
  li.append(dot, box);
  return li;
}

function showDetail(actor) {
  const items = state.events.filter((e) => e.actor === actor && (e.html || e.kind !== "start"));
  $("#detail-title").textContent = `${NODES[actor].name}, ${NODES[actor].role}`;
  const body = $("#detail-body");
  body.replaceChildren();
  if (!items.length) body.append(el("p", { class: "empty" }, "Nothing from this one in the selected run yet."));
  for (const e of items) {
    const entry = el("div", { class: "detail-entry" });
    entry.append(el("time", { datetime: e.ts }, clock(e.ts)), el("p", {}, e.title));
    if (e.html) {
      const prose = el("div");
      prose.innerHTML = e.html;
      entry.append(prose);
    }
    body.append(entry);
  }
  $("#detail").showPopover();
}

async function loadRuns() {
  const runs = await api("/api/runs");
  const select = $("#run");
  const keep = select.value;
  const signature = runs.map((r) => r.id + r.status).join();
  state.latest = runs[0] || null;
  if (signature === state.runSignature) return runs;
  state.runSignature = signature;
  select.replaceChildren(...runs.map((r) => el("option", { value: r.id }, `${r.id.replace("T", " ")} ${r.status === "running" ? "(live)" : ""}`)));
  state.latest = runs[0] || null;
  if (keep && runs.some((r) => r.id === keep)) select.value = keep;
  return runs;
}

async function selectRun(id) {
  state.run = id;
  state.lastId = 0;
  state.events = [];
  $("#feed").replaceChildren();
  resetFloor();
  await pollEvents(false);
}

async function pollEvents(animate = true) {
  if (!state.run) return;
  const events = await api(`/api/runs/${encodeURIComponent(state.run)}/events?after=${state.lastId}`);
  const feed = $("#feed");
  for (const ev of events) {
    state.events.push(ev);
    state.lastId = ev.id;
    apply(ev, animate);
    feed.append(feedItem(ev));
  }
  if (events.length) feed.lastElementChild?.scrollIntoView({ block: "nearest", behavior: calm.matches ? "auto" : "smooth" });
}

function planCard(p) {
  const card = el("article", { class: "plan" });
  const head = el("header");
  head.append(
    el("span", { class: "asset" }, `${p.asset} ${p.side}`),
    el("span", {}, `${p.horizon} term, ${p.rating}, confidence ${p.confidence}`),
    el("span", { class: `state ${p.status}` }, p.status === "proposed" ? "waiting for you" : p.status),
  );
  card.append(head);
  card.append(el("p", { class: "levels" },
    `${p.entry_type} entry ${fmt(p.entry)} | stop ${fmt(p.stop)} | target ${fmt(p.take_profit)} | R/R ${p.reward_risk ?? "n/a"} | size ${fmt(p.qty, 4)}${p.leverage > 1 ? ` at ${p.leverage}x` : ""} | risk ${Number(p.risk_amount || 0).toFixed(2)}`));
  card.append(el("p", { class: "thesis" }, p.thesis));
  if (p.status === "rejected" && p.reasons) card.append(el("p", { class: "reasons" }, p.reasons));
  if (p.status === "proposed") {
    const row = el("div", { class: "actions" });
    const yes = el("button", { type: "button", class: "go" }, "Approve and send");
    const no = el("button", { type: "button" }, "Drop");
    yes.addEventListener("click", () => act(`/api/plans/${p.id}/approve`, yes));
    no.addEventListener("click", () => act(`/api/plans/${p.id}/reject`, no));
    row.append(yes, no);
    card.append(row);
  }
  return card;
}

async function act(path, button) {
  button.disabled = true;
  try {
    await api(path, "POST");
  } catch (e) {
    alert(e.message);
  }
  await Promise.all([loadState(), pollEvents()]);
}

function table(target, headers, rows) {
  const t = $(target);
  t.replaceChildren();
  if (!rows.length) {
    t.append(el("caption", { class: "empty" }, "None"));
    return;
  }
  const head = el("tr");
  for (const h of headers) head.append(el("th", { scope: "col" }, h));
  t.append(el("thead"), el("tbody"));
  t.tHead.append(head);
  for (const cells of rows) {
    const tr = el("tr");
    for (const c of cells) {
      const td = el("td");
      if (c instanceof Node) td.append(c);
      else td.textContent = c;
      tr.append(td);
    }
    t.tBodies[0].append(tr);
  }
}

function signed(value) {
  return el("span", { class: value >= 0 ? "up" : "down" }, money(value));
}

async function loadState() {
  const s = await api("/api/state");
  const last = s.equity.at(-1);
  $("#meta").textContent = `${s.mode} ${s.market}, quote ${s.quote}`;
  $("#equity-now").textContent = last ? `${Number(last.value).toFixed(2)} ${s.quote}` : "no equity yet";
  const chart = $("#equity-chart");
  chart.replaceChildren();
  if (s.equity.length > 1) {
    const values = s.equity.map((e) => e.value);
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const d = values.map((v, i) => `${i ? "L" : "M"}${(i / (values.length - 1)) * 300} ${55 - ((v - lo) / span) * 50}`).join(" ");
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", d);
    chart.append(path);
  }
  const plans = $("#plans");
  plans.replaceChildren(...s.plans.map(planCard));
  if (!s.plans.length) plans.append(el("p", { class: "empty" }, "No plans in the last three days."));
  table("#positions", ["Asset", "Side", "Term", "Size", "Entry", "Now", "Stop", "Target", "Open P&L", ""],
    s.positions.map((p) => {
      const sign = p.side === "long" ? 1 : -1;
      const pnl = p.price == null ? 0 : (p.price - p.entry_price) * p.qty * sign;
      const close = el("button", { type: "button" }, "Close");
      close.addEventListener("click", () => {
        if (confirm(`Close ${p.asset} at market?`)) act(`/api/positions/${p.id}/close`, close);
      });
      return [p.asset, p.side, p.horizon, fmt(p.qty, 4), fmt(p.entry_price), fmt(p.price), fmt(p.stop), fmt(p.take_profit), signed(pnl), close];
    }));
  table("#closed", ["Closed", "Asset", "Side", "Term", "Exit", "Why", "P&L"],
    s.closed.map((p) => [p.closed_at.slice(0, 10), p.asset, p.side, p.horizon, fmt(p.exit_price), p.exit_reason, signed(p.pnl)]));
}

async function tick() {
  try {
    const runs = await loadRuns();
    if (!state.run && runs[0]) await selectRun(runs[0].id);
    else if (state.run) await pollEvents();
  } catch (e) {
    console.error(e);
  }
}

drawFloor();
$("#run").addEventListener("change", (e) => selectRun(e.target.value));
$("#sync").addEventListener("click", (e) => act("/api/sync", e.target).then(() => { e.target.disabled = false; }));
await tick();
await loadState();
setInterval(tick, 2500);
setInterval(loadState, 15000);
