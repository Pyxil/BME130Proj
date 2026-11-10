## Summary

<!-- What does this change and why? -->

Closes #

## Team / component

- [ ] Frontend
- [ ] Backend
- [ ] Speech analysis
- [ ] AI feedback
- [ ] Infrastructure / CI

## How was this tested?

- [ ] Unit tests added or updated
- [ ] `python scripts/dev.py check` passes locally
- [ ] Model integration tests (`pytest -m model`) if scoring code changed
- [ ] Manually tested in the browser (attach screenshots for UI changes)

## Contracts and data

- [ ] No API / analysis contract change
- [ ] Contract changed: ran `python scripts/dev.py contracts`, bumped `CONTRACT_VERSION` if breaking, updated `docs/api_documentation.md`
- [ ] Database change: Alembic migration added and tested (upgrade + downgrade)
- [ ] Scoring change: re-ran `scripts/evaluate_speechocean762.py` and updated `docs/validation.md`

## Privacy and safety

- [ ] No recordings, personal data or secrets committed
- [ ] User-facing text makes no clinical or diagnostic claims
