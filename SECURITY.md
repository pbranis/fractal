# Security model

fractal puts a shell, your home directory and a "run this stack" button on a
web page. Read this before you install it anywhere you would not hand your
unlocked laptop to.

## Boundary: the tailnet

The only access control is **network origin**. nginx restricts every
location that can do harm to the CIDRs in `FRACTAL_ALLOW` (default: Tailscale
IPv4 `100.64.0.0/10` and IPv6 `fd7a:115c:a1e0::/48`) plus `127.0.0.1`:

| Location | What is behind it | Access |
|---|---|---|
| `/` `status.json` `projects.json` | dashboard, machine stats, project list | anyone who reaches :80 |
| `/term/` | a **shell as your user**, via ttyd | tailnet only |
| `/ctl/` | start/stop stacks, paste text into the agent, run hooks | tailnet only |
| `/files/` | read + upload anywhere under `~` | tailnet only |
| `/upload/` | write into `~/uploads` | tailnet only |

Consequences you should accept explicitly:

- **Anyone on your tailnet is you.** There is no login. If you share the
  tailnet with other people or devices you do not fully control, do not run
  this, or front it with something that authenticates (Tailscale Serve with
  identity headers, an oauth2 proxy, a VPN ACL that only your devices match).
- **The plain dashboard leaks project names, ports, hostnames and machine
  stats to the LAN.** `projects.json` is public on :80. If that matters, wrap
  `location /` in the tailnet snippet as well.
- **No TLS.** Fine over Tailscale (WireGuard underneath); on a LAN it is
  cleartext.

## What the browser can and cannot do

The client never sends a command. Every write endpoint takes a *name* and
looks the command up server-side:

| Endpoint | Client sends | Server executes |
|---|---|---|
| `POST /ctl/<p>/start\|stop` | project name | `projects[p].service.start/stop` from the registry |
| `POST /ctl/run/<p>/<hook>` | project + hook name | `projects[p].hooks[hook]` |
| `POST /ctl/agent/<p>/send` | free text | pasted into a tmux pane via `load-buffer`/`paste-buffer` |
| `POST /ctl/agent/<p>/query` | free text | `claude -p …` with the text on **stdin** |
| `PUT /files/up`, `/upload/<name>` | file body | written under `~`, never overwriting, `realpath` must stay inside `~` |
| `/term/?arg=<p>` | project name | `work <p>` only if `p` is in the registry; otherwise a plain shell |

Commands run with `shlex.split` + `execvp`, no shell, so a crafted name cannot
chain anything. Text for the agent goes through tmux buffers (literal paste,
no key interpretation) or stdin, never onto a command line.

That said: pasting text into an interactive coding agent that runs with
permission prompts disabled **is** arbitrary code execution by design. It is
the feature. It is why `/ctl` is tailnet-only.

## The agent flags

The default is

```
FRACTAL_AGENT=claude
FRACTAL_AGENT_FLAGS=--dangerously-skip-permissions
```

because on a personal dev box, approving every file edit from a phone is not
a workflow. It means anything typed into the agent window, from any device on
your tailnet, runs unattended. If that is not acceptable, set
`FRACTAL_AGENT_FLAGS=` (empty) and the agent will ask, or point
`FRACTAL_AGENT` at something else entirely.

## File endpoints

- Every path from the client is resolved with `realpath` and must stay under
  `~`. This blocks `..` and symlinks that point out of the home directory.
- Uploads never overwrite: an existing name gets `-1`, `-2`, … appended.
- There is no delete, rename or edit. The worst a browser can do is fill the
  disk (capped at 4 GB per file) or read what you can read.
- File names are reduced to a basename with control characters stripped and a
  leading dot removed.

## What fractal reads that you might not expect

- `fractal-claude-usage` reads the OAuth access token from
  `~/.claude/.credentials.json` to query the usage API, and writes only
  percentages and reset times to the web root. The token never leaves the
  machine except towards `api.anthropic.com`. The timer is enabled only when
  the `claude` CLI exists; disable it with
  `systemctl --user disable --now fractal-claude-usage.timer`.
- `fractal-codex-usage` asks the local Codex app-server for rate limits; no
  network call of its own.
- `fractal-status` reads `/proc`, `/sys`, `df`, `iwconfig`, `docker ps`.

## Reporting

This is a personal project. If you find something that lets a LAN client
(outside the allowed ranges) reach a tailnet-only endpoint, or a tailnet
client escape `~` through `/files`, open an issue.
