# Linking Google Play to Firebase / GA4 (Android app data)

A short guide for whoever manages our Google Play account. Following this once
per app gets Android store-acquisition data (installs, where installs come from)
flowing into our analytics warehouse automatically.

Last updated: June 2026.

## What this does and why

Our apps already report **in-app** activity (sessions, active users, retention)
to Google Analytics through the Firebase SDK built into them. What's missing on
Android is the **store side** — how many people see the Play listing, where
installs come from (organic search, explore, referral), and install/uninstall
counts from the store.

Linking Google Play to Firebase fills that gap. Once linked, Play's store data
shows up in the same GA4 property as the in-app data, and it then flows into our
Neon warehouse through the existing pull — no new tools.

This is **Android only**. Apple's App Store does not offer an equivalent link.

## Who can do this

You need **both** of these:
- **Owner** on the Firebase project, and
- **Admin / manage** rights on the **Google Play Console** developer account.

If you don't hold both, ask whoever manages the Play account to do it (or to
grant you access first).

## The steps — do this once per app

We have two apps, each in its own Firebase project:
- `radio-milwaukee-app-2024` (Radio Milwaukee)
- `hyfin-from-radio-milwaukee` (HYFIN)

For each one:

1. Go to **console.firebase.google.com** and open the project.
2. Click the **⚙️ gear → Project settings**.
3. Open the **Integrations** tab.
4. Find the **Google Play** card and click **Link**.
5. Select the Android app in that project to associate with our Play listing.
6. Confirm.

That's it. Repeat for the second project.

## What you get after linking

In each app's GA4 property, the **Acquisition** reports start showing Android
store data:
- Play store-listing visitors
- Install source (organic search vs. explore vs. referral)
- Play install / uninstall events

Because this lands in the same GA4 property as the in-app data, it reaches our
Neon warehouse through the existing Coupler pull.

## Caveats

- **Forward-looking.** Data starts accruing after you link — there's little or no
  backfill, so link it sooner rather than later.
- **Android only.** There is no App Store Connect equivalent; iOS store-funnel
  data would require a separate, custom build (out of scope for now).
- After linking, the data team may need to add the new acquisition fields to the
  warehouse pull so they come all the way through.

## After you've linked both apps

Tell the data team (Tarik) it's done. We'll confirm the Play data is appearing
in GA4 and update the warehouse pull to include the new acquisition fields.
