# Getting started

From a bare Linux box to a dashboard you can open on your phone, with one
project and a coding agent in it. Plan for about half an hour.

What you end up with: `http://<box>/` shows a card per project; the
Terminal button on a card opens the project's tmux session in the browser,
with Claude Code already running in the project directory. The same session
is there when you SSH in, on the laptop, the phone and the iPad.

## 1. The machine

Any always-on Linux box you own: an old desktop, a mini PC, a VM. Tested on
Debian 13; Ubuntu 24.04 works the same. It needs systemd (user services) and
a user account of your own - fractal runs everything as that user, never as
root.

Wire it with Ethernet if you can. A USB Wi-Fi adapter works, but if it drops
the box is unreachable until someone walks over to it - see
[operations.md](operations.md#a-box-on-wi-fi) for the watchdog that handles
that.

## 2. Tailscale

The tailnet is the security boundary (read [SECURITY.md](../SECURITY.md)
first). Install Tailscale on the box and on every device you will use:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Turn on **MagicDNS** in the Tailscale admin console, so the box is reachable
by its short name (`http://devbox/`) from every device on the tailnet.

Only put devices you fully control on that tailnet. There is no login in
fractal: whoever reaches `/term/` from the tailnet has a shell as you.

## 3. Packages

```bash
sudo apt install nginx tmux jq python3 gettext-base git curl
```

**ttyd** (the browser terminal): Debian 12+ and Ubuntu 23.04+ have it in apt
(`sudo apt install ttyd`). A newer build is a single static binary from the
[releases page](https://github.com/tsl0922/ttyd/releases):

```bash
sudo curl -fsSL -o /usr/local/bin/ttyd \
  https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64
sudo chmod +x /usr/local/bin/ttyd
```

Optional: `docker` (container list on the Machine card), `wireless-tools`
(`iwconfig`, the Wi-Fi tile), `usbutils` (`usbreset`, for the network
watchdog).

## 4. Claude Code

Install it as your user and log in once, in a normal SSH session:

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude            # follow the login, then /exit
```

Claude Code asks once per directory whether you trust it. The agent windows
fractal opens will stop at that question for a project you never opened
before - answer it in the browser terminal, it is remembered.

Any other agent CLI works too, see `FRACTAL_AGENT` in
[configuration.md](configuration.md).

## 5. Install fractal

```bash
git clone <repo url> ~/projects/fractal
cd ~/projects/fractal
./install.sh --nginx                 # asks for sudo only for /etc/nginx and /var/www
sudo loginctl enable-linger "$USER"  # user services and tmux keep running without a login
```

The first run creates `~/.config/fractal/fractal.env` from the example. Open
it and set at least:

```bash
FRACTAL_URL=http://devbox/       # what you type into the browser
```

then run `./install.sh` once more so the units and the 403 page pick it up.
The other keys are explained in the file itself and in
[configuration.md](configuration.md).

Optional but recommended: `cp extras/tmux.conf ~/.tmux.conf` (mouse scrolling,
long scrollback, windows numbered from 1).

## 6. Check it

```bash
systemctl --user list-units 'fractal-*'   # everything active, timers waiting
```

Open `http://devbox/` on your laptop. You should see the Machine card and an
empty project list. Open `http://devbox/term/?arg=home` - a shell in the
browser. From a device that is **not** on the tailnet the terminal must
answer 403; if it does not, stop and read the nginx section of
[operations.md](operations.md#troubleshooting).

## 7. The demo project

```bash
./install.sh --demo
```

A card "Demo: hello" appears. The switch starts and stops a static web
server on port 7777, the *Web* link opens it, *Terminal* drops you into the
tmux session `demo` with Claude Code in the first window. Play with it, then
remove it with `project-register remove demo`.

## 8. Your first own project

Follow [adding-a-project.md](adding-a-project.md). The short version:

```bash
cp examples/ctl-script.sh ~/.local/bin/shop && $EDITOR ~/.local/bin/shop
chmod +x ~/.local/bin/shop
project-register add shop --root ~/projects/shop --title "Shop" --group Work \
  --ctl "shop start" --link "Web:3000:/" \
  --service-start "shop start" --service-stop "shop stop" --probe 3000 --autostart
```

A project does not need services at all - `project-register add notes --root
~/projects/notes` gives a card with a terminal and an agent, nothing more.

If you use Claude Code, link the skill and let the agent do the wiring:

```bash
ln -s ~/projects/fractal/skill/fractal-project ~/.claude/skills/fractal-project
```

then say *"wire ~/projects/shop into the dashboard"*.

## 9. Phone and tablet

- Add `http://devbox/` to the home screen. The terminal works in Safari and
  Chrome. The on-screen keyboard has no arrows, Esc, Tab or Ctrl: switch on
  the terminal key bar on the dashboard (or with ⌨ in the corner of any
  terminal). It is remembered per device, together with the font size
  (A− / A+ at the end of the bar).
- The Telegram bot gives you start/stop, questions to the agent and task
  dictation without opening a browser: [configuration.md](configuration.md#the-telegram-bot).

Next: [daily-use.md](daily-use.md) for how the pieces are meant to be used,
[operations.md](operations.md) for updates, logs and what happens after a
reboot.
