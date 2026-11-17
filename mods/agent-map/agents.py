#!/usr/bin/env python3
"""What each agent of a Herdr space does right now, read from its local transcript.

  agents.py '<json: [{address, agent, cwd, status}]>'  ->  {address: {station, tool, label, running, model, ctx, age}}

Claude Code: ~/.claude/projects/<cwd, every non-alphanumeric as ->/<session>.jsonl
Codex:       ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (the first line names its cwd)
Agents that share a folder get that folder's newest transcripts, the working ones first: a guess,
marked `shared`. Nothing leaves this computer. The stations follow lot-map (github.com/alexeyw/lot-map).
"""
import json, os, re, sys, time
from pathlib import Path

HOME = Path.home()
TAIL = 400_000
FILES = {'cat', 'ls', 'grep', 'rg', 'sed', 'awk', 'mv', 'cp', 'rm', 'mkdir', 'find', 'head', 'tail', 'tee', 'touch', 'wc', 'chmod', 'ln', 'diff', 'tree', 'stat', 'du'}
NET = {'curl', 'wget', 'gh', 'ssh', 'scp', 'rsync', 'kubectl', 'docker', 'aws', 'gcloud', 'npx', 'pip', 'pip3', 'brew', 'ping'}


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
    if tool in ('Read', 'Write', 'Edit', 'NotebookEdit', 'MultiEdit'):
        return 'files', f'{tool} {base(inp.get("file_path") or inp.get("notebook_path") or "")}'
    if tool in ('Grep', 'Glob'):
        return 'files', f'{tool} {str(inp.get("pattern", ""))[:40]}'
    if tool in ('Bash', 'PowerShell', 'shell', 'exec', 'exec_command', 'local_shell'):
        cmd = inp.get('command') or inp.get('cmd') or inp.get('input') or ''
        if isinstance(cmd, list): cmd = ' '.join(map(str, cmd[2:] if cmd[:2] == ['bash', '-lc'] else cmd))
        return shell_station(str(cmd)), str(inp.get('description') or str(cmd).strip().split('\n')[0])[:70]
    if tool in ('WebFetch', 'WebSearch'):
        return 'network', f'{tool} {str(inp.get("url") or inp.get("query") or "")[:50]}'
    if tool in ('Agent', 'Task', 'Workflow', 'SendMessage', 'spawn_agent', 'send_input', 'wait'):
        return 'agents', f'{tool} {str(inp.get("description") or inp.get("name") or "")[:50]}'.strip()
    if tool in ('Skill', 'ToolSearch'):
        return 'skills', f'{tool} {str(inp.get("skill") or inp.get("query") or "")[:50]}'
    if tool in ('AskUserQuestion', 'TodoWrite', 'ExitPlanMode', 'update_plan'):
        return 'you', tool
    if tool.startswith('mcp__'):
        server = tool.split('__')[1] if tool.count('__') >= 2 else tool
        kind = 'browser' if re.search(r'chrome|browser|playwright', server, re.I) else 'memory' if 'memory' in server.lower() else 'network'
        return kind, f'{server}: {tool.split("__")[-1]}'[:60]
    return 'shell' if tool in ('sleep',) else 'tool', tool[:40]


def tail_lines(path):
    with open(path, 'rb') as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - TAIL))
        data = f.read().decode('utf-8', 'replace')
    lines = data.split('\n')
    return lines[1:] if size > TAIL else lines


def seconds_ago(stamp, now):
    try: return now - __import__('datetime').datetime.fromisoformat(str(stamp).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError): return None


def read_claude(path):
    last, done, model, ctx, calls, now = None, set(), None, None, [], time.time()
    for line in tail_lines(path):
        if '"tool_use"' not in line and '"tool_result"' not in line and '"usage"' not in line: continue
        try: d = json.loads(line)
        except ValueError: continue
        if d.get('isSidechain'): continue
        m = d.get('message') or {}
        c = m.get('content')
        if d.get('type') == 'assistant':
            model = m.get('model') or model
            u = m.get('usage') or {}
            if u: ctx = (u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0) + (u.get('cache_creation_input_tokens') or 0)
            for b in c if isinstance(c, list) else []:
                if b.get('type') == 'tool_use':
                    last = b
                    calls.append((classify(b.get('name', ''), b.get('input'))[0], seconds_ago(d.get('timestamp'), now)))
        elif d.get('type') == 'user':
            for b in c if isinstance(c, list) else []:
                if b.get('type') == 'tool_result': done.add(b.get('tool_use_id'))
    out = {'model': re.sub(r'^claude-', '', model or '') or None, 'ctx': ctx, 'trail': [c[0] for c in calls[-7:]],
           'recent': sum(1 for c in calls if c[1] is not None and c[1] < 300)}
    if last:
        station, label = classify(last.get('name', ''), last.get('input'))
        out.update(station=station, tool=last.get('name'), label=label, running=last.get('id') not in done, call=last.get('id'))
    return out


def read_codex(path):
    last, done, model, calls, now = None, set(), None, [], time.time()
    for line in tail_lines(path):
        if '_call' not in line and '"model"' not in line: continue
        try: d = json.loads(line)
        except ValueError: continue
        p = d.get('payload') or {}
        t = p.get('type')
        if t in ('function_call', 'custom_tool_call'):
            last = p
            arg = p.get('arguments') if t == 'function_call' else {'command': p.get('input')}
            if isinstance(arg, str):
                try: arg = json.loads(arg)
                except ValueError: arg = {'command': arg}
            calls.append((classify(p.get('name', ''), arg)[0], seconds_ago(d.get('timestamp'), now)))
        elif t in ('function_call_output', 'custom_tool_call_output'): done.add(p.get('call_id'))
        model = p.get('model') or model
    out = {'model': model, 'ctx': None, 'trail': [c[0] for c in calls[-7:]],
           'recent': sum(1 for c in calls if c[1] is not None and c[1] < 300)}
    if last:
        inp = last.get('arguments') if last.get('type') == 'function_call' else {'command': last.get('input')}
        if isinstance(inp, str):
            try: inp = json.loads(inp)
            except ValueError: inp = {'command': inp}
        station, label = classify(last.get('name', ''), inp)
        out.update(station=station, tool=last.get('name'), label=label, running=last.get('call_id') not in done, call=last.get('call_id'))
    return out


def claude_files(cwd):
    d = HOME / '.claude/projects' / re.sub(r'[^A-Za-z0-9]', '-', cwd)
    return sorted(d.glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []


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


def main():
    agents = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    out, now, groups = {}, time.time(), {}
    for a in agents:
        kind = 'codex' if 'codex' in (a.get('agent') or '') else 'claude'
        groups.setdefault((kind, a.get('cwd') or ''), []).append(a)
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
    print(json.dumps(out))


if __name__ == '__main__':
    main()
