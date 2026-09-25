# Registry schema — `projects.json`

Location: `$FRACTAL_WWW/projects.json`. Owned by the user. Read on every
request by every component, so edits apply immediately. Prefer
`project-register`, which writes atomically, but hand edits are fine.

```jsonc
{
  "_comment": "free text",
  "groups": ["Work", "Personal"],          // tab order; unknown groups land in "Other"
  "footer": "<small>HTML</small>",         // optional, replaces the default footer
  "projects": [ { ...project }, ... ]
}
```

## Project

| Field | Type | Meaning |
|---|---|---|
| `name` | string, `^[a-z][a-z0-9-]{0,30}$` | identifier; also the tmux session name and `?arg=` value |
| `title` | string | card heading |
| `group` | string | tab; must appear in `groups` to be shown there |
| `root` | absolute path | project directory; `work` and the agent start here |
| `desc` | HTML string | small print under the heading |
| `ctl` | string | command `work <name>` runs before attaching (usually `<name> start`) |
| `claudeArgs` | string | extra flags appended to the agent command |
| `terminal` | bool, default `true` | show the Terminal button; `false` for libraries |
| `links` | array of Link | rows on the card |
| `service` | Service | enables the on/off switch |
| `pinned` | bool | render as a highlighted section next to the Machine card |
| `color` | number 0–360 | hue of the project's colour (card stripe, session tags); default: a palette by registry order |
| `sendLabel` | string | label of the pinned card's send button (default "✍ Poslat agentovi") |
| `sendPrefix` | string | prepended to text sent to the agent window, e.g. `"/braindump "` |
| `hooks` | object name → command | commands the dashboard may run via `/ctl/run/<name>/<hook>` |
| `actions` | array of Action | buttons on a pinned card |

### Link

```json
{"name": "Admin", "port": 3000, "path": "/admin", "note": "proxy"}
```

`port: null` means same origin as the dashboard (a path served by nginx).
The dashboard probes `http://<host>:<port><path>` with a `no-cors` fetch to
draw the dot.

### Service

```json
{"start": "shop start", "stop": "shop stop", "probe": 3000, "unit": "shop.service"}
```

`probe` is the port the application itself listens on; up/down is a TCP
connect to it. `unit` is optional and defaults to `<name>.service`.

### Action

```json
{"name": "⟳ Inbox & dashboard", "hook": "refresh", "href": "/notes-html/dashboard.html"}
```

`hook` must exist in `hooks`. `href` is optional; when the hook succeeds the
status line offers an "open" link.

## Commands run without a shell

`service.start`, `service.stop` and every `hooks` value are split with
`shlex.split` and executed directly (`execvp`), with `~/.local/bin` on `PATH`
and the home directory (service) or `root` (hooks) as working directory.
Pipes, redirects and `&&` do not work here — put them inside your control
script.
