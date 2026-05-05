# TODO

## Step 1 — Job-board MVP

- [x] Import current CSM roles CSV into static JSON.
- [x] Build a mobile-first list of offers.
- [x] Add filters: search, region, ATS provider, department, company.
- [x] Add starred shortlist stored locally in the browser.
- [x] Add export/import for starred jobs.
- [ ] Publish the private repository to GitHub.
- [ ] Decide hosting strategy:
  - GitHub Pages if public preview is acceptable.
  - Password-protected Vercel/Netlify/Cloudflare Access if the page must stay private.

## Step 2 — Offer-content enrichment

- [ ] Create a scraper/fetcher for each ATS provider: Ashby, Greenhouse, Lever, Workday, Teamtailor, BambooHR, Workable.
- [ ] Store full job descriptions under `data/descriptions/` or in an enriched `jobs.json`.
- [ ] Add a short generated summary per offer.
- [ ] Add tags extracted from descriptions: segment, seniority, language, travel, remote policy, tools, salary if available.
- [ ] Add stale/dead-link detection.

## Step 3 — Fit scoring against her profile

- [ ] Add her CV/profile as structured JSON once provided.
- [ ] Define scoring criteria: location, language, seniority, domain fit, CSM motion, required tools, red flags.
- [ ] Generate a match score and a 3–5 bullet rationale for each offer.
- [ ] Add filters for `high fit`, `maybe`, and `skip`.
- [ ] Add notes/status fields: interested, applied, rejected, interview, archived.

## Nice-to-have

- [ ] Add PWA install support for smartphone home screen.
- [ ] Add shareable filtered views via URL parameters.
- [ ] Add notes per job. Local-first first, synced later if needed.
- [ ] Add CSV/JSON export of shortlisted offers.
