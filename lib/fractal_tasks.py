"""Task files: the data model behind fractal-tasks (the board) and
fractal-task-run (the agent runner).

A project has tasks when its registry ``root`` holds a ``tasks/`` directory.
Every task is one markdown file in it, ``tasks/<id>-<slug>.md``:

    ---
    id: 042
    title: Indicator page width
    status: todo
    order: 30
    priority: 3
    assignee: claude
    phase: dev
    verify: npm --prefix web run build
    created: 2026-10-01 14:02
    updated: 2026-10-01 14:30
    ---
    <the request, written by the owner - never rewritten>

    ## Plan (agent · 2026-10-01 14:05)
    ...appended sections: Plan, Questions, Answers, Feedback, Result, Run

The file is the whole history of the task: everything after the request is
appended, nothing is rewritten. That is what makes it usable as the prompt for
the agent (it reads the file), as a git-tracked record, and as something a
human can fix with any editor when the tooling is not around.

Status (one column each on the board, or shared):
    triage          agent is reading the code and writing a plan + questions
    backlog         approved, not scheduled
    todo            queued; ``order`` is the position, the runner takes the first
    in-progress     agent is implementing
    need-attention  blocked on the owner (questions, failed verify, crashed run)
    review          agent finished; the owner approves (plan -> todo, work -> done)
    done, canceled

``phase`` says what the agent was last asked to do (``triage`` or ``dev``), so
``review`` and ``need-attention`` know where "approve" / "answer" leads.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import unicodedata

from fractal_config import REGISTRY, STATE_DIR

STATUSES = ("triage", "backlog", "todo", "in-progress", "need-attention", "review", "done", "canceled")
RUNNING = ("triage", "in-progress")
PHASES = ("triage", "dev")
PRIORITIES = (1, 2, 3, 4)                     # 1 urgent .. 4 low
FIELDS = ("id", "title", "status", "order", "priority", "assignee", "phase", "verify",
          "timeout_minutes", "created", "updated")
TASKS_DIRNAME = "tasks"
ARCHIVE_DIRNAME = "archive"
LOGS_DIRNAME = "logs"
ORDER_STEP = 10
INTERNAL = ("path", "file", "request", "sections", "body", "run")
STATE_FILE = os.path.join(STATE_DIR, "tasks-state.json")      # per-project board settings

_FRONT = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?", re.S)
_SECTION = re.compile(r"^## (Plan|Questions|Answers|Feedback|Result|Run|Verify|Deploy|Error)\b(.*)$", re.M)


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


# --- projects -----------------------------------------------------------------

def registry_projects() -> list[dict]:
    try:
        with open(REGISTRY, encoding="utf-8") as f:
            return json.load(f).get("projects", [])
    except (OSError, ValueError):
        return []


def tasks_dir(project: dict) -> str:
    return os.path.join(project.get("root") or "", TASKS_DIRNAME)


def projects_with_tasks() -> list[dict]:
    """Registry projects whose root has a tasks/ directory, registry order."""
    return [p for p in registry_projects() if p.get("root") and os.path.isdir(tasks_dir(p))]


def project(name: str) -> dict | None:
    for p in projects_with_tasks():
        if p.get("name") == name:
            return p
    return None


# --- file format --------------------------------------------------------------

def parse(text: str) -> tuple[dict, str]:
    """(frontmatter dict, body). A file without a frontmatter is a bare request."""
    meta: dict = {}
    m = _FRONT.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        text = text[m.end():]
    for k in ("order", "priority", "timeout_minutes"):
        if k in meta:
            try:
                meta[k] = int(meta[k])
            except ValueError:
                meta.pop(k)
    return meta, text


def render(meta: dict, body: str) -> str:
    lines = ["---"]
    for k in FIELDS:
        if k in meta and meta[k] not in (None, ""):
            lines.append(f"{k}: {meta[k]}")
    for k, v in meta.items():                     # unknown keys survive round trips
        if k not in FIELDS and k not in ("path", "file") and v not in (None, ""):
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body.lstrip("\n").rstrip("\n") + "\n"


def split_body(body: str) -> tuple[str, list[dict]]:
    """The owner's request and the appended sections, in file order."""
    parts = list(_SECTION.finditer(body))
    if not parts:
        return body.strip(), []
    request = body[:parts[0].start()].strip()
    sections = []
    for i, m in enumerate(parts):
        end = parts[i + 1].start() if i + 1 < len(parts) else len(body)
        sections.append({"kind": m.group(1), "head": m.group(2).strip(" ()·"),
                         "text": body[m.end():end].strip()})
    return request, sections


# --- tasks of a project -------------------------------------------------------

def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:48].rstrip("-") or "task"


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        meta, body = parse(f.read())
    stem = os.path.splitext(os.path.basename(path))[0]
    task = {"id": stem.split("-", 1)[0] if stem[:1].isdigit() else stem,
            "title": stem, "status": "backlog", "order": 0, "priority": 3,
            "assignee": "claude", "phase": "triage"}
    task.update({k: v for k, v in meta.items() if v not in (None, "")})
    if task["status"] not in STATUSES:
        task["status"] = "backlog"
    task["path"] = path
    task["file"] = os.path.basename(path)
    request, sections = split_body(body)
    task["request"] = request
    task["sections"] = sections
    task["body"] = body
    return task


def list_tasks(project: dict, archive: bool = False) -> list[dict]:
    d = tasks_dir(project)
    if archive:
        d = os.path.join(d, ARCHIVE_DIRNAME)
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".md") or n.lower() == "readme.md":
            continue
        try:
            out.append(load(os.path.join(d, n)))
        except (OSError, UnicodeDecodeError):
            continue
    out.sort(key=lambda t: (t.get("order", 0), t["id"]))
    return out


def find(project: dict, task_id: str) -> dict | None:
    task_id = str(task_id)
    for t in list_tasks(project):
        if t["id"] == task_id:
            return t
    return None


def next_id(project: dict) -> str:
    nums = [0]
    for sub in ("", ARCHIVE_DIRNAME):
        d = os.path.join(tasks_dir(project), sub)
        try:
            for n in os.listdir(d):
                m = re.match(r"^(\d+)", n)
                if m and n.endswith(".md"):
                    nums.append(int(m.group(1)))
        except OSError:
            pass
    return f"{max(nums) + 1:03d}"


def next_order(project: dict, status: str) -> int:
    orders = [t.get("order", 0) for t in list_tasks(project) if t["status"] == status]
    return (max(orders) if orders else 0) + ORDER_STEP


def write(task: dict) -> None:
    """Atomic rewrite of the whole file from the task dict (frontmatter +
    body). The body is never edited by the tooling except through
    append() and set_request()."""
    meta = {k: task.get(k) for k in FIELDS if task.get(k) not in (None, "")}
    meta.update({k: v for k, v in task.items()                 # custom keys survive (legacy_id, ...)
                 if k not in FIELDS and k not in INTERNAL and isinstance(v, (str, int))})
    meta["updated"] = now()
    text = render(meta, task.get("body") or "")
    tmp = task["path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, task["path"])
    task["updated"] = meta["updated"]


def create(project: dict, title: str, request: str = "", status: str = "triage", **extra) -> dict:
    d = tasks_dir(project)
    os.makedirs(d, exist_ok=True)
    tid = next_id(project)
    title = " ".join(title.split()) or "Untitled"
    path = os.path.join(d, f"{tid}-{slugify(title)}.md")
    task = {"id": tid, "title": title[:200], "status": status if status in STATUSES else "triage",
            "order": next_order(project, status), "priority": 3, "assignee": "claude",
            "phase": "triage", "created": now(), "path": path, "body": (request or title).strip() + "\n"}
    task.update({k: v for k, v in extra.items() if v not in (None, "")})
    write(task)
    return load(path)


def append(task: dict, kind: str, text: str, who: str = "") -> None:
    """Append a dated section; the request and earlier sections stay as they are."""
    head = f"## {kind} ({who + ' · ' if who else ''}{now()})"
    with open(task["path"], "a", encoding="utf-8") as f:
        f.write(f"\n{head}\n{text.strip()}\n")
    fresh = load(task["path"])
    task["body"], task["sections"] = fresh["body"], fresh["sections"]


def set_request(task: dict, request: str) -> None:
    """Replace the owner's request (the text before the first section)."""
    m = _SECTION.search(task.get("body") or "")
    tail = task["body"][m.start():] if m else ""
    task["body"] = request.strip() + "\n" + ("\n" + tail if tail else "")
    write(task)


def archive(task: dict) -> str:
    d = os.path.join(os.path.dirname(task["path"]), ARCHIVE_DIRNAME)
    os.makedirs(d, exist_ok=True)
    target = os.path.join(d, os.path.basename(task["path"]))
    os.replace(task["path"], target)
    return target


def reorder(project: dict, status: str, ordered_ids: list[str]) -> None:
    """Renumber the tasks of one column in the given order (ORDER_STEP apart)."""
    by_id = {t["id"]: t for t in list_tasks(project) if t["status"] == status}
    pos = ORDER_STEP
    for tid in ordered_ids:
        t = by_id.pop(str(tid), None)
        if t is None:
            continue
        if t.get("order") != pos:
            t["order"] = pos
            write(t)
        pos += ORDER_STEP
    for t in sorted(by_id.values(), key=lambda t: (t.get("order", 0), t["id"])):   # not mentioned: after
        if t.get("order") != pos:
            t["order"] = pos
            write(t)
        pos += ORDER_STEP


# --- git ---------------------------------------------------------------------

def git(root: str, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=check)


def tracked(root: str, path: str) -> bool:
    """Should the tooling commit this task file? Only in a git repo where the
    tasks directory is not ignored."""
    if git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return False
    return git(root, "check-ignore", "-q", path).returncode != 0


def commit_task_file(root: str, path: str, message: str) -> str:
    """Commit just this one file (``git commit -- <path>`` ignores whatever
    else is staged or dirty). Returns the short hash or ''."""
    if not tracked(root, path):
        return ""
    rel = os.path.relpath(path, root)
    git(root, "add", "--", rel)
    if git(root, "diff", "--cached", "--quiet", "--", rel).returncode == 0:
        return ""
    r = git(root, "commit", "-q", "-m", message, "--", rel)
    if r.returncode != 0:
        return ""
    return git(root, "rev-parse", "--short", "HEAD").stdout.strip()


# --- a task's own commits, and whether a ref has them ---------------------------
# The agent commits with the prefix "task <id>: "; the board's own bookkeeping
# touches tasks/ only and does not count. Whether a ref (the upstream, the
# production's commit) has a commit is decided by patch id, not ancestry: a
# task deployed on its own reaches the remote as a cherry-picked copy.

def task_commits(root: str, task_id: str, head: str = "HEAD") -> list[tuple[str, str, str]]:
    """(hash, short hash, subject) of the task's own commits on head, oldest first."""
    r = git(root, "log", "--reverse", "--format=%H %h %s", "--grep", f"^task {task_id}: ", head,
            "--", ".", f":(exclude){TASKS_DIRNAME}/")
    return [tuple(ln.split(" ", 2)) for ln in r.stdout.splitlines() if ln.count(" ") >= 2]


def missing_from(root: str, ref: str, head: str = "HEAD") -> set[str]:
    """Hashes of the commits on head whose change ref does not have."""
    r = git(root, "cherry", ref, head)
    return {ln[2:].strip() for ln in r.stdout.splitlines() if ln.startswith("+ ")}


def upstream(root: str) -> tuple[str, str]:
    """(remote, branch) the current branch pushes to, or ("", "")."""
    r = git(root, "rev-parse", "--abbrev-ref", "@{upstream}").stdout.strip()
    remote, _, branch = r.partition("/")
    return (remote, branch) if branch else ("", "")


def fetch_upstream(root: str) -> bool:
    """Refresh the remote-tracking ref of the upstream. Through the push URL:
    a repo may fetch over https without credentials but push over ssh."""
    remote, branch = upstream(root)
    if not branch:
        return False
    url = git(root, "remote", "get-url", "--push", remote).stdout.strip() or remote
    return git(root, "fetch", "-q", url, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}").returncode == 0


# --- board settings (per project, outside the repo) ---------------------------

def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


# machine-local, they name hosts: deploy_check prints the commit the production
# runs, deploy_prepare readies an isolated checkout for the verify (links the
# dependencies), deploy_run deploys what was pushed
DEPLOY_SETTINGS = ("deploy_check", "deploy_prepare", "deploy_run")


def project_settings(name: str) -> dict:
    s = load_state().get("projects", {}).get(name, {})
    return {"auto": bool(s.get("auto", False)), "auto_triage": bool(s.get("auto_triage", True)),
            **{k: str(s.get(k) or "") for k in DEPLOY_SETTINGS}}



def set_project_setting(name: str, key: str, value) -> dict:
    state = load_state()
    state.setdefault("projects", {}).setdefault(name, {})[key] = value
    save_state(state)
    return project_settings(name)


# --- the interactive session of a task (machine-local, so not in the file) ----

def task_session(name: str, task_id: str) -> dict:
    """{"session": tmux session, "id": Claude session id, "driver": bool} or {}.
    driver = the task is being implemented from that session, not by a run."""
    return dict(load_state().get("sessions", {}).get(f"{name}/{task_id}", {}))


def has_transcript(sid: str) -> bool:
    """Does Claude Code keep a conversation with this id (any project dir)?"""
    d = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    try:
        return any(os.path.exists(os.path.join(d, x, sid + ".jsonl")) for x in os.listdir(d))
    except OSError:
        return False


def set_task_session(name: str, task_id: str, **kv) -> dict:
    """Merge kv into the record; a None value removes the key, an empty
    record is dropped."""
    state = load_state()
    sessions = state.setdefault("sessions", {})
    rec = sessions.get(f"{name}/{task_id}", {})
    rec.update(kv)
    rec = {k: v for k, v in rec.items() if v is not None}
    if rec:
        sessions[f"{name}/{task_id}"] = rec
    else:
        sessions.pop(f"{name}/{task_id}", None)
    save_state(state)
    return rec
