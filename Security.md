# Security Policy

## Supported Versions

Silicium is still under development. Security fixes are prioritized for the
`main` branch and, when possible, for the `dev` branch.

| Reference | Supported |
| --- | --- |
| `main` | Yes, for the currently deployed version |
| `dev` | Best effort, for development versions |
| Older branches, commits, or releases | Not guaranteed |

The `BackEnd`, `FrontEnd`, and `Network` submodules may have their own
security policies. A vulnerability affecting one of them should also be
reported to its upstream repository when appropriate.

## Reporting a Vulnerability

Do not create a public Issue for a vulnerability. Do not publish a secret,
private key, token, or exploit details.

Use GitHub's **Private vulnerability reporting** feature from the repository's
**Security** tab whenever it is available. If it is not available, contact the
project maintainers through a private channel and state that the message is a
security report.

When possible, include:

- a description and the potential impact;
- the affected components, files, or workflows;
- the minimum steps needed to reproduce the issue;
- a non-destructive proof of concept;
- the affected version, commit, or environment;
- a proposed fix, if you have one.

Sensitive data may be redacted. Never send working credentials: use dummy
values or revoke secrets before sharing reproduction material.

## Report Handling

The maintainers aim for the following time frames:

- acknowledgment within 7 calendar days;
- initial triage within 14 days;
- a fix, mitigation, or request for additional information as soon as the
  analysis is sufficiently advanced.

The disclosure schedule is agreed with the reporter. Public disclosure should
not happen before a reasonable fix or mitigation is available.

## Scope

Reports concerning the following areas are relevant:

- the API, frontend, distributed network, and workloads;
- GitHub Actions workflows, permissions, and secrets;
- deployment scripts, containers, and VPS configuration;
- project dependencies when they expose Silicium to risk.

Purely theoretical issues, reports about obsolete versions without demonstrated
impact, spam, social engineering, and denial-of-service tests against real
infrastructure are not authorized testing channels.
