# Configuration

One file: `~/.config/fractal/fractal.env` (override the path with
`$FRACTAL_ENV`). Plain `KEY=VALUE`, so the same file is sourced by bash
(`lib/fractal-env.sh`), parsed by Python (`lib/fractal_config.py`) and
rendered into systemd units and nginx snippets by `install.sh`. Every key
has a default; an absent file is not an error.

| Key | Default | Used by |
|---|---|---|
| `FRACTAL_WWW` | `/var/www/fractal` | everything: web root, registry, status files |
| `FRACTAL_URL` | `http://<hostname>/` | hints printed by `project-register`, the 403 page |
| `FRACTAL_ALLOW` | `100.64.0.0/10 fd7a:115c:a1e0::/48` | nginx `fractal-tailnet-only.conf` (rendered) |
| `FRACTAL_UPLOADS` | `~/uploads` | `fractal-upload` |
| `FRACTAL_STATE_DIR` | `~/.config/fractal` | `autostart.json`, install backups |
| `FRACTAL_CTL_PORT` | `7691` | `fractal-ctl`, nginx, unit |
| `FRACTAL_FILES_PORT` | `7692` | `fractal-files`, nginx, unit |
| `FRACTAL_UPLOAD_PORT` | `7690` | `fractal-upload`, nginx, unit |
| `FRACTAL_TERM_PORT` | `7685` | ttyd unit, nginx |
| `FRACTAL_AGENT` | `claude` | `work`, `fractal-ctl` (agent window, headless ask) |
| `FRACTAL_AGENT_FLAGS` | `--dangerously-skip-permissions` | appended to the agent command |
| `FRACTAL_AGENT_WINDOW` | `claude` | tmux window name the agent lives in |
| `FRACTAL_WIFI_IFACE` | *(autodetect)* | `fractal-status` |

After changing ports or `FRACTAL_ALLOW`, run `./install.sh --nginx` so the
snippets and units are re-rendered. After changing anything else,
`./install.sh` is enough (services are restarted; tmux sessions are not
touched).

## Where things live after install

| What | Where |
|---|---|
| scripts | `~/.local/bin/*` → symlinks into `<repo>/bin/` |
| dashboard | `$FRACTAL_WWW/index.html`, `docs.html`, `termkeys.js` (copies; `./install.sh --www-only` refreshes them) |
| registry | `$FRACTAL_WWW/projects.json` |
| generated data | `$FRACTAL_WWW/status.json`, `claude-usage.json`, `codex-usage.json` |
| autostart memory | `$FRACTAL_STATE_DIR/autostart.json` |
| user units | `~/.config/systemd/user/fractal-*.service|timer`, `<project>.service` |
| nginx | `/etc/nginx/sites-available/fractal`, `/etc/nginx/snippets/fractal-*.conf` |

Why copies for the web root and not symlinks: nginx runs as `www-data` and a
home directory is normally `drwx------`, so a symlink from `/var/www` into
`~/projects/fractal/www` would be a 403.

## The agent command

With `FRACTAL_AGENT=claude` the first tmux window runs

```
claude -c <flags> <claudeArgs> || claude <flags> <claudeArgs>; exec bash
```

— resume the last conversation in this directory, else start a new one, and
fall back to a shell when the agent exits so the window survives. Any other
value is started as `<agent> <flags> <claudeArgs>; exec bash`; the headless
"ask" box on pinned cards is claude-only.
