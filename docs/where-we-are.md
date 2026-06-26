# Where we are with the data project

Last updated: June 23, 2026

## The short version

We're building one place that holds all of Radio Milwaukee's data: streaming
numbers, website traffic, social media, email newsletters, donations, and
eventually finance. Right now that data lives in a dozen different tools and
spreadsheets, and nobody can see the whole picture at once. The point of this
project is to fix that.

The end goal: connect that single database to Hex.tech and build a data app
the whole organization can actually use. Not another spreadsheet someone has
to update by hand. A real app where a program director, the development team,
underwriting, and the executive director each open it and see the numbers that
matter to them, kept current automatically.

## The pieces, in plain terms

- **Neon** is the database. Think of it as the warehouse where every number
  eventually gets stored, organized the same way no matter where it came from.
- **Coupler.io** is the delivery service. It connects to Google Analytics,
  Facebook, Instagram, and Mailchimp, pulls the data on a schedule, and drops
  it into the warehouse. No manual exporting.
- **Hex.tech** is where people will actually look at the data. It reads from
  the warehouse and turns it into charts, dashboards, and the app itself.

So the flow is: the tools we already use, into Coupler, into Neon, into Hex.

## What's already done

The streaming side is finished. Every listening number from Triton (our four
brands: 88Nine, HYFIN, 414 Music, Rhythm Lab Radio) flows into the warehouse
automatically every morning. Two and a half years of history is loaded and the
daily updates run on their own.

## What we're working on right now

Adding the marketing and audience data. This week that means:

- **Google Analytics (websites).** This is live. The Radio Milwaukee website's
  full history is in the warehouse now, back to September 2023 when that
  Analytics account started, about 2 million sessions. We're adding HYFIN's
  website next so both sit side by side.
- **Next up for the websites:** breaking traffic down by location, by device
  (phone vs desktop), by page, and by the actions people take (like clicking
  to start the stream or donate). And an hour by hour view so we can line up
  web activity against when people are actually listening.
- **After that:** Facebook and Instagram for all three brands (Radio
  Milwaukee, HYFIN, and Grace Weber's Music Lab), then the Mailchimp
  newsletters.

Each source gets connected once, then it keeps itself updated.

## What comes after

Once the audience data is flowing, the same approach extends to donations
(Funraise) and finance. The finance numbers our executive director keeps in a
spreadsheet will get pulled in automatically, so nobody has to change how they
work, the data just shows up in the warehouse too.

Then the real payoff: Hex reads all of it and we start building the app, one
view per audience, so the whole organization is working from the same numbers.

## Honest status

The plumbing is the slow part, and we're in it. Connecting each source has its
quirks, and we just spent real time sorting out one database connection issue.
But the streaming side proves the model works end to end, and the first
website data is now live in the warehouse. The pattern is set. The rest is
repeating it, source by source.
