#!/usr/bin/env bash

set -u

wait_seconds="${BENZAITEN_DEV_TAB_WAIT_SECONDS:-120}"

if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to check development services." >&2
    exit 1
fi

if ! command -v xdg-open >/dev/null 2>&1; then
    echo "xdg-open is required to open development tabs." >&2
    exit 1
fi

open_when_ready() {
    local label="$1"
    local health_url="$2"
    local browser_url="$3"
    local deadline=$((SECONDS + wait_seconds))

    while ((SECONDS < deadline)); do
        if curl --noproxy '*' --fail --silent --show-error \
            --max-time 2 "$health_url" >/dev/null 2>&1; then
            echo "Opening ${label}: ${browser_url}"
            xdg-open "$browser_url" >/dev/null 2>&1 &
            return 0
        fi
        sleep 2
    done

    echo "Skipped ${label}; service did not become reachable: ${health_url}" >&2
    return 1
}

open_when_ready \
    "DeepSeek Harness" \
    "http://127.0.0.1:3080" \
    "http://127.0.0.1:3080" &
harness_wait_pid=$!

open_when_ready \
    "Gemma API documentation" \
    "http://127.0.0.1:8003/v1/models" \
    "http://127.0.0.1:8003/docs" &
gemma_wait_pid=$!

status=0
wait "$harness_wait_pid" || status=1
wait "$gemma_wait_pid" || status=1
exit "$status"
