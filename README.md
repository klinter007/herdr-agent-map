# Agent Map

A live map of the agents in a [Herdr](https://herdr.dev) space: who works, on what, with which kind of tool.

![Agent Map](preview.png)

*The picture shows the mod's demo data (`props { demo: true }`), not a real project.*

## What it shows

- **One node per agent** of the space on screen, with its program's logo. If one agent started the others (a coordinator), it sits in the middle with its workers around it. If not, the space is the hub.
- **The kind of work, by color:** files blue, shell green, network purple, browser orange, agents yellow, skills pink, memory teal. Three dots mean the agent is thinking.
- **A night sky behind it:** small dots joined by a faint web, a few that twinkle, and a soft band of light that drifts across. A working agent lights a small constellation around it in the color of its call.
- **Motion:** a working agent has a ring that turns. When it starts a call, its link lights up as a growing beam, a streak shoots in, and a pulse in that color flies out along its spoke; when the call ends, a pulse flies back; when it finishes its turn, a wide ring leaves it.
- **History:** a row of beads under each name shows the last calls. A spoke is thicker when the agent was busier in the last five minutes.
- **Work out of sight, under the agent that runs it:** an agent's in-process subagents (Claude Code), its background shells, and the Kimi Code and `codex exec` agents those shells start show as smaller nodes under it, each with its own kind of work, last calls and state. A Kimi or Codex agent hangs under the background shell that started it. A finished one says "Done 40s ago" and fades out over three minutes. The header counts them ("+5 in the background").
- **A list** under the map: one row per agent, the latest first, with its model, and its background work indented under it. A click on a node or a row shows that agent (for background work: the agent it belongs to).

## Where the data comes from

Statuses and who started whom come from Herdr. What an agent does comes from its local transcript, read by `agents.py` every 2 seconds while the map shows: Claude Code (`~/.claude/projects/...`; the exact session through `~/.claude/sessions/<pid>.json`), Codex (`~/.codex/sessions/...`) and Kimi Code (`~/.kimi-code/sessions/...`). Background work comes from the same files: subagent transcripts (`<session>/subagents/`), background Bash calls and their end notices, and Kimi and `codex exec` sessions in the agent's folder, matched to their shell through `ps`. Transcripts are read from where the last poll stopped, so a quiet space costs a few file checks. Nothing leaves your computer.

## Install

Built and tested on **Herdr app 0.1.16 with herdr-core 0.1.21**, macOS. Needs `python3` on your PATH (standard library only).

Ask your agent in Herdr:

> Add the mod herdr.dev/mods/klinter007/herdr-agent-map

Or by hand:

```sh
git clone https://github.com/klinter007/herdr-agent-map
cp -R herdr-agent-map/mods/agent-map ~/.config/herdr-app/mods/
herdr-app check ~/.config/herdr-app/mods/agent-map
herdr-app do pane.split '{"direction":"right","mod":"agent-map"}'
```

To keep it as a side panel, add this block to the row of your own layout that holds your panes:

```json
{ "id": "agent-map", "type": "block", "size": { "px": 460 }, "content": { "mod": "agent-map" } }
```

## Limits

- Two agents in the same folder: which transcript belongs to which agent is a guess.
- Agents other than Claude Code and Codex show their status, without the kind of work.
- Background work shows only for a Claude Code agent whose exact session is known (Herdr gives its process). Calls to a model API from a script have no transcript: the background shell that runs them shows, not each call.
- A coordinator sits in the middle only when Herdr lists it as an agent of the same space.

## Credit

The idea and the stations follow [lot-map](https://github.com/alexeyw/lot-map) by alexeyw (MIT), which draws one Claude Code session this way. Agent Map is new code for Herdr and draws a whole space.

## License

MIT
