"""Shared configuration for the fractal scripts.

Every script reads the same file, ``~/.config/fractal/fractal.env`` (override
the location with ``$FRACTAL_ENV``). The file is plain ``KEY=VALUE`` lines so
the very same file can be sourced from bash (see ``fractal-env.sh``) and
rendered into systemd units and nginx snippets by ``install.sh``.

Everything has a default, so a missing file is not an error - the defaults
describe a stock installation (web root in /var/www/fractal, Tailscale CGNAT
ranges allowed, loopback ports in the 769x range).
"""
import os
import re
import socket

ENV_FILE = os.environ.get("FRACTAL_ENV") or os.path.expanduser("~/.config/fractal/fractal.env")

HOME = os.path.realpath(os.path.expanduser("~"))

DEFAULTS = {
    # web root served by nginx on :80; owned by the user, not by root
    "FRACTAL_WWW": "/var/www/fractal",
    # public base URL printed in hints (dashboard, terminal links)
    "FRACTAL_URL": f"http://{socket.gethostname()}/",
    # CIDRs allowed to reach shells and personal content (Tailscale by default)
    "FRACTAL_ALLOW": "100.64.0.0/10 fd7a:115c:a1e0::/48",
    # where the drop zone on the dashboard puts files
    "FRACTAL_UPLOADS": os.path.join(HOME, "uploads"),
    # autostart memory and other small state files
    "FRACTAL_STATE_DIR": os.path.join(HOME, ".config", "fractal"),
    # loopback ports of the helper services (nginx proxies them)
    "FRACTAL_CTL_PORT": "7691",
    "FRACTAL_FILES_PORT": "7692",
    "FRACTAL_UPLOAD_PORT": "7690",
    "FRACTAL_TERM_PORT": "7685",
    "FRACTAL_TASKS_PORT": "7693",
    # coding agent started in the "claude" tmux window of every project
    "FRACTAL_AGENT": "claude",
    "FRACTAL_AGENT_FLAGS": "--dangerously-skip-permissions",
    "FRACTAL_AGENT_WINDOW": "claude",
    # wireless interface for the Wi-Fi tile; empty = autodetect
    "FRACTAL_WIFI_IFACE": "",
    # Telegram bot (optional): allowed numeric user IDs, token file, watch interval
    "FRACTAL_TELEGRAM_USERS": "",
    "FRACTAL_TELEGRAM_TOKEN_FILE": os.path.join(HOME, ".config", "fractal", "telegram-token"),
    "FRACTAL_TELEGRAM_WATCH": "60",
}

_LINE = re.compile(r"""^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$""")


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return os.path.expandvars(os.path.expanduser(v))


def load() -> dict:
    """Defaults overlaid with the env file, overlaid with the process env."""
    cfg = dict(DEFAULTS)
    try:
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                m = _LINE.match(line)
                if m and m.group(1) in DEFAULTS:
                    cfg[m.group(1)] = _unquote(m.group(2))
    except OSError:
        pass
    for k in DEFAULTS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


CFG = load()

WWW = CFG["FRACTAL_WWW"]
REGISTRY = os.path.join(WWW, "projects.json")
STATE_DIR = CFG["FRACTAL_STATE_DIR"]
URL = CFG["FRACTAL_URL"].rstrip("/") + "/"


def port(name: str) -> int:
    return int(CFG[f"FRACTAL_{name}_PORT"])


def agent_cmd(extra: str = "") -> str:
    """Shell command for the agent window: resume the last session in this
    directory if there is one, start fresh otherwise, and drop to a shell when
    the agent exits so the tmux window survives."""
    a, f = CFG["FRACTAL_AGENT"], CFG["FRACTAL_AGENT_FLAGS"]
    extra = (" " + extra.strip()) if extra and extra.strip() else ""
    if a == "claude":
        return f"claude -c {f}{extra} || claude {f}{extra}; exec bash"
    return f"{a} {f}{extra}; exec bash"


def bin_path_env() -> dict:
    """systemd does not put ~/.local/bin on PATH; the scripts need it."""
    return dict(os.environ, PATH=os.path.join(HOME, ".local", "bin") + ":" + os.environ.get("PATH", ""))
