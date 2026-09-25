"""Live Claude Code sessions for the dashboard: who runs where, in what state,
and what it was last asked and answered.

Nothing here needs hooks or a running daemon. Every interactive Claude Code
process keeps ``~/.claude/sessions/<pid>.json`` up to date by itself (status
busy/idle, or "shell" = idle with a background shell still running; when it changed, cwd, tmux pane, session id); the text comes
from the tail of its transcript ``~/.claude/projects/*/<session id>.jsonl``.

Transcripts grow to megabytes, so they are parsed incrementally: every file
remembers the byte offset it was read up to and only new lines are parsed on
the next request. The first read starts at most ``FIRST_READ`` bytes before
the end - the title is re-written into the transcript every few turns, so the
tail is enough.

The optional one-sentence summary is made on demand by ``claude -p`` with a
small model and cached in ``$FRACTAL_STATE_DIR/session-summaries.json``.
"""
import glob
import json
import os
import re
import subprocess
import threading
import time
from collections import deque

from fractal_config import HOME, REGISTRY, STATE_DIR, bin_path_env

CLAUDE_DIR = os.path.join(HOME, ".claude")
SESSIONS_DIR = os.path.join(CLAUDE_DIR, "sessions")
PROJECTS_DIR = os.path.join(CLAUDE_DIR, "projects")
SUMMARY_FILE = os.path.join(STATE_DIR, "session-summaries.json")

FIRST_READ = 4 * 1024 * 1024
PROMPT_LEN = 400             # what the dashboard shows; the card clamps it further
ANSWER_LEN = 600
SUMMARY_MODEL = "haiku"
SUMMARY_TIMEOUT = 120
SUMMARY_PROMPT = (
    "You are shown the recent part of a coding-agent session: the user's prompts and the "
    "agent's replies. In one or two short sentences say what is being worked on and where "
    "it stands now (done, waiting for the user, blocked...). Write in the language the user "
    "writes in. No preamble, no markdown."
)

_lock = threading.Lock()
_tails: dict[str, dict] = {}          # transcript path -> parse state
_running: set[str] = set()            # session ids with a summary in progress
_errors: dict[str, str] = {}          # session id -> last summary error


# --- transcript tail ----------------------------------------------------------

_CMD = re.compile(r"<command-name>(.*?)</command-name>", re.S)
_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def _prompt_text(content) -> str:
    """The user's own words from a transcript "user" entry, or "" for tool
    results, task notifications, command output and other injected text."""
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return ""
    s = content.strip()
    if s.startswith("<"):
        m = _CMD.search(s)            # a slash command: show it as typed
        if not m:
            return ""
        a = _ARGS.search(s)
        return (m.group(1).strip() + " " + (a.group(1).strip() if a else "")).strip()
    return s


def _answer_text(content) -> str:
    if not isinstance(content, list):
        return ""
    return "\n\n".join(b.get("text", "").strip() for b in content
                       if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip())


def _new_tail() -> dict:
    return {"off": 0, "ino": None, "title": "", "prompt": "", "answer": "",
            "prompts": deque(maxlen=10), "answers": deque(maxlen=4), "partial": ""}


def _feed(t: dict, line: str) -> None:
    try:
        o = json.loads(line)
    except ValueError:
        return
    if not isinstance(o, dict) or o.get("isSidechain"):
        return
    k = o.get("type")
    if k == "ai-title" and o.get("aiTitle"):
        t["title"] = o["aiTitle"]
    elif k == "custom-title" and o.get("customTitle"):
        t["title"] = o["customTitle"]
    elif k == "user" and not o.get("isMeta"):
        p = _prompt_text((o.get("message") or {}).get("content"))
        if p:
            t["prompt"] = p
            t["prompts"].append(p)
    elif k == "assistant":
        a = _answer_text((o.get("message") or {}).get("content"))
        if a:
            t["answer"] = a
            t["answers"].append(a)


def transcript_path(session_id: str) -> str | None:
    hits = glob.glob(os.path.join(PROJECTS_DIR, "*", glob.escape(session_id) + ".jsonl"))
    return max(hits, key=os.path.getmtime) if hits else None


def read_tail(path: str) -> dict:
    """Parse whatever was appended to the transcript since the last call."""
    try:
        st = os.stat(path)
    except OSError:
        return _new_tail()
    with _lock:
        t = _tails.get(path)
        if t is None or t["ino"] != st.st_ino or st.st_size < t["off"]:
            t = _tails[path] = _new_tail()
            t["ino"] = st.st_ino
            t["off"] = max(0, st.st_size - FIRST_READ)
            skip_first = t["off"] > 0          # we landed mid-line
        else:
            skip_first = False
        if st.st_size == t["off"]:
            return t
        with open(path, "rb") as f:
            f.seek(t["off"])
            chunk = f.read()
        t["off"] += len(chunk)
        text = t["partial"] + chunk.decode("utf-8", "replace")
        lines = text.split("\n")
        t["partial"] = lines.pop()             # unfinished last line waits for the next read
        if skip_first and lines:
            lines.pop(0)
        for line in lines:
            if line:
                _feed(t, line)
        return t


# --- sessions -----------------------------------------------------------------

def _alive(pid: int, proc_start: str | None) -> bool:
    """The pid runs AND is the same process (pids get reused after a reboot
    or a long uptime - a stale session file must not match a stranger)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            stat = f.read()
    except OSError:
        return False
    if not proc_start:
        return True
    fields = stat.rsplit(")", 1)[-1].split()
    return len(fields) > 19 and fields[19] == str(proc_start)   # field 22 = starttime


def _projects() -> list[dict]:
    try:
        with open(REGISTRY, encoding="utf-8") as f:
            return json.load(f).get("projects", [])
    except (OSError, ValueError):
        return []


def _project_of(tmux_session: str, cwd: str, projects: list[dict]) -> str | None:
    """The tmux session name wins (work/ctl name sessions after the project);
    otherwise the project whose root holds cwd, deepest root first."""
    for p in projects:
        if p.get("name") == tmux_session:
            return p["name"]
    best, blen = None, -1
    for p in projects:
        root = os.path.realpath(os.path.expanduser(p.get("root") or ""))
        if root and root != HOME and (cwd == root or cwd.startswith(root + os.sep)) and len(root) > blen:
            best, blen = p["name"], len(root)
    return best


def _clip(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


def load_summaries() -> dict:
    try:
        with open(SUMMARY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def collect() -> list[dict]:
    projects = _projects()
    summaries = load_summaries()
    out = []
    for fn in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(fn, encoding="utf-8") as f:
                s = json.load(f)
            pid = int(s["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if s.get("kind", "interactive") != "interactive" or not _alive(pid, s.get("procStart")):
            continue
        sid = s.get("sessionId") or ""
        cwd = s.get("cwd") or ""
        tmux = s.get("tmux") or ""                  # "session:@window.%pane"
        m = re.match(r"^(.*):@(\d+)\.%(\d+)$", tmux)
        tsess, pane = (m.group(1), m.group(3)) if m else ("", "")
        path = transcript_path(sid) if sid else None
        t = read_tail(path) if path else _new_tail()
        with _lock:
            running, err = sid in _running, _errors.get(sid)
        out.append({
            "pid": pid,
            "sessionId": sid,
            "name": s.get("name") or "",
            "title": t["title"],
            "status": s.get("status") or "unknown",
            "since": (s.get("statusUpdatedAt") or s.get("updatedAt") or 0) / 1000,
            "started": (s.get("startedAt") or 0) / 1000,
            "cwd": cwd.replace(HOME, "~", 1) if cwd.startswith(HOME) else cwd,
            "project": _project_of(tsess, cwd, projects),
            "tmux": tsess,
            "pane": pane,
            "prompt": _clip(t["prompt"], PROMPT_LEN),
            "answer": _clip(t["answer"], ANSWER_LEN),
            "summary": summaries.get(sid),
            "summarizing": running,
            "summaryError": err,
        })
    # one conversation can be open in two processes (claude -r inside the
    # shell of another); show it once, the most recently active wins
    out.sort(key=lambda x: -x["since"])
    seen, uniq = set(), []
    for x in out:
        if x["sessionId"] and x["sessionId"] in seen:
            continue
        seen.add(x["sessionId"])
        uniq.append(x)
    return uniq


# --- on-demand summary --------------------------------------------------------

def _summary_input(sid: str) -> str | None:
    path = transcript_path(sid)
    if not path:
        return None
    t = read_tail(path)
    if not t["prompts"] and not t["answers"]:
        return None
    parts = []
    if t["title"]:
        parts.append(f"Session title: {t['title']}")
    parts.append("Recent user prompts, oldest first:")
    parts += [f"- {_clip(p, 600)}" for p in t["prompts"]]
    parts.append("\nRecent agent replies, oldest first:")
    parts += [f"---\n{_clip(a, 1500)}" for a in t["answers"]]
    return "\n".join(parts)


def _summarize(sid: str) -> None:
    err = None
    try:
        text = _summary_input(sid)
        if text is None:
            raise RuntimeError("nothing to summarize yet")
        # no tools, no settings (hooks, CLAUDE.md), no transcript of its own -
        # a plain text-in/text-out call; cwd is the state dir so nothing lands
        # in a project's history even if persistence was on
        r = subprocess.run(
            ["claude", "-p", "--model", SUMMARY_MODEL, "--no-session-persistence",
             "--tools", "", "--setting-sources", "", "--system-prompt", SUMMARY_PROMPT],
            input=text, capture_output=True, text=True, timeout=SUMMARY_TIMEOUT,
            env=bin_path_env(), cwd=STATE_DIR)
        answer = r.stdout.strip()
        if r.returncode or not answer:
            raise RuntimeError((r.stderr.strip() or answer or f"claude exit {r.returncode}")[-300:])
        with _lock:
            data = load_summaries()
            live = _live_ids()
            data = {k: v for k, v in data.items() if k in live}    # drop ended sessions
            data[sid] = {"text": answer, "at": time.time()}
            tmp = SUMMARY_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, SUMMARY_FILE)
    except subprocess.TimeoutExpired:
        err = f"no answer within {SUMMARY_TIMEOUT} s"
    except Exception as e:                                    # noqa: BLE001
        err = str(e) or type(e).__name__
    with _lock:
        _running.discard(sid)
        if err:
            _errors[sid] = err
        else:
            _errors.pop(sid, None)


def _live_ids() -> set[str]:
    ids = set()
    for fn in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(fn, encoding="utf-8") as f:
                ids.add(json.load(f).get("sessionId") or "")
        except (OSError, ValueError):
            pass
    return ids


def request_summary(sid: str) -> str | None:
    """Start a summary in the background. None, or why it cannot start."""
    if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", sid or "") or sid not in _live_ids():
        return "unknown session"
    with _lock:
        if sid in _running:
            return None
        _running.add(sid)
        _errors.pop(sid, None)
    threading.Thread(target=_summarize, args=(sid,), daemon=True).start()
    return None
