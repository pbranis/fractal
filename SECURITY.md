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
| `/term/?arg=pane:<n>` | digits | attaches to tmux pane `%<n>` only if it already exists; nothing is started |
| `POST /ctl/sessions/<id>/summary` | session id | `claude -p` without tools, fed that session's transcript tail on stdin; the id must belong to a live session |

Commands run with `shlex.split` + `execvp`, no shell, so a crafted name cannot
chain anything. Text for the agent goes through tmux buffers (literal paste,
no key interpretation) or stdin, never onto a command line.

That said: pasting text into an interactive coding agent that runs with
permission prompts disabled **is** arbitrary code execution by design. It is
the feature. It is why `/ctl` is tailnet-only.

## The Telegram bot

`fractal-telegram` is a **second door** that does not go through nginx or
the tailnet. Its guard is Telegram's identity: the bot only acts on private
messages from the numeric user IDs in `FRACTAL_TELEGRAM_USERS` and ignores
everyone else. Everything it can do, it does via `fractal-ctl` on loopback,
so it is limited to the same verbs as the browser (start/stop, hooks, text
into the agent window, headless questions) - which, as above, includes
"paste arbitrary instructions into an agent that runs unattended".

What that means:

- Whoever controls your Telegram account (or a phone with it logged in)
  controls this machine. Use Telegram's two-step verification.
- Whoever has the bot token can read the messages you send to the bot and
  impersonate the bot towards you, but **cannot** issue commands: the bot
  process on this machine is the only thing that acts, and it checks the
  sender. Keep the token in the 0600 file anyway; revoke it in @BotFather
  if it leaks.
- While `FRACTAL_TELEGRAM_USERS` is empty the bot replies to anyone with
  their own user ID. That is the only thing it does in that state.
- Groups and channels are ignored; the bot works in private chats only.
- Messages travel through Telegram's servers (not end-to-end encrypted for
  bots). Do not `/send` secrets.

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
- `fractal-ctl` (`/ctl/sessions`) reads `~/.claude/sessions/*.json` and the
  tail of each live session's transcript to show its last prompt and answer.
  That is why the list is behind tailnet-only `/ctl`, not in the web root. A
  summary sends the recent prompts and answers of one session to the model,
  and only when you press the button.

## Reporting

This is a personal project. If you find something that lets a LAN client
(outside the allowed ranges) reach a tailnet-only endpoint, or a tailnet
client escape `~` through `/files`, open an issue.
