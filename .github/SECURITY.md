# Security Policy

## Supported versions

The following versions of `sabi` currently receive security updates:

| Version | Supported |
|---------|-----------|
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x: |

## Reporting a vulnerability

Please disclose security vulnerabilities responsibly. Do not open a public GitHub issue for security concerns.

Instead, contact the maintainer directly (see the repository profile or GitHub security advisories) with:
- A description of the vulnerability and its impact.
- Steps to reproduce, including any affected versions.
- Suggested remediation, if you have one.

## Credentials

This tool handles SABI Informa credentials (`SABI_USERNAME`, `SABI_PASSWORD`). Never commit credentials, session cookies, or tokens to the repository. Use environment variables or a local `.env` file (gitignored).

## Disclosure timeline

We aim to acknowledge reports within 5 business days and provide a remediation timeline within 14 days.
