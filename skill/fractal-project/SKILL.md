---
name: fractal-project
description: Wire a project from ~/projects into the fractal dashboard on port 80 — a card with links, a browser terminal, the `work` switcher, a start/stop switch and boot-time autostart. Use it whenever a new project appears on the machine, when an existing project should show up on the dashboard, or when the ports and links of a registered project change.
---

# Wiring a project into the fractal dashboard

The dashboard lives at `$FRACTAL_URL` (see `~/.config/fractal/fractal.env`;
default `http://<hostname>/`). Every project in `~/projects` should have a card
with links to its services and a Terminal button.

**Everything is driven by one registry: `$FRACTAL_WWW/projects.json`**
(default `/var/www/fractal/projects.json`). The dashboard, the `work`
switcher, the browser terminal `/term/`, the start/stop backend and the
autostart memory all read it. The file belongs to the user, so writing it
needs no root and changes neither HTML nor nginx.

## Steps

### 1. Find out how the project starts and which port it uses

Look at `package.json`, `docker-compose.yml`, `Makefile`, `run.*`, README.
You need:

- the command that starts the service,
- the port(s) it listens on,
- whether it binds `0.0.0.0` or only `127.0.0.1`.

**If it binds only `127.0.0.1`, that has to change** (typically a
`--host 0.0.0.0` switch), otherwise the dashboard link cannot reach it. Do
not edit `package.json` for that — pass the switch from the control script.

### 2. Write a control script `~/.local/bin/<name>`

This part cannot be generated; every project is different. Start from
`examples/ctl-script.sh` in the fractal repo (one service) — for several
services add one tmux window per service. The script must support
`start|stop|restart|status|attach|logs|cd`, run services in a tmux session
named after the project, and be **idempotent** — `start` on a running service
must not start it twice (check port ownership, not pid files).

### 3. Register the project

```bash
project-register add <name> --root ~/projects/<dir> \
  --title "Display name" --group "Tab name" \
  --desc 'control with <code>&lt;name&gt; start|stop|status</code>' \
  --ctl "<name> start" \
  --link "Web:5000:/" \
  --link "Admin:5000:/admin" \
  --service-start "<name> start" --service-stop "<name> stop" --probe 5000 \
  --autostart
```

- `--ctl` is what `work <name>` runs before attaching to tmux
- `--link` is `Label:PORT:/path[:note]`; an empty port means the same origin as
  the dashboard (for things behind nginx, e.g. `"Docs::/reports/:tailnet only"`)
- `--service-start/--service-stop/--probe` give the card its on/off switch;
  `--probe` is the port **the application itself** listens on, never an nginx
  proxy port (nginx keeps it open even when the app is down)
- `--autostart` writes a systemd user unit so the project comes back after a
  reboot — but only if it was running before (`fractal-autostart show`)
- `--no-terminal` for projects with nothing to run (libraries)
- `--pinned` renders the project as a highlighted section next to the Machine
  card, with "send to agent" and "ask" boxes; `--hook NAME=cmd` plus
  `--action "Label:NAME"` add buttons that run registry commands

`project-register list` shows what is registered, `edit` changes fields,
`remove` takes a project out.

### 4. Verify

```bash
work <name>                  # from SSH
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<port>/
```

Reload the dashboard — the card must be there — and open
`$FRACTAL_URL/term/?arg=<name>`.

### 5. Optional: a task board

Create an empty `tasks/` directory in the project root (and add
`tasks/logs/` to its `.gitignore`) and the project appears on
`/tasks.html` - a kanban whose cards are markdown files the agent plans and
implements. Nothing else to register; see `docs/tasks.md` in the fractal
repo.

## Pitfalls

**Dev servers reject foreign Host headers.** Vite, Astro and Next return 403
or an empty page to anything not coming through `localhost`. Symptom: `curl`
on the server returns 200, the browser gets 403.

| Tool | Where it is configured |
|---|---|
| Vite / Astro | `vite.server.allowedHosts` |
| Next.js | `allowedDevOrigins` in `next.config` |

Add every name you use to reach the box (hostname, MagicDNS name, LAN IP,
tailnet IP, `localhost`). Pass the list from the control script through an
environment variable (see `DEV_HOSTS` in `examples/ctl-script.sh`), not
hard-coded into the project config.

**The port must be free.** Check `ss -ltn` before assigning one. The fractal
helpers use 7685 and 7690–7692 by default.

**Root is needed in one case only** — when the project has a service on
`127.0.0.1` that you want to expose through nginx. Then add a `server` block
on its own port to `/etc/nginx/sites-available/fractal` (template at the
bottom of `nginx/fractal.conf.template`), run `sudo nginx -t`, then
`sudo systemctl reload nginx`. In every other case root is not needed.

**Terminals, `/files`, `/upload` and `/ctl` are tailnet-only.** From the LAN
they return 403 — that is not a bug, there is a shell behind them. The
dashboard itself works from the LAN.

## Finally

If the machine has a hand-written reference document (ports, services,
pitfalls), record the new project there too. The registry is the truth for
the dashboard; the document is the truth for humans.
