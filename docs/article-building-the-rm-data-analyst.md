# How I built an AI data analyst for a public radio station

Radio Milwaukee runs four streaming brands: 88Nine, HYFIN, 414 Music, and Rhythm Lab Radio. Add the website, the social accounts, the email list, donations, Nielsen ratings, and the finance spreadsheets, and on any given week our numbers live in something like eight different places, each with its own login and its own idea of what a "listener" is.

So when a director asked a normal question, the honest answer was usually "give me a day." How is HYFIN's cume trending year over year? Which newsletters actually drive opens? Did the spring pledge campaign move streaming at all? Every one of those meant exporting a spreadsheet from one tool, exporting another from a second tool, and lining them up by hand. The data existed. Getting an answer out of it did not.

I built a thing to fix that. This is how it works, what's under it, and the parts I'd want a peer at another station to steal.

A quick note on who built it: mostly me, working with AI coding tools (Claude Code) as a pair programmer. I'm not a traditional engineer. I come at this from radio and product and system design. If that describes you too, the takeaway is that a project like this is now within reach for a small shop, which was not true a couple of years ago.

## What it actually is

Two pieces.

The first is a data warehouse: one Postgres database where every source lands in its own labeled section. Triton streaming data here, donations there, Nielsen over here, and so on. Nothing fancy conceptually. It's the "one place where the numbers live" that we never had.

The second is the part people actually touch: a dashboard at data.radiomilwaukee.org with a chat panel called the Radio Milwaukee Data Analyst. You can read the charts like a normal dashboard, or you can open the chat and ask a question in plain English. "How many active donors do we have and what's their total lifetime giving?" "Break down streaming by device for HYFIN." "What caused the January revenue spike?" It answers in a few seconds, and it cites where each number came from.

The dashboard is nice. The chat is the point. A development director should not have to learn SQL or remember which of six tools holds the cume number. They should be able to ask.

## How I planned it

One decision did more work than any other: each vendor's data is sacred and gets copied in exactly as the vendor sends it, untouched.

That sounds boring. It saved the project. Triton, Funraise, Nielsen, Mailchimp, Google Analytics, and Meta all disagree about field names, date formats, and what counts as a session or a reach. If I'd tried to mash them into one "clean" shape on the way in, every vendor change would have broken something, and I'd never trust the numbers. Instead, each source gets its own schema that mirrors the source. When two sources need to meet, that happens in a separate layer built for joining, called marts, which I can rebuild whenever I want without touching the raw data.

A few other calls from the planning stage that I'd defend:

I built streaming first and designed everything else to slot in later without a rewrite. Streaming is the daily heartbeat, so it forced the hard questions early.

I picked the grain deliberately instead of storing everything at the finest level "just in case." Cume, for example, is non-additive. You cannot add Monday's cume to Tuesday's and get anything real. So I store it at the exact grains we report at (hourly, daily, weekly, monthly) rather than trying to roll it up after the fact.

I minimized donor data on purpose. The warehouse holds no donor names, no raw email addresses, no phone numbers. It keeps a one-way hashed email, city and state, giving totals, and dates. That's enough for analysis and a lot less to worry about if anything ever leaked. For a nonprofit handling members' information, that felt like the responsible default, not an afterthought.

## The stack

Plain version, with why each one is there:

- Postgres, hosted on Neon. The warehouse. Boring, reliable, and everyone can query it.
- A small ingestion service written in Python (FastAPI), running on Fly.io in their Chicago region. This is the thing that catches incoming reports and loads them.
- The dashboard is a React app (built with Vite) hosted on Vercel.
- The assistant is built on CopilotKit, an open-source framework for putting AI chat into an app, with Claude (Anthropic) as the model doing the reasoning.
- Sign-in runs on Clerk, and I added my own access rules on top so only Radio Milwaukee staff and board can get in.
- For the sources that already have good connectors (Google Analytics, Meta, Mailchimp), I use Coupler.io to pipe them into the warehouse instead of writing that plumbing myself.

None of this is exotic. That's deliberate. I wanted parts I could reason about and replace.

## The assistant, and the tools it can use

Here's the thing that makes an AI analyst trustworthy instead of terrifying: it does not make up numbers. It can't. The model has no idea what our cume is. What it has is a set of tools it's allowed to call, and every number in an answer comes back from one of those tools hitting the real warehouse.

The assistant has five tools:

- One for getting a curated metric (streaming TLH, active donors, sustainer MRR, and so on).
- One for listing which curated metrics exist, so it can find the right one.
- One for reading the warehouse's structure, so it knows what tables and columns are actually there.
- One for running a read-only SQL query, for the long tail of questions no curated metric covers.
- One for pulling the full text and topic tags of a specific email newsletter.

The curated metrics live in a registry, which is just a single definition of each important number that both the chat and the dashboard read from. That matters more than it sounds. It means the chat and the dashboard can never quietly disagree. When the assistant says active donors is 14,087, that's the same definition the dashboard renders. There's no second version of the truth.

For everything the registry doesn't cover, the assistant can write its own SQL. That's powerful and a little scary, so it's fenced in hard. The query runs as a restricted, read-only database role that can look but never change anything. Only a single SELECT is allowed, with a row cap and a 15-second timeout, and a validator rejects anything that smells like a write. Donor data is de-identified before it's reachable at all. The model can read; it cannot delete, update, or wander into anything it shouldn't.

A couple more guardrails worth mentioning. The assistant's instructions live on the server, not in the browser, so a clever user can't talk it into a new personality. Every figure it reports has to name its source and time window. And the whole thing sits behind sign-in plus an allowlist, so it's staff and board only, with the donor data treated as the sensitive thing it is.

The effect, when it works, is that someone can ask "do event-promo emails or regular newsletters get better click rates" and get an answer that's grounded in our actual Mailchimp data, with the query it ran shown right there if they want to check the work.

### How it works through a question

It's worth slowing down on what happens between you hitting enter and an answer appearing, because it isn't one shot. The assistant takes several steps, and it can correct itself along the way.

Say you ask which dayparts have the most listening on HYFIN. Claude first checks the list of curated metrics to see if one already answers it. If yes, it calls that and you're done. If not, it reads the warehouse structure to learn what tables and columns actually exist, writes a SQL query against the streaming tables, and runs it. If the query comes back with an error, say it guessed a column name wrong, it reads the error, rewrites the query, and tries again. Once it has real rows back, it writes the answer in plain language and names the metric or the query and the time window it used.

That self-correcting loop is most of why it feels capable instead of brittle. Early on I capped it at too few steps and it would give up halfway through a harder question. Giving it room to discover, try, fail, and retry is what lets it handle the messy real ones.

Two more things shape how it behaves. Its instructions, the equivalent of a job description, tell it that it's a Radio Milwaukee analyst, who the four brands are, that it has to cite every number, and that "the warehouse doesn't track that yet" is a perfectly good answer. That last rule matters more than it looks. I would much rather it admit a gap than invent a plausible number, because a confident wrong number is worse than no number. It also knows what you're looking at, the active tab and the filters, so "why did this move" is grounded in the figures actually on your screen.

## What CopilotKit is, in plain English

If you've never built software, "CopilotKit" means nothing, so here's the version I'd give a colleague.

When you type a question into the chat box, three things have to happen. Your question goes to the AI model. The model, if it needs data, has to be able to call your functions, the tools I described above. And the answer has to stream back into the chat, word by word, with the charts and tables formatted nicely.

CopilotKit is the wiring for all of that. It gives you the chat panel for the React app, and it runs a small piece of server code, the runtime, that sits between the chat and the model. When Claude decides it needs a number, the runtime runs the matching tool, hands the result back to Claude, and Claude turns it into a sentence. CopilotKit is what lets the model reach into our warehouse in a controlled way instead of guessing.

So I didn't build the chat box or the model or the streaming from scratch. I built the five tools, the instructions, and the data behind them, and CopilotKit connected them to Claude. That division of labor is most of why one person could do this.

## What you can ask, by role

The people I built this for ask very different questions, so here's roughly what each one reaches for. These are phrased the way you'd actually type them.

If you run programming, you care about what's working on air and where you lose people:

- "Which dayparts have the highest average active sessions on HYFIN?"
- "How is 88Nine's time spent listening trending over the last six months?"
- "What devices are people using to stream 414 Music, and how has that shifted?"
- "What's the age and gender breakdown of our broadcast audience?" (that one comes from Nielsen)

If you run development, you care about audience size, loyalty, geography, and donors:

- "How is cume trending year over year for 88Nine?"
- "How many active donors do we have, and what's their total lifetime giving?"
- "What's our recurring versus one-time giving split, and current sustainer MRR?"
- "Which markets is our streaming audience concentrated in?" (useful for grant narratives)
- "What caused the revenue spike in January?"

If you run underwriting, you care about sellable inventory and who's listening:

- "What's average active sessions by daypart for 88Nine, and where's the unsold time?"
- "What's the device split, how many people are on smart speakers versus mobile versus in the car?"
- "How much underwriting revenue did we book this quarter?"

If you're in finance or leadership, you care about the whole picture against plan:

- "Revenue versus budget, year to date."
- "What's our revenue mix by category this month?"
- "How is membership tracking, net new members and MRR?"

One honest note: the assistant only knows what's loaded. Ask about something we haven't wired up yet and it will tell you, not guess.

### The questions it's really for

Single-source questions are useful. But the reason to build a warehouse at all is the questions that cross sources, the ones that used to be a day of lining up spreadsheets. This is where it earns its keep:

- "Did the spring campaign move streaming, web traffic, and donations? Compare the campaign window to the month before."
- "Do our top donor states line up with where we have the most streaming audience?"
- "Which newsletters drove the most donations or stream starts?"
- "What's our total reach for 88Nine, broadcast plus streaming?" (Nielsen and Triton, which I keep in separate places on purpose and only join for a question like this)
- "Walk the funnel: paid social to organic reach to web sessions to stream starts to email signups to donations."

I'll be straight about where this stands. The assistant can join across sources today wherever the data is loaded, and several of those already work. The richest ones lean on a layer I'm still building that pre-joins the common stories so they come back instantly, plus a couple of sources still filling in. But that list is the whole point. A warehouse is just storage until someone asks it a question that spans it.

## Handling Triton streaming reports

Triton is our streaming analytics vendor. They don't have a tidy API I could just call, but they can email a scheduled report. So I leaned into that.

Inside Triton I set up the reports we care about, six of them: hourly listening, daily cume, weekly cume, monthly cume, monthly geography, and monthly device breakdown. Each one is scheduled to email itself out every morning (or every Monday, or the first of the month, depending on the report) as a spreadsheet.

Those emails go to a dedicated inbox. A webhook on the Fly.io service wakes up whenever one arrives, reads it, and figures out which report it is. The trick that makes this clean: Triton uses the saved report's name as the email subject, and I named each report to start with a tag like [WMS-Q1-HOURLY]. The service just reads the tag and routes the file to the right loader. No guessing, no fragile parsing of the email body.

The loader parses the spreadsheet and writes it into the warehouse. Every loader is idempotent, which is the one piece of jargon worth keeping: it means running the same report twice does nothing bad. If a report arrives late, or I re-send last month's file, the loader updates the rows that changed and leaves the rest alone. No duplicates, no double-counting. That property is what lets me sleep. Reports can show up out of order, get resent, overlap, and the warehouse stays correct.

To backfill history, I ran the same loaders by hand against bulk exports. The hourly report alone was around sixty thousand rows going back to the start of 2024. Same code, two front doors: a webhook for the daily drip, my laptop for the one-time history.

## Handling Nielsen reports

Nielsen is the strange one, and I'm a little proud of how it turned out.

The Nielsen "Vital Signs" report does not come as a clean table. It comes as a wide grid: metrics down the side, survey periods across the top, broken into sections like Estimates, P1 information, daypart trends, and demographic breakdowns by age, gender, and ethnicity. It's built to be read by a person looking at a page, not loaded into a database.

So the loader flips it. It unpivots that grid into one long, narrow table where each row is a single fact: this station, this demo, this daypart, this period, this section, this metric, this value. Once it's in that shape, it's queryable like anything else, and our four-brand world coexists with Nielsen's broadcast world without me having to force them together. Streaming and broadcast stay in separate places and only meet when I want to tell a total-reach story.

Two details I like. The report describes itself, so I don't have to configure anything per upload: the station comes from the report title, the demo and daypart from the preamble. Drop in a different station's report and it just files itself correctly. And it's idempotent in a useful way. Nielsen's monthly trend reports overlap almost entirely with the previous month, so re-uploading refreshes the shared months, adds the new one, and keeps the older months that have aged off the current report. The history grows past Nielsen's own window instead of getting truncated.

Loading it is deliberately dumb on purpose: there's a plain web page where someone exports the report from Nielsen and uploads the file. No integration to maintain, no credentials to rotate. For a report that comes once a month and is licensed and confidential, a human pressing a button is the right amount of technology.

## What I'd tell another station

A few honest things.

Most of the work was not the AI. It was the plumbing: catching reports, parsing vendor formats, deciding on grains, keeping the loads idempotent, getting the donor privacy right. The chat is the last ten percent that makes the other ninety percent usable. If you're tempted to start with the shiny assistant, start with the boring warehouse instead.

Trust is a feature you build, not a thing you assume. The reason I let an AI near our numbers at all is that it can only read, it has to cite, and it can't touch donor identities. Take any of those away and I wouldn't ship it.

You don't need a big team anymore, but you do need taste and patience. AI coding tools got me from "I have an idea" to "it's running in production" mostly solo. They did not make the architecture decisions for me, and the architecture decisions are what this project lives or dies on.

And it's genuinely not done. The marts layer that joins everything for the best cross-source stories is still coming. Some sources are still landing. But a director can already open a browser, ask a real question, and get a cited answer in the time it used to take to find the right login. For us, that's the whole game.

If you're at a station and want to compare notes, I'm easy to find.
