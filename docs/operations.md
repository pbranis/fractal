# Operations

Keeping a fractal box running: updates, logs, state, reboots, and what to
check when something does not work.

## Updating

```bash
cd ~/projects/fractal
git pull
./install.sh             # scripts, dashboard, units; restarts the helpers
./install.sh --nginx     # only when nginx/ changed (it says so in the commit)
```

`install.sh` is idempotent and never touches tmux sessions or project units,
so running agents and services keep running through an update. Scripts are
symlinks into the repo, so a `git pull` changes them immediately; the
dashboard files are copies and need the `install.sh` run.

Working on fractal itself: edit in the repo, then `./install.sh --www-only`
after touching `www/`, plain `./install.sh` after touching `bin/` daemons
(`fractal-ctl`, `fractal-tasks`, `fractal-files`, `fractal-upload`,
`fractal-telegram` are long-running and need the restart it does).

## What runs

```bash
systemctl --user list-units 'fractal-*' --all
systemctl --user list-timers 'fractal-*'
tmux ls
```

| Unit | Kind | Job |
|---|---|---|
| `fractal-ctl` | daemon | `/ctl/`: start/stop, agent send/ask, terminals, sessions |
| `fractal-files`, `fractal-upload` | daemons | `/files/`, `/upload/` |
| `fractal-tasks` | daemon | `/tasks/`, the task board |
| `fractal-term` | daemon | ttyd behind `/term/` |
| `fractal-telegram` | daemon | the bot (only with a token) |
| `fractal-status.timer` | 20 s | `status.json` for the Machine card |
| `fractal-claude-usage.timer`, `fractal-codex-usage.timer` | 5 min | usage meters (only when the CLI exists) |
| `fractal-resume-save.timer` | 1 min | snapshot of the open agent conversations |
| `fractal-autostart` | oneshot at boot | starts the projects that were on |
| `fractal-resume` | oneshot at boot | resumes the agent conversations |
| `<project>.service` | oneshot per project | `<ctl> start` / `stop`, started by autostart |

## Logs

```bash
journalctl --user -u fractal-ctl -f                 # any fractal unit
journalctl --user -u fractal-autostart -u fractal-resume -b   # what came back after this boot
journalctl --user -u shop -b                        # a project's start/stop
shop logs                                           # a service's output, if the ctl script has `logs`
```

A service's own output lives in its tmux window; `tmux capture-pane -p -t
=shop:web` prints it without attaching.

## State worth backing up

Everything instance-specific is outside the repo:

| Path | What |
|---|---|
| `~/.config/fractal/fractal.env` | configuration |
| `$FRACTAL_WWW/projects.json` | the registry - every project, link, command |
| `~/.config/fractal/autostart.json` | which projects come back after a reboot |
| `~/.config/fractal/resume.json` | which agent conversations come back |
| `~/.config/fractal/telegram-*` | bot token (0600), chat state, help text |
| `~/.local/bin/<project>` | the control scripts |
| `<project>/tasks/` | task files (in the project's own repo) |

The agent conversations themselves are Claude Code's, in `~/.claude/`.

## Reboots

After a reboot - planned or not - the box comes back on its own, provided
lingering is on (`loginctl show-user $USER | grep Linger` says `yes`):

1. user services start without anybody logging in;
2. `fractal-autostart boot` starts the project units that were switched on
   (`fractal-autostart show` compares saved and actual state);
3. `fractal-resume restore` waits for those sessions, then resumes every
   agent conversation from the last snapshot (`fractal-resume show`).

To find out why a box rebooted:

```bash
last -x reboot shutdown | head        # "shutdown" right before "reboot" = an orderly reboot
journalctl --list-boots | tail -5
sudo journalctl -b -1 -n 80 --no-pager   # end of the previous boot
```

An orderly shutdown in the log means something asked for it (a watchdog,
unattended-upgrades, a person). A log that just stops means a hard freeze or
a power cut - look at memory first (`sar -r -S` with sysstat, `earlyoom` to
keep the box responsive under memory pressure), then at hardware.

## A box on Wi-Fi

A headless box on a single Wi-Fi adapter is unreachable - over the LAN and
over Tailscale - when the adapter drops, and USB adapters do that more often
than they should. `extras/net-watchdog` checks the connection every two
minutes as root and escalates: ifdown/ifup at 6 minutes, a driver and USB
reset (or a restart of wpa_supplicant and networking) at 12, a reboot at 20.
It also restarts `tailscaled` when the LAN works but Tailscale does not.

```bash
cd ~/projects/fractal/extras/net-watchdog
sudo install -m 755 net-watchdog /usr/local/sbin/net-watchdog
sudo install -m 644 net-watchdog.default /etc/default/net-watchdog   # then edit it
sudo install -m 644 net-watchdog.service net-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now net-watchdog.timer
```

With nothing configured it watches the interface of the default route. For a
USB adapter whose firmware hangs (the in-kernel rtw88 drivers are known for
it: `failed to get tx report from firmware` in `dmesg`), set `DRIVER`,
`USB_ID` and `FW_HANG_PATTERN` - a driver and USB reset uploads the firmware
again and brings the adapter back without a reboot. The defaults file has a
worked example.

Its log is `/var/log/net-watchdog.log`, one line per event; the Machine card
shows the current failure count. If the reboot step keeps firing, the real
fix is a cable or a different adapter.

## Troubleshooting

| Symptom | Check |
|---|---|
| Dashboard loads, terminal is a blank page or 502 | `systemctl --user status fractal-term`; is `ttyd` installed (`which ttyd`)? |
| Terminal answers 403 from your laptop | the laptop is not on the tailnet, or `FRACTAL_ALLOW` does not cover it; after changing it run `./install.sh --nginx` |
| Terminal answers 200 from outside the tailnet | stop - the nginx site must `include snippets/fractal-core.conf;` (which limits every sensitive location) and nothing else may serve those paths; `sudo nginx -T \| grep -n fractal` |
| Card shows a service down although it runs | `probe` must be the port the application itself listens on, and it must answer on 127.0.0.1 |
| Link from another device does not open, works on the box | the dev server binds 127.0.0.1 or rejects the `Host` header - see [adding-a-project.md](adding-a-project.md) |
| Switch flips back after a few seconds | the start command failed: `journalctl --user -u <project> -b`, or `work <project>` and look at the window |
| Agent window stops at "Do you trust this folder?" | first start of Claude Code in that directory; answer it once in the terminal |
| Conversations did not come back after a reboot | `journalctl --user -u fractal-resume -b`; `fractal-resume show`; lingering on? |
| Everything is gone after a reboot | lingering is off: `sudo loginctl enable-linger $USER` |
| Usage meters empty | `journalctl --user -u fractal-claude-usage`; the CLI must be logged in |
