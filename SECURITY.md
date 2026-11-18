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

### Vulnerabilities in upstream projects

If the problem is in Reticulum (RNS) or LXMF rather than in MeshBeacon, please note that the
upstream GitHub repositories are public mirrors that do not accept issues. We will still
coordinate where we can, and will protect MeshBeacon users (for example by pinning or advising on
configuration) while an upstream fix is pending.

## Our security commitments

These are design requirements. See the [threat model](docs/security/threat-model.md) for detail.

- No privileged containers, no Docker socket access, no host networking by default.
- No Home Assistant or Supervisor API permissions beyond what a feature strictly needs.
- No public-facing ports enabled by default.
- No automatic publication of gateway addresses or locations; no automatic connection to
  discovered interfaces.
- No custom cryptography or networking protocol implementations — all protocol work is done by
  the unmodified Reticulum reference implementation.
- Private keys stored with restrictive permissions and never written to logs.
- Pinned dependencies (by hash), pinned base images (by digest), signed images, SBOMs.
- Automated vulnerability and secret scanning in CI.
- Explicit opt-in for every sensitive feature.
- No telemetry, analytics or crash reporting.

## Handling your Reticulum identity

Your node's identity is a private key stored in the app's `/data` directory. Anyone who obtains it
can impersonate your node. Home Assistant backups include it: **use encrypted backups**, and
never share backups or diagnostics files that have not been redacted.
