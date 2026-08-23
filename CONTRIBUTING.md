# Contributing

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in GEMINI_API_KEY and SECRET_KEY
alembic upgrade head          # falls back to SQLite when DATABASE_URL is unset
```

`COHERE_API_KEY` and `REDIS_URL` are optional: without them reranking falls back
to a keyword ranker and long-term memory is skipped. Both degrade quietly, so if
you expect them to be live, check the logs rather than assuming.

On an Intel Mac, `cryptography >= 47` publishes no x86_64 macOS wheel and pip
falls back to a Rust build. Add `-c <(echo "cryptography<47")` to the install.

## Before opening a PR

CI runs these four, and so should you:

```bash
ruff check backend/ tests/
ruff format --check backend/ tests/
mypy backend/
pytest tests/ -q
```

`pytest tests/` needs no infrastructure — the suite is hermetic. A real
`COHERE_API_KEY` or `REDIS_URL` in your `.env` is neutralised by a fixture in
`tests/conftest.py`, so no test makes a billed API call. The exception is
`tests/test_e2e`, which skips itself unless a backend is live on port 8000.

## Comments

This codebase comments the *why*, not the *what*. Many comments record a bug that
was actually hit and the reason the code is shaped the way it is — deleting one
invites the bug back. If you change the behaviour a comment explains, update the
comment in the same commit; if you find a comment that only restates its code,
that one is worth removing.

## What needs care

- **The HITL gate.** Any path that can put an answer in front of a customer must
  run `risk_service` on the text that is actually shown. See `SECURITY.md`.
- **RBAC in retrieval.** The Qdrant payload filter is the second of two layers,
  not a convenience. Tests assert no `internal` chunk reaches a `public` asker.
- **The semantic cache.** It matches on meaning, so anything question-specific —
  images, unit listings, a follow-up resolved against one session's history —
  must not be cached, or it will be replayed under a different question.
- **Prompts are production code.** `backend/ai/prompts.py` decides what a Sale
  reads out to a customer; treat a wording change as a reviewable behaviour change.

## Commits

Explain why the change is needed, not what the diff shows. Reference the failure
or requirement that motivated it.
