# Shared configuration for the bash scripts. Source it:
#
#   . "$(dirname "$(readlink -f "$0")")/../lib/fractal-env.sh"
#
# Defaults first, then ~/.config/fractal/fractal.env on top, then whatever is
# already in the environment wins. Same keys and defaults as fractal_config.py.

FRACTAL_ENV="${FRACTAL_ENV:-$HOME/.config/fractal/fractal.env}"

_fractal_default() { [ -n "${!1:-}" ] || printf -v "$1" '%s' "$2"; }

if [ -f "$FRACTAL_ENV" ]; then
    # the file is plain KEY=VALUE; ignore anything that is not a known key
    while IFS= read -r _l || [ -n "$_l" ]; do
        case "$_l" in ''|'#'*) continue ;; esac
        _k="${_l%%=*}"; _k="${_k#export }"; _k="${_k// /}"
        _v="${_l#*=}"
        case "$_k" in FRACTAL_*) [ -n "${!_k:-}" ] || eval "$_k=$_v" ;; esac
    done < "$FRACTAL_ENV"
    unset _l _k _v
fi

_fractal_default FRACTAL_WWW          /var/www/fractal
_fractal_default FRACTAL_URL          "http://$(hostname)/"
_fractal_default FRACTAL_ALLOW        "100.64.0.0/10 fd7a:115c:a1e0::/48"
_fractal_default FRACTAL_UPLOADS      "$HOME/uploads"
_fractal_default FRACTAL_STATE_DIR    "$HOME/.config/fractal"
_fractal_default FRACTAL_CTL_PORT     7691
_fractal_default FRACTAL_FILES_PORT   7692
_fractal_default FRACTAL_UPLOAD_PORT  7690
_fractal_default FRACTAL_TERM_PORT    7685
_fractal_default FRACTAL_TASKS_PORT   7693
_fractal_default FRACTAL_AGENT        claude
_fractal_default FRACTAL_AGENT_FLAGS  "--dangerously-skip-permissions"
_fractal_default FRACTAL_AGENT_WINDOW claude
_fractal_default FRACTAL_WIFI_IFACE   ""
_fractal_default FRACTAL_TELEGRAM_USERS      ""
_fractal_default FRACTAL_TELEGRAM_TOKEN_FILE "$HOME/.config/fractal/telegram-token"
_fractal_default FRACTAL_TELEGRAM_WATCH      60

FRACTAL_URL="${FRACTAL_URL%/}/"
FRACTAL_REGISTRY="$FRACTAL_WWW/projects.json"

# Command for the agent window: resume in this directory, else start fresh,
# and fall back to a shell so the tmux window does not vanish on exit.
fractal_agent_cmd() {
    local extra="${1:-}" f="$FRACTAL_AGENT_FLAGS"
    [ -n "$extra" ] && extra=" $extra"
    if [ "$FRACTAL_AGENT" = claude ]; then
        printf '%s' "claude -c $f$extra || claude $f$extra; exec bash"
    else
        printf '%s' "$FRACTAL_AGENT $f$extra; exec bash"
    fi
}

# Same, but always a new conversation - for the extra prompt windows (p1, p2...),
# which would otherwise resume the one the main agent window is in.
fractal_agent_new_cmd() {
    local extra="${1:-}"
    [ -n "$extra" ] && extra=" $extra"
    printf '%s' "$FRACTAL_AGENT $FRACTAL_AGENT_FLAGS$extra; exec bash"
}

export PATH="$HOME/.local/bin:$PATH"
