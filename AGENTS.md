# Terroir Atlas — daily editorial updates

This checkout owns the existing Site `appgprj_6aa55222bf1081919621a3997b471852`, at https://terroir-atlas-jy.dark-skunk-1225.chatgpt.site . Preserve its identity and audience. Never create a replacement Site. Only the Site-owning agent edits or publishes; delegated agents may research and return findings without editing or calling Sites.

The user authorized daily internet research and publication of winery and wine information, wine news, harvest updates, events, weather observations and verified natural disasters on the world map. Daily schedule: 09:00 Asia/Shanghai. They have not supplied invitees; do not send invitations or change audience.

## Daily work

1. Read the existing datasets, recent event history and current date before searching. Read Sites building/hosting instructions and call get_site before editing this existing Site.
2. Search multiple countries/continents. Prefer wineries, regional associations, universities, meteorological or civil protection agencies, and event organizers. Start with new publications since last checked date; upcoming events may extend 60 days. Open primary pages and confirm the facts and dates. Do not treat search snippets as verification. Search news and natural-disaster categories each run, but do not create items merely to fill a category.
3. Update `data/events.json`. Preserve stable IDs. Deduplicate by event subject, dates and location, not just URLs. Keep occurrence dates separate from source publication and retrieval dates. Unknown end/publication dates are null. Cancellation and corrections update the original item; record previous values plus reason/source/check time in `data/event-history.json`. Use short original Chinese summaries, never full copied articles.
4. Each event requires source URL/name, checked date, verification description, country/region, coordinates and explicit location precision. Use an evidenced location or clearly identified region/town representative point. Never invent parcel boundaries, ownership, planting data, precise disaster footprints, casualty counts or ongoing alert status. Forecasts and agricultural observations are `weather`; confirmed disasters are `disaster`. If facts are uncertain, omit or attribute them explicitly, and do not mark them independently verified.
5. Add useful, verified winery/wine discoveries to `data/catalog-seed.json` with stable IDs and original sources. A wine and its vintage are distinct records; varietal composition belongs to the vintage when it varies. Reuse existing grape/winery/region IDs. Leave coordinates null when unverified; connect to an already-known region only when the source supports that connection. The map displays a known-region link when a wine has no winery coordinates. Production D1 overrides and community records take precedence; do not overwrite or reset them. Do not rerun `seed.mjs` or `add-initial-wines.mjs`; they were one-time bootstrap scripts.
6. A typical run adds at most 10 distinct meaningful events and 5 new wine/winery records, selecting quality over volume. Keep old events as history; the UI filters current items by dates. If no meaningful changes, do not redeploy just to manufacture activity.
7. Run `node scripts/validate-data.mjs`, then the Sites build wrapper. For data-only changes, do not modify schema/migrations or repeat unrelated UI tests. Commit and push exact source with a short-lived credential kept only in memory, package with the Sites helper and deploy to the same current audience. Verify terminal deployment success. Do not change runtime OWNER_EMAIL or membership. Never expose credentials.
8. On a source outage, skip that source and continue elsewhere. On deployment failure keep the current live version intact, report the actionable issue and do not claim the update went live. Notify the user only when there is meaningful new content, a failure requiring attention, or an action they need to take; stay quiet when nothing meaningful changed. Do not send emails or messages to other people.

## Structure

- `public/`: existing map, community and catalogue UI. `worker/`: Cloudflare Worker APIs; D1 and R2 store durable submissions, members, published versions and attachments.
- `db/schema.ts` and `drizzle/`: schema-only generated migrations. Applied migrations are immutable.
- `data/catalog-seed.json`: initial/curated sourced catalogue, merged with production community changes. `data/events.json`: daily editorial event feed. `data/event-history.json`: editorial corrections.
- `npm run build` embeds static assets into `dist/server/index.js`. `npm run dev` is a local-only preview with a test identity injected by a proxy; this proxy is never deployed. `npm test` runs isolated real D1/R2 emulation for authorization and publishing conflicts.
- Every write API checks identity, membership and origin. Never add a public admin switch or frontend-only authorization. Production owner bootstrap uses the runtime secret OWNER_EMAIL and the platform-asserted signed-in identity.

## Shared-data rules

Preserve source evidence and immutable version history. Repeated imports are idempotent. Editing requires the expected revision/base version. Reviewers cannot approve their own submissions. Owner self-publication requires explicit action plus reason and is recorded. Invitations register app roles only; the private Site sharing gate must separately allow each visitor.
