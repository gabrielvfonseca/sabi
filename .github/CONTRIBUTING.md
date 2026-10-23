# Contributing to sabi

Thank you for contributing! Please read this short guide before opening issues or pull requests.

## Getting started

1. Fork the repo and create a branch from `main`.
2. Create a virtual environment and install dev dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. Run the test suite:

   ```bash
   pytest
   ```

4. Lint and format:

   ```bash
   ruff check .
   ruff format .
   ```

## Making changes

- Follow the existing code style in `src/` and `tests/`.
- Add tests for new behavior and update tests for changed behavior.
- Keep credentials out of the repo; use environment variables (`SABI_USERNAME`, `SABI_PASSWORD`) or a `.env` file (never commit `.env`).
- Update `README.md` when user-facing behavior changes.

## Submitting a pull request

1. Push your branch and open a PR against `main`.
2. Use the PR template; fill out the checklist.
3. Ensure CI passes (lint, tests on Python 3.10–3.12, and Docker build).
4. Request review from a maintainer.

## Code of conduct

Be respectful and constructive in issues, PRs, and discussions.
