# CloakBrowser macOS image

This public repository builds the headed CloakBrowser CDP renderer used by the
CRW Stack in cjangrist/infra. It tracks upstream CloakHQ/CloakBrowser main while
applying small source patches before building; do not edit installed containers.

## Contents and relationships

- `Dockerfile` and `docker-bake.hcl` layer runtime defaults over an exact upstream
  source revision and publish the rolling image plus upstream-revision tag.
- `patches/` contains ordered source patches. They preserve the profile and
  Widevine setup, and reject obsolete CDP WebSocket upgrades before acknowledging
  clients so client discovery/retry can recover after a browser restart.
- `bin/` contains the environment-driven launcher and macOS font-cache fetcher.
- `config/` holds secret-free font configuration and integrity checksums.
- `tests/` covers launcher behavior, fingerprint/profile state, real-loopback CDP
  recovery, and real Chromium crash/reconnect fault injection.
- `.github/workflows/refresh-image.yml` checks upstream hourly, runs source and
  runtime gates, then publishes. This is a public repository, so hosted CI is
  appropriate. Never publish a failed runtime candidate.

## Safety and invariants

- Keys, license values, populated dotenv files, browser profiles, and captured
  user pages must never enter this repository or CI artifacts.
- Production credentials come only from CRW's Infisical project in infra. Pro
  browser binaries and paid license entitlement are separate checks.
- Browser profiles survive crashes and container recreation. Only stale lock
  files are moved aside; never delete the persistent profile to heal a failure.
- Do not acknowledge a client CDP handshake until the exact upstream endpoint
  has connected. A stale browser ID must fail before upgrade, not appear healthy
  and then close. Never replay ambiguous client CDP commands after a crash.
- Process-generation locks remain canonical while callers wait. Cancelled
  launches reap their browser; disconnected proxies retire both pump tasks.

## Validation and deployment

Apply all patches in filename order to a fresh exact upstream checkout. Install
its serve/dev extras, then run upstream `tests/test_cloakserve.py` together with
`tests/test_cdp_recovery.py` using `UPSTREAM_CONTEXT` for that checkout. Run
`tests/test_launcher.sh`, build the candidate with Bake, and execute the runtime
profile/fingerprint smoke and `tests/runtime_recovery.py` inside isolated
containers with native init and core dumps disabled.

A push to this repository runs image CI. Production adoption remains GitOps-only
through cjangrist/infra and Komodo's CRW Stack. Verify published image/source
provenance, paid-license hash parity, renderer readiness, browser crash and
container-restart recovery, and real Jasa first-tier fetches before handoff.
