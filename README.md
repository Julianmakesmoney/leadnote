# LEADNOTE

**The Death Note for sales. Every name in it closes.**

*Every company on the map. A briefing for the ones worth calling.*

Most lead lists are a phone book. LEADNOTE is a notebook: it reads every company in your niche on the map, and only
the ones that truly fit get written in, each with the evidence, the opening line and a one-page call briefing.

LEADNOTE builds the most complete prospect list you can get for one B2B niche in one area, then tells you which of
those companies are worth a call, why, and how to open the conversation. It sweeps Google Maps cell by cell (so a
busy city centre doesn't get cut off at Maps' 120-result limit), drops the duplicates, reads each company's own
website, and then Claude Code checks every company against your criteria with a quote as proof.

It works for any niche in any country: IT service providers in Utrecht, accountants in Ghent, machine shops in Ohio.
It only finds and qualifies. It does not send e-mail, it does not call, and it never collects e-mail addresses.

```
find      Google Maps, cell by cell      →  every listing in the area, deduplicated
visit     each company's own website     →  what they do, jobs, size, contact page
qualify   Claude Code, two steps         →  fit yes / partly / no, a quote as evidence, one opening line
brief     Claude Code, best fits only    →  a cold-call briefing per company
npm start a local page                   →  funnel, filters, company cards, CSV export
```

## What you need

- [Claude Code](https://claude.com/claude-code). Your Claude plan covers the qualifying; no API key.
- Python 3.10 or newer, for finding and visiting.
- [Node.js](https://nodejs.org) 20 or newer, for the local page. Nothing to install beyond that.
- Mac, Windows or Linux.

## Setup

```bash
git clone https://github.com/<you>/leadnote.git && cd leadnote
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m playwright install chromium
claude
```

On Windows use `.venv\Scripts\pip` and `.venv\Scripts\python`.
Or open Claude Code anywhere and say: "Clone github.com/<you>/leadnote and set it up for me."

## Run it

1. **`/leadnote-setup`** in Claude Code. A short interview, one question at a time: what you sell, who your ideal
   customer is, what's a deal-breaker, and where. Claude proposes Google Maps search terms in the language of that
   country, you pick. It writes `config/niche.json` and `config/criteria.md`.
2. **`python run.py find`** sweeps Google Maps. It shows live how many searches, results and unique companies it has.
   It is slow on purpose (see *Google and the pace* below); stop it with Ctrl+C whenever you like and run it again
   to continue where it left off. `python run.py plan` shows the size of the job first.
3. **`python run.py visit`** reads each company's own website: what they sell or do, open jobs, size signals, the
   contact page.
4. **`/leadnote-qualify`** in Claude Code. It shows how many companies and the estimated tokens and waits for your
   OK. Then a quick sieve on a small model drops what clearly doesn't fit, and a deeper check on a better model
   labels the rest: **fit** (yes, partly, no), the **reason**, a **verbatim quote** from their site as evidence, and
   **one opening line** built on the most specific true detail it found.
5. **`/leadnote-brief`** in Claude Code (optional). For every **fit = yes** company, a sub-agent does a short deep
   research (their own site and recent news) and writes a **cold-call briefing**: who they are and why now, 3
   talking points with evidence, the opener, 2 likely objections with answers, and what to ask. It shows the cost
   first; `max_brief` (default 25) caps it. Briefings land in `data/briefings/<id>-<name>.md`, on the company card
   and in the CSV. Partly-fits keep their short qualification.
6. **`npm start`** and open http://localhost:4760. A funnel on top (searches → results → unique → visited → fit),
   a table you can filter by fit, area, size and hiring, a card per company with the evidence and the opening
   line, and **Export CSV** for calling, LinkedIn or your CRM. `python run.py export` writes the same CSV.

Use `.venv/bin/python` in place of `python` if you set up the virtual environment as above.

## An example run

These are the real totals of the engine LEADNOTE was extracted from: Julian Verboom's own prospecting engine,
run for one niche (technical wholesalers in hydraulics, pneumatics and drive technology) across the Netherlands and
Flanders.

| Step | Count |
|---|---|
| Google Maps searches | 2,321 |
| Results read from the lists | 171,558 |
| Unique companies | 13,560 |
| Screened by AI (the sieve) | 12,116 |
| Deep-checked | 2,416 |
| **Perfect fit** | **650** (plus 687 partial) |

Every one of the 650 came with the reason, a quote from its own site, and an opening line. Those numbers are from
that engine, not from a LEADNOTE run; LEADNOTE is the same method, made general for any niche and country.

A small smoke test of LEADNOTE itself, "IT managed service provider" in the city of Utrecht with the test pace
(14 searches, then 8 minutes rest): 19 searches in 17 minutes, 2,256 results, 502 unique listings, 228 companies
inside the city after filters and de-duplication, 217 readable websites. Of 15 companies sent through
`/leadnote-qualify`, the sieve kept 8; the deep check marked 1 yes, 3 partly and 4 no (three of those were IT firms
of 250+ people, a deal-breaker), with every evidence quote found on the stored pages. A second smoke test, "accountant" and
"boekhouder" in Ghent (30 searches, stopped there on purpose with 14 left in the queue): 3,609 results, 534 unique
listings, 210 companies, 128 readable websites, in 27 minutes, without a single block from Google.

## What to put in your criteria

`/leadnote-setup` writes `config/criteria.md` for you; edit it whenever you learn something. The qualifier is only
as good as this page. Put in:

- **What you sell**, in one or two lines.
- **Fit: yes.** The kind of company, as things a website can show: what they do, for whom, size range.
- **Fit: partly.** Close, with one doubt: too big, the matching service is a side line, unclear customers.
- **Fit: no.** Your deal-breakers: freelancers, chains, consumer shops, the wrong trade.
- **Signals that make it stronger.** Hiring, a service page for X, a webshop, a named sector, how long they've existed.
- **Opening line.** What the first sentence should touch on, the tone, and the language.

See [`examples/criteria.md`](examples/criteria.md) for a complete one.

## Cost and time

- **Finding** costs nothing but time. Google tends to block after a fixed number of searches in a row, so LEADNOTE
  works in blocks (12 searches by default) with a rest in between (20 minutes by default), and adjusts the block
  size itself when it meets a block. That makes it about 30 searches an hour. A city with one or two search terms
  takes an hour or two; a whole country can take days in the background. `python run.py plan` tells you before you
  start.
- **Visiting** websites is fast: a few minutes per 200 companies.
- **Qualifying** uses your Claude plan, no API key. Measured in the smoke test: a sieve batch (up to 40 companies,
  Haiku) costs roughly 90,000 to 150,000 tokens, a deep batch of 8 companies (Sonnet) about 140,000. Most of that is
  each sub-agent's fixed overhead, so bigger batches are cheaper per company. `/leadnote-qualify` shows the estimate
  and waits for your OK, and `max_qualify` in `config/niche.json` (default 300) caps how many companies get checked.
- **Briefings** cost about 90,000 tokens for a batch of up to 3 companies, including a little web research.
  `/leadnote-brief` shows the estimate first; `max_brief` (default 25) caps it.

## Google and the pace (read this)

Google's Terms of Service do not allow automated reading of Google Maps. LEADNOTE does it anyway, the way a person
would at a calm pace: one browser, one search at a time, pauses between searches, long rests between blocks, and a
full stop when Google pushes back. **Use it at your own responsibility.** Keep the default pace, don't run several
at once, and expect that Google may still block you for a while (LEADNOTE pauses and continues later; nothing is
lost).

LEADNOTE keeps **business data only**: company name, category, business address, business phone, website, rating
and review count from the Maps listing, and text from the company's own website. It does not open review pages,
does not store reviews or reviewer names, and **removes e-mail addresses** from everything it stores. Briefings
may name decision makers, but only with the name and role the company publishes on its own website. What you then
do with the list (calling, messaging) is subject to the rules for B2B outreach where you are, such as the GDPR in
Europe.

## How it works

- **The grid.** Each area you name is looked up on OpenStreetMap (free, no key), which gives its outline. LEADNOTE
  covers the outline with square cells (a third of the area's longest side, between 3 and 20 km) and searches every
  term in every cell. When a list comes back full and the cell itself is busy, the cell is split into four smaller
  cells one zoom level deeper, up to `max_depth` times. Companies outside the outline are dropped.
- **Duplicates.** One listing can show up in many searches: it is stored once (Maps id). Listings that share a
  website become one company, and listings with the same phone number within 50 metres are merged.
- **The filter.** `category_exclude` drops Maps categories that are certainly wrong (a word in the company name from
  `name_keywords` overrules it). Companies without a website are left out unless you set `keep_without_website`.
- **Resume.** Every search is a row in a local SQLite database (`data/leadnote.db`). Stop at any point; `find`
  continues with what's left, and the learned pace is kept in `data/pace.json`.
- **Qualifying.** `run.py qualify-prep` writes batches to `data/qualify/`; Claude Code's sub-agents
  (`.claude/agents/leadnote-sieve.md` on Haiku, `.claude/agents/leadnote-qualifier.md` on Sonnet) write labels next to
  them; `run.py import-labels` stores them and checks every evidence quote against the stored pages. A quote it
  can't find is marked on the card. `/leadnote-brief` works the same way with `run.py brief-prep` and the
  `leadnote-briefer` sub-agent.
- **The page** is a zero-dependency Node server that asks `run.py json` for the data.

## What's inside

| Path | What |
|---|---|
| `run.py` | The command line: `plan`, `find`, `visit`, `status`, `export`, `qualify-prep`, `brief-prep`, `import-labels` |
| `leadnote/` | Maps search and grid, website visits and signals, qualifying, reports |
| `.claude/commands/` | `/leadnote-setup`, `/leadnote-qualify` and `/leadnote-brief` |
| `.claude/agents/` | The sieve, qualifier and briefer sub-agents |
| `app/` | The local page (Node 20, no dependencies) |
| `examples/` | A complete `niche.json` and `criteria.md` |
| `tests/` | Unit tests: `pip install pytest`, then `python -m pytest -q` |
| `config/`, `data/` | Your niche and your data (kept out of git) |

## Settings

Everything lives in `config/niche.json`; see [`examples/niche.json`](examples/niche.json).

| Key | Default | What |
|---|---|---|
| `country`, `language` | | ISO country code and the Maps interface language (`hl`) for that country |
| `areas` | | OpenStreetMap names: `"Utrecht, Utrecht, Nederland"`, `"Belgium"`, `"Greater Manchester"` |
| `search_terms` | | Maps categories and words, in the country's language |
| `category_exclude`, `name_keywords` | `[]` | The category filter and its override |
| `keep_without_website` | `false` | Keep companies that have no website |
| `grid.cell_km` | `"auto"` | Cell size in km, or `auto` |
| `grid.max_depth` | `3` | How often a busy cell may be split |
| `pace.block`, `pace.rest_minutes` | `12`, `20` | Searches per work block, minutes of rest |
| `max_qualify` | `300` | Most companies to qualify |
| `max_brief` | `25` | Most cold-call briefings per `/leadnote-brief` |

`LEADNOTE_CONFIG` and `LEADNOTE_DATA` (or `--config` and `--data`) let you keep several projects side by side.

## Credits

Built by Julian Verboom ([Viral Conversions](https://viralconversions.io)). MIT licensed; see `LICENSE`.
