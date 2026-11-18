# Changelog

## 0.1.1 — unreleased (local prototype)

- **Fix:** the app failed immediately on start on Home Assistant OS
  (`/bin/sh: can't open '/init': Permission denied`). The AppArmor profile allowed s6-overlay's
  start-up scripts to be executed but not read, which a shell script needs. The profile has been
  rewritten and is now tested under real AppArmor enforcement in CI.
- **Update with "Update", not "Rebuild":** Home Assistant loads an app's AppArmor profile only
  when the app is installed or updated to a new version. This version number change makes Home
  Assistant offer an update, which loads the corrected profile.
- Identity replacement is now crash-safe as a whole; slow start-up no longer risks a watchdog
  restart.

## 0.1.0 — unreleased (local prototype)

First local prototype of the v0.1.0 foundation. Not published; build and install it as a local
app (see DOCS.md). Experimental — do not depend on it yet.

- Runs the unmodified Reticulum reference implementation (RNS 1.6.0) as a supervised,
  non-root process.
- Manually configured outbound TCP peers; optional transport mode (off by default).
- Crash-safe, persistent node identity with verified backup and no silent replacement.
- Plain-language status messages, bounded recovery and resource guards.
