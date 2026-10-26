# Dragnet

This project is Dragnet: it finds every company of one kind in an area on Google Maps, reads their websites, and
qualifies them against the user's criteria, with a quote as evidence and one opening line per company. It only
finds and qualifies. It does not send e-mail, call, or collect e-mail addresses.

## Setting it up for someone

If the user asks you to set it up ("clone … and set it up for me"):
1. Create a virtual environment and install: `python3 -m venv .venv`, then `.venv/bin/pip install -r requirements.txt`
   and `.venv/bin/python -m playwright install chromium` (Windows: `.venv\Scripts\pip`, `.venv\Scripts\python`).
   Python 3.10+ is needed; Node 20+ for the page.
2. Run the tests: `.venv/bin/python -m pytest -q`.
3. Start `/dragnet-setup` to interview the user and write `config/niche.json` and `config/criteria.md`.

## The flow

- `/dragnet-setup`: the interview. One question at a time, examples with every question, in the user's language.
- `python run.py plan`: preview of the grid and the time. Safe; it does not touch Google.
- `python run.py find`: the Maps search. It is slow on purpose (a work-rest rhythm against blocks) and can be stopped
  and restarted at any time. For a long run, start it in the background and tell the user how to follow it.
  Never run two `find` processes at once, and never lower the pace settings without the user asking.
- `python run.py visit`: reads the companies' websites.
- `/dragnet-qualify`: the two-step qualification. Always show the count and estimated cost and wait for an OK.
- `/dragnet-brief`: cold-call briefings for fit = yes companies (cost first, `max_brief` cap).
- `npm start`: the local page on http://localhost:4760 (zero dependencies). It calls `run.py json`.
- `python run.py status` and `python run.py export` at any time.

## Where things live

| Path | What |
|---|---|
| `dragnet/maps.py` | Maps search: grid queue, list reading, splitting full cells, de-duplication, work-rest rhythm |
| `dragnet/area.py` | Areas from OpenStreetMap Nominatim, the grid, point-in-area |
| `dragnet/visit.py`, `dragnet/signals.py` | Website visits and the general signals (services, jobs, size, contact) |
| `dragnet/qualify.py` | Batches for the sub-agents and `import-labels` with quote checking |
| `dragnet/brief.py` | Briefing batches, import, markdown per company |
| `.claude/commands/` | `/dragnet-setup`, `/dragnet-qualify`, `/dragnet-brief` |
| `.claude/agents/` | `dragnet-sieve` (Haiku), `dragnet-qualifier` and `dragnet-briefer` (Sonnet) |
| `config/` | The user's niche (not in git). Examples in `examples/` |
| `data/` | The database and work files (not in git). `DRAGNET_DATA` points elsewhere |

## Rules

- Keep only business data. Do not add e-mail harvesting, personal profiles, or review text.
- Be honest about Google's terms: automated reading of Maps is not allowed by Google; the user runs this at their own
  responsibility. Do not add tricks to evade detection beyond the slow rhythm that is already there.
- Labels must quote the stored pages literally. `import-labels` checks every quote and marks the ones it cannot find.
- Write plain English in code, docs and the page. Keep it simple and reliable over clever.
