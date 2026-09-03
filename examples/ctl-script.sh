#!/bin/bash
# <name> - control script template for a project on fractal.
#
# Copy to ~/.local/bin/<name>, fill in the three variables, and register:
#   project-register add <name> --root "$ROOT" --ctl "<name> start" \
#     --link "Web:$PORT:/" --service-start "<name> start" \
#     --service-stop "<name> stop" --probe $PORT --autostart
#
#   <name>                 status
#   <name> start|stop|restart
#   <name> attach          attach to the tmux session
#   <name> logs            last 40 lines of the service window
#   <name> cd              print the project directory
#
# Rules the dashboard relies on:
#   * services run in a tmux session named after the project, one window each
#   * `start` is idempotent - a running service is never started twice
#     (checked by port ownership, not by pid files)
#   * bind 0.0.0.0, otherwise the dashboard links will not reach the service
set -u
export PATH="$HOME/.local/bin:$PATH"

ROOT="$HOME/projects/myapp"          # project directory
SESSION=myapp                        # tmux session = registry name
PORT=5000                            # port the app itself listens on (= probe)
CMD="npm run dev -- --host 0.0.0.0 --port $PORT"

# Dev servers (Vite, Astro, Next) reject foreign Host headers. Pass the names
# you use to reach the box; how the framework consumes them differs
# (vite.server.allowedHosts, next allowedDevOrigins, ...).
export DEV_HOSTS="${DEV_HOSTS:-localhost,$(hostname),$(hostname).local}"

port_owner() { ss -ltnp "sport = :$PORT" 2>/dev/null | grep -oP "pid=\K[0-9]+" | head -1; }

start_app() {
    local owner; owner=$(port_owner)
    if [ -n "$owner" ]; then echo "  $SESSION already running (port $PORT, pid $owner)"; return; fi
    local run="cd \"$ROOT\"; $CMD; echo; echo \"--- $SESSION exited (rc \$?) ---\"; exec bash"
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux new-window -t "$SESSION" -n web "$run"
    else
        tmux new-session -d -s "$SESSION" -n web "$run"
    fi
    echo "  $SESSION starting in tmux window $SESSION:web (port $PORT)"
}

stop_app() {
    local owner pgid; owner=$(port_owner)
    if [ -z "$owner" ]; then echo "  $SESSION was not running"; else
        # kill the whole process group: dev servers fork workers
        pgid=$(ps -o pgid= -p "$owner" | tr -d " ")
        [ -n "$pgid" ] && kill -- "-$pgid" 2>/dev/null || kill "$owner" 2>/dev/null
        echo "  $SESSION stopped (pid $owner)"
    fi
    tmux kill-window -t "$SESSION:web" 2>/dev/null
}

status() {
    local owner; owner=$(port_owner)
    if [ -n "$owner" ]; then echo "  $SESSION: running (port $PORT, pid $owner)"; else echo "  $SESSION: stopped"; fi
    tmux has-session -t "$SESSION" 2>/dev/null && echo "  tmux session '$SESSION' exists (attach: $SESSION attach)"
}

case "${1:-status}" in
    start)   start_app ;;
    stop)    stop_app ;;
    restart) stop_app; sleep 1; start_app ;;
    status)  status ;;
    attach)  exec tmux attach -t "$SESSION" ;;
    logs)    tmux capture-pane -p -t "$SESSION:web" -S -40 ;;
    cd)      echo "$ROOT" ;;
    *)       echo "usage: $SESSION start|stop|restart|status|attach|logs|cd" >&2; exit 2 ;;
esac
