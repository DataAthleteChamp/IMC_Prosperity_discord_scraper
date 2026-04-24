# Contributing

Thanks for your interest! Before opening a PR:

1. **Read** `docs/architecture.md` — it explains the modules and data flow,
   and `README.md` for the ToS context.
2. **Never commit scraped data.** CI will reject any PR that touches `data/`,
   `*.jsonl`, or anything that looks like a real Discord message payload.
3. **Never commit credentials.** Pre-commit + CI run `gitleaks`.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,user]"
pre-commit install
pytest
```

## Style

- `ruff` for formatting and linting (config in `pyproject.toml`).
- Type hints are mandatory on public functions.
- Tests for every new normalization/paginate/preprocess behaviour.

## Out-of-scope / won't-fix

- Any feature whose only purpose is to evade Discord detection
  (fingerprint spoofing beyond a standard UA string, captcha farming,
  token stealers). Issues of that shape will be closed.
