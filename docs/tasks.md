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
  is needed. A plan is short (decisions, one-line steps, risks, size) and a
  new one replaces the previous one as a whole. The drawer shows what
  counts now: everything before the newest plan folds into one *Historie*,
  the runner's *Run* records and a failed verify that was dealt with fold
  too, and once there is a *Result* the plan folds behind it.
  The task lands in *Čeká na mě* for approval. Answering the
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
- **Failed verify**: the work is committed but the check did not pass.
  Fix the command in the drawer and *Ověřit znovu* runs only `verify`
  (`fractal-task-run <project> <id> verify`, no agent); *Přesto hotovo*
  closes the task anyway. The agent checks in triage that every part of
  the command exists and passes on the current tree, and may correct it
  with a `verify:` line at the end of its Result.

The drawer opens with a line saying where the task is and what is
expected from you next.

Dropping a card on *Triage* re-plans it, on *Backlog* or *Fronta* moves
it, on *Hotovo* closes it. The *Běží* and *Čeká na mě* columns do not take
drops: starting a run is a button, and waiting is something the agent
decides.

## Watching a run

Every run is a tmux window `task-<id>` in the project's session (the one
`work <project>` attaches to), so *Sledovat v terminálu* opens exactly that
pane and the run survives a restart of `fractal-tasks`. The window shows
each tool call with the head of its output (15 lines) and the agent's
messages; the same text goes to `tasks/logs/` and into the drawer's log
panel. The complete record is the conversation itself, see below. When the run ends the window stays for
three minutes, then closes. A run whose window disappeared without
writing an outcome (reboot, kill) is parked in *need-attention* by the
board's watcher after two minutes.

The runner is plain `claude -p` with `--dangerously-skip-permissions`,
started in the project root so the project's `CLAUDE.md` applies, with
`ANTHROPIC_API_KEY` removed so subscription auth is used like in the
interactive windows. Triage sessions get 25 minutes and 80 turns,
implementation 120 minutes and 250 turns; `timeout_minutes` in the
frontmatter overrides the time.

Notes can be added while the agent works (*＋ Připsat* in the drawer, or
`fractal-task <id> note`): they are appended to the task file as usual,
and the run's Claude Code hooks hand every new note to the agent
right away - after its next tool call (`PostToolUse`), or, when it is
about to finish, by blocking the stop once (`Stop`). The log marks each
delivery. The hook state is `~/.config/fractal/inbox/<project>-<id>.json`
for the length of the run.

## Deployed or not

Done is not deployed. For a task with commits of its own - the agent's,
prefixed `task <id>: `, outside `tasks/` - the board shows where they are:
*jen lokálně* (not pushed), *nenasazeno* (pushed, the production does
not have them yet) or *nasazeno*. The drawer lists the commits with their
state, the done column counts the undeployed tasks, and a done task's
banner says which of the two kinds of done it is.

Pushed means reachable from the branch's upstream. Deployed needs a
per-project command that prints the commit the production runs - a
machine-local board setting, since it usually names a host:

```
curl -X POST localhost/tasks/<project>/settings \
     -d '{"deploy_check": "...", "deploy_prepare": "...", "deploy_run": "..."}'
```

Anything `git rev-parse` resolves will do, so a ref such as
`origin/production` works too (the command may simply `echo` it). The
board runs it every five minutes and on *↻ zjistit* in the drawer, and
fetches once when the answer is a commit it does not know. Without it a
pushed task just says *pushnuto*. Commits are compared by patch, not by
hash, because a task deployed on its own arrives as a cherry-picked copy.

## Deploying one task

All tasks commit to the same branch, so pushing it would ship every
finished-but-unreviewed task along with the one meant. *🚀 Nasadit* on a
done task (or `fractal-task deploy`) runs `fractal-task-deploy` in a tmux
window `deploy-<id>` instead:

1. fetch the upstream and pick the task's own commits it does not have;
2. cherry-pick them onto the upstream in a throwaway worktree - a conflict
   stops here and names the undeployed task it builds on;
3. run `deploy_prepare` and the task's verify in that worktree, so the
   task has to pass without the other tasks' code (a verify that names
   the project's absolute path is pointed at the worktree);
4. push it (fast-forward only), run `deploy_run`, ask `deploy_check`;
5. realign the local branch: rebase it in another throwaway worktree and
   move the branch only when the tree comes out identical - the working
   tree, the index and uncommitted work are never touched; skipped while
   a task is being implemented;
6. append a *Deploy* record to the task and commit it.

When a task depends on another one, the drawer offers *Nasadit spolu s
…* (once that one is done too); `fractal-task deploy <other id>` does the
same. `--dry-run` stops before the push and shows whether a task applies
and passes on its own. The three settings, for example:

```
deploy_check    ssh prod git -C /srv/app rev-parse HEAD
deploy_prepare  ln -s "$FRACTAL_ROOT/node_modules" node_modules
deploy_run      ssh prod 'cd /srv/app && ./deploy.sh' && curl -fsS https://example.org/ >/dev/null
```

`deploy_prepare` runs in the worktree in the same shell as the verify, so
it can link dependencies from the main checkout (`$FRACTAL_ROOT`) and
export variables (a `PYTHONPATH` that puts the worktree's sources ahead
of an editable install). Follow-up steps a task's Result names -
migrations, backfills - stay with the task's Claude session.

## The task's own session

Every new task also gets an interactive Claude Code session: a tmux session
`<project>-p<n>`, the same kind the dashboard's *＋ Claude* makes, so it
shows on the project card and in the session list under the task's name
(`042 · Indicator page width`). It exists to talk the task through and,
when you want, to implement it there instead of in a headless run - from
the browser terminal or `work <project> p<n>`, whichever is at hand.

Claude in it gets the task as an appended system prompt and a fixed session
id. Closing the session loses nothing: *Claude úkolu* in the drawer (or
`fractal-task session`) starts it again with the same conversation. Old
tasks get one the same way, on first click. Archiving a task closes its
session. Which session belongs to which task is kept in
`tasks-state.json`, not in the committed file.

Runs are part of that conversation: the runner starts `claude -p` with
the task's session id (`--resume`, or `--session-id` the first time), so
triage, implementation and your own talk with the agent are one thread.
A conversation takes one writer at a time, so a run closes the
interactive window when it starts, and *Claude úkolu* is hidden while it
works (watch the run instead). Afterwards *Claude úkolu* brings the
conversation back with everything the run did - every command and its
full output, as if you had run it yourself - and you can ask the agent
why it did something, or carry on, with its whole context. The Run record
names the conversation (`- conversation: <id>`).

The file stays the one shared record: the agent in the session reads it
before answering, and changes the task only with `fractal-task`, which goes
through the board's service - it appends, commits the file, and the board
updates live:

```
fractal-task show                       # state and the whole file
fractal-task plan|questions|answers|feedback|result <<'EOF'
...
EOF
fractal-task approve | run | triage | move <status> | answer <text> | reject <text>
fractal-task claim                      # implementing here: in-progress, the queue waits
fractal-task finish                     # -> review
fractal-task release                    # given up -> backlog
```

Inside the session the task is the default (`$FRACTAL_TASK`); elsewhere
name it as `<project>/<id>`, or just `<id>` inside the project directory.
A claimed task is *in progress* like a run - one implementation at a time
still holds - and it is parked in *need-attention* when its session is
closed before `finish`.

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

The board's settings (auto queue, auto triage) and the task sessions are
in `$FRACTAL_STATE_DIR/tasks-state.json`; everything else is in the files.
