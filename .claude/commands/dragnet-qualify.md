---
description: Qualify the companies Dragnet found against config/criteria.md. Shows the count and cost first; then a quick sieve and a deep check, with evidence and an opening line per company.
argument-hint: "[--limit N] [--yes]"
---

# Dragnet qualify

You qualify the companies that `python run.py find` and `python run.py visit` collected. You never search or crawl
here: you read what is stored, judge it against the user's criteria, and write the labels back through
`run.py import-labels`. Use the `.venv` Python if the project has one (`.venv/bin/python`, on Windows
`.venv\Scripts\python`), else `python3`. Talk to the user in their language; labels are written in English, the
opening line in the language of the company's website unless `criteria.md` says otherwise.

## 1. Check and estimate (always, before any work)

1. Read `config/criteria.md` and `config/niche.json`. No criteria file: tell the user to run `/dragnet-setup` first
   and stop.
2. Run `python run.py status`. If nothing has been visited yet, say that `python run.py visit` comes first and stop.
3. Run `python run.py qualify-prep --stage sieve` (add `--limit N` if the user gave one). It writes the batches and
   prints JSON with `companies`, `batches`, `est_tokens`, `est_minutes_parallel4` and the batch `files`.
   It already respects `max_qualify` from `niche.json`.
4. Estimate the deep check yourself: about half the companies usually pass the sieve; a deep batch of 8 companies is
   about 25,000 tokens. So deep tokens ≈ `companies × 0.5 / 8 × 25,000`.
5. Tell the user, in at most four short lines: how many companies, the two estimates added up (round to the nearest
   10k tokens), roughly how many minutes, and that this uses their Claude plan (no API key). If more companies are
   waiting than `max_qualify` allows, say how many are left out and how to raise it.
6. **Ask for a clear OK and wait.** Only skip this when the user passed `--yes`. If the number is 0, say so and stop.

## 2. Step 1: the sieve (cheap and fast)

For each sieve batch file, spawn a `dragnet-sieve` sub-agent (Agent tool, `subagent_type: "dragnet-sieve"`), up to
4 at a time in one message, foreground. Give each one only:

> Batch: `<batch file path>`. Criteria: `<criteria path from the batch>`. Write the labels to the `label_file`
> named in the batch.

If the `dragnet-sieve` type is not available in this session, use `general-purpose` with `model: "haiku"` and paste
the instructions from `.claude/agents/dragnet-sieve.md` into the prompt.

When a round of agents is back, run `python run.py import-labels <the .labels.json files>`. Read its notes. If a
file is missing or broken, run that batch once more; if it fails again, tell the user which batch and continue.

## 3. Step 2: the deep check (better model)

1. Run `python run.py qualify-prep --stage deep`. It writes batches of 8 with the full page text for the companies
   that passed the sieve. If its estimate is far above what you announced (more than 1.5×), tell the user and ask
   again before continuing.
2. For each deep batch, spawn a `dragnet-qualifier` sub-agent (`subagent_type: "dragnet-qualifier"`), up to 4 at a
   time, with the same three lines as above. Fallback: `general-purpose` with `model: "sonnet"` and the
   instructions from `.claude/agents/dragnet-qualifier.md`.
3. After each round, `python run.py import-labels <files>`. Notes such as "evidence quote not found on the stored
   pages" mean the agent paraphrased; for those companies, open the batch file, find the real sentence, and fix the
   quote in the labels file yourself, then import that file again. Do not invent a quote: if none supports the
   label, set `fit` to `partly` or `no` and say why in `reason`.

## 4. Report

Run `python run.py status`. Then tell the user, short:
- how many yes, partly and no;
- the 3 to 5 best "yes" companies, one line each: name, why, and their opening line;
- that `npm start` (http://localhost:4760) shows every company with its evidence and opening line, and exports CSV,
  and that `python run.py export` writes `data/prospects.csv`.

## Rules

- Never ask the sub-agents to browse, search or fetch: they judge what is in the batch.
- Never put e-mail addresses in labels or opening lines.
- Never change `config/` here.
