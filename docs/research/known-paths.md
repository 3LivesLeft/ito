# Why "Known paths" reads exactly 2,048

**Question (maintainer, 18 Nov 2026):** the first physical v0.2.0 reading showed **Known paths:
2,048** after seven minutes. Is that a Reticulum routing-table limit?

**Short answer:** it is not a hard limit. **[Verified]** (source reading, RNS 1.6.0, the pinned
version): 2,048 is Reticulum's **target for never-used path-table entries**. A flat 2,048 means the
connected network announces more destinations than that, and RNS is trimming the excess as
designed. Paths that are actually used are not trimmed by this rule, so the total can go above
2,048. Nothing is wrong, and nothing in MeshBeacon caps the number.

## What MeshBeacon reports

| Step | Source | Notes |
|---|---|---|
| Sensor "Known paths" | `sensor.py` `known_paths`, from the status field `network.paths` | Passed through unchanged; never capped |
| Core | `node.py` `NODE_COUNTERS`: RNS's `tpcount` becomes `paths` | Read from the public `RNS.Reticulum.get_interface_stats()` |
| RNS | `RNS/Reticulum.py` (1.6.0), `get_interface_stats()`: `tpcount` is the first value of `Transport.path_pool_counts()` | **[Verified]** |
| RNS | `RNS/Transport.py` (1.6.0), `path_pool_counts()`: the total number of path-table entries, and the number never used | **[Verified]** |

MeshBeacon's own bounds (≤ 10 peers, ≤ 8 rate samples, 256 KiB responses) do not touch this value.
The integration's parser accepts any non-negative integer (`client.py` `_int`).

## How RNS 1.6.0 trims the path table

Read from `RNS/Transport.py` at version 1.6.0 (constants near line 225–235; the culling step in
the periodic job near lines 1120–1160; `path_pool_counts()` near line 3565). The behaviour is
described here, not reproduced.

| Item | Value in 1.6.0 | Effect |
|---|---|---|
| `PATH_POOL_UNUSED_TARGET` | **2048** | When more than this many entries have **never been used**, the surplus is removed, starting with entries on fast interfaces with the earliest expiry |
| `pool_size_check_interval` | 5 minutes | The check runs at most every 5 minutes, so the count can briefly go above 2,048 between checks |
| `UNUSED_PATH_LINGER` | 1 h 45 min (transport nodes) | A never-used entry is also removed once it is this old |
| `UNUSED_PATH_LINGER_LEAF` | 12 minutes (non-transport nodes) | The same, for nodes without transport |
| `PATH_SLOW_LINGER_FACTOR` | ×10 on interfaces under 25 kbit/s | Slow-link entries are kept longer and trimmed last |
| `PATH_TIMEOUT` | 7 days | Entries that are used expire only after a week without liveness |

**What a reading means:**
- A total of exactly 2,048 (or just above) means the pool of never-used entries is full and RNS is
  holding it at its target. On a transport node linked to a well-connected peer, this is reached
  within minutes, which fits the reading after seven minutes.
- When MeshBeacon itself starts using paths (for example LXMF in v0.3) or relays traffic for
  others, those used entries are added on top, so the total can exceed 2,048.
- A trimmed destination is not lost. RNS finds it again with a path request when it is needed.

## Consequences

| | |
|---|---|
| Memory | **[Assumption]** A full pool is in the order of a megabyte of Python objects (not measured). The 78 MiB reading (seven minutes) is well inside the 128 MB budget (RG-1). Watch it during the longer physical run (hardware step E1) |
| User interface | The panel shows a short note under "Known paths" when the count reaches 2,048: "Normal on a busy network: Reticulum trims paths it has never used to about 2,048." (`model.js` `pathsNote`) |
| Monitoring | No change to the status schema in v0.2. **[Recommendation]** for v0.3: also report RNS's `unupcount` (never-used entries) as an allow-listed counter, so "used paths" can be shown separately. This is a schema-1 addition, and it needs the contract test updated |
| Pin canary | `tests/unit/test_rns_path_pool.py` fails if a future RNS pin changes `Transport.PATH_POOL_UNUSED_TARGET`, so this document and the panel note are reviewed with the upgrade |

## Still open

| ID | Question | How to settle |
|---|---|---|
| KP-1 | **[Open]** Confirm on the Pi that the count stays near 2,048 over hours and goes above it only briefly | Record "Known paths" at hardware steps E1 and E3 (read-only; no change to the installation) |
| KP-2 | **[Open]** Confirm that the 2,048 entries are mostly never-used | Needs `unupcount` (the v0.3 recommendation) or RNS's own `rnpath` tool. Not run on the Pi without approval |
