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
| `bin/term` | validates the `?arg=` project name before handing over to `work` |
| `bin/fractal-ctl` | `service.start/stop/probe`, `hooks`, `sendPrefix` |
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

## Processes and lifetimes

```
systemd --user
 ├─ fractal-ctl.service        long-running, restarts on failure
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
  `sendPrefix` (e.g. `/braindump `) is prepended.
- **ask** — `POST /ctl/agent/<p>/query {q}` returns a job id; the server runs
  `claude -p --output-format stream-json` in the project directory and appends
  text deltas to the job; the page polls `GET .../query/<id>` and shows the
  answer while it is being written. Long answers never hit an HTTP timeout.
- **actions** — buttons that `POST /ctl/run/<p>/<hook>`; the command comes
  from `hooks` in the registry, runs to completion in the background, and the
  page polls its status.

None of this is specific to a "second brain"; that is just the first thing it
was used for.

## Dashboard internals

`www/index.html` is one file: CSS, markup, JS. It fetches `projects.json`,
`status.json`, the two usage JSONs, `/ctl/state` and `/files/list`, all with
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
