#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# M4 Raspberry Pi acceptance, step C (docs/testing/m4-pi-acceptance.md): one measurement run.
#
#   sh pi_measure.sh <v02|m4p|m4d> <run number> [settle minutes, default 10] [sample minutes, default 30]
#
# Starts ONE test app (local_meshbeacon_v02, _m4p or _m4d, and never anything else), lets it
# settle, samples the Supervisor's figures for it every 30 s, saves its log, and stops it. It also
# samples the live app's state and memory (read-only) to show it was not disturbed. Results go to
# /share/meshbeacon-m4/ (reach it with the Samba share's "share" folder). Only numbers and the
# test app's own log are written; the test apps have no peers, so their logs hold no addresses.
set -eu

case "${1:-}" in
    v02|m4p|m4d) ;;
    *) echo "usage: sh pi_measure.sh <v02|m4p|m4d> <run number> [settle min] [sample min]" >&2; exit 2 ;;
esac
case "${2:-}" in
    ''|*[!0-9]*) echo "the run number must be a whole number" >&2; exit 2 ;;
esac
LABEL="$1"; RUN="$2"; SETTLE="${3:-10}"; SAMPLE="${4:-30}"
TEST="local_meshbeacon_$LABEL"
LIVE="local_meshbeacon"
OUT="${MESHBEACON_M4_OUT:-/share/meshbeacon-m4}"
if ha apps --help >/dev/null 2>&1; then APPS=apps; else APPS=addons; fi

field() {  # field <key> <command...>: one top-level value of `ha ... info|stats`
    key="$1"; shift
    "$@" 2>/dev/null | awk -v k="$key:" '$1 == k { print $2; exit }'
}

mkdir -p "$OUT"
csv="$OUT/$LABEL-run$RUN.csv"
log="$OUT/$LABEL-run$RUN.log"
[ -e "$csv" ] && { echo "$csv exists: choose another run number" >&2; exit 2; }

# Only the three test apps; and only one of them running at a time.
for other in v02 m4p m4d; do
    [ "$(field state ha "$APPS" info "local_meshbeacon_$other")" = "started" ] && {
        echo "local_meshbeacon_$other is running: stop it first" >&2; exit 2; }
done
[ -n "$(field version ha "$APPS" info "$TEST")" ] || { echo "$TEST is not installed" >&2; exit 2; }
live_state="$(field state ha "$APPS" info "$LIVE")"
echo "live app $LIVE: ${live_state:-not installed} (it is only read, never changed)"

echo "# label=$LABEL run=$RUN cpus=$(nproc) settle_min=$SETTLE sample_min=$SAMPLE version=$(field version ha "$APPS" info "$TEST")" > "$csv"
echo "epoch,cpu_percent,memory_bytes,live_state,live_memory_bytes,host_mem_available_kib" >> "$csv"

echo "starting $TEST"
ha "$APPS" start "$TEST" >/dev/null
trap 'echo "stopping $TEST"; ha "$APPS" stop "$TEST" >/dev/null 2>&1 || true' EXIT INT TERM
echo "settling for $SETTLE minutes"
sleep $((SETTLE * 60))

end=$(( $(date +%s) + SAMPLE * 60 ))
n=0
while [ "$(date +%s)" -lt "$end" ]; do
    stats="$(ha "$APPS" stats "$TEST" 2>/dev/null || true)"
    cpu="$(printf '%s\n' "$stats" | awk '$1 == "cpu_percent:" { print $2 }')"
    mem="$(printf '%s\n' "$stats" | awk '$1 == "memory_usage:" { print $2 }')"
    lstate="$(field state ha "$APPS" info "$LIVE")"
    lmem="$(field memory_usage ha "$APPS" stats "$LIVE")"
    avail="$(awk '/^MemAvailable:/ { print $2 }' /proc/meminfo)"
    echo "$(date +%s),${cpu:-},${mem:-},${lstate:-},${lmem:-},${avail:-}" >> "$csv"
    n=$((n + 1))
    sleep 30
done
ha "$APPS" logs "$TEST" > "$log" 2>&1 || true
echo "$n samples in $csv; log in $log"
