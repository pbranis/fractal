# fractal

**A one-page control room for a personal dev box on a tailnet.**
Cards for your projects, a start/stop switch on each, a browser terminal that
drops you into the project's tmux session with a coding agent already running,
machine health, a file browser — all driven by one JSON file, no root needed
to add a project.

> Built for a single developer's Linux box that is reached over
> [Tailscale](https://tailscale.com) from a laptop, a phone and an iPad.
> It is not a multi-user platform and does not try to be one.

<!-- screenshot: docs/img/dashboard.png -->

## What you get

- **Project cards** with links to every service, live up/down dots, and an
  iOS-style switch that starts or stops the whole stack (docker compose, dev
  servers, whatever your control script does).
- **Browser terminal** (`ttyd` + `tmux`) on every card. It attaches to the
  *same* tmux session you get over SSH, so a conversation with the coding agent
  started on the laptop continues on the phone.
- **Coding agent in the first window.** `work <project>` starts the services
  and lands you in a tmux window with [Claude Code](https://claude.com/claude-code)
  resumed in the project directory (any other CLI can be configured).
- **Pinned projects** get a highlighted section with two extra boxes: *send*
  pastes text into the agent's tmux window, *ask* runs a headless query and
  streams the answer back. Buttons can run named commands from the registry.
- **Autostart with memory.** After a reboot only the projects that were
  running come back.
- **Machine card:** load, temperature, memory, disk, Wi-Fi, docker containers,
  optionally your Claude / Codex usage limits.
- **Files:** browse your home directory, download, drag-and-drop upload.
- **On-screen key bar** for terminals on iOS (arrows, Esc, Tab, sticky Ctrl).
- **A Claude Code skill** (`skill/fractal-project`) that teaches the agent to
  wire a new project into the dashboard by itself.

Everything that exposes a shell or your home directory is limited by nginx to
the tailnet. The plain dashboard is visible from the LAN too.

## How it works

```
 browser ──:80──▶ nginx ─┬─ /            static  index.html, projects.json, status.json
                         ├─ /term/       ttyd  ──▶ term ──▶ work <project> ──▶ tmux session
                         ├─ /ctl/        fractal-ctl     start/stop, agent send/ask, hooks
                         ├─ /files/      fractal-files   browse ~ (read + upload only)
                         └─ /upload/     fractal-upload  drop zone
                                                   ▲
                    all helpers: loopback, run as you, read projects.json
```

`projects.json` is the single source of truth. The dashboard renders cards
from it, `work` and the terminal validate project names against it, the
control backend takes *commands* from it — the browser only ever sends a
project name. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full picture
and [SECURITY.md](SECURITY.md) for the threat model.

## Requirements

Debian/Ubuntu-ish Linux with systemd user sessions. Packages:

```
nginx tmux jq python3 gettext-base        # apt
ttyd                                       # https://github.com/tsl0922/ttyd (release binary is fine)
```

Optional: `docker` (container list), `iwconfig` (Wi-Fi tile),
`claude` / `codex` CLIs (agent window, usage meters), Tailscale (or any VPN —
the allowed ranges are configurable).

## Install

```bash
git clone https://github.com/<you>/fractal ~/projects/fractal
cd ~/projects/fractal
./install.sh --nginx          # asks for sudo only for /etc/nginx and /var/www
sudo loginctl enable-linger $USER   # keep user services and tmux alive without a login
```

Then edit `~/.config/fractal/fractal.env` (at least `FRACTAL_URL`), and try
the demo project:

```bash
./install.sh --demo           # registers "demo": python http.server on :7777
```

Open `http://<your-box>/` — the card is there, the switch turns it on and off,
the Terminal button lands you in tmux session `demo`.

`install.sh` is idempotent: run it again after every `git pull`. Scripts are
symlinked into `~/.local/bin`, dashboard files are copied into the web root,
systemd units are rendered from templates with your configuration.

## Adding a project

Three steps, no root: write a control script, register, done.
Full walkthrough in [docs/adding-a-project.md](docs/adding-a-project.md);
the short version:

```bash
cp examples/ctl-script.sh ~/.local/bin/shop && $EDITOR ~/.local/bin/shop
project-register add shop --root ~/projects/shop --title "Shop" --group Work \
  --ctl "shop start" --link "Web:3000:/" --link "Admin:3000:/admin" \
  --service-start "shop start" --service-stop "shop stop" --probe 3000 --autostart
```

Or, if you use Claude Code: symlink `skill/fractal-project` into
`~/.claude/skills/` and say *"wire ~/projects/shop into the dashboard"*.

## Configuration

One file, `~/.config/fractal/fractal.env`, read by every script and rendered
into the systemd units and nginx snippets by `install.sh`. All keys are
documented in [examples/fractal.env.example](examples/fractal.env.example);
the ones you will touch:

| Key | Meaning |
|---|---|
| `FRACTAL_URL` | The address you type into the browser; used in hints and the 403 page |
| `FRACTAL_ALLOW` | CIDRs allowed to reach shells (`/term`, `/ctl`, `/files`, `/upload`). Default: Tailscale ranges |
| `FRACTAL_WWW` | Web root, owned by you. Default `/var/www/fractal` |
| `FRACTAL_AGENT`, `FRACTAL_AGENT_FLAGS` | What runs in the first tmux window. Default `claude --dangerously-skip-permissions` — read SECURITY.md |

## Layout

```
bin/        fractal-ctl, fractal-files, fractal-upload, fractal-status, fractal-autostart,
            project-register, work, term, fractal-claude-usage, fractal-codex-usage
lib/        shared config loader (bash + python)
www/        index.html (dashboard), docs.html (cheat sheet), termkeys.js (iOS key bar)
nginx/      site template + snippets (core locations, tailnet-only, ttyd proxy)
systemd/    user unit templates
skill/      Claude Code skill: wiring a project in
examples/   fractal.env, projects.json, control-script template, demo project
extras/     agent CLI wrappers, tmux.conf
docs/       adding a project, configuration, registry schema
```

## Status and caveats

- The dashboard UI and its inline comments are **Czech** (it grew on a Czech
  desk). Scripts, docs and the skill are English. An i18n pass is welcome.
- Single user by design. Everything runs as *you*; the security boundary is
  the VPN, not a login form.
- Tested on Debian 13 with Python 3.13, nginx 1.26, tmux 3.5, ttyd 1.7.

## License

MIT — see [LICENSE](LICENSE).
