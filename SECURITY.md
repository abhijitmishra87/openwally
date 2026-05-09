# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in OpenWally, please **do not open a public GitHub issue**. Public disclosure before a fix is available puts all users at risk.

Instead, report it privately via one of these channels:

- **GitHub private vulnerability reporting** (preferred): go to the [Security tab](../../security/advisories/new) of this repository and click "Report a vulnerability"
- **Email**: abhijitmishra87@gmail.com — include "OpenWally Security" in the subject line

### What to include

- A clear description of the vulnerability
- Steps to reproduce or a proof-of-concept
- The potential impact (what an attacker could achieve)
- Your suggested fix, if you have one (optional but appreciated)

### What to expect

- **Acknowledgement** within 48 hours
- **Status update** within 7 days — whether the issue is confirmed, needs more information, or is out of scope
- **Credit** in the release notes if you'd like it, once the fix ships

## Scope

OpenWally is a local CLI tool — it runs on your machine and calls the Anthropic API or a local Ollama instance. The primary attack surfaces are:

| Area | Notes |
|---|---|
| Generated project code | AI-generated code may contain security flaws — always review before deploying |
| API key handling | Keys are read from `.env` and passed to the Anthropic SDK — never logged or written to disk |
| `deps.txt` processing | Package names from AI output are passed to `uv` — review before running in sensitive environments |
| Eval harness | `inspect eval` runs the full pipeline in a temp directory — no network exposure beyond the Anthropic API |

## Out of scope

- Vulnerabilities in third-party dependencies (report those to the upstream project)
- Issues in AI-generated project output (these are not bugs in OpenWally itself)
- Social engineering or phishing

## Supported versions

Only the latest version on the `main` branch receives security fixes.
