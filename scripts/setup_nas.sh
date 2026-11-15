#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

config_args=()
case "${1:-}" in
    "") setup=true; launch=true ;;
    --setup-only) setup=true; launch=false ;;
    --start-only) setup=false; launch=true ;;
    --rotate-token) setup=true; launch=true; config_args=(--rotate-token) ;;
    *) echo "Usage: bash scripts/setup_nas.sh [--setup-only|--start-only|--rotate-token]" >&2; exit 2 ;;
esac

mkdir -p data
exec 9>data/nas.lock
if ! flock -n 9; then
    echo "Chromantis is already running or being configured in this checkout." >&2
    exit 1
fi

venv=.venv
if [[ -e "$venv" ]] && ! "$venv/bin/python" -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then
    venv=data/nas-venv
fi
python="$venv/bin/python"

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        uv="$(command -v uv)"
        return
    fi
    uv="$HOME/.local/bin/uv"
    if [[ ! -x "$uv" ]]; then
        (
            installer="$(mktemp)"
            trap 'rm -f -- "$installer"' EXIT
            curl -fsSL https://astral.sh/uv/install.sh -o "$installer"
            UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$installer"
        )
    fi
}

if "$setup"; then
    if ! "$python" -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then
        if python3 -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then
            python3 -m venv "$venv" || { find_uv; "$uv" venv --allow-existing --python "$(command -v python3)" "$venv"; }
        else
            find_uv
            "$uv" python install 3.12
            "$uv" venv --allow-existing --python 3.12 "$venv"
        fi
    fi
    if "$python" -m pip --version >/dev/null 2>&1; then
        "$python" -m pip install '.[telegram]'
    else
        find_uv
        "$uv" pip install --python "$python" '.[telegram]'
    fi
    "$python" scripts/configure_nas.py "${config_args[@]}"
    "$python" scripts/init_db.py
    "$python" scripts/reindex_source.py --incremental --progress-every 500
fi

if "$launch"; then
    if [[ ! -r .env || ! -x "$python" ]]; then
        echo "Run bash scripts/setup_nas.sh first." >&2
        exit 1
    fi
    api_pid= bot_pid=
    cleanup() {
        for pid in "$api_pid" "$bot_pid"; do
            if [[ -n "$pid" ]]; then
                kill "$pid" 2>/dev/null || true
                wait "$pid" 2>/dev/null || true
            fi
        done
    }
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    "$python" -u scripts/run_api.py &
    api_pid=$!
    "$python" -u scripts/run_bot.py &
    bot_pid=$!
    echo "Press Ctrl+C to stop the API and bot."
    if wait -n; then
        echo "A Chromantis process stopped."
    else
        exit "$?"
    fi
fi
