---
description: Set up LEADNOTE for your niche. A short interview, one question at a time; writes config/niche.json and config/criteria.md.
argument-hint: "[optional: what you sell and where, in one line]"
---

# LEADNOTE setup

You are setting up LEADNOTE for this user. LEADNOTE finds every company of one kind in an area on Google Maps, reads
their websites, and then qualifies them against the user's criteria. Your job here: interview the user, then write
two files. Nothing is searched yet.

## How to talk

- **Speak the user's language.** Detect it from their first message (or `$ARGUMENTS`) and keep to it. The files you
  write are in English, except the search terms, which are in the language of the country being searched.
- **One question per message.** Each question comes with 2 or 3 short, concrete example answers so the user can
  just pick or adapt one. Never send a list of questions.
- Keep messages short: plain words, no jargon, no tables.
- **Vague answers are normal.** If an answer is too vague to search or judge with ("everyone", "small businesses",
  "Europe", "I don't know"), ask **one** follow-up that offers concrete options (A, B, C) and says which one you
  would pick and why. If it is still vague, choose a sensible default yourself, say so in one line, and write it
  under *Assumptions* in `criteria.md`. Never ask the same thing a third time.
- If `$ARGUMENTS` or earlier answers already answer a question, do not ask it again: confirm it in half a line.

## Before the interview

1. If `config/niche.json` already exists, ask whether to start over or adjust it. Adjusting: ask only what changes.
2. Check that Python and the browser are ready: `python3 -c "import playwright, requests, bs4"` (or the `.venv`
   Python if there is one). If that fails, offer to run the install from the README (`python3 -m venv .venv`,
   `.venv/bin/pip install -r requirements.txt`, `.venv/bin/python -m playwright install chromium`; on Windows
   `.venv\Scripts\...`). Ask before installing.

## The questions (in this order)

1. **What do you sell?** Examples: "IT support contracts for offices", "accounting software", "recruitment for
   technical roles".
2. **Who is your ideal customer?** The kind of company and what makes it a great fit. Examples: "IT companies that
   do managed services for SMEs, 5 to 50 people", "independent accounting firms with a few partners", "wholesalers
   with a webshop and their own warehouse".
3. **What is a deal-breaker?** Too small, too big, wrong type, part of a chain or franchise, consumers only.
   Examples: "freelancers and one-person firms", "anything above 250 people or part of a big group", "shops that
   sell to consumers".
4. **Where?** A country, a region or a list of cities. Examples: "all of Belgium", "Utrecht and Amersfoort",
   "Greater Manchester". Turn each place into an OpenStreetMap-style name with the country: "Utrecht, Utrecht,
   Nederland", "Gent, Oost-Vlaanderen, België", "Belgium". A whole country is fine; say it takes longer.
   If the user hesitates between a small and a big area, write a draft `config/niche.json` and run
   `python run.py plan` for each, so the options show real numbers (searches, hours) instead of guesses.
5. **Search terms.** Now *you* propose 4 to 8 terms for Google Maps **in the language of that country** (Belgium:
   Dutch for Flanders, French for Wallonia, both for all of Belgium; Switzerland: German/French/Italian per region).
   Mix the Google Maps category names a company of this kind would pick ("Accountant", "Boekhouder", "IT-bedrijf",
   "Computerondersteuning en -services") with the words people search for. Show them as a numbered list with one
   line each on why, mark the 2 or 3 you would start with, and let the user pick. Fewer terms = faster; each term
   adds a full pass over the grid. Recommend 2 to 4.
6. **Size of the run.** How many companies to qualify at most (`max_qualify`, default 300). Mention that the
   qualifying uses their Claude plan and that `/leadnote-qualify` shows the cost before it starts.

Then propose, without asking a separate question for each:
- `category_exclude`: Google Maps categories that are certainly not a fit in this niche (shops, restaurants, the
  wrong trade), in the country's language. 5 to 15 items.
- `name_keywords`: word stems that, in a company name, show it *is* in the niche even when its Maps category is in
  the exclude list (e.g. "accountan", "boekhoud" for accountants). 3 to 8 items.
- `keywords`: 20 to 40 word stems **in the language(s) of the companies' websites** that a fitting company would use
  for what it does, for whom, and for the deal-breakers (e.g. "beheer", "servicedesk", "ontzorg", "werkplek",
  "backup", "mkb", "zorg", "onderwijs" for IT service providers in the Netherlands). LEADNOTE uses them to pick the
  sentences of each site that the AI reads, which keeps qualifying cheap. Stems, lowercase, no sentences.
- `sieve_drop_words` (optional, usually empty): words that in a company name or Maps category mean a certain "no"
  (e.g. "reparatie" when phone repair shops are a deal-breaker). They are dropped without AI. Only sure ones.
- `keep_without_website`: true only if the user calls or visits companies that have no website.
Show these in one short message and ask "OK, or change something?".

## Write the files

`config/niche.json` (see `examples/niche.json` for the full shape):

```json
{
  "name": "<short name of the niche and area>",
  "country": "<ISO 2-letter code, lowercase>",
  "language": "<language code of the Maps interface for that country, e.g. nl, fr, de, en>",
  "areas": ["<OpenStreetMap-style area>", "..."],
  "search_terms": ["..."],
  "category_exclude": ["..."],
  "name_keywords": ["..."],
  "keywords": ["..."],
  "sieve_drop_words": [],
  "keep_without_website": false,
  "grid": {"cell_km": "auto", "max_depth": 3, "split_min_in_cell": 10},
  "pace": {"block": 12, "rest_minutes": 20, "wait_seconds": [4, 8]},
  "visit": {"max_pages": 6, "threads": 6},
  "max_qualify": 300
}
```

`config/criteria.md`, in English, using this outline (fill every section; keep it under one page):

```markdown
# Criteria: <niche>

## What I sell
## Fit: yes
<the ideal customer, as checkable statements: type of company, what they do, size range, who they serve>
## Fit: partly
<close but with one doubt: e.g. right type but bigger than ideal, or the service is a side line>
## Fit: no (deal-breakers)
## Signals that make it stronger
<things a website can show: hiring, a service page for X, a webshop, number of people, founded before Y>
## Opening line
<what the user wants the first sentence of a call or message to touch on; tone; language (default: the language
of the company's website)>
## Assumptions
<defaults you chose because an answer was vague; "none" if none>
```

## After writing

1. Run `python run.py plan` (or `.venv/bin/python run.py plan`). It looks up the areas on OpenStreetMap and shows
   the number of cells, searches and a rough time. It does not touch Google.
2. Tell the user in 3 short lines: how many searches and roughly how long; that `find` keeps a slow work-rest
   rhythm and can be stopped with Ctrl+C and restarted any time; and the next steps:
   `python run.py find`, then `python run.py visit`, then `/leadnote-qualify`, optionally `/leadnote-brief` for the
   best fits, and `npm start` to watch.
3. Mention once, plainly: Google's terms do not allow automated reading of Maps; the user runs it at their own
   responsibility, at a calm pace, and LEADNOTE keeps only business data (no e-mail addresses).
