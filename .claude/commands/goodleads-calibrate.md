---
description: Check the criteria on about 10 real companies before qualifying hundreds. You say per company "right" or "wrong (why)"; the corrections become rules in config/criteria.md.
argument-hint: "[--n 10] [--yes]"
---

# GOODLEADS calibrate

The qualifier is only as good as `config/criteria.md`. Here the user checks it on about 10 companies GOODLEADS already
visited: the qualifier judges them, the user says per company whether that is right, and every correction becomes a
concrete rule under *Learned from calibration*. At most 3 rounds. Use the `.venv` Python if there is one. Talk in
the user's language, short and plain. Do not open the batch files yourself.

## 1. Check and estimate

1. `config/criteria.md` must exist; if not, say `/goodleads-setup` comes first and stop. Run
   `python run.py criteria-check`. If it lists problems, fix them in `criteria.md` first (an old-style file: rewrite
   it into the outline of `examples/criteria.md`, keeping every rule, and show the user the new must-haves and
   deal-breakers in a few lines).
2. Run `python run.py calibrate-prep` (add `--n N` if the user gave one). It picks a mix of visited companies
   (likely yes, likely partly, likely no; companies of earlier rounds are skipped), writes one batch and prints JSON
   with `round`, `companies`, `file`, `labels` and `est_tokens`. With 0 companies: say `python run.py visit` comes
   first and stop.
3. Tell the user in two lines: how many companies, about how many tokens (rounded to 10k) and that it takes about 2
   minutes of their Claude plan. **Wait for a clear OK**, unless the arguments contain `--yes`.

## 2. Judge

Spawn one `goodleads-qualifier` sub-agent (`subagent_type: "goodleads-qualifier"`), foreground, with only:

> Batch: `<file>`

Fallback: `general-purpose` with `model: "sonnet"` and the instructions from `.claude/agents/goodleads-qualifier.md`.
Then run `python run.py calibrate-show <labels file>`. It prints one line per company: number, name, site, verdict
(with the hard rules applied), score and reason. Nothing is stored as a label.

## 3. Ask

Show the lines as they are (a numbered list), then ask once:

> Per company: right, or wrong and why? For example: "all right except 3: they only do web design" or "4 should be
> yes, size doesn't matter to me". If you don't know a company, skip it.

When an answer is vague ("3 is wrong"), ask **one** follow-up with options: "Wrong because (A) they are another
kind of business, (B) too big or too small, (C) they would buy after all, because ...?"

## 4. Learn

Turn every correction into a concrete rule a website can show, not a company name. Good: "A company whose only IT
service is web hosting is not a managed service provider: no (D2)." Bad: "Company X is a no." Then:

1. Show the rules in one short message ("I'll add these rules: ...") and ask "OK?".
2. Run `python run.py learn "<rule 1>" "<rule 2>" --note "round <n>"`. It adds them as L-items under *Learned from
   calibration*. If a correction shows that an item itself is wrong (a must-have that is only nice, a wrong weight),
   edit that item in place as well and say so.
3. Run `python run.py criteria-check`.

## 5. Again, or done

- No corrections: say the criteria look right and suggest `/goodleads-qualify`.
- Corrections, and fewer than 3 rounds: offer one more round, which re-judges the companies that were wrong plus a
  few new ones: `python run.py calibrate-prep --recheck <ids that were wrong>`. Then steps 2 to 5 again.
- After round 3, stop; say what changed and suggest `/goodleads-qualify`.
- If companies were already qualified before these changes, say so in one line and offer
  `/goodleads-qualify` with a fresh start (`qualify-prep --stage sieve --again` forgets the old labels; the cost
  question comes first as always).
