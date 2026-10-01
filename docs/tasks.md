# Task board

A kanban for work you hand to the coding agent: `/tasks.html` on the
dashboard, backed by `fractal-tasks` and run by `fractal-task-run`. It is
deliberately small - one person, one machine, no database - and it exists
because a request dictated into a phone should end up as a reviewed plan, a
commit and a note of what happened, without anyone copying text between
tools.

## Where the tasks live

A project takes part as soon as its registry `root` has a `tasks/`
directory. Every task is one markdown file in it:

```
---
id: 042
title: Indicator page width
status: todo          # triage | backlog | todo | in-progress | need-attention | review | done | canceled
order: 30             # position inside its column; drag and drop renumbers
priority: 3           # 1 urgent .. 4 low (badge only)
assignee: claude      # anything else means "a human does this"; the auto queue skips it
phase: dev            # what the agent was last asked to do: triage or dev
verify: npm --prefix web run build
created: 2026-10-01 14:02
updated: 2026-10-01 14:30
---
the request, as the owner wrote it - never rewritten

## Plan (agent · 2026-10-01 14:05)
...
## Questions (agent · 2026-10-01 14:05)
1. ...
## Answers (owner · 2026-10-01 14:20)
1. ...
## Result (agent · 2026-10-01 15:10)
...
## Run (runner · 2026-10-01 15:10)
- mode: run
- outcome: review
- commits: ...
```

Everything after the request is appended; nothing is rewritten. The file
is the prompt the agent reads, the record git keeps, and something you can
fix with any editor. `tasks/logs/` holds the session logs (put it in
`.gitignore`), `tasks/archive/` the tasks you archived from the board.
The board commits a task file whenever it changes it (just that file, with
`git commit -- <file>`), unless the directory is ignored or the project is
not a git repository.

## The flow

```
 new task ──▶ triage ──▶ review (plan) ──approve──▶ todo ──▶ in-progress ──▶ review (work) ──approve──▶ done
                 ▲            │                       ▲             │
                 └── answer ──┘ (questions)           └── answer ───┤ need-attention (questions, failed verify, crash)
                                                      └── feedback ─┘ (reject finished work)
```

- **Triage** (default for every new task, switchable per project): the
  agent reads the code without changing it and appends a *Plan* - steps,
  files, a `verify:` command, risks, size - and *Questions* if a decision
  is needed. The task lands in *Čeká na mě* for approval. Answering the
  questions runs the triage again with the answers in hand; approving puts
  the task at the end of the queue.
- **Queue** (*Fronta*): ordered by drag and drop. *Implementovat teď*
  starts the first run immediately; with *Fronta běží sama* on, the board
  starts the next queued task whenever nothing is being implemented. One
  implementation at a time per project, since they share the working tree.
- **Implementation**: the agent follows the plan and the latest answers or
  feedback, commits only its own files with a `task <id>:` prefix and
  appends a *Result*. The runner then executes `verify`; success means
  *review*, anything else *need-attention* with the reason in the file.
- **Review**: *Hotovo* closes the task, *Vrátit s připomínkami* appends
  your feedback and puts it at the front of the queue.

Dropping a card on *Triage* re-plans it, on *Backlog* or *Fronta* moves
it, on *Hotovo* closes it. The *Běží* and *Čeká na mě* columns do not take
drops: starting a run is a button, and waiting is something the agent
decides.

## Watching a run

Every run is a tmux window `task-<id>` in the project's session (the one
`work <project>` attaches to), so *Sledovat v terminálu* opens exactly that
pane and the run survives a restart of `fractal-tasks`. The window shows
one line per tool call and message; the same text goes to `tasks/logs/`
and into the drawer's log panel. When the run ends the window stays for
three minutes, then closes. A run whose window disappeared without
writing an outcome (reboot, kill) is parked in *need-attention* by the
board's watcher after two minutes.

The runner is plain `claude -p` with `--dangerously-skip-permissions`,
started in the project root so the project's `CLAUDE.md` applies, with
`ANTHROPIC_API_KEY` removed so subscription auth is used like in the
interactive windows. Triage sessions get 25 minutes and 80 turns,
implementation 120 minutes and 250 turns; `timeout_minutes` in the
frontmatter overrides the time.

## From the phone

With the Telegram bot: `/task <project> <text>` creates a task (triage
starts at once), `/tasks [project]` lists what waits for you, and a plain
message that starts with `task` or `úkol` does the same as `/task` - no
slash needed when dictating. `fractal-task-run` messages every allowed
user when a run ends with a link straight to the task.

## By hand

```
fractal-task-run <project> <id> triage    # plan only
fractal-task-run <project> <id> run       # implement
curl -s 127.0.0.1:7693/<project>/tasks | jq '.tasks[] | {id, status, title}'
```

The board's settings (auto queue, auto triage) are in
`$FRACTAL_STATE_DIR/tasks-state.json`; everything else is in the files.
