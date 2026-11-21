# Agent Map

A person opens it beside their work and sees every agent of the space as a node on a ring: which ones work, what kind of tool each one uses now, and what the call is. Pulses fly along the spokes as calls start and end.

![Agent Map](preview.png)

**What you see:**

- A header 40 px high: the space's name; at the right a small turning arc and "N working" in the theme's `working` color, and "N need you" in `blocked` when any do.
- The map on `theme().canvas`: a dotted ellipse; a hub in the middle; one node per agent on the ellipse.
  - The backdrop, behind everything: a still sky of 50 to 170 small dots (one per 2600 px², seeded, so it does not move between frames), each joined to its two nearest neighbours within 80 px by a 0.6 px line in `foreground` at 7.5%; one dot in ten brighter and white; up to 12 green dots that twinkle (opacity loop, 1.6 to 4.4 s). A band of violet light (`#8b7cff`, 7.5% at its middle, a third of the width) swings across and back every 18 s.
  - A working node lights a small constellation around it in its call's colour: five (a kid: three) 8 px rings with a dot, 16 to 40 px out, joined to the node and in pairs to each other, breathing (opacity 0.3 to 1).
  - An idle spoke is a dotted thread; a busy or live one a solid line.
  - The hub with no coordinator: a 72 px disc with the count of working agents (or of agents) and the space's name under it. With one coordinator (the only agent that started others) the hub is that agent's node, 72 px.
  - A node: a 50 px disc with the program's logo in full color (`icons/claude.svg`, `codex.svg`, `cursor.svg`, `pi.svg`, `gemini.svg`, `grok.svg`, else `icons/agent.svg`; 45% opacity when idle). A 20 px badge on its lower right corner holds the icon of the kind of work, filled with that kind's color while the call runs. Under the disc: the name (11.5 px), a row of up to 7 beads (4 px, the newest 6 px), and one line (10 px) such as "Shell · Run the cart tests", "Thinking · after …", "Needs you", "Last: …".
  - Colors by kind: files `#5aa9ff`, shell `#4cd08a`, network `#b48cff`, browser `#ff9f5a`, agents `#ffd166`, skills `#ff7ab6`, memory `#62c7ba`, you `#e8e6e1`, other `#9aa0aa`; thinking uses `theme().working`.
  - Spokes from the hub's rim to each node's rim, 1 px plus 0.4 px per call in the last five minutes (8 at most), in the kind's color while the agent works.
  - Kids: the work an agent runs with no Herdr terminal (subagents, background shells, Kimi Code and `codex exec` agents), each a 34 px node one ring further out than the one that started it, fanned out in its sector, at any depth. Its logo (`icons/claude.svg`, `kimi.svg`, `codex.svg`, or the shell icon), a 15 px badge, the name (10.5 px) and line; when kids are crowded, a node is as wide as the arc it has and shows the name only. A finished kid: "Done 40s ago · <last call>" (or its end status, such as "Failed"), its node and spoke fade from 1 to 0.15 over 180 s, then agents.py drops it.
  - The header adds "+N in the background" (running kids) in `muted`.
- A list under the map, at most 200 px high: per agent an 18 px colored chip with the kind's icon, the name (104 px wide), the line, and at the right the model and the age of the last call. Each agent's kids follow it, 14 px further in per level, running ones first; "+N more" when agents.py left some out.

**How it behaves:**

- working: a soft glow that breathes (opacity loop, 1500 ms) and a thin arc that turns around the disc (1300 ms; 2600 ms while thinking). blocked: a red ring that beats (900 ms) and the line "Needs you". done: the disc's edge in `theme().done`. idle: dim.
- A call starts: four dots with a tail fly from the hub (or the parent) to the node in 750 ms, then a ring spreads there; the link lights up as a beam that grows from the parent in 400 ms and fades in 600 ms; a streak shoots in from out of the map onto the node (650 ms, its tail in three fading parts). The call ends: the dots fly back. The turn ends: a wide white ring leaves the node (1100 ms).
- A click on a node or a row runs `agent.focus { terminal }`; on a kid, with the terminal of the agent it belongs to.
- A new kid gets a pulse from its parent; a kid that ends sends the wide ring, as an agent does.
- As a panel (`props { panel: true }`, a child `agentmap` of a `panel-body` stack) it reads transcripts only while that child shows. `props { demo: true }` shows a made-up team and reads nothing.

**Built from:**

- `mods/agent-map/`: `main.js`, `agents.py`, `mod.json`, and the icons `files, shell, network, browser, agents, skills, memory, you, tool, ai, arc` (`.svg`).
- `herdr`: `agents()` (address, space, status, app, tab_name, seq), `terminals()` (cwd, parent, name, foreground.pid), `spaces()`, `theme()`, `settings()` (zoom), `exec`, `appHome`, `run`, `props`, `layout`.
- `agents.py '<json list of {address, agent, cwd, status, pid}>'` prints `{agents: {address: {station, tool, label, running, call, model, ctx, trail, recent, age}}, kids: [{id, parent, kind, name, running, ended, station, label, call, trail, recent, model, age}], more: {parent: n}}` (see its docstring for where each kind of kid comes from). For an agent it reads the last 400 KB of the transcript: Claude Code `~/.claude/projects/<cwd with every non-alphanumeric as ->/*.jsonl` (`tool_use` / `tool_result` blocks), Codex `~/.codex/sessions/*/*/*/rollout-*.jsonl` (`function_call`, `custom_tool_call` and their outputs; the first line names the cwd). A shell command is files, network or shell by its first word.
- Drawing: nodes and flying dots are absolutely placed `div`s; spokes and the ellipse are `window.paint_path(PathBuilder…)`; the arc is an `svg().spin()`; glows use `.loop("opacity", …)`. One `cx.timer.every(33)` redraws only while a pulse is in flight; a second one polls every 2000 ms.

**Watch out:**

- Path coordinates follow Herdr's zoom (0.1.16): do not multiply them by the zoom. Sizes from `on_size_change` are real px: divide by the zoom.
- `.loop` swings one property; two loops on one element do not move it along a line. That is why the pulses are drawn by the timer.
- `.bg()` takes a colour, not a `Background`: a gradient is painted with `window.paint_path(RECT(), Background.linear_gradient(...))` (else the mod shows "unsupported argument type").
- Agents that share a folder get that folder's newest transcripts, working agents first: a guess.
- A parent that Herdr does not list as an agent of the space is not drawn as a coordinator.
- Kids come only from an exact transcript (the pid's `~/.claude/sessions/<pid>.json`): a guessed one could show another session's work.
- A Kimi wire.jsonl is long: its turn's start is often older than the tail read. A live `kimi-code` process in the session's folder (`lsof -d cwd`) is what says it runs; when lsof does not answer, a write in the last 2 minutes does.
- Which background shell started a Kimi or Codex session: walk up `ps` from its process to the one right under the lead, and pick the running shell whose command shows most in that command line. It is remembered in `~/.cache/herdr-agent-map/owners.json`, so a finished session stays under its shell.
- Codex code mode sends JavaScript (`tools.exec_command({cmd: ...})`): the call shown is the first tool it names.

**Done when:**

- `herdr-app check ~/.config/herdr-app/mods/agent-map` passes.
- With `props { demo: true }` it shows seven agents, the coordinator in the middle, four of them working, and four kids: a subagent and a background shell under the coordinator, a Kimi agent under that shell, and a finished subagent of `checkout`, faded.
- In a space with a working Claude Code agent, its node shows the kind and the name of the running call within 2 seconds, and a pulse flies when the next call starts.
- A click on a node shows that agent.
- In a space whose Claude Code agent runs a background shell that starts `kimi -p` or `codex exec` agents, each shows under that shell while it runs, and fades out within 3 minutes after it ends.
