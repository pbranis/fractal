#!/bin/bash
# install.sh - install or upgrade fractal on this machine. Idempotent: run it
# again after every `git pull`.
#
#   ./install.sh              scripts, web files, systemd user units
#   ./install.sh --nginx      ...plus the nginx snippets and (if missing) the site
#   ./install.sh --www-only   just copy the dashboard files (after editing www/)
#   ./install.sh --demo       also register the demo project (examples/demo-project)
#
# What it does:
#   1. creates ~/.config/fractal/fractal.env from the example if missing
#   2. symlinks bin/* into ~/.local/bin
#   3. copies www/* into $FRACTAL_WWW (a copy, not a symlink: nginx cannot
#      follow a link into a drwx------ home directory)
#   4. renders systemd/user/* into ~/.config/systemd/user and (re)starts the
#      core services: fractal-ctl, fractal-files, fractal-upload, fractal-term,
#      fractal-status.timer, fractal-autostart; the usage timers only when the
#      corresponding CLI (claude / codex) is installed
#   5. with --nginx: renders the snippets into /etc/nginx/snippets/ and, when
#      no site named "fractal" exists yet, installs one and reloads nginx
#
# Nothing here touches tmux sessions or project units.
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SUDO="${SUDO:-sudo}"
DO_NGINX=0; WWW_ONLY=0; DEMO=0
for a in "$@"; do
    case "$a" in
        --nginx) DO_NGINX=1 ;;
        --www-only) WWW_ONLY=1 ;;
        --demo) DEMO=1 ;;
        -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
        *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
done

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }

# --- 1. configuration --------------------------------------------------------
ENV_FILE="${FRACTAL_ENV:-$HOME/.config/fractal/fractal.env}"
if [ ! -f "$ENV_FILE" ]; then
    mkdir -p "$(dirname "$ENV_FILE")"
    cp "$REPO/examples/fractal.env.example" "$ENV_FILE"
    say "config: created $ENV_FILE from the example - review it"
fi
. "$REPO/lib/fractal-env.sh"
FRACTAL_TTYD="$(command -v ttyd || echo /usr/local/bin/ttyd)"
export HOME USER FRACTAL_WWW FRACTAL_URL FRACTAL_ALLOW FRACTAL_UPLOADS FRACTAL_STATE_DIR \
       FRACTAL_CTL_PORT FRACTAL_FILES_PORT FRACTAL_UPLOAD_PORT FRACTAL_TERM_PORT FRACTAL_TTYD
VARS='${HOME} ${USER} ${FRACTAL_WWW} ${FRACTAL_URL} ${FRACTAL_UPLOADS} ${FRACTAL_STATE_DIR} ${FRACTAL_CTL_PORT} ${FRACTAL_FILES_PORT} ${FRACTAL_UPLOAD_PORT} ${FRACTAL_TERM_PORT} ${FRACTAL_TTYD} ${FRACTAL_ALLOW_LINES}'
render() { envsubst "$VARS" < "$1" > "$2"; }

# --- dependencies ------------------------------------------------------------
missing=""
for c in python3 jq tmux envsubst; do command -v "$c" >/dev/null || missing="$missing $c"; done
[ -n "$missing" ] && { echo "missing:$missing (apt install python3 jq tmux gettext-base)" >&2; exit 1; }
command -v ttyd >/dev/null || note "warning: ttyd not found - the browser terminal will not start (https://github.com/tsl0922/ttyd)"

# --- 3. web root -------------------------------------------------------------
say "www: $FRACTAL_WWW"
if [ ! -d "$FRACTAL_WWW" ]; then
    if mkdir -p "$FRACTAL_WWW" 2>/dev/null; then :; else
        $SUDO mkdir -p "$FRACTAL_WWW" && $SUDO chown "$USER:" "$FRACTAL_WWW"
    fi
fi
[ -w "$FRACTAL_WWW" ] || { echo "$FRACTAL_WWW is not writable by $USER (chown it)" >&2; exit 1; }
for f in "$REPO"/www/*; do
    install -m 644 "$f" "$FRACTAL_WWW/"
done
if [ ! -f "$FRACTAL_REGISTRY" ]; then
    install -m 664 "$REPO/examples/projects.example.json" "$FRACTAL_REGISTRY"
    jq '.projects = []' "$FRACTAL_REGISTRY" > "$FRACTAL_REGISTRY.tmp" && mv "$FRACTAL_REGISTRY.tmp" "$FRACTAL_REGISTRY"
    note "created an empty registry $FRACTAL_REGISTRY"
fi
note "dashboard files copied"
[ "$WWW_ONLY" = 1 ] && exit 0

# --- 2. scripts --------------------------------------------------------------
say "bin: ~/.local/bin"
mkdir -p "$HOME/.local/bin"
BACKUP="$FRACTAL_STATE_DIR/backup-$(date +%Y%m%d-%H%M%S)"
for f in "$REPO"/bin/*; do
    n="$(basename "$f")"; t="$HOME/.local/bin/$n"
    if [ -e "$t" ] && [ ! -L "$t" ]; then
        mkdir -p "$BACKUP"; mv "$t" "$BACKUP/"; note "backed up old $n to $BACKUP/"
    fi
    ln -sfn "$f" "$t"
done
note "symlinked $(ls "$REPO"/bin | wc -l) scripts"
mkdir -p "$FRACTAL_STATE_DIR" "$FRACTAL_UPLOADS"

# --- 4. systemd user units ---------------------------------------------------
say "systemd: user units"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
for f in "$REPO"/systemd/user/*; do
    render "$f" "$UNIT_DIR/$(basename "$f")"
done
systemctl --user daemon-reload
CORE="fractal-ctl.service fractal-files.service fractal-upload.service fractal-autostart.service fractal-status.timer"
command -v ttyd >/dev/null && CORE="$CORE fractal-term.service"
for u in $CORE; do
    systemctl --user enable "$u" >/dev/null 2>&1 || true
    # autostart is a oneshot that starts project units - only ever "start" it (no-op when active)
    if [ "$u" = fractal-autostart.service ]; then systemctl --user start "$u"; else systemctl --user restart "$u"; fi
    note "$u: $(systemctl --user is-active "$u")"
done
# optional meters: only when the CLI exists, otherwise the timer would just log errors
for tool in claude codex; do
    u="fractal-$tool-usage.timer"
    if command -v "$tool" >/dev/null; then
        systemctl --user enable --now "$u" >/dev/null 2>&1 && note "$u: enabled"
    else
        systemctl --user disable --now "$u" >/dev/null 2>&1 || true
    fi
done
# lingering keeps the user session (and the tmux server) alive without a login
if command -v loginctl >/dev/null && ! loginctl show-user "$USER" 2>/dev/null | grep -q 'Linger=yes'; then
    note "enable lingering so the services survive logout/reboot: sudo loginctl enable-linger $USER"
fi
systemctl --user start fractal-status.service 2>/dev/null || true

# --- 5. nginx ----------------------------------------------------------------
if [ "$DO_NGINX" = 1 ]; then
    say "nginx"
    if ! command -v nginx >/dev/null && [ ! -x /usr/sbin/nginx ]; then
        echo "nginx is not installed (apt install nginx)" >&2; exit 1
    fi
    TMP="$(mktemp -d)"
    FRACTAL_ALLOW_LINES="$(for c in $FRACTAL_ALLOW; do echo "allow $c;"; done)"
    export FRACTAL_ALLOW_LINES
    render "$REPO/nginx/snippets/fractal-core.conf.template" "$TMP/fractal-core.conf"
    render "$REPO/nginx/snippets/fractal-tailnet-only.conf.template" "$TMP/fractal-tailnet-only.conf"
    cp "$REPO/nginx/snippets/fractal-ttyd-proxy.conf" "$TMP/"
    $SUDO install -m 644 "$TMP"/fractal-*.conf /etc/nginx/snippets/
    note "snippets installed to /etc/nginx/snippets/"
    if [ ! -e /etc/nginx/sites-available/fractal ] && [ ! -e /etc/nginx/conf.d/fractal.conf ]; then
        render "$REPO/nginx/fractal.conf.template" "$TMP/fractal"
        $SUDO install -m 644 "$TMP/fractal" /etc/nginx/sites-available/fractal
        $SUDO ln -sfn /etc/nginx/sites-available/fractal /etc/nginx/sites-enabled/fractal
        [ -e /etc/nginx/sites-enabled/default ] && $SUDO rm /etc/nginx/sites-enabled/default \
            && note "removed the stock 'default' site (it also claimed :80)"
        note "site installed to /etc/nginx/sites-available/fractal"
    else
        note "a fractal site already exists - left untouched; make sure it has 'include snippets/fractal-core.conf;'"
    fi
    rm -rf "$TMP"
    if $SUDO nginx -t 2>&1 | tail -1; then $SUDO systemctl reload nginx && note "nginx reloaded"; fi
fi

# --- demo project ------------------------------------------------------------
if [ "$DEMO" = 1 ]; then
    say "demo project"
    ln -sfn "$REPO/examples/demo-project/demo-hello" "$HOME/.local/bin/demo-hello"
    if ! jq -e '.projects[] | select(.name=="demo")' "$FRACTAL_REGISTRY" >/dev/null 2>&1; then
        project-register add demo --root "$REPO/examples/demo-project" \
            --title "Demo: hello" --group "Demo" \
            --desc 'static page served by <code>python3 -m http.server</code> · control with <code>demo-hello start|stop</code>' \
            --ctl "demo-hello start" --link "Web:7777:/" \
            --service-start "demo-hello start" --service-stop "demo-hello stop" --probe 7777 \
            --autostart
    else
        note "demo already registered"
    fi
fi

say "done"
note "dashboard:  $FRACTAL_URL"
note "terminal:   ${FRACTAL_URL}term/?arg=home"
note "add a project: project-register add <name> --root <dir> ...  (see docs/adding-a-project.md)"
