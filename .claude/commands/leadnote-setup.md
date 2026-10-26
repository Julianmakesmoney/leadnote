---
description: Set up LEADNOTE for your niche. Paste one long description, or answer a short interview (one question at a time); writes config/niche.json and config/criteria.md.
argument-hint: "[optional: paste everything about your offer and ideal customer, or one line]"
---

# LEADNOTE setup

You are setting up LEADNOTE for this user. LEADNOTE finds every company of one kind in an area on Google Maps, reads
their websites, and qualifies them against the user's criteria, so the user can call exactly the companies they
want. **The criteria are the whole product**: the qualifier only knows what you write down here. Your job: understand
the user's offer and ideal customer in detail, then write two files. Nothing is searched yet.

## How to talk

- **Speak the user's language.** Detect it from their first message (or `$ARGUMENTS`) and keep to it. The files you
  write are in English, except the search terms and `keywords`, which are in the language of the country searched.
- **One question per message.** Each comes with 2 or 3 short, concrete example answers the user can pick or adapt.
  Never send a list of questions.
- Keep messages short: plain words, no jargon, no tables.
- **Vague answers are normal.** If an answer is too vague to search or judge with ("everyone", "small businesses",
  "Europe", "I don't know"), ask **one** follow-up that offers concrete options (A, B, C) and says which one you
  would pick and why. If it is still vague, choose a sensible default yourself, say so in one line, and write it
  under *Assumptions* in `criteria.md`. Never ask the same thing a third time.
- **Skip what you already know.** If `$ARGUMENTS` or an earlier answer already answers a question, do not ask it:
  confirm it in half a line at most. Optional questions (marked below) may be skipped when the user is in a hurry.
- **At most 3 follow-ups in the whole setup.** Spend them on what decides the leads: the offer, the ideal customer,
  the area. On "I don't know" for price, bad fits, buying signals or the first call, do not follow up: propose a
  default in one line, go on, and write it under *Assumptions*.
- **If the offer or the ideal customer stays unknown**, say plainly that the criteria will be your guess and the
  leads will be too, and point to `examples/setup-prompt.md` (a template, and a prompt that lets ChatGPT or Claude
  write it from their website). Go on only if the user wants.

## Before you start

1. If `config/niche.json` already exists, ask whether to start over or adjust it. Adjusting: ask only what changes.
2. Check that Python and the browser are ready: `python3 -c "import playwright, requests, bs4"` (or the `.venv`
   Python if there is one; use that Python for every `run.py` call below). If that fails, offer to run the install
   from the README (`python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`,
   `.venv/bin/python -m playwright install chromium`; Windows `.venv\Scripts\...`). Ask before installing.

## Path A: the user pasted a description (one-prompt setup)

If `$ARGUMENTS` or the first message holds more than a line or two about the offer and the customers (for example
the filled-in template from `examples/setup-prompt.md`):

1. Pull out everything the list in Path B asks for: offer, price or deal size, ideal customer, best clients (names
   or websites), bad-fit examples, must-haves, nice-to-haves, deal-breakers, buying signals, who to ask for, what a
   good first call is, area, search terms. Read best-client websites as in question 3 below.
2. Send **one** short summary, headed "This is what I understood" (in the user's language): one line per topic,
   with what you inferred marked as such ("(my guess)"). Leave out what is missing.
3. Then ask only what is **missing, vague or contradictory**, still one question per message, in the order of Path
   B. Best clients, buying signals and the first call are optional here: ask for best clients once only if none
   were named; propose the rest as defaults inside the summary instead of asking. Contradictions first, said plainly ("You say 5 to 50 people, but your best client has 200. Which counts?").
   The must-haves, the deal-breakers and the area are needed; everything else may become an assumption.
4. Go on with "Search terms and filters" below.

## Path B: the interview (when there is no description)

Ask in this order. Keep it as short as the answers allow.

1. **What do you sell, and roughly what does it cost?** A price range or a typical deal size per year, so you can
   judge who can afford it. Examples: "IT support contracts, about EUR 1,000 a month", "accounting software, EUR
   50 a user a month", "recruitment, about EUR 15,000 per hire".
2. **Who is your ideal customer?** The kind of company and what makes it a great fit. Examples: "IT companies that
   do managed services for SMEs, 5 to 50 people", "independent accounting firms with a few partners", "wholesalers
   with a webshop and their own warehouse".
3. **Name 2 or 3 of your best clients** (name or website). Explain in one line why: you will look at their sites
   and find what they have in common. Examples: "acme-it.nl and brightdesk.nl", "Jansen Accountants in Utrecht",
   "I'd rather not say" (then skip). With a name but no website, ask for the website once; if the user does not know
   it, one web search for the name and town is fine, but confirm the site with the user before reading it.
   Then run `python run.py lookalike <url> <url>` (it reads up to 4 pages per site, stores nothing) and tell the
   user in 3 to 5 short lines what the clients have in common (what they sell, for whom, size, age, how they
   describe themselves), **only from what the output shows**; mark anything from your own knowledge as such. If a
   site gave 1 page, only brand language, or looks like the wrong domain (a holding, a shop, a stub), say so and ask
   for the right site or what that client does; never invent a common trait. If a best client is clearly bigger or
   smaller than the ideal size range, ask whether size counts for the whole company or per branch, and write the
   answer as a rule. Then ask: "Is that what makes them good clients, or is it
   something else?" Their answer, plus what you saw, becomes *Lookalikes from best clients*.
4. **Give 1 or 2 examples of a bad fit, and why.** Companies that looked right but were not, or that you never want
   to call. Examples: "big IT groups: they have it all in-house", "one-man shops: no budget", "computer repair
   shops: they sell to consumers".
5. **What must a company have, and what is only nice?** Propose the split yourself from what you know so far: 2 to
   4 must-haves (without them it is never a fit; only things a website normally *states*, such as what they do and
   for whom; a must-have the site is silent about turns every yes into partly, so "not part of a big group" or
   "not a franchise" belongs under deal-breakers instead) and 3 to 6 nice-to-haves (they make a company a better fit). Ask
   the user to move, add or remove items. Give each nice-to-have a weight 1 to 3 (3 = matters most) and say which
   ones you weighted highest.
6. **Deal-breakers.** Propose them from the bad fits and the answers so far (too small, too big, wrong type, chain
   or franchise, consumers only) and ask "anything to add or remove?".
7. **Buying signals** (optional). What on a website shows they need you *now*? Examples: "they're hiring a service
   desk engineer", "a new office or a merger", "they mention NIS2 or ISO 27001", "they use Exact or AFAS", "news
   from the last months". Propose 2 to 4 that fit the offer, with weights 1 to 3; the user picks.
8. **Who do you want to speak to?** The role of the decision maker, so the briefing says who to ask for. Examples:
   "the owner", "the operations manager", "the head of IT, or the director in small firms".
9. **What is a good first call?** (optional) What counts as success, and which objections they hear most. Examples:
   "a demo booked", "they send me their price list", "'we already have a supplier' and 'no time'". This steers the
   opening line and the objections in the briefing.
10. **Where?** A country, a region or a list of cities. Examples: "all of Belgium", "Utrecht and Amersfoort",
    "Greater Manchester". Turn each place into an OpenStreetMap-style name with the country: "Utrecht, Utrecht,
    Nederland", "Gent, Oost-Vlaanderen, België", "Belgium". A whole country is fine; say it takes longer. If the
    user hesitates between a small and a big area, write a draft `config/niche.json` and run `python run.py plan`
    for each, so the options show real numbers (searches, hours) instead of guesses.
11. **Size of the run.** How many companies to qualify at most (`max_qualify`, default 300). Mention that the
    qualifying uses their Claude plan and that `/leadnote-qualify` shows the cost before it starts.

## Search terms and filters (both paths)

**Search terms.** Propose 4 to 8 terms for Google Maps **in the language of that country** (Belgium: Dutch for
Flanders, French for Wallonia, both for all of Belgium; Switzerland: German/French/Italian per region). Mix the
Google Maps category names a company of this kind would pick ("Accountant", "Boekhouder", "IT-bedrijf",
"Computerondersteuning en -services") with the words people search for. Show them as a numbered list with one line
each on why, mark the 2 or 3 you would start with, and let the user pick. Fewer terms = faster; each term adds a full
pass over the grid. Recommend 2 to 4.

Then propose, in one short message, and ask "OK, or change something?":
- `category_exclude`: Google Maps categories that are certainly not a fit, in the country's language. 5 to 15.
  Never a category a fitting company might pick for itself (for sanitary installers, not "Loodgieter").
- `name_keywords`: word stems that, in a company name, show it *is* in the niche even when its Maps category is in
  the exclude list (e.g. "accountan", "boekhoud"). 3 to 8.
- `keywords`: 15 to 40 word stems (no padding) **in the language(s) of the companies' websites** for what a fitting company does,
  for whom, the must-haves, nice-to-haves, buying signals and deal-breakers (e.g. "beheer", "servicedesk",
  "ontzorg", "werkplek", "backup", "mkb", "zorg", "vacature", "nis2" for IT service providers in the Netherlands).
  They pick the sentences of each site the AI reads, which keeps qualifying cheap. Stems, lowercase, no sentences.
- `sieve_drop_words` (optional, usually empty): words that in a company name or Maps category mean a certain "no"
  (e.g. "reparatie" when phone repair shops are a deal-breaker). Dropped without AI. Only sure ones.
- `keep_without_website`: true only if the user calls or visits companies that have no website.

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
  "max_qualify": 300,
  "max_brief": 25
}
```

`config/criteria.md`, in English, with **exactly these sections in this order** (see `examples/criteria.md` for a
complete one). Write every item as something a company's website or Maps listing can show. Number the items: the
qualifier names them, LEADNOTE counts them.

```markdown
# Criteria: <niche, area>

## Offer
<what the user sells, in 1 or 2 lines>
## Price
<price range or deal size, and what that means for who can afford it (minimum size, budget); "unknown" if unknown>
## Ideal customer
<one short paragraph: type of company, what they do, for whom, size range, region>
## Lookalikes from best clients
<3 to 5 bullets: what the best clients have in common, from their sites and the user's answer; "none given" if none>
## Must-haves
- M1: <without this it is never a fit>
## Nice-to-haves
- N1 (weight 3): <makes it a better fit; weight 1 to 3>
## Deal-breakers
- D1: <one is enough for "no">
## Buying signals
- S1 (weight 2): <shows they need it now; weight 1 to 3>
## Who to ask for
<the role(s) to ask for, by company size, with the local job titles>
## What a good first call looks like
<what success is, the objections to expect, tone, language of the opener (default: the language of their site)>
## Assumptions
<defaults you chose because an answer was vague; "none" if none>
## Learned from calibration
none yet
```

Then run `python run.py criteria-check`. Fix every problem it lists before you go on.

## After writing

1. Run `python run.py plan`. It looks up the areas on OpenStreetMap and shows the number of cells, searches and a
   rough time. It does not touch Google.
2. Tell the user in 3 short lines: how many searches and roughly how long; that `find` keeps a slow work-rest
   rhythm and can be stopped with Ctrl+C and restarted any time; and the next steps: `python run.py find`, then
   `python run.py visit`, then **`/leadnote-calibrate`** (10 companies to check the criteria with them), then
   `/leadnote-qualify`, optionally `/leadnote-brief` for the best fits, and `npm start` to watch.
3. If the database already holds visited companies (`python run.py status` shows "visited" above 0), offer the
   calibration right away instead: "Shall I check the criteria on 10 companies we already have? About 2 minutes,
   about 110k tokens of your plan."
4. Mention once, plainly: Google's terms do not allow automated reading of Maps; the user runs it at their own
   responsibility, at a calm pace, and LEADNOTE keeps only business data (no e-mail addresses).
