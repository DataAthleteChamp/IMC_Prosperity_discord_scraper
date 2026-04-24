# Security policy

## Reporting a vulnerability

If you discover a bug that could leak credentials (user tokens, bot tokens)
or scraped personal data, **please do not open a public issue**. Email the
maintainer directly or use GitHub's private vulnerability reporting
(`Security → Report a vulnerability`).

## Token handling rules

1. Tokens live only in `.env` or the OS keyring — never in code, never in git.
2. `.gitignore` excludes `.env`; pre-commit runs `gitleaks` to double-check.
3. A Discord user token is **equivalent to your password**. It grants full
   account access, including DMs. Rotate it (change your Discord password) if
   you suspect exposure.
4. Bot tokens should be regenerated in the Developer Portal if leaked.

## What this project does *not* store

- No scraped messages are ever committed to this repository. The `data/`
  directory is gitignored.
- Tests use synthetic fixtures only.
