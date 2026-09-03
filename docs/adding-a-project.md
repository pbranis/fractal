# Adding a project

Three steps. None of them needs root.

## 1. Know how it starts

Find the start command and the port. Check whether the server binds
`0.0.0.0`; most dev servers default to `127.0.0.1`, which the dashboard link
cannot reach from another machine. Pass `--host 0.0.0.0` (or equivalent) from
the control script rather than editing the project's own config.

Dev servers (Vite, Astro, Next) also reject unknown `Host` headers — you will
see 200 with `curl` on the box and 403 in the browser. Allow the names you use
(`vite.server.allowedHosts`, Next `allowedDevOrigins`, …); the control script
template shows how to pass them through an environment variable.

## 2. Write a control script

Copy `examples/ctl-script.sh` to `~/.local/bin/<name>`, fill in `ROOT`,
`SESSION`, `PORT`, `CMD`. The contract the dashboard relies on:

- `start` runs the service in a **tmux window** of a session named after the
  project, and is **idempotent** — it checks the port and refuses to start a
  second copy.
- `stop` kills the process group and closes the window.
- `status`, `attach`, `logs`, `cd` are for you.

Several services → several windows in the same session (one `start_x`
function per service; `start all` calls them in order). A docker compose stack
is simply `docker compose up` in one window with `--abort-on-container-exit`
or `docker compose logs -f` after `up -d`.

## 3. Register

```bash
project-register add shop --root ~/projects/shop \
  --title "Shop" --group "Work" \
  --desc 'Next.js + Postgres · <code>shop start|stop|status</code>' \
  --ctl "shop start" \
  --link "Web:3000:/" \
  --link "Admin:3000:/admin" \
  --link "API docs:8811:/docs:proxy" \
  --service-start "shop start" --service-stop "shop stop" --probe 3000 \
  --autostart
```

What each flag does:

| Flag | Effect |
|---|---|
| `--group` | tab on the dashboard; created if new |
| `--desc` | small print under the title; HTML allowed |
| `--ctl` | what `work shop` runs before attaching to tmux |
| `--link Label:PORT:/path[:note]` | a row on the card with a live up/down dot; empty PORT = same origin as the dashboard |
| `--service-start/-stop` | commands behind the card's switch |
| `--probe` | port **the app itself** listens on. Never an nginx proxy port — nginx keeps it open while the app is down |
| `--autostart` | writes `~/.config/systemd/user/shop.service`; `fractal-autostart` starts it at boot if the project was running before |
| `--no-terminal` | for libraries and other things with nothing to run |
| `--claude-args` | extra flags for the agent, e.g. `--add-dir ../shared` |

Reload the dashboard. The card is there, the switch works, the Terminal
button opens tmux session `shop` with the agent in the first window.

## Edit, move, remove

```bash
project-register list
project-register edit shop --add-link "Storybook:6006:/" --title "Shop (v2)"
project-register group shop "Clients"
project-register groups --order "Clients,Work,Personal"
project-register remove shop            # keeps the tmux session running
```

## Pinned projects

Something you open every day deserves a spot next to the Machine card
instead of a tab:

```bash
project-register edit notes --pinned \
  --send-prefix "/braindump " \
  --hook refresh="notes-inbox --force" \
  --action "⟳ Inbox & dashboard:refresh"
```

A pinned card shows its links as buttons, a **send** box that pastes text
into the agent's tmux window (prefixed with `sendPrefix`), an **ask** box
that runs a headless query in the project directory and streams the answer,
and one button per `action` that runs the named `hook` from the registry.

## Exposing a 127.0.0.1-only backend

The one case that needs root. Add a server block on a spare port to
`/etc/nginx/sites-available/fractal`:

```nginx
server {
    listen 8811;
    location / {
        proxy_pass http://127.0.0.1:8801;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

`sudo nginx -t && sudo systemctl reload nginx`, then link to `:8811` with
note `proxy`. Keep `--probe` on the real port (8801).

## Letting Claude Code do it

```bash
ln -s ~/projects/fractal/skill/fractal-project ~/.claude/skills/fractal-project
```

Then, in Claude Code: *"wire ~/projects/shop into the dashboard"*. The skill
walks the agent through the three steps above, including the Host-header
pitfall and the probe-port rule.
