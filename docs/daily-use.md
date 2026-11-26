# Daily use

How the pieces are meant to be used once fractal runs. The dashboard UI is
in Czech; its labels are quoted as they appear, with a translation.

## The model in one paragraph

Every project is a **tmux session** named after it. Its windows are the
project's services (one window per dev server, compose stack, worker) plus a
window `claude` with the coding agent running in the project directory. The
dashboard, the browser terminal, SSH and `work` all attach to the *same*
sessions, so nothing is tied to the device you started it on: start a
conversation with the agent on the laptop, check on it from the phone,
finish it over SSH.

## The dashboard

- **Project cards**, grouped into tabs (the registry's `group`). A card has
  links to the project's services with live up/down dots, a switch that
  starts or stops the whole stack, and *▸ Terminál*.
- **Machine card**: load, temperature, memory, disk, Wi-Fi, docker
  containers, the network watchdog's state and (optionally) your Claude /
  Codex usage limits.
- **Claude sessions**: every interactive Claude Code session on the machine,
  wherever it was started - its state (working, waiting for you, idle, and
  for how long), the conversation's title, your last prompt and its last
  answer. A click opens its exact tmux pane in the browser; ✦ asks for a
  one-sentence summary.
- **Pinned projects** (`pinned: true` in the registry) get two extra boxes:
  *✍ Poslat agentovi* pastes text into the agent's window as if you typed
  it, *🗨 Zeptat se* runs a one-off headless question in the project and
  streams the answer back without touching the running conversation.
- **Files**: browse the home directory, download, drag and drop uploads into
  `~/uploads`.
- **▸ Terminál v ~** opens a plain shell (tmux session `home`).

## Terminals

*▸ Terminál* on a card attaches to the project session; the agent window is
first. Inside tmux:

| Keys | |
|---|---|
| `Ctrl-b w` | list of all sessions and windows, searchable |
| `Ctrl-b n` / `Ctrl-b p` | next / previous window |
| `Ctrl-b d` | detach (everything keeps running) |
| `Ctrl-b [` | scroll mode (`q` to leave); with `extras/tmux.conf` the mouse wheel scrolls |

The same cheat sheet is at `http://<box>/docs.html`.

**More conversations in one project.** *＋ Claude* on a card opens a new
terminal with a fresh agent conversation in the project directory, *＋ shell*
a plain shell. Each is its own tmux session, `<project>-p1`, `<project>-p2`,
`<project>-s1`, so several agents can work on one project side by side, and
stopping the services does not touch them. They are listed on the card;
× closes one (it asks first, and warns when the agent is still working).

**Tab names.** ✎ in the corner of a terminal names it ("chart fixes"). The
name is kept in tmux, so every device and the dashboard show it, and it goes
away with the terminal.

**On a phone or tablet** switch on the key bar (dashboard, or ⌨ in the
terminal) for arrows, Esc, Tab and a sticky Ctrl; A− / A+ change the font
size on that device.

## From the command line

```bash
work                 # list the projects
work shop            # start shop's services and attach to its session
work shop p2         # attach to (or create) the extra agent terminal shop-p2
shop status          # whatever the project's control script offers
project-register list
```

`work` started from inside tmux switches the client instead of nesting.

## The agent windows

The agent runs with the flags from `FRACTAL_AGENT_FLAGS` - by default
`--dangerously-skip-permissions`, so it does not stop to ask before every
edit. That is convenient from a phone and dangerous if you do not trust what
you paste into it; see [SECURITY.md](../SECURITY.md#the-agent-flags).

When the agent exits, the window falls back to a shell instead of closing;
`claude -c` there continues the last conversation in that directory.

## After a reboot

You do not have to do anything:

1. `fractal-autostart` starts the projects that were running before
   (switched off on the dashboard = stays off).
2. `fractal-resume` brings back every agent conversation that was open in
   tmux - the `claude` window of a project, the extra terminals
   `<project>-p<n>`, anything else - under the same name, with
   `claude --resume`, and with its tab name. The conversation is back; work
   that was in flight at the moment of the crash is not, so tell the agent to
   continue.

`fractal-resume show` lists what was saved and what runs now. A conversation
you ended yourself (`/exit`, closed terminal) is not brought back.

## Tasks and the phone

- The **task board** (`/tasks.html`) is a kanban over markdown files in each
  project's `tasks/`: the agent plans a task, you approve it, it implements
  it in a window you can watch, and hands it back for review. See
  [tasks.md](tasks.md).
- The **Telegram bot** does start/stop, questions, dictated tasks and a
  free conversation with Claude on the machine from your phone, and pings
  you when a project dies or a task finishes. See
  [configuration.md](configuration.md#the-telegram-bot).
