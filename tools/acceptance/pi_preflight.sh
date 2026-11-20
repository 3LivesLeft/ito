#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# M4 Raspberry Pi acceptance, step A (docs/testing/m4-pi-acceptance.md): READ-ONLY pre-flight.
#
#   sh pi_preflight.sh            (in the Advanced SSH & Web Terminal app, protection mode ON)
#
# Prints the facts the procedure needs and nothing else: architecture, CPUs, RAM and swap, free
# storage, Home Assistant / OS / Supervisor versions and health, the installed apps' slugs, states
# and versions, the live MeshBeacon app's state (never its options: they hold peer addresses), and
# whether the test slugs are free. It changes nothing: it only reads files under /proc and calls
# `ha ... info`. It never prints hostnames, IP or MAC addresses, URLs or app options. Read the
# output before sharing it all the same.
set -u

# Home Assistant renamed add-ons to apps; the CLI accepts one of these.
if ha apps --help >/dev/null 2>&1; then APPS=apps; else APPS=addons; fi

# Print only the named top-level keys of `ha <...> info` (YAML "key: value" lines).
pick() {
    keys="$1"; shift
    "$@" 2>/dev/null | awk -v keys="$keys" '
        BEGIN { n = split(keys, k, " "); for (i = 1; i <= n; i++) want[k[i]] = 1 }
        /^[a-z_]+: / { key = substr($1, 1, length($1) - 1); if (key in want) print "  " $0 }'
}

echo "== Hardware"
echo "  machine: $(uname -m)"
echo "  cpus: $(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo)"
awk '/^(MemTotal|MemAvailable|SwapTotal|SwapFree):/ { printf "  %s %.0f MiB\n", $1, $2 / 1024 }' /proc/meminfo
model="$( (tr -d '\0' < /proc/device-tree/model) 2>/dev/null || true)"
[ -n "$model" ] && echo "  model: $model"

echo "== Storage (the Home Assistant data disk)"
df -Pm /share 2>/dev/null | awk 'NR == 2 { printf "  total %d MiB, used %d MiB, free %d MiB\n", $2, $3, $4 }'

echo "== Versions and health"
echo " core:";       pick "version version_latest arch machine" ha core info
echo " os:";         pick "version version_latest board" ha os info
echo " supervisor:"; pick "version version_latest healthy supported channel" ha supervisor info
echo " host:";       pick "operating_system kernel disk_free disk_total disk_used" ha host info

echo "== Installed apps (slug, state, version)"
ha "$APPS" 2>/dev/null | awk '
    /^- / || /^  - / { if (slug != "") print "  " slug " " state " " version; slug = state = version = "" }
    { sub(/^[ -]+/, "") }
    /^slug: /    { slug = $2 }
    /^state: /   { state = $2 }
    /^version: / { version = $2 }
    END { if (slug != "") print "  " slug " " state " " version }'

echo "== Live MeshBeacon app (local_meshbeacon): state only, never options"
pick "state version version_latest boot watchdog apparmor stage" ha "$APPS" info local_meshbeacon

echo "== Local apps folder"
for d in /addons /local_apps; do
    [ -d "$d" ] || continue
    names=""
    for f in "$d"/*; do [ -e "$f" ] && names="$names ${f##*/}"; done
    echo "  $d:${names:- (empty)}"
done
for slug in meshbeacon_v02 meshbeacon_m4p meshbeacon_m4d; do
    if ha "$APPS" info "local_$slug" >/dev/null 2>&1; then
        echo "  local_$slug: ALREADY INSTALLED (stop here and report)"
    else
        echo "  local_$slug: free"
    fi
done

echo "== Tools in this terminal"
for t in python3 pip3 jq; do
    if command -v "$t" >/dev/null 2>&1; then echo "  $t: yes"; else echo "  $t: no"; fi
done
if docker ps >/dev/null 2>&1; then
    echo "  docker: REACHABLE (protection mode is off; the procedure expects it on)"
else
    echo "  docker: not reachable (protection mode on, as expected)"
fi
echo "== Done. Nothing was changed."
