// Agent Map: the agents of the space on screen, as a live map.
// A coordinator (the one agent that started others) sits in the middle with its workers around
// it; with none, the space is the hub and every agent is on the ring.
//
// What you see for an agent: its program's logo in a disc; the kind of work it does now as a
// coloured badge (files, shell, network, browser, agents, skills, memory, you; three dots while
// it thinks); a ring that turns while it works; under its name the last calls as a row of
// coloured beads, and a line that names the call. Its spoke is as thick as it was busy in the
// last five minutes. When a call starts, a pulse in that call's colour flies out along the
// spoke and a ring spreads where it lands; when the call ends, a pulse flies back; when the
// agent finishes its turn, a wide ring leaves it. A click shows the agent.
//
// What an agent does comes from its local transcript (agents.py, every 2 s while this shows);
// who started whom and the statuses come from Herdr. The work an agent runs out of sight (its
// in-process subagents, background shells, Kimi agents) hangs under it as smaller nodes, from
// the same transcripts; a finished one fades out over FADE seconds. Only the pulses are drawn by a timer, and
// only while one flies: the rest moves natively, so an idle map costs nothing.
// The idea and the stations follow lot-map by alexeyw (github.com/alexeyw/lot-map, MIT).
//
// It runs as a panel beside Files and Changes (props { panel: true }, a child `agentmap` of the
// `panel-body` stack) or as a pane (pane.split { mod: "agent-map" }).

import { View, div, svg, image, PathBuilder } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { agents, terminals, spaces, theme, settings, exec, appHome, run, props, layout } from "herdr";

const DIR = "mods/agent-map";
const SCRIPT = () => `${appHome()}/${DIR}/agents.py`;
const POLL = 2000, FRAME = 33, FLY = 750, RIPPLE = 550, DONE = 1100;
const R = 25, HUB = 36, KR = 17, FADE = 180;
const COLOR = { files: "#5aa9ff", shell: "#4cd08a", network: "#b48cff", browser: "#ff9f5a", agents: "#ffd166", skills: "#ff7ab6", memory: "#62c7ba", you: "#e8e6e1", tool: "#9aa0aa" };
const LONG = { files: "Files", shell: "Shell", network: "Network", browser: "Browser", agents: "Agents", skills: "Skills", memory: "Memory", you: "You", tool: "Tool" };
const APP = { "claude-code": "Claude", codex: "Codex", "cursor-agent": "Cursor", pi: "Pi" };
const LOGO = { "claude-code": "icons/claude.svg", codex: "icons/codex.svg", "cursor-agent": "icons/cursor.svg", pi: "icons/pi.svg", gemini: "icons/gemini.svg", grok: "icons/grok.svg", kimi: "icons/kimi.svg" };
const KID_APP = { subagent: "claude-code", kimi: "kimi", codex: "codex", shell: "shell" };
const ago = (s) => (s == null ? "" : s < 90 ? `${Math.max(0, Math.round(s))}s` : s < 5400 ? `${Math.round(s / 60)}m` : `${Math.round(s / 3600)}h`);
const zoomOf = (s) => (Number(s?.zoom) > 0 ? Number(s.zoom) : 1);
const alpha = (hex, a) => `${hex.slice(0, 7)}${Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, "0")}`;
const ease = (p) => 1 - (1 - p) ** 3;

// props { demo: true }: a made-up team, for a picture of the mod or a look at it with no agents running.
const DEMO = {
  space: { id: "demo", name: "shop-api", active: true },
  list: [
    { address: "d0", status: "working", app: "claude-code", cwd: "", seq: 9, name: "coordinator", parent: null },
    { address: "d1", status: "working", app: "codex", cwd: "", seq: 8, name: "checkout", parent: "d0" },
    { address: "d2", status: "working", app: "claude-code", cwd: "", seq: 7, name: "search", parent: "d0" },
    { address: "d3", status: "done", app: "claude-code", cwd: "", seq: 6, name: "docs", parent: "d0" },
    { address: "d4", status: "blocked", app: "codex", cwd: "", seq: 5, name: "payments", parent: "d0" },
    { address: "d5", status: "idle", app: "cursor-agent", cwd: "", seq: 4, name: "reviewer", parent: "d0" },
    { address: "d6", status: "working", app: "claude-code", cwd: "", seq: 3, name: "tests", parent: "d0" },
  ],
  info: {
    d0: { station: "agents", label: "Send the next task to checkout", running: true, call: "a", trail: ["files", "agents", "agents", "you", "agents"], recent: 6, model: "fable-5-2" },
    d1: { station: "shell", label: "Run the cart tests", running: true, call: "b", trail: ["files", "files", "shell", "files", "shell"], recent: 8, model: "gpt-6" },
    d2: { station: "network", label: "WebFetch the search API docs", running: true, call: "c", trail: ["files", "shell", "network", "files", "network"], recent: 4, model: "fable-5-2" },
    d3: { station: "files", label: "Write README.md", running: false, call: "d", trail: ["files", "files", "skills", "files"], recent: 1, model: "fable-5-2", age: 240 },
    d4: { station: "you", label: "AskUserQuestion", running: false, call: "e", trail: ["files", "shell", "you"], recent: 2, model: "gpt-6", age: 60 },
    d5: { station: "browser", label: "chrome: read_page", running: false, call: "f", trail: ["browser", "browser", "files"], recent: 0, model: "auto", age: 2700 },
    d6: { label: "Run the unit tests", trail: ["shell", "files", "shell", "shell", "files", "shell"], recent: 7, model: "fable-5-2" },
  },
  kids: [
    { id: "k1", parent: "d0", kind: "subagent", name: "Find the cart code", running: true, station: "files", label: "Grep applyCoupon", call: "g", trail: ["files", "files"], recent: 3, model: "haiku-5-5", age: 4 },
    { id: "k2", parent: "d0", kind: "shell", name: "Run the load test", running: true, station: "shell", label: "Run the load test", call: "h", trail: [], recent: 0, age: 30 },
    { id: "k3", parent: "k2", kind: "kimi", name: "load · worker 1", running: true, station: "network", label: "curl /cart", call: "i", trail: ["shell", "network"], recent: 2, model: "kimi-k3", age: 2 },
    { id: "k4", parent: "d1", kind: "subagent", name: "Check the totals", running: false, ended: 60, station: "files", label: "Read totals.ts", trail: ["files"], recent: 1, age: 60 },
  ],
};

export default class AgentMap extends View {
  init(_p, cx) {
    this.demo = Boolean(props()?.demo);
    this.info = this.demo ? { ...DEMO.info, ...Object.fromEntries(DEMO.kids.map((k) => [k.id, k])) } : {};   // address or kid id -> what agents.py read
    this.kids = this.demo ? DEMO.kids : [];   // work with no Herdr terminal, each under the one that started it
    this.more = {};       // parent -> how many kids agents.py left out
    this.was = {};        // address -> status at the last poll
    this.size = null;     // the canvas, layout px
    this.pos = new Map(); // address -> where its node is; "hub" for the middle
    this.anims = [];      // pulses and rings in flight
    cx.timer.every(POLL, (cx) => this.poll(cx));
    cx.timer.every(FRAME, (cx) => {
      if (!this.anims.length) return;
      const now = Date.now();
      this.anims = this.anims.filter((a) => now - a.t0 < a.dur);
      cx.notify();
    });
    this.poll(cx);
  }

  // As a panel, only while it is the panel on screen.
  showing() {
    if (!props()?.panel) return true;
    const find = (n, id) => (!n ? null : n.id === id ? n : (n.children ?? []).map((c) => find(c, id)).find(Boolean) ?? null);
    const root = layout(), panel = find(root, "panel"), body = find(root, "panel-body");
    return Boolean(panel && !panel.hidden && body?.active === "agentmap");
  }

  // A tab with a name of its own goes by it; a numbered tab by its program and number.
  nameOf(a, t) {
    const app = APP[a.app ?? t.agent] ?? a.app ?? t.agent ?? "Agent";
    const tab = String(a.tab_name ?? "").trim();
    if (tab && !/^\d+$/.test(tab)) return tab;
    return t.name || `${app} ${tab || a.address}`;
  }

  // The agents of the shown space, with who started each one.
  team() {
    if (this.demo) return { space: DEMO.space, list: DEMO.list };
    const space = spaces().find((s) => s.active);
    if (!space) return { space: null, list: [] };
    const terms = new Map(terminals().map((t) => [t.address, t]));
    const mine = agents().filter((a) => a.space === space.id);
    const here = new Set(mine.map((a) => a.address));
    const list = mine.map((a) => {
      const t = terms.get(a.address) ?? {};
      return { address: a.address, status: a.status, app: a.app ?? t.agent ?? "", cwd: t.cwd ?? "", seq: a.seq ?? 0,
        pid: t.foreground?.pid ?? null, name: this.nameOf(a, t), parent: here.has(t.parent) ? t.parent : null };
    });
    return { space, list };
  }

  // The agents with their kids after them: one list for the map, the rows and the pulses.
  // A kid is "working" while it runs and "done" after; `ended` is how long ago it finished.
  withKids(list) {
    const ids = new Set([...list.map((a) => a.address), ...this.kids.map((k) => k.id)]);
    const kids = this.kids.filter((k) => ids.has(k.parent)).map((k) => ({
      address: k.id, kid: k.kind, status: k.running ? "working" : "done", app: KID_APP[k.kind] ?? "", cwd: "",
      seq: -(k.age ?? 0), name: k.name, parent: k.parent, ended: k.ended ?? null }));
    return [...list, ...kids];
  }

  poll(cx) {
    if (this.demo || this.busy || !this.showing()) return;
    const { list } = this.team();
    if (!list.length) return;
    this.busy = true;
    cx.spawn(async (cx) => {
      try {
        const r = await exec("python3", [SCRIPT(), JSON.stringify(list.map((a) => ({ address: a.address, agent: a.app, cwd: a.cwd, status: a.status, pid: a.pid })))], { timeout: 15000 });
        const out = JSON.parse(r.stdout || "{}");
        const kids = Array.isArray(out.kids) ? out.kids : [];
        const next = { ...(out.agents ?? {}), ...Object.fromEntries(kids.map((k) => [k.id, k])) };
        this.kids = kids;
        this.more = out.more ?? {};
        this.events(this.withKids(list), this.info, next);
        const same = JSON.stringify(next) === JSON.stringify(this.info);
        this.info = next;
        this.failed = "";
        if (!same) cx.notify();
      } catch (e) {
        if (!this.failed) { this.failed = String(e?.message ?? e); cx.notify(); }
      }
      this.busy = false;
    });
  }

  // What changed since the last poll, as pulses: a call began (out), a call ended (back), a turn ended (a wide ring).
  events(list, before, after) {
    const now = Date.now(), first = !Object.keys(before).length;
    for (const a of list) {
      const b = before[a.address], n = after[a.address];
      const from = a.parent && this.pos.has(a.parent) ? a.parent : "hub";
      if (!first && n?.call && n.call !== b?.call) {
        const c = COLOR[n.station] ?? COLOR.tool;
        this.anims.push({ kind: "fly", from, to: a.address, color: c, t0: now, dur: FLY }, { kind: "ring", at: a.address, color: c, t0: now + FLY - 80, dur: RIPPLE + FLY });
      } else if (!first && b?.running && n && !n.running && n.call === b.call) {
        this.anims.push({ kind: "fly", from: a.address, to: from, color: COLOR[n.station] ?? COLOR.tool, t0: now, dur: FLY });
      }
      const was = this.was[a.address];
      if (was === "working" && a.status !== "working") this.anims.push({ kind: "ring", at: a.address, color: "#ffffff", t0: now, dur: DONE, wide: true });
      this.was[a.address] = a.status;
    }
  }

  // What an agent does: the station (or "ai" while it thinks), its colour, the line under its name, whether it is live.
  doing(a, t) {
    const i = this.info[a.address] ?? {};
    const working = a.status === "working";
    if (working && i.station && i.running) return { key: i.station, color: COLOR[i.station] ?? COLOR.tool, line: `${LONG[i.station] ?? "Tool"} · ${i.label ?? i.tool ?? ""}`, live: true };
    if (working) return { key: "ai", color: t.working, line: i.label ? `Thinking · after ${i.label}` : "Thinking", live: true };
    if (a.status === "blocked") return { key: "you", color: t.blocked, line: "Needs you", live: false, alarm: true };
    if (a.kid) {
      const how = i.status && i.status !== "completed" ? i.status : "Done";
      return { key: i.station ?? null, color: i.station ? COLOR[i.station] : t.dim, line: `${how[0].toUpperCase()}${how.slice(1)} ${ago(a.ended)} ago${i.label && i.label !== a.name ? ` · ${i.label}` : ""}`, live: false };
    }
    return { key: i.station ?? null, color: i.station ? COLOR[i.station] : t.dim, line: i.label ? `Last: ${i.label}` : a.status === "done" ? "Done" : "Idle", live: false };
  }

  // Where everything goes, in layout px: the hub, then rings.
  place(list, W, H) {
    const kids = (id) => list.filter((a) => a.parent === id);
    const roots = list.filter((a) => !a.parent);
    const bosses = roots.filter((r) => kids(r.address).length);
    const center = bosses.length === 1 ? bosses[0] : null;
    const ring = center ? [...kids(center.address), ...roots.filter((r) => r !== center)] : roots;
    const depth = (a, seen = 0) => (seen > 8 ? 0 : Math.max(0, ...kids(a.address).map((c) => 1 + depth(c, seen + 1))));
    const D = Math.max(0, ...ring.map((a) => depth(a)));
    const cx = W / 2, cy = H / 2 - 8, rx = Math.max(60, W / 2 - 78), ry = Math.max(50, H / 2 - 74);
    const f = (level) => (D ? 0.58 + (0.42 * (level - 1)) / D : 1);   // level 1 is the ring; the deepest kids sit on the rim
    const pos = new Map([["hub", { x: cx, y: cy }]]), spokes = [];
    if (center) pos.set(center.address, pos.get("hub"));
    // a node, then its kids fanned out in its sector, one level further out
    const put = (a, ang, sector, level, from, soft, room = 152) => {
      const p = { x: cx + rx * f(level) * Math.cos(ang), y: cy + ry * f(level) * Math.sin(ang), room };
      pos.set(a.address, p);
      spokes.push({ from, to: p, a, soft });
      const k = kids(a.address), step = Math.min(0.5 / level, (sector * 0.9) / Math.max(1, k.length));
      // the room a kid has for its name: the arc between it and the next one
      const kidRoom = k.length > 1 ? step * ((rx + ry) / 2) * f(level + 1) : 152;
      k.forEach((c, m) => put(c, ang + (m - (k.length - 1) / 2) * step, step, level + 1, a.address, false, kidRoom));
    };
    ring.forEach((a, n) => put(a, -Math.PI / 2 + (n * 2 * Math.PI) / Math.max(1, ring.length), ((2 * Math.PI) / Math.max(1, ring.length)) * 0.8, 1, "hub", !center || a.parent !== center.address));
    return { center, pos, spokes, orbit: { cx, cy, rx: rx * f(1), ry: ry * f(1) } };
  }

  // A kid has no terminal: a click on it shows the agent it belongs to.
  focus(a) {
    if (this.demo) return;
    const by = new Map(this.kids.map((k) => [k.id, k]));
    let id = a.address;
    for (let n = 0; n < 12 && by.has(id); n++) id = by.get(id).parent;
    run("agent.focus", { terminal: id });
  }

  radius(a, big = false) { return big ? HUB : a.kid ? KR : R; }
  fade(a) { return a.kid && a.status !== "working" ? Math.max(0.15, 1 - (a.ended ?? 0) / FADE) : 1; }

  // The last calls as beads, oldest first; the newest is the largest.
  beads(i) {
    const trail = i.trail ?? [];
    return h_flex().h(8).gap(3).items_center().justify_center()
      .children(trail.map((s, n) => { const last = n === trail.length - 1; return div().size(last ? 6 : 4).flex_none().rounded_full().bg(alpha(COLOR[s] ?? COLOR.tool, last ? 1 : 0.35 + 0.5 * (n / trail.length))); }));
  }

  node(a, p, t, big = false) {
    const d = this.doing(a, t), i = this.info[a.address] ?? {}, r = this.radius(a, big);
    const w = a.kid ? Math.max(44, Math.min(120, (p.room ?? 120) - 4)) : 152, tight = a.kid && w < 80;   // crowded kids: the name only
    const working = a.status === "working";
    const edge = working ? d.color : a.status === "blocked" ? t.blocked : a.status === "done" ? (a.kid ? t.border : t.done) : t.border;
    const logo = a.kid === "shell" ? svg(`${DIR}/shell.svg`).size(15).text_color(working ? COLOR.shell : t.muted)
      : image(LOGO[a.app] ?? "icons/agent.svg").size(big ? 28 : a.kid ? 16 : 22).opacity(working ? 1 : a.status === "idle" ? 0.45 : 0.75);
    return div().id(`n-${a.address}`).absolute().left(p.x - w / 2).top(p.y - r).w(w).flex().flex_col().items_center().cursor_pointer().opacity(this.fade(a))
      .on_click(() => this.focus(a))
      .child(div().relative().size(2 * r).flex_none()
        // a soft glow and a turning ring while it works; a slow red beat when it needs you
        .when(working, (el) => el
          .child(div().absolute().left(-9).top(-9).size(2 * r + 18).rounded_full().bg(alpha(d.color, 0.16)).loop("opacity", { from: 0.25, to: 1, period: 1500 }))
          .child(svg(`${DIR}/arc.svg`).absolute().left(-6).top(-6).size(2 * r + 12).text_color(d.color).spin(d.key === "ai" ? 2600 : 1300)))
        .when(Boolean(d.alarm), (el) => el.child(div().absolute().left(-6).top(-6).size(2 * r + 12).rounded_full().border(2).border_color(t.blocked).loop("opacity", { from: 0.15, to: 1, period: 900 })))
        .child(div().size(2 * r).rounded_full().bg(working ? alpha(d.color, 0.13) : t.raised).border(working ? 2 : 1).border_color(edge)
          .flex().items_center().justify_center()
          .child(logo))
        // the kind of work, as a badge on the disc's corner
        .when(Boolean(d.key) && a.kid !== "shell", (el) => { const b = a.kid ? 15 : 20; return el.child(div().absolute().left(2 * r - b + 3).top(2 * r - b + 3).size(b).rounded_full().bg(d.live ? d.color : t.surface)
          .border(1).border_color(d.live ? t.background : alpha(d.color, 0.6)).flex().items_center().justify_center()
          .child(svg(`${DIR}/${d.key}.svg`).size(a.kid ? 8 : 11).text_color(d.live ? "#101216" : d.color))); }))
      .child(div().mt(a.kid ? 4 : 6).max_w(w).truncate().text_size(a.kid ? 10.5 : 11.5).font_medium().text_color(a.status === "idle" || (a.kid && !working) ? t.muted : t.foreground).child(a.name))
      .when(!tight && (!a.kid || (i.trail ?? []).length > 0), (el) => el.child(div().mt(3).child(this.beads(i))))
      .when(!tight, (el) => el.child(div().mt(2).max_w(w).truncate().text_size(a.kid ? 9.5 : 10).text_color(d.live ? alpha(d.color, 0.95) : t.dim).child(d.line)));
  }

  // A pulse or a ring in flight, as elements at where it is now.
  flight(an, now) {
    const p = (now - an.t0) / an.dur;
    if (p < 0 || p >= 1) return [];
    if (an.kind === "fly") {
      const a = this.pos.get(an.from), b = this.pos.get(an.to);
      if (!a || !b) return [];
      return [0, 1, 2, 3].map((k) => {
        const q = ease(Math.max(0, p - k * 0.045)), s = 9 - 2 * k;
        return div().absolute().left(a.x + (b.x - a.x) * q - s / 2).top(a.y + (b.y - a.y) * q - s / 2).size(s).rounded_full()
          .bg(alpha(an.color, (1 - 0.24 * k) * (p > 0.85 ? (1 - p) / 0.15 : 1)));
      });
    }
    const at = this.pos.get(an.at);
    if (!at) return [];
    const lead = an.wide ? 0 : FLY / an.dur;          // a landing ring waits for its pulse
    if (p < lead) return [];
    const q = (p - lead) / (1 - lead), r = R + 4 + (an.wide ? 46 : 20) * ease(q);
    return [div().absolute().left(at.x - r).top(at.y - r).size(2 * r).rounded_full().border(an.wide ? 2 : 1.5).border_color(alpha(an.color, (1 - q) * (an.wide ? 0.6 : 0.9)))];
  }

  canvas(t, list, space) {
    const Z = zoomOf(settings());
    const el = div().id("map").relative().flex_1().min_h(200).w_full().overflow_hidden().bg(t.canvas)
      .on_size_change((s, cx) => { this.size = { width: s.width / Z, height: s.height / Z }; cx.notify(); });
    if (!this.size) return el;
    const { width: W, height: H } = this.size;
    const { center, pos, spokes, orbit } = this.place(list, W, H);
    this.pos = pos;
    const layer = (path, color) => window.paint_path(path, color).absolute().left(0).top(0).size_full();
    // the ring the agents sit on, dotted
    let ring = PathBuilder.stroke(1).dash_array([1.5, 7]);
    for (let n = 0; n <= 72; n++) {
      const a = (n / 72) * 2 * Math.PI, x = orbit.cx + orbit.rx * Math.cos(a), y = orbit.cy + orbit.ry * Math.sin(a);
      ring = n ? ring.line_to(x, y) : ring.move_to(x, y);
    }
    const lines = spokes.map((sp) => {
      const s = { ...sp, from: pos.get(sp.from), fromId: sp.from };
      const d = this.doing(s.a, t), busy = Math.min(8, this.info[s.a.address]?.recent ?? 0);
      const live = s.a.status === "working";
      // from the rim of one disc to the rim of the other
      const len = Math.hypot(s.to.x - s.from.x, s.to.y - s.from.y) || 1, ux = (s.to.x - s.from.x) / len, uy = (s.to.y - s.from.y) / len;
      const fromA = s.fromId === "hub" ? null : list.find((x) => x.address === s.fromId);
      const a0 = (!fromA || fromA === center ? HUB : this.radius(fromA)) + 5, b0 = this.radius(s.a) + 9;
      const f = this.fade(s.a);
      const path = PathBuilder.stroke(1 + busy * 0.4 + (live ? 0.6 : 0)).move_to(s.from.x + ux * a0, s.from.y + uy * a0).line_to(s.to.x - ux * b0, s.to.y - uy * b0).build();
      return layer(path, live ? alpha(d.color, 0.75 * f) : busy ? alpha(d.color, 0.28 * f) : f < 1 ? alpha(t.border, f) : t.border);
    });
    const hub = pos.get("hub");
    const team = list.filter((a) => !a.kid), working = team.filter((a) => a.status === "working").length;
    const hubNode = center ? this.node(center, hub, t, true)
      : div().absolute().left(hub.x - 76).top(hub.y - HUB).w(152).flex().flex_col().items_center()
        .child(div().relative().size(2 * HUB).flex_none()
          .when(working > 0, (el) => el.child(div().absolute().left(-10).top(-10).size(2 * HUB + 20).rounded_full().bg(alpha(t.working, 0.12)).loop("opacity", { from: 0.2, to: 1, period: 2400 })))
          .child(div().size(2 * HUB).rounded_full().bg(t.surface).border(1).border_color(working ? alpha(t.working, 0.7) : t.input).flex().flex_col().items_center().justify_center()
            .child(div().text_size(18).font_semibold().text_color(working ? t.working : t.muted).child(String(working || team.length)))
            .child(div().text_size(9).text_color(t.dim).child(working ? "working" : team.length === 1 ? "agent" : "agents"))))
        .child(div().mt(6).max_w(152).truncate().text_size(11.5).font_medium().text_color(t.muted).child(space?.name ?? ""));
    const now = Date.now();
    return el.child(layer(ring.build(), alpha(t.foreground, 0.16))).children(lines).child(hubNode)
      .children(list.filter((a) => a !== center && pos.has(a.address)).map((a) => this.node(a, pos.get(a.address), t)))
      .children(this.anims.flatMap((an) => this.flight(an, now)));
  }

  // The rows' order: the agents, newest first, each followed by its kids (working first), depth first.
  ordered(list) {
    const out = [], seen = new Set();
    const walk = (a, depth) => {
      if (seen.has(a.address)) return;
      seen.add(a.address); out.push([a, depth]);
      list.filter((c) => c.kid && c.parent === a.address).sort((x, y) => (x.status === "working" ? 0 : 1) - (y.status === "working" ? 0 : 1) || y.seq - x.seq).forEach((c) => walk(c, depth + 1));
    };
    [...list].filter((a) => !a.kid).sort((a, b) => b.seq - a.seq).forEach((a) => walk(a, 0));
    list.forEach((a) => walk(a, 0));
    return out;
  }

  rows(t, list) {
    const mark = { working: t.working, blocked: t.blocked, done: t.done };
    return v_flex().id("rows").flex_none().max_h(200).overflow_y_scrollbar().border_t(1).border_color(t.border).py(4)
      .children(this.ordered(list).map(([a, depth]) => {
        const d = this.doing(a, t), i = this.info[a.address] ?? {}, more = this.more[a.address];
        return h_flex().id(`r-${a.address}`).h(a.kid ? 22 : 26).pl(12 + 14 * depth).pr(12).gap(8).items_center().cursor_pointer().hover((s) => s.bg(t.hover)).opacity(this.fade(a))
          .on_click(() => this.focus(a))
          .child(div().size(18).flex_none().rounded_full().bg(d.live ? d.color : alpha(d.color, 0.14)).flex().items_center().justify_center()
            .when(d.live, (el) => el.loop("opacity", { from: 0.55, to: 1, period: 1300 }))
            .child(d.key ? svg(`${DIR}/${d.key}.svg`).size(10).text_color(d.live ? "#101216" : d.color) : div().size(5).rounded_full().bg(mark[a.status] ?? t.border)))
          .child(div().w(Math.max(60, 104 - 14 * depth)).flex_none().truncate().text_size(a.kid ? 10.5 : 11.5).text_color(a.status === "idle" || (a.kid && !d.live) ? t.muted : t.foreground).child(a.name))
          .child(div().flex_1().min_w(0).truncate().text_size(a.kid ? 10 : 11).text_color(d.live ? t.muted : t.dim).child(d.line))
          .child(div().flex_none().text_size(10).text_color(t.dim).child([more ? `+${more} more` : "", i.model, d.live || a.kid ? "" : ago(i.age)].filter(Boolean).join(" · ")));
      }));
  }

  render() {
    const t = theme(), { space, list: agentsOnly } = this.team();
    const list = this.withKids(agentsOnly);
    const working = agentsOnly.filter((a) => a.status === "working").length, blocked = agentsOnly.filter((a) => a.status === "blocked").length;
    const behind = list.filter((a) => a.kid && a.status === "working").length;
    const root = v_flex().id("agentmap").size_full().bg(t.background).text_color(t.foreground)
      .when(Boolean(props()?.panel), (el) => el.rounded(10).overflow_hidden().border_1().border_color(t.border))
      .child(h_flex().h(40).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().flex_1().min_w(0).truncate().font_semibold().text_size(13).child(space ? space.name : "No space"))
        .when(working > 0, (el) => el.child(svg(`${DIR}/arc.svg`).size(12).flex_none().text_color(t.working).spin(1300)))
        .child(div().flex_none().text_size(11).text_color(working ? t.working : t.dim).child(`${working} working`))
        .when(behind > 0, (el) => el.child(div().flex_none().text_size(11).text_color(t.muted).child(`+${behind} in the background`)))
        .when(blocked > 0, (el) => el.child(div().flex_none().text_size(11).text_color(t.blocked).child(`${blocked} need you`))));
    if (!list.length) return root.child(div().flex_1().flex().items_center().justify_center().text_size(12.5).text_color(t.muted).child("No agents in this space"));
    return root.child(this.canvas(t, list, space)).child(this.rows(t, list))
      .when(Boolean(this.failed), (el) => el.child(div().px(12).py(4).text_size(10).text_color(t.blocked).truncate().child(`Can't read the transcripts: ${this.failed}`)));
  }
}
