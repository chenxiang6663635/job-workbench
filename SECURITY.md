# Security Policy

Job Workbench is a **local-first desktop app**: there is no server component, no
account, and no telemetry. The app runs on your machine, reads and writes files in
your workspace, and talks only to services **you** configure. That shape decides
what counts as a vulnerability here, so please read the threat model below before
reporting.

## Supported versions

Pre-1.0: fixes land on the latest release only. Please reproduce on the newest
build before reporting.

| Version | Supported |
|---|---|
| latest release (`v0.2.x`) | Yes |
| older tags | No |

## Reporting a vulnerability

**Do not open a public issue for a security problem** — that puts every user at
risk before a fix exists.

Use GitHub private reporting (enabled on this repository — verified 2026-09-13):
**Security → Advisories → Report a vulnerability**
https://github.com/chenxiang6663635/job-workbench/security/advisories/new

Please include, as far as you can:

- affected version or commit,
- what an attacker gains (data read? credential leak? code execution?),
- whether it needs local access to the machine or only network access,
- reproduction steps or a proof of concept.

If you cannot use GitHub private reporting, open a minimal public issue that says
only *"I have a security report and need a private channel"* — no details in the
issue body.

This is a single-maintainer, unpaid project: expect a best-effort reply in days
rather than hours, and honest *"not planned"* answers with the reasoning attached.

## Threat model — what is in scope

- **Data leaving the machine without your intent.** Anything that uploads
  workspace files, personal facts, resumes or tracker data to a third party.
- **Credential exposure.** The app stores your IMAP authorization code and your
  BYOK provider API key in **plaintext** in `<workspace>/config/imap.json` and
  `<workspace>/config/provider.json`. Leaking those values into logs, error
  messages, export packages or the network is a bug.
- **TLS downgrade on outbound connections.** Connections to your mail server and to
  fetched job pages verify certificates by default and refuse to continue when the
  certificate cannot be checked.
  **Known exception (tracked in #59):** the *provider connectivity test* opens an
  unverified connection (`ssl._create_unverified_context()`) because the local
  certificate store can crash the strict loader on affected Windows machines. That
  request carries your BYOK API key, so do not run it on a network you do not
  trust. Bringing it onto the same policy as IMAP is in scope for #59.
- **The local HTTP API.** It listens on `127.0.0.1` by default; anything that makes
  it reachable from the network or from another origin is a bug.
- **Export / backup packages** must never contain credential files. This is pinned
  by `tests/test_export_privacy.py`; a bypass is a bug.

## Known limitations (accepted, not vulnerabilities)

- **The local API has no authentication.** The boundary is the loopback bind
  (`127.0.0.1`). `--host` can widen it by hand, and anyone who can reach the port
  can then read and write your workspace. Do not expose it to a network you do not
  control; the API is not designed to be the thing that stops them.
- **Updates are unsigned.** The installer has no code signing, so the auto-update
  chain (GitHub Releases + `electron-updater`) uses this GitHub account and this
  repository's protection rules as its trust anchor. A compromised maintainer
  account could ship a malicious update — inherent to unsigned distribution, and
  accepted until code signing is adopted (recorded in CONTRIBUTING's "not doing"
  list).
- **Fetched job pages are text.** HTML from a job posting is fetched, size-capped,
  stripped to text and stored as plain text (`JD原文.md`). The backend never
  executes it, and the UI renders it through normal text interpolation
  (`<pre>{text}</pre>` in `JobDetailView`) — there is no HTML-injection path. A
  hostile page is therefore a content problem unless you can show script execution
  or a path escape.
- **Credentials are plaintext on disk** (see above). An attacker who already has
  your OS user account does not need an exploit.

## Explicitly out of scope (by design)

- Anyone who can read your OS user account can read the plaintext credential
  files. Use separate OS accounts and disk encryption; that is a property of
  local-first, not a vulnerability in the app.
- Job pages fetched from the internet are untrusted input by definition. Hostile
  HTML in a job posting is a content-handling problem, not a boundary we claim to
  provide.
- Dependency advisories with no reachable path in this app.
- The desktop installer is unsigned: SmartScreen warnings on first run are
  expected and documented, not a vulnerability.

## What the app already does

- Backend binds loopback only by default (`--host` defaults to `127.0.0.1`; do not
  change it), CORS restricted to the local dev origin.
- No telemetry, no analytics, no accounts, no uploads — the system endpoint
  reports `telemetry: false` and the Settings page says the same thing.
- Credentials are masked in API responses and never written into logs.
- Certificate verification is on by default on the IMAP path. Skipping it requires
  an explicit environment opt-in (`JOBWS_IMAP_TLS=insecure`); otherwise the failure
  is refused with an actionable message. The provider connectivity test is the
  documented exception above — never for the mail path.
- Auto-update is opt-in, asks twice, and only fetches from this repository's
  GitHub Releases.

## Disclosure

Once a fix ships, reporters are credited in the advisory unless you ask to stay
anonymous. Please give us a chance to release before publishing details.
