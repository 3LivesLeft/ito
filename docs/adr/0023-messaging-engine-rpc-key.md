# ADR 0023: The messaging engine authenticates to the shared instance's RPC

**Status:** Proposed (awaiting the maintainer's approval; needed before merge, CLAUDE.md rule 4).
**Amends:** roadmap IS-3a ("RNS RPC keeps its key, readable by Reticulum's user only") and the M4
finding that the engine needs no RPC key. **Related:** ADR 0008 (messaging process), ADR 0018
(isolation by user), ADR 0022 (one standard image), threat model T75 and T80.

## Context

The first 0.3.0 installation on a Raspberry Pi 4B (Home Assistant OS, aarch64) showed, with
messaging switched on, every ~10 s:

```text
[messaging] Could not load known destinations from shared instance database, continuing with an empty table. The contained exception was: unable to open database file
[reticulum] An error ocurred while handling RPC call from local client: digest received was wrong
[messaging] Shared instance RPC failed while setting destination data use: digest sent was rejected
```

The same lines appear on amd64 with the image built from `develop` (`74a5ad6`), so this is not
architecture-specific.

**How RNS 1.6.0 authenticates local RPC clients [Verified, `RNS/Reticulum.py` in the `rns-1.6.0`
wheel, `__init__` near line 375, `__apply_config` near line 580, `get_rpc_client` near line 1546].**
A shared instance opens an RPC listener (`multiprocessing.connection.Listener` on the abstract Unix
socket `\0rns/<instance_name>/rpc`) with `authkey=rpc_key`. Every client connects with
`multiprocessing.connection.Client(..., authkey=rpc_key)`, which runs an HMAC challenge in both
directions. `rpc_key` is read from the `[reticulum]` section of the configuration; when it is
absent, RNS derives it from the instance's *own* transport identity. RNS therefore assumes that the
clients of a shared instance use the same configuration folder (the same user's `~/.reticulum`).

**Root cause.** MeshBeacon gives the node a random `rpc_key` (prepare step) and runs the engine as
its own user with its own configuration folder (`/data/messaging/rns`) and, by design (IS-3a), no
key. The engine's RNS derived a key from the engine's own client identity; the node's HMAC check
failed ("digest received was wrong") and so did the engine's ("digest sent was rejected").

**Why it matters.** In RNS 1.6.0 a client's ordinary operation goes through this RPC, not just
control: each `Identity.recall` of a known destination reports its use to the node
(`_used_destination_data`; the core's 10 s health poll asks for the contacts' state, which recalls
them, hence the 10 s rhythm); LXMF retains its recipients' keys on the node
(`_retain_destination_data`), registers the destination types it needs
(`wants_destination_type`) and checks each inbound sender against the node's blackhole list
(`LXMF/LXMessage.py`, `is_blackholed`: on failure it logs a warning and treats the sender as *not*
blackholed); RNS drops link identifications it cannot check (`RNS/Link.py`). Sending and receiving
worked in M4's tests, but the node's culling, its blackhole list and link identification were not
applied to the engine, and the dashboard showed "Running".

**The database message is the same mismatch, not a permissions error [Verified,
`RNS/Identity.py` `load_known_destinations` and `get_ratchet`, `RNS/Storage.py`
`KnownDestinationsStore`].** A client reads the shared instance's destination table directly, as
SQLite opened read-only, from `<its own configuration folder>/storage/known_destinations.db`
(RNS's own comment there marks it for a move to RPC). For the engine that is
`/data/messaging/rns/storage/known_destinations.db`, which does not exist: nothing is refused, there
is simply nothing there. Sharing the node's table would mean giving the engine's user search
access to `/data/reticulum/storage` (which holds the transport identity) and read access to the
database and its WAL and shared-memory files, which RNS creates `0600` under Reticulum's user.
That is the access to Reticulum's private files this fix must not grant.

**Start order [Verified].** The core starts the engine only after Reticulum's first status line,
which `node.py` writes after `RNS.Reticulum()` has returned; RNS opens the RPC listener inside that
constructor. A running engine survives a restart of Reticulum (its client reconnects). The start
order was not a cause.

## Decision

1. **One shared key, created by root, readable by exactly two users.** While messaging is on, the
   root init step (`20-messaging`) writes a fresh 256-bit key to `/run/meshbeacon-rpc/rpc_key`
   (`root:mb-rpc 0640`, folder `0750`) at every container start. The new group `mb-rpc` (9112) holds
   Reticulum's user `mb-rns` and the engine's user `mb-lxmf`, never the core. The key is written by
   Python and never passed through the shell, printed or logged.
2. **Both sides use it.** The prepare step renders it as the node's `rpc_key` (only while
   messaging is on; otherwise a fresh random key, as before). It is reused on every restart of
   Reticulum within the container's life, so a running engine is never locked out. The engine
   renders the same key into its own client configuration (`/data/messaging/rns/config`, `0600`,
   its user only). Both are validated as exactly 64 lower-case hex digits; RNS would otherwise fall
   back silently.
3. **Narrow what the key allows.** While the instance is shared, the node's configuration sets
   `enable_interface_management = No`, so interfaces cannot be attached, detached or reloaded over
   RPC (RNS's own internal calls are not affected). Without a shared instance there is no RPC
   listener and the node's configuration is unchanged.
4. **Report it.** The engine checks every 30 s, with one read-only authenticated request
   (`Reticulum.is_blackholed` of its own identity, public API), whether the node accepts it, and
   reports `rpc` (`true`, `false`, or `null` before the first answer) in its `status` answer.
   The core shows messaging as **Running** only when the engine is connected *and* the node accepts
   its requests; while the node refuses them the dashboard shows a problem ("Messaging is running,
   but Reticulum refuses its requests …"). A missing key never stops Reticulum: the prepare step
   warns, and messaging reports the problem.
5. **The destination table is not shared.** The "Could not load known destinations from shared
   instance database" line stays, once per engine start. It is accurate (the engine starts with an
   empty table) and harmless: at start the engine asks the node for its contacts' paths, and the
   node's answers carry their keys (container test: the contact becomes reachable and messages flow
   both ways). Revisit when RNS moves this to RPC.

## Consequences

- **Gained:** the engine's RPC requests succeed; the node's culling, blackhole list and link
  identification apply to messaging; no repeating RPC errors; the dashboard reports a messaging
  problem instead of "Running".
- **Given:** the engine's user can now make the requests any RNS local client with the key can:
  read the node's path, rate, link and interface statistics; drop paths and announce queues;
  blackhole and unblackhole identities (RNS 1.6.0's `rpc_loop`). It cannot read Reticulum's files,
  the transport identity or the node's configuration, attach or detach interfaces, or reach the
  core, options or Supervisor. A compromised engine could degrade the node's routing until the next
  restart, or blackhole identities until they are unblackholed. **Residual risk, recorded as T80.**
- **Unchanged:** messaging off (the default) creates no key, folder or group membership in use; the
  separate process, user and identity (ADR 0008, 0009, 0018); the gateway carries on when messaging
  is off, refused or broken.
- **Tests:** `tests/container/test_messaging_container.py` (the real users, the real RNS 1.6.0
  shared instance and the LXMF engine): key permissions and authentication by user; the key
  survives a Reticulum restart; LXMF delivery both ways with a second local client and no RPC
  error; and the 0.3.0 failure reproduced (engine without the key: RNS's own errors, `rpc: false`,
  the dashboard's problem state, Reticulum unaffected).
