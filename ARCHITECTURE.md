# Architecture

fractal is deliberately small: a static page, four tiny Python HTTP servers
on the loopback interface, a handful of shell scripts, nginx in front, and
tmux underneath everything. There is no database, no build step and no
framework. This document explains why each piece is where it is.

## The registry is the only source of truth

`$FRACTAL_WWW/projects.json` (default `/var/www/fractal/projects.json`) is
read, on every request, by:

| Reader | Uses |
|---|---|
| `www/index.html` | groups → tabs, projects → cards, `pinned` → highlighted section, `footer` |
| `bin/work` | `root`, `ctl`, `claudeArgs` to prepare and attach a tmux session |
| `bin/term` | validates the `?arg=` project name before handing over to `work`; `pane:<n>` attaches to an existing pane; `<name>:p<n>`/`<name>:s<n>` opens an extra terminal session `<name>-p<n>` |
| `bin/fractal-ctl` | `service.start/stop/probe`, `hooks`, `sendPrefix` |
| `bin/fractal-telegram` | validates project names; everything else goes through `fractal-ctl` |
| `bin/fractal-autostart` | `service` to know which units to start at boot |

The file is owned by the user, so a new project is a plain file write — no
HTML edits, no nginx change, no root. `project-register` is a convenience
around that write (atomic replace, validation, optional systemd unit).

Schema: [docs/registry.md](docs/registry.md).

## Request flow

```
                         ┌──────────────────────────────── nginx :80 ────────────────────────────────┐
 browser ──────────────▶ │  /                    static files from $FRACTAL_WWW                       │
                         │  /term/   (tailnet)   ──▶ ttyd :7685 ──▶ term ──▶ work <p> ──▶ tmux <p>    │
                         │  /ctl/    (tailnet)   ──▶ fractal-ctl    :7691                             │
                         │  /files/  (tailnet)   ──▶ fractal-files  :7692                             │
                         │  /upload/ (tailnet)   ──▶ fractal-upload :7690                             │
                         └───────────────────────────────────────────────────────────────────────────┘
                                                        │ all run as the user, bind 127.0.0.1
                                                        ▼
                                              projects.json  ·  tmux server  ·  ~/
```

**Why loopback services and not nginx modules?** Three reasons, one per
service: `/ctl` executes commands, which `www-data` must never do; `/files`
and `/upload` need to read and write a `drwx------` home directory; `/term`
needs a pty. All three are trivially solved by a process running as the user.
nginx only adds TLS-less routing and, crucially, the access-control layer.

**Why one `/term` location for every project?** ttyd's `--url-arg` passes
`?arg=<name>` to the command it runs. The `term` script checks the name
against the registry and calls `work <name>`. So one nginx location and one
ttyd instance serve every project, present and future, and adding a project
never needs root.

**Extra terminals per project.** `/term/?arg=<name>` attaches to the
project's tmux session (services + the main agent). `/term/?arg=<name>:p2`
(a new agent conversation) or `:s1` (a shell) is a tmux session of its own,
`<name>-p2` / `<name>-s1`, rooted in the project directory. The dashboard's ＋
creates it first with `POST /ctl/<name>/term/p|s`: `fractal-ctl` picks the
lowest free number from what tmux runs right now, under a lock, and starts it
with `work -d <name> p2`; only then does the page open the address. `term`
only attaches to an extra terminal - a closed one is never re-created, so an
old browser tab reconnecting (or a stale dashboard list) cannot pass a new
conversation off under an old address and name. Only `p<n>`/`s<n>` (1-99)
gets through. These sessions are independent of the project session: stopping
the services leaves them alone. A registered project whose name is exactly
`<name>-p2` owns that session name; `work` refuses to create the extra
terminal and the dashboard skips that number. `fractal-ctl` lists them in
`/state` (`terms`) and kills one on `POST /<name>/term/<window>/close`;
`fractal_sessions` files their agents under `<name>`.

**Tab names.** The ✎ icon that `termkeys.js` adds to every terminal page
renames the browser tab. The name is stored in tmux as the user option
`@fractal_title` (`POST /ctl/term-title {arg, title}`): on the session for a
project, `home` or an extra terminal, on the window for `pane:<n>`. So every
device shows the same name, the dashboard shows it too, and it goes away
with the terminal. The tab puts the project's registry group in front of it
(`Work: chart fixes`, the `prefix` in `GET /ctl/term-title`); only the name
itself is stored. The page only sends its own address; `fractal-ctl` maps it
to a tmux target by the same rules as `term`. `GET /ctl/term-title` answers
404 for an address it does not manage - only such terminals keep the name in
that browser's localStorage - and 409 for one of its own that is not running;
the page then asks again and never falls back to localStorage (it clears any
stale entry), so a new `p5` cannot inherit the name of a closed `p5`.

On the project card every agent terminal (`p<n>`) is a row of its own named,
in this order, by the ✎ name, the `/rename` name, the title Claude gave the
conversation; shells stay chips. `fractal_sessions` reports the ✎ name as
`label` (one `tmux list-panes -a`) and keeps a `/rename` title over later
ai-titles.

Because of these names every fractal tmux call targets sessions exactly
(`-t "=shop"`): tmux resolves a bare `shop` by prefix, so with the project
session down it would land in `shop-p1`. Project control scripts should do
the same (see `examples/ctl-script.sh`).

## Processes and lifetimes

```
systemd --user
 ├─ fractal-ctl.service        long-running, restarts on failure
 ├─ fractal-telegram.service   optional bot; only started when the token file exists
 ├─ fractal-files.service      long-running
 ├─ fractal-upload.service     long-running
 ├─ fractal-term.service       ttyd, long-running
 ├─ fractal-status.timer       every 20 s → status.json
 ├─ fractal-claude-usage.timer every 5 min (optional)
 ├─ fractal-codex-usage.timer  every 5 min (optional)
 ├─ fractal-autostart.service  oneshot at login: starts project units per autostart.json
 └─ <project>.service ...      oneshot+RemainAfterExit, ExecStart = "<ctl> start"
                               NOT wanted by default.target — autostart decides
tmux server (one, shared)
 ├─ session <project>: window "claude" (agent), one window per service, "shell"
 └─ session home
```

Project services live in **tmux windows**, not in systemd cgroups. That is
the whole point: the process you can see and scroll in the browser terminal is
the same process the dashboard switch controls, and the same one you get over
SSH. The systemd unit is only a way to run `<ctl> start` at boot.

Two consequences shape the unit template `project-register` writes:

- `KillMode=process`: the tmux server daemonizes into the cgroup of whichever
  unit created it first; without this, stopping one project would kill every
  other project's windows.
- `RemainAfterExit=yes` with `Type=oneshot`: `systemctl --user stop` runs the
  control script's `stop`, `start` is a no-op while active.

`sudo loginctl enable-linger $USER` keeps the user manager, and with it the
tmux server, alive without an open login.

## State detection

The dashboard never trusts a return code and never asks a control script for
status. Up/down is a TCP connect to `service.probe` — the port the application
itself listens on — with a 400 ms timeout. Two reasons:

- `docker compose ps` takes seconds; a dashboard poll every 15 s cannot afford it.
- Control scripts lie: `stop` may end with `tmux kill-window` on a window that
  is already gone and return non-zero although the stack is down.

The same probe drives the up/down dot on each link (a `no-cors` fetch from the
browser), the autostart `save` command, and the success check after a toggle
(`fractal-ctl` waits up to 45 s for the port to appear).

`probe` must not be an nginx proxy port: nginx keeps it open while the app
behind it is dead, and the card would show green forever.

## Autostart memory

`~/.config/fractal/autostart.json` maps project → on/off. `fractal-ctl` writes
it **when a toggle is accepted**, not when it finishes, so a power cut in the
middle of a `docker compose up` still remembers the intent. `work <p>` writes
"on". A project missing from the file counts as on, so a freshly registered
project starts after the next reboot until someone switches it off.

## Pinned projects and the agent

A project with `"pinned": true` is drawn as a highlighted section next to the
Machine card instead of a tab card. Besides its links it gets:

- **send** — `POST /ctl/agent/<p>/send {text}`. `fractal-ctl` makes sure the
  agent runs in tmux window `<p>:claude` (starting the session exactly the way
  `work` would), then `load-buffer` + `paste-buffer -p` the text (bracketed
  paste, so newlines do not submit) and presses Enter. An optional
  `sendPrefix` (e.g. `/braindump `) is prepended, unless the text itself
  starts with `/` - a slash command is meant literally.
- **ask** — `POST /ctl/agent/<p>/query {q}` returns a job id; the server runs
  `claude -p --output-format stream-json` in the project directory and appends
  text deltas to the job; the page polls `GET .../query/<id>` and shows the
  answer while it is being written. Long answers never hit an HTTP timeout.
- **actions** — buttons that `POST /ctl/run/<p>/<hook>`; the command comes
  from `hooks` in the registry, runs to completion in the background, and the
  page polls its status.

None of this is specific to a "second brain"; that is just the first thing it
was used for.

## The Telegram bot

`fractal-telegram` is the same client as the dashboard, minus the browser:
`/start p` is `POST /ctl/p/start`, `/ask p q` is `POST /ctl/agent/p/query`
followed by polling, `/run p h` is `POST /ctl/run/p/h`. It reads
`projects.json` only to validate names and to list what a project can do;
it never executes anything itself. The Bot API is long-polled
(`getUpdates`, 50 s), so a tailnet-only machine needs no webhook. On start
the backlog of updates is dropped: replaying a `/stop` from an hour ago is
never what anyone wants. Each command runs in its own thread so a long
`/ask` does not block `/status`. Plain text without a command is a `/send`
to the chat's default project (`/use`), which with a `sendPrefix` makes the
chat a capture inbox. `/help` shows `$FRACTAL_STATE_DIR/telegram-help.txt`
when it exists, so an instance can carry its own text in its own language.
A watcher thread compares `/ctl/state`
snapshots and messages every allowed user when a project changed between
up and down while no toggle was in flight.

## Claude sessions

The *Claude sessions* card lists every interactive Claude Code process on the
machine, not just the agent windows `work` created. `lib/fractal_sessions.py`
(served as `GET /ctl/sessions`) needs no hooks: Claude Code keeps
`~/.claude/sessions/<pid>.json` current by itself (status, when it changed,
cwd, tmux pane, session id). A file only counts when its pid is alive and
`/proc/<pid>/stat` has the recorded start time, so a reused pid never
resurrects an old session. `busy` means working, `waiting` means it asked
something (a question, a permission) and is blocked on you; `idle` and
`shell` (turn finished, a background shell still running) mean it is done. Title, last
prompt and last answer come from the transcript
`~/.claude/projects/*/<session id>.jsonl`, parsed incrementally from a
remembered byte offset (first read: at most the last 4 MB). The project is the
tmux session name when it is in the registry, else the deepest `root` that
holds the cwd.

A session can also carry its task: a Claude Code mod may write
`$FRACTAL_SESSION_TASK_DIR/<session id>.json` (default
`~/.local/state/claude-task/`) with `summary` (one line: what the session is
about), `active` (what it is doing right now), `done`/`total` (progress) and
`pinned`. When the file exists, the summary replaces the conversation title on
the card and `active` with the progress is a line under it; nothing else
depends on it.

The one-sentence summary is on demand only (`POST /ctl/sessions/<id>/summary`):
`claude -p --model haiku` with no tools, no setting sources and no session
persistence, fed the recent prompts and answers on stdin. Results are cached in
`$FRACTAL_STATE_DIR/session-summaries.json` and pruned when a session ends.
The terminal button opens `/term/?arg=pane:<n>`, which joins a grouped tmux
session so other clients keep their current window.

The card groups sessions by the registry `group`, then by project; each
project has a hue (`color` in the registry, or a palette by registry order)
shared by its session tag and the stripe on its project card.

It is served by `/ctl` rather than as a static JSON in the web root because
prompts are personal content and `/ctl` is tailnet-only.

## The task board

`fractal-tasks` (`GET/POST /tasks/...`, tailnet only) is the fourth loopback
service and the only one with a watcher thread. It owns no data: a project
has a board when its `root` holds `tasks/`, and every task is a markdown
file there with a small frontmatter (status, order, priority, phase,
verify) followed by the owner's request and appended, dated sections
(Plan, Questions, Answers, Feedback, Result, Run). `lib/fractal_tasks.py`
is the parser both the service and the runner use. The file is the prompt,
the history and the git record at once, so the board never has to be
trusted more than a text editor; the format is in
[docs/tasks.md](docs/tasks.md).

Running a task means `fractal-task-run <project> <id> triage|run` in a tmux
window `task-<id>` of the project's session - the same session `work` and
`/term` attach to. The service only creates the window; the runner sets the
status, drives one headless `claude -p` session (stream-json, printed one
line per event, logged to `tasks/logs/`), decides the outcome from what the
agent appended (a Plan, a Questions section, the `NEED_ATTENTION` marker),
runs `verify`, appends a Run section and commits the task file alone. That
is why a run survives a restart of `fractal-tasks` and can be started by
hand without the board.

The watcher polls file mtimes and the tmux window list every two seconds
and pushes `{"project"}` events over server-sent events (`/tasks/events`;
nginx has buffering off for the prefix). It also parks a "running" task
whose window vanished for two minutes without an outcome, and with the
per-project *auto* switch (in `$FRACTAL_STATE_DIR/tasks-state.json`) starts
the first queued task when nothing is being implemented - one
implementation at a time per project because the runs share a working
tree, while a triage (read-only) may run beside it.

The page `www/tasks.html` is one file like the dashboard: the kanban is a
render of the task list, drag and drop posts the target column plus the
column's order, and every change is followed by a reload rather than local
bookkeeping. The Telegram bot gained `/task` and `/tasks`, a bare `task …`
/ `úkol …` message for dictation, and a `notify` subcommand the runner
calls when a run ends.

## Dashboard internals

`www/index.html` is one file: CSS, markup, JS. It fetches `projects.json`,
`status.json`, the two usage JSONs, `/ctl/state`, `/ctl/sessions` and `/files/list`, all with
`cache: no-store`, and re-polls on intervals (15 s state, 20 s status/probes,
faster while a toggle is in flight). Sections whose data is absent hide
themselves (no usage file → no meters, no `pinned` → single-column top row,
no `wifi` → no tile). Light/dark follows the system; status colours are
always paired with a word so nothing depends on colour alone.

`termkeys.js` is injected into ttyd pages by nginx (`sub_filter`) and adds a
key bar for touch devices; it also fixes the tab title per project, since one
ttyd instance cannot know which project a tab shows.

## What is deliberately not here

- **No auth.** The boundary is the VPN. See SECURITY.md.
- **No TLS.** Tailscale encrypts the wire; on a LAN this is plain HTTP.
- **No process supervisor for project services.** tmux windows are visible,
  scrollable and killable, which for a dev box beats being restarted behind
  your back.
- **No container for fractal itself.** It manages tmux and systemd on the
  host; a container would only add indirection.
