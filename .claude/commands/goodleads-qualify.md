---
description: Qualify the companies GOODLEADS found against config/criteria.md. Shows the count and cost first; then a quick sieve and a deep check, with evidence and an opening line per company.
argument-hint: "[--limit N] [--again] [--yes]"
---

# GOODLEADS qualify

You qualify the companies that `python run.py find` and `python run.py visit` collected. You never search or crawl
here: `run.py` prepares compact batches, sub-agents judge them, and `run.py import-labels` stores the labels. Use the
`.venv` Python if the project has one (`.venv/bin/python`, on Windows `.venv\Scripts\python`), else `python3`.
Talk to the user in their language. Keep your own turns short: do not open the batch files yourself, the
sub-agents read them.

## 1. Check and estimate (always, before any work)

1. Check that `config/criteria.md` exists (in the folder `GOODLEADS_CONFIG` points to, if set). If not: tell the
   user to run `/goodleads-setup` first and stop. Run `python run.py criteria-check`; if it lists problems (an
   old-style file without numbered must-haves and deal-breakers), say in one line that hard rules and the ranking
   need the new outline and offer to rewrite it into the outline of `examples/criteria.md`, keeping every rule.
   If no calibration was done yet (*Learned from calibration* says "none yet") and more than 50 companies wait,
   suggest `/goodleads-calibrate` first in one line; go on if the user wants.
2. Run `python run.py qualify-prep --stage sieve` (add `--limit N` if the user gave one, and `--again` if the user
   asked to judge everything again, e.g. after a calibration; it forgets the old labels, so confirm that with the
   user first, even with `--yes`). It labels what needs no
   AI (parked domains, sites that could not be reached, `sieve_drop_words`), writes the batches and prints JSON with
   `companies` (left for the sieve), `auto_pass`, `auto_drop`, `batches`, `est_tokens`, `est_minutes_parallel4`
   and the batch `files`. It already respects `max_qualify`. If it says 0 companies and nothing was visited yet,
   say that `python run.py visit` comes first and stop.
   If it says `"keywords_missing": true`, first add `keywords` to `config/niche.json`: 20 to 40 lowercase word stems
   in the language(s) of the companies' websites, for what a fitting company does, for whom, and the deal-breakers
   (see `examples/niche.json`). They decide which sentences of each site the sub-agents read. Tell the user in one
   line, then run `qualify-prep --stage sieve` again (it continues where it was).
3. Estimate the deep check: about half the companies pass the sieve, and a deep batch of up to 20 companies costs
   about 110,000 tokens (measured). So deep tokens ≈ `ceil(companies × 0.5 / 20) × 110,000`.
4. Tell the user, in at most four short lines: how many companies, the two estimates added up (round to the nearest
   10k tokens), roughly how many minutes, and that this uses their Claude plan (no API key).
5. **Ask for a clear OK and wait.** Skip this only when the arguments contain `--yes`: then say the estimate in one
   line and go on. If the number is 0, say so and stop.

## 2. Step 1: the sieve (cheap and fast)

For each sieve batch file, spawn a `goodleads-sieve` sub-agent (Agent tool, `subagent_type: "goodleads-sieve"`), up to
4 at a time in one message, foreground, with only this prompt:

> Batch: `<batch file path>`

If that type is not available in this session, use `general-purpose` with `model: "haiku"` and put the
instructions from `.claude/agents/goodleads-sieve.md` in the prompt.

Then run `python run.py import-labels <the .labels.json files>`. If a file is missing or broken, run that batch once
more; if it fails again, tell the user which batch and continue.

## 3. Step 2: the deep check (better model)

1. Run `python run.py qualify-prep --stage deep`. It writes batches of up to 20 for the companies that passed. If
   its estimate is more than 1.5× what you announced, tell the user and ask again (also with `--yes`).
2. For each deep batch, spawn a `goodleads-qualifier` sub-agent (`subagent_type: "goodleads-qualifier"`), up to 4 at a
   time, with the same one-line prompt. Fallback: `general-purpose` with `model: "sonnet"` and the instructions from
   `.claude/agents/goodleads-qualifier.md`.
3. Then `python run.py import-labels <files>`. It applies the hard rules: a deal-breaker or a failed must-have
   makes a company `no`, an unclear must-have turns `yes` into `partly`, and the nice-to-haves and buying signals
   it shows give a score of 0-100 that ranks the fits (notes say where a label was changed). A note "evidence
   quote not found on the stored pages" means the agent
   paraphrased: search the batch file for a few words of it (Grep, not a full read), put the exact sentence in the
   labels file and import that file again. Never invent a quote: if none supports the label, set `fit` to `partly`
   or `no` and say why in `reason`.

## 4. Report

Run `python run.py status`. Then tell the user, short:
- how many yes, partly and no;
- the 3 to 5 best "yes" companies (highest score first), one line each: name, score, why, and their opening line;
- that `npm start` (http://localhost:4760) shows every company with its evidence and opening line, and exports CSV,
  and that `python run.py export` writes `data/prospects.csv`, both best first (fit, then score).

## Rules

- Never ask the sub-agents to browse, search or fetch: they judge what is in the batch.
- Never put e-mail addresses in labels or opening lines.
- Never change `config/` here, except adding missing `keywords` and, with the user's OK, rewriting an old-style
  `criteria.md` into the new outline, as above.
