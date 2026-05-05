# CSM Job Board

Public GitHub project for browsing 428 live Customer Success Manager roles from the provided CSV.

## What exists now

- Static, mobile-first job board: `index.html`, `styles.css`, `app.js`
- Data generated from the CSV: `data/jobs.json`
- Filters by search, region, ATS provider, department, company, and starred-only mode
- Starred shortlist saved in the browser with `localStorage`
- Dead-link scan report: `data/dead-jobs-report.json`

## Starring strategy

For the first version, browser storage is the right trade-off:

- **Pros:** zero login, no backend, works perfectly on smartphone, private by default to her device/browser.
- **Cons:** stars do not automatically sync across browsers/devices and can disappear if browser data is cleared.

If she needs cross-device sync later, add one of these:

1. **Supabase/Firebase anonymous auth** — easiest proper product route.
2. **GitHub Gist token** — hacky but simple if only one user.
3. **Backend API + tiny DB** — best if we later add profiles, scoring, notes, and statuses.

## GitHub Pages caveat

The repository can be private, but a GitHub Pages website is generally public unless the account/org has GitHub Enterprise private Pages. If privacy of the live site matters, use Vercel/Netlify with password protection, Cloudflare Access, or GitHub Pages only as an internal/dev preview.

## Local preview

```bash
python3 -m http.server 8080
# then open http://localhost:8080
```

## Learnings

See [LEARNINGS.md](LEARNINGS.md) for what worked, what didn't, and what to do differently for the next role-type job board.

## Data refresh

Replace the CSV and regenerate `data/jobs.json` using the conversion logic in the initial commit, or later add a script under `scripts/`.
