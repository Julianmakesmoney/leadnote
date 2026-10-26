---
description: Write a cold-call briefing for each best-fit prospect (fit = yes). Shows the count and cost first.
argument-hint: "[--limit N] [--include-partly] [--yes]"
---

# LEADNOTE brief

For the companies `/leadnote-qualify` marked **fit = yes**, a sub-agent does a short deep research and writes a
cold-call briefing: who they are and why now, 3 talking points with evidence, the opener, 2 likely objections with
answers, and what to ask. "Partly" fits keep their short qualification, unless the user passes `--include-partly`.
Use the `.venv` Python if there is one. Talk in the user's language.

## 1. Estimate and ask (always)

1. Read `config/criteria.md`. Run `python run.py status`. No "yes" companies yet: say `/leadnote-qualify` comes first
   and stop.
2. Run `python run.py brief-prep` (add `--fit yes,partly` for `--include-partly`, `--limit N` if given). It writes
   batches of 3 companies and prints JSON: `companies`, `waiting`, `cap` (from `max_brief` in `niche.json`, default
   25), `batches`, `est_tokens`, `est_minutes_parallel3`, `files`.
3. Tell the user in at most four lines: how many briefings, how many more are waiting beyond the cap, the estimated
   tokens (rounded to 10k) and minutes, and that this uses their Claude plan and does a little web research per
   company (their own site and recent news). **Wait for a clear OK**, unless `--yes` was given.

## 2. Write the briefings

For each batch file, spawn a `leadnote-briefer` sub-agent (`subagent_type: "leadnote-briefer"`), up to 3 at a time in
one message, foreground, with only:

> Batch: `<batch file>`. Criteria: `<criteria path from the batch>`. Write the briefings to the `label_file` named
> in the batch.

Fallback when that type is not available: `general-purpose` with `model: "sonnet"` and the instructions from
`.claude/agents/leadnote-briefer.md`.

After each round: `python run.py import-labels <the .briefs.json files>`. It stores each briefing, writes
`data/briefings/<id>-<name>.md`, and notes evidence it could not find on the stored pages (fine when the briefer
marked it `web: true`). Fix or rerun a batch once if a file is missing or broken.

## 3. Report

Short: how many briefings, where they are (`data/briefings/`), and the one company to call first with its
who/why-now line. The page (`npm start`) shows each briefing on the company card, and the CSV export has a
`briefing` column.
