#!/usr/bin/env python3
"""What each agent of a Herdr space does right now, and the work it runs out of sight.

  agents.py '<json: [{address, agent, cwd, status, pid}]>'
    ->  {"agents": {address: {station, tool, label, running, call, model, ctx, trail, recent, age}},
         "kids":   [{id, parent, kind, name, running, ended, station, label, call, trail, recent, model, age}],
         "more":   {parent id: count of hidden kids}}

Herdr agents:
  Claude Code  ~/.claude/sessions/<pid>.json names the session, so its transcript is exact;
               without a pid: the folder's newest transcripts, the working agents first (a guess, `shared`).
  Codex        ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (the first line names its cwd).
Kids (work that has no Herdr terminal), each under the one that started it:
  subagents    <session>/subagents/agent-*.jsonl + .meta.json (Claude Code, any depth)
  shells       background Bash calls of a Claude transcript, ended by their <task-notification>
  Kimi         ~/.kimi-code/sessions/*/session_*/ in the agent's folder (kimi -p, AgentSwarm items);
  Codex exec   ~/.codex/sessions/.../rollout-*.jsonl of `codex exec` runs in the agent's folder;
               both under the background shell whose process started them, when ps shows one
Finished kids stay FADE seconds, so the map can fade them out. Transcripts are read incrementally
(byte offsets in a small cache file), so a quiet space costs a few stat() calls.
Nothing leaves this computer. The stations follow lot-map (github.com/alexeyw/lot-map).
"""
import hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
TAIL = 400_000
FADE = 180            # seconds a finished kid stays on the map
STALE = 900           # with no live owner to ask: a kid with no end event and no write for this long is gone
MAX_KIDS = 24         # per parent; the rest is counted in `more`
CACHE = Path(os.environ.get('XDG_CACHE_HOME') or HOME / '.cache') / 'herdr-agent-map'
FILES = {'cat', 'ls', 'grep', 'rg', 'sed', 'awk', 'mv', 'cp', 'rm', 'mkdir', 'find', 'head', 'tail', 'tee', 'touch', 'wc', 'chmod', 'ln', 'diff', 'tree', 'stat', 'du'}
NET = {'curl', 'wget', 'gh', 'ssh', 'scp', 'rsync', 'kubectl', 'docker', 'aws', 'gcloud', 'npx', 'pip', 'pip3', 'brew', 'ping'}
NOTE = re.compile(r'<task-id>([^<]+)</task-id>\s*<tool-use-id>([^<]+)</tool-use-id>.*?<status>([^<]+)</status>', re.S)
BG_ID = re.compile(r'running in background with ID: ([A-Za-z0-9_-]+)')


def shell_station(cmd):
    words = re.split(r'\s+', re.sub(r'^(cd [^;&]+(&&|;)\s*)+', '', cmd.strip()))
    while words and (words[0] in ('sudo', 'env', 'timeout', 'nohup', 'time') or '=' in words[0]): words = words[1:]
    name = os.path.basename(words[0]) if words else ''
    rest = ' '.join(words[1:3])
    if name in NET or (name == 'git' and re.match(r'(push|pull|fetch|clone)', rest)) or (name in ('npm', 'pnpm', 'yarn', 'uv') and re.match(r'(install|add|ci|sync)', rest)):
        return 'network'
    return 'files' if name in FILES else 'shell'


def classify(tool, inp):
    """(station, label) for one tool call."""
    inp = inp if isinstance(inp, dict) else {}
    base = lambda p: os.path.basename(str(p).rstrip('/')) or str(p)
    if tool in ('Read', 'Write', 'Edit', 'NotebookEdit', 'MultiEdit', 'apply_patch'):
        return 'files', f'{tool} {base(inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or "")}'
    if tool in ('Grep', 'Glob'):
        return 'files', f'{tool} {str(inp.get("pattern", ""))[:40]}'
    if tool in ('Bash', 'PowerShell', 'shell', 'exec', 'exec_command', 'local_shell', 'write_stdin'):
        cmd = inp.get('command') or inp.get('cmd') or inp.get('input') or ''
        if isinstance(cmd, list): cmd = ' '.join(map(str, cmd[2:] if cmd[:2] == ['bash', '-lc'] else cmd))
        label = str(inp.get('description') or str(cmd).strip().split('\n')[0])[:70]
        return shell_station(str(cmd)), label or {'write_stdin': 'Wait for a command'}.get(tool, tool)
    if tool in ('WebFetch', 'WebSearch'):
        return 'network', f'{tool} {str(inp.get("url") or inp.get("query") or "")[:50]}'
    if tool in ('Agent', 'Task', 'Workflow', 'SendMessage', 'spawn_agent', 'send_input', 'wait', 'AgentSwarm', 'WaitFor', 'TaskOutput', 'TaskStop', 'TaskList'):
        return 'agents', f'{tool} {str(inp.get("description") or inp.get("name") or "")[:50]}'.strip()
    if tool in ('Skill', 'ToolSearch'):
        return 'skills', f'{tool} {str(inp.get("skill") or inp.get("query") or "")[:50]}'
    if tool in ('AskUserQuestion', 'TodoWrite', 'TodoList', 'ExitPlanMode', 'update_plan', 'SubagentHandback'):
        return 'you', tool
    if tool.startswith('mcp__'):
        server = tool.split('__')[1] if tool.count('__') >= 2 else tool
        kind = 'browser' if re.search(r'chrome|browser|playwright', server, re.I) else 'memory' if 'memory' in server.lower() else 'network'
        return kind, f'{server}: {tool.split("__")[-1]}'[:60]
    return 'shell' if tool in ('sleep',) else 'tool', tool[:40]


def tail_lines(path, n=TAIL):
    with open(path, 'rb') as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - n))
        data = f.read().decode('utf-8', 'replace')
    lines = data.split('\n')
    return lines[1:] if size > n else lines


def stamp(s):
    try: return __import__('datetime').datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError): return None


def mtime(p):
    try: return p.stat().st_mtime
    except OSError: return None


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False


def summary(calls, last, model, ctx, now):
    """calls: [(station, time)]; last: (name, input, id, done) or None."""
    out = {'model': model, 'ctx': ctx, 'trail': [c[0] for c in calls[-7:]], 'recent': sum(1 for c in calls if c[1] and now - c[1] < 300)}
    if last:
        station, label = classify(last[0], last[1])
        out.update(station=station, tool=last[0], label=label, running=not last[3], call=last[2])
    return out


def read_claude(path, sidechain=False):
    last, done, model, ctx, calls, now = None, set(), None, None, [], time.time()
    for line in tail_lines(path):
        if '"tool_use"' not in line and '"tool_result"' not in line and '"usage"' not in line: continue
        try: d = json.loads(line)
        except ValueError: continue
        if d.get('isSidechain') and not sidechain: continue
        m = d.get('message') or {}
        c = m.get('content')
        if d.get('type') == 'assistant':
            model = m.get('model') or model
            u = m.get('usage') or {}
            if u: ctx = (u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0) + (u.get('cache_creation_input_tokens') or 0)
            for b in c if isinstance(c, list) else []:
                if b.get('type') == 'tool_use':
                    last = b
                    calls.append((classify(b.get('name', ''), b.get('input'))[0], stamp(d.get('timestamp'))))
        elif d.get('type') == 'user':
            for b in c if isinstance(c, list) else []:
                if b.get('type') == 'tool_result': done.add(b.get('tool_use_id'))
    model = re.sub(r'^claude-', '', model or '') or None
    return summary(calls, last and (last.get('name', ''), last.get('input'), last.get('id'), last.get('id') in done), model, ctx, now)


def code_mode(name, arg):
    """Codex's code mode sends JavaScript that calls tools (tools.exec_command({cmd: ...}), ...):
    the call is the first tool it names."""
    code = arg.get('command') if isinstance(arg, dict) else None
    if not isinstance(code, str) or 'tools.' not in code: return name, arg
    m = re.search(r'tools\.exec_command\(\s*\{[^}]*?\bcmd\s*:\s*(["\'`])(.*?)\1', code, re.S)
    if m: return 'exec_command', {'cmd': m.group(2).replace('\\n', '\n')}
    m = re.search(r'\*\*\* (?:Update|Add|Delete) File: (\S+)', code)
    if 'apply_patch' in code and m: return 'apply_patch', {'file_path': m.group(1)}
    m = re.search(r'tools\.(\w+)', code)
    return (m.group(1), {}) if m else (name, arg)


def read_codex(path):
    last, done, model, calls, now = None, set(), None, [], time.time()
    for line in tail_lines(path):
        if '_call' not in line and '"model"' not in line: continue
        try: d = json.loads(line)
        except ValueError: continue
        p = d.get('payload') or {}
        t = p.get('type')
        if t in ('function_call', 'custom_tool_call'):
            arg = p.get('arguments') if t == 'function_call' else {'command': p.get('input')}
            if isinstance(arg, str):
                try: arg = json.loads(arg)
                except ValueError: arg = {'command': arg}
            name, arg = code_mode(p.get('name', ''), arg)
            last = (name, arg, p.get('call_id'))
            calls.append((classify(name, arg)[0], stamp(d.get('timestamp'))))
        elif t in ('function_call_output', 'custom_tool_call_output'): done.add(p.get('call_id'))
        model = p.get('model') or model
    return summary(calls, last and (*last, last[2] in done), model, None, now)


def read_kimi(path):
    """A Kimi Code agent's wire.jsonl: its calls, model, and whether its turn is still open."""
    last, done, model, calls, now, open_, t_end = None, set(), None, [], time.time(), None, None
    for line in tail_lines(path, 200_000):
        if '"tool.' not in line and 'turn.' not in line and 'profile.bind' not in line and 'llm.request' not in line: continue
        try: d = json.loads(line)
        except ValueError: continue
        t, ev, ms = d.get('type'), d.get('event') or {}, d.get('time')
        if t in ('agent.turn.started', 'turn.prompt'): open_ = True
        elif t in ('turn.ended', 'agent.turn.ended'): open_, t_end = False, (ms or 0) / 1000 or t_end
        elif t in ('profile.bind', 'llm.request'): model = d.get('modelAlias') or d.get('model') or model
        elif ev.get('type') == 'tool.call':
            last = (ev.get('name', ''), ev.get('args'), ev.get('toolCallId'))
            calls.append((classify(ev.get('name', ''), ev.get('args'))[0], (ms or 0) / 1000 or None))
        elif ev.get('type') == 'tool.result': done.add(ev.get('toolCallId'))
    out = summary(calls, last and (*last, last[2] in done), model, None, now)
    out['open'], out['t_end'] = open_, t_end
    return out


# --- transcripts of Herdr agents ------------------------------------------------------------

def project_dir(cwd):
    return HOME / '.claude/projects' / re.sub(r'[^A-Za-z0-9]', '-', cwd)


def claude_files(cwd):
    d = project_dir(cwd)
    return sorted(d.glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []


def claude_by_pid(pid):
    """The exact transcript of the Claude Code process `pid`, from ~/.claude/sessions/<pid>.json."""
    try: s = json.loads((HOME / '.claude/sessions' / f'{int(pid)}.json').read_text())
    except (OSError, ValueError, TypeError): return None
    f = project_dir(s.get('cwd') or '') / f'{s.get("sessionId")}.jsonl'
    return f if f.is_file() else None


_codex = None
def codex_files(cwd):
    global _codex
    if _codex is None:
        _codex = {}
        root = HOME / '.codex/sessions'
        files = sorted(root.glob('*/*/*/rollout-*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)[:60] if root.is_dir() else []
        for f in files:
            try:
                with open(f, 'rb') as h: head = h.read(3000).decode('utf-8', 'replace')
            except OSError: continue
            m = re.search(r'"cwd":"([^"]+)"', head)
            if m: _codex.setdefault(m.group(1), []).append(f)
    return _codex.get(cwd, [])


# --- background work inside a Claude transcript (incremental) ----------------------------------

def load_cache(key):
    try: return json.loads((CACHE / f'{key}.json').read_text())
    except (OSError, ValueError): return None


def save_cache(key, data):
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = CACHE / f'{key}.{os.getpid()}.tmp'
        tmp.write_text(json.dumps(data))
        tmp.replace(CACHE / f'{key}.json')
    except OSError:
        pass


def bg_tasks(path):
    """Background shells and subagent calls started in one transcript:
    {tool_use_id: {kind, label, cmd, t0, id, status, t1}}. Reads only the bytes added since the last poll."""
    key = hashlib.sha1(str(path).encode()).hexdigest()[:16]
    size = path.stat().st_size
    c = load_cache(key)
    if not c or c.get('v') != 2 or c.get('off', 0) > size:
        c = {'v': 2, 'off': 0, 'tasks': {}}
    if c['off'] == size:
        return c['tasks']
    tasks = c['tasks']
    by_id = {t['id']: k for k, t in tasks.items() if t.get('id')}
    with open(path, 'rb') as f:
        f.seek(c['off'])
        data = f.read(size - c['off'])
    end = data.rfind(b'\n') + 1          # a half-written last line waits for the next poll
    for raw in data[:end].split(b'\n'):
        if not raw or (b'run_in_background' not in raw and b'task-notification' not in raw and b'"Agent"' not in raw
                       and b'"Task"' not in raw and b'in background with ID' not in raw):
            continue
        line = raw.decode('utf-8', 'replace')
        try: d = json.loads(line)
        except ValueError: continue
        t = stamp(d.get('timestamp'))
        m = d.get('message') if isinstance(d.get('message'), dict) else {}
        content = m.get('content')
        if d.get('type') == 'assistant':
            for b in content if isinstance(content, list) else []:
                if b.get('type') != 'tool_use': continue
                inp = b.get('input') or {}
                if b.get('name') in ('Agent', 'Task'):
                    tasks[b['id']] = {'kind': 'subagent', 'label': str(inp.get('description') or 'Subagent')[:70], 't0': t}
                elif b.get('name') == 'Bash' and inp.get('run_in_background'):
                    cmd = str(inp.get('command') or '')
                    tasks[b['id']] = {'kind': 'shell', 'label': str(inp.get('description') or cmd.split('\n')[0])[:70], 'cmd': cmd[:400], 't0': t}
        elif d.get('type') == 'user':
            for b in content if isinstance(content, list) else []:
                if b.get('type') == 'tool_result' and b.get('tool_use_id') in tasks:
                    g = BG_ID.search(json.dumps(b.get('content')))
                    if g:
                        tasks[b['tool_use_id']]['id'] = g.group(1)
                        by_id[g.group(1)] = b['tool_use_id']
        if 'task-notification' in line:
            for tid, tuid, status in NOTE.findall(line.replace('\\n', '\n')):
                k = tuid if tuid in tasks else by_id.get(tid)
                if k and not tasks[k].get('status'):
                    tasks[k].update(status=status, t1=t or time.time())
    c.update(off=c['off'] + end, tasks=tasks)
    save_cache(key, c)
    return tasks


# --- kids -------------------------------------------------------------------------------------

def trim(kids):
    """At most MAX_KIDS per parent, the working ones and the newest first. Returns (kept, more)."""
    groups, more = {}, {}
    for k in kids: groups.setdefault(k['parent'], []).append(k)
    keep = []
    for parent, ks in groups.items():
        ks.sort(key=lambda k: (not k['running'], -(k.get('t0') or 0)))
        keep += ks[:MAX_KIDS]
        if len(ks) > MAX_KIDS: more[parent] = len(ks) - MAX_KIDS
    ids, parents = {k['id'] for k in keep}, {k['id']: k['parent'] for k in kids}
    for k in keep:   # a kid whose parent was trimmed hangs on its nearest shown ancestor
        while k['parent'] in parents and k['parent'] not in ids: k['parent'] = parents[k['parent']]
    return keep, more


def claude_kids(kids, owner, path, lead_alive, now):
    """Subagents and background shells of one Claude transcript; recurses into subagents.
    lead_alive: whether the Claude process is alive (None: unknown)."""
    tasks = bg_tasks(path)
    sub_dir = path.parent if path.parent.name == 'subagents' else path.parent / path.stem / 'subagents'
    metas = {}
    if any(t['kind'] == 'subagent' for t in tasks.values()) and sub_dir.is_dir():
        for m in sub_dir.glob('agent-*.meta.json'):
            try: meta = json.loads(m.read_text())
            except (OSError, ValueError): continue
            metas[meta.get('toolUseId')] = (m, meta)
    for tuid, t in tasks.items():
        t0 = t.get('t0') or now
        if t['kind'] == 'shell':
            ended = t.get('t1')
            running = not ended and (lead_alive or (lead_alive is None and now - t0 < STALE))
            end_at = ended or t0
            if not running and now - end_at > FADE: continue
            kids.append({'id': f'sh-{tuid[-10:]}', 'parent': owner, 'kind': 'shell', 'name': t['label'], 'running': bool(running),
                         'ended': None if running else round(now - end_at), 'station': 'shell', 'label': t['label'],
                         'call': tuid, 'trail': [], 'recent': 0, 'model': None, 'age': round(now - t0),
                         't0': t0, 'cmd': t.get('cmd'), 'status': t.get('status')})
        elif t['kind'] == 'subagent' and tuid in metas:
            m, meta = metas[tuid]
            f = m.with_name(m.name.replace('.meta.json', '.jsonl'))
            fm = mtime(f) or mtime(m) or t0
            finished = bool(meta.get('finished'))
            running = not finished and (lead_alive or (lead_alive is None and now - fm < STALE))
            end_at = max(fm, mtime(m) or 0)
            if not running and now - end_at > FADE: continue
            sid = f'sa-{f.stem[-10:]}'
            info = read_claude(f, sidechain=True) if f.is_file() else {}
            kids.append({**info, 'id': sid, 'parent': owner, 'kind': 'subagent',
                         'name': meta.get('description') or meta.get('agentType') or 'Subagent', 'running': bool(running),
                         'ended': None if running else round(now - end_at), 'age': round(now - fm), 't0': t0,
                         'model': re.sub(r'^claude-', '', meta.get('model') or info.get('model') or '') or None})
            if f.is_file() and running or now - end_at < FADE:
                claude_kids(kids, sid, f, lead_alive if running else False, now)


def ps_tree():
    try: out = subprocess.run(['ps', '-axww', '-o', 'pid=,ppid=,command='], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError): return {}
    procs = {}
    for line in out.splitlines():
        p = line.strip().split(None, 2)
        if len(p) >= 2 and p[0].isdigit() and p[1].isdigit(): procs[int(p[0])] = (int(p[1]), p[2] if len(p) > 2 else '')
    return procs


def cwd_of(pids):
    """{pid: folder}; None when lsof did not answer (a busy machine): then nobody knows."""
    if not pids: return {}
    try: out = subprocess.run(['lsof', '-a', '-d', 'cwd', '-p', ','.join(map(str, pids)), '-Fpn'], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError): return None
    res, pid = {}, None
    for line in out.splitlines():
        if line.startswith('p'): pid = int(line[1:])
        elif line.startswith('n') and pid: res[pid] = line[1:]
    return res


def kimi_sessions(roots, now):
    """Kimi Code sessions in one of the `roots` folders (or below) that wrote in the last FADE seconds or are still open."""
    base = HOME / '.kimi-code/sessions'
    if not base.is_dir() or not roots: return []
    found = []
    for ws in base.iterdir():
        if not ws.name.startswith('wd_') or now - (mtime(ws) or 0) > 7 * 86400: continue
        for s in ws.glob('session_*'):
            if now - max(mtime(s / 'state.json') or 0, mtime(s / 'agents/main/wire.jsonl') or 0) > 6 * 3600: continue
            try: state = json.loads((s / 'state.json').read_text())
            except (OSError, ValueError): continue
            cwd = state.get('cwd') or ''
            root = next((r for r in roots if cwd == r or cwd.startswith(r.rstrip('/') + '/')), None)
            if root: found.append((s, state, root))
    return found


class Procs:
    """ps and the folders of the processes that match `pattern`, read once per poll and only when needed."""
    def __init__(self): self.procs = None; self.cwds = {}

    def tree(self):
        if self.procs is None: self.procs = ps_tree()
        return self.procs

    def by_cwd(self, pattern):
        if pattern not in self.cwds:
            pids = [pid for pid, (pp, cmd) in self.tree().items() if re.match(pattern, cmd)]
            cwds, res = cwd_of(pids), {}
            for pid, c in (cwds or {}).items(): res.setdefault(c, []).append(pid)
            self.cwds[pattern] = res if cwds is not None else None
        return self.cwds[pattern]

    def pids_in(self, pattern, cwd):
        """The matching processes in `cwd`; None when that is not known."""
        m = self.by_cwd(pattern)
        return None if m is None else m.get(cwd, [])


_owners = None
def remembered():
    """{session key: [shell kid id, time]}: the shell that started a session, kept after its process ends."""
    global _owners
    if _owners is None:
        _owners = (load_cache('owners') or {}).get('m', {})
        old = time.time() - 86400
        _owners = {k: v for k, v in _owners.items() if v[1] > old}
    return _owners


def owner_of(kids, procs, lead_pids, pids, fallback, key=None):
    """The background shell whose process started one of `pids` (remembered under `key`), else `fallback`."""
    known = remembered().get(key) if key else None
    found = _owner_of(kids, procs, lead_pids, pids, fallback)
    if found == fallback and known and any(k['id'] == known[0] for k in kids): return known[0]   # its process ended or left the lead
    if key and found != fallback and (not known or known[0] != found):
        remembered()[key] = [found, time.time()]
        save_cache('owners', {'m': remembered()})
    return found


def _owner_of(kids, procs, lead_pids, pids, fallback):
    shells = [k for k in kids if k['kind'] == 'shell' and k['running']]

    def shell_for(pid):
        """Walk up from a kimi process to the lead; the process right under the lead is a background Bash call."""
        p = pid
        for _ in range(40):
            pp = procs.get(p, (0, ''))[0]
            if not pp: return None
            if pp in lead_pids:
                # the shell whose command shows most in that process's command line (the newest on a tie)
                text, best = procs.get(p, (0, ''))[1], (0, 0, None)
                for k in shells:
                    words = [w for w in re.split(r'\s+', k.get('cmd') or '') if len(w) > 3 and "'" not in w and '"' not in w]
                    if not words or not all(w in text for w in words[:4]): continue
                    best = max(best, (sum(w in text for w in words) / len(words), k.get('t0') or 0, k['id']))
                return best[2]
            p = pp
        return None

    return next((sh for sh in map(shell_for, pids) if sh), fallback) if shells else fallback


def add_kimi(kids, owners, lead_pids, P, now):
    """owners: {folder: owner address}. A Kimi session is a kid of the background shell whose process
    started it (found through ps), else of the agent that owns its folder."""
    sessions = kimi_sessions(list(owners), now)
    if not sessions: return
    for s, state, root in sessions:
        cwd = state.get('cwd') or ''
        known = P.pids_in(r'(\S*/)?kimi(-code)?(\s|$)', cwd)
        pids = known or []
        owner = owner_of(kids, P.tree(), lead_pids, pids, owners[root], key=f'km-{s.name}')
        agents = state.get('agents') or {'main': {'type': 'main'}}
        name = os.path.basename(cwd.rstrip('/')) or 'kimi'
        ids = {}
        for aid in sorted(agents, key=lambda a: a != 'main'):
            a = agents[aid] or {}
            wire = s / 'agents' / aid / 'wire.jsonl'
            wm = mtime(wire)
            if wm is None: continue
            info = read_kimi(wire)
            # the turn's start can be older than the tail we read (open None): a live kimi process in
            # that folder, or a recent write, says it still runs
            running = bool(pids) or (now - wm < 120 and (known is None or info.get('open') is not False))
            end_at = info.get('t_end') or wm
            if not running and now - end_at > FADE: continue
            kid = f'km-{s.name[-8:]}-{aid}'
            ids[aid] = kid
            brief = (a.get('labels') or {}).get('swarmItem')
            kids.append({**info, 'id': kid, 'parent': owner if aid == 'main' else ids.get(a.get('parentAgentId') or 'main', owner),
                         'kind': 'kimi', 'name': name if aid == 'main' else f'{name} · {aid}', 'running': running,
                         'ended': None if running else round(now - end_at), 'age': round(now - wm),
                         't0': (state.get('createdAt') or 0) / 1000, 'brief': (brief or '')[:80] or None})


def add_codex(kids, owners, lead_pids, taken, P, now):
    """`codex exec` runs in an owner's folder (or below), as kids like the Kimi sessions.
    taken: rollout files already read as Herdr agents."""
    root = HOME / '.codex/sessions'
    if not root.is_dir(): return
    days = sorted(root.glob('*/*/*'), reverse=True)[:2]   # today and the day before
    for f in [f for d in days for f in d.glob('rollout-*.jsonl')]:
        fm = mtime(f)
        if fm is None or now - fm > 6 * 3600 or str(f) in taken: continue
        try:
            with open(f, 'rb') as h: head = h.read(4000).decode('utf-8', 'replace')
        except OSError: continue
        if '"codex_exec"' not in head and '"exec"' not in head: continue
        m = re.search(r'"cwd":"([^"]+)"', head)
        cwd = m.group(1) if m else ''
        rt = next((r for r in owners if cwd == r or cwd.startswith(r.rstrip('/') + '/')), None)
        if not rt: continue
        pids = P.pids_in(r'(\S*/)?codex\s+(.*\s)?exec(\s|$)', cwd) or []
        if not pids and now - fm > FADE: continue
        info = read_codex(f)
        running = bool(pids) or now - fm < 60
        name = os.path.basename(cwd.rstrip('/')) or 'codex'
        if name in ('code', 'src', 'repo', 'work'): name = os.path.basename(os.path.dirname(cwd.rstrip('/'))) or name
        kids.append({**info, 'id': f'cx-{f.stem[-10:]}', 'parent': owner_of(kids, P.tree(), lead_pids, pids, owners[rt], key=f'cx-{f.stem}'),
                     'kind': 'codex', 'name': name, 'running': running, 'ended': None if running else round(now - fm),
                     'age': round(now - fm), 't0': fm})


def main():
    agents = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    out, now, groups, kids, claude_paths = {}, time.time(), {}, [], {}
    for a in agents:
        kind = 'codex' if 'codex' in (a.get('agent') or '') else 'claude'
        f = claude_by_pid(a.get('pid')) if kind == 'claude' and a.get('pid') else None
        if f: claude_paths[a['address']] = f
        else: groups.setdefault((kind, a.get('cwd') or ''), []).append(a)
    for addr, f in claude_paths.items():
        try:
            info = read_claude(f)
            info['age'] = round(now - f.stat().st_mtime)
            out[addr] = info
        except OSError:
            pass
    for (kind, cwd), members in groups.items():
        files = (codex_files if kind == 'codex' else claude_files)(cwd) if cwd else []
        members.sort(key=lambda a: 0 if a.get('status') == 'working' else 1)
        for a, f in zip(members, files):
            try:
                info = (read_codex if kind == 'codex' else read_claude)(f)
                info['age'] = round(now - f.stat().st_mtime)
                if len(members) > 1: info['shared'] = True
                out[a['address']] = info
            except OSError:
                pass
    pid_of = {a['address']: a.get('pid') for a in agents}
    for addr, f in claude_paths.items():   # kids only from exact transcripts: a guessed one could show another session's work
        try: claude_kids(kids, addr, f, alive(pid_of[addr]), now)
        except OSError: pass
    owners = {}
    for a in sorted(agents, key=lambda a: a.get('address') not in claude_paths):
        cwd = a.get('cwd') or ''
        if len(cwd) > 1 and cwd != str(HOME): owners.setdefault(cwd, a['address'])
    if owners:
        P, lead_pids = Procs(), {int(a['pid']) for a in agents if str(a.get('pid') or '').isdigit()}
        add_kimi(kids, owners, lead_pids, P, now)
        add_codex(kids, owners, lead_pids, {str(f) for fs in (_codex or {}).values() for f in fs}, P, now)
    keep, more = trim(kids)
    for k in keep:
        for f in ('cmd', 'open', 't_end'): k.pop(f, None)
    print(json.dumps({'agents': out, 'kids': keep, 'more': more}))


if __name__ == '__main__':
    main()
