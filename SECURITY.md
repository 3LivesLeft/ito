# Security policy

## Status

MeshBeacon is in **Phase 0 (research and design)**. There is no released software yet, so there
are no supported versions. This policy applies from the first release onwards, and to the
documentation and design in the meantime.

| Version | Supported |
|---|---|
| None released | — |

Once releases exist, only the latest minor version will receive security fixes until v1.0.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately using GitHub's **"Report a vulnerability"** button on the repository's
**Security** tab (GitHub private vulnerability reporting). Please include:

- what is affected (version, commit, or document);
- how to reproduce it;
- the impact you believe it has;
- whether you would like to be credited.

You should receive an acknowledgement within **7 days**. We aim to agree a fix and disclosure
timeline with you within **30 days**, and to publish an advisory when a fix is available. This is
a volunteer project with no commercial backing, so timelines are best-effort.

> **Maintainer action required:** private vulnerability reporting must be switched on in the
> repository settings (*Settings → Code security → Private vulnerability reporting → Enable*). If
> the **Report a vulnerability** button is not visible on the Security tab, it is not yet enabled;
> in that case, please open a public issue that says only "security contact requested", with no
> details, and the maintainer will arrange a private channel.

### Vulnerabilities in upstream projects

If the problem is in Reticulum (RNS) or LXMF rather than in MeshBeacon, please note that the
upstream GitHub repositories are public mirrors that do not accept issues. We will still
coordinate where we can, and will protect MeshBeacon users (for example by pinning or advising on
configuration) while an upstream fix is pending.

## Our security commitments

These are design requirements. See the [threat model](docs/security/threat-model.md) for detail.

- No privileged containers, no Docker socket access, no host networking.
- The service runs as a dedicated non-root user; root is used only for a short initialisation
  step.
- No Home Assistant or Supervisor API permissions beyond what a feature strictly needs (none in
  v0.1).
- No public-facing ports; no external connections unless you configure them.
- No automatic publication of gateway addresses or locations; no automatic connection to
  discovered interfaces.
- All user input validated against strict allow-lists before it reaches Reticulum's
  configuration.
- No custom cryptography or networking protocol implementations — all protocol work is done by
  the unmodified Reticulum reference implementation.
- Private keys stored with restrictive permissions, never written to logs, and never silently
  replaced.
- Self-imposed limits on memory, CPU priority, storage and log volume to protect Home Assistant.
- Pinned dependencies (by hash), pinned base images (by digest), signed images, SBOMs.
- Automated vulnerability and secret scanning in CI.
- Explicit opt-in for every sensitive feature.
- No telemetry, analytics or crash reporting.

The Home Assistant **security rating** shown for the app is a useful signal about its declared
permissions, but it is **not proof of security**.

## Handling your Reticulum identity

Your node's identity is a private key stored in the app's `/data` directory. Anyone who obtains it
can impersonate your node. Home Assistant backups include it: **use encrypted backups**, and
never share backups or diagnostics files that have not been redacted.
