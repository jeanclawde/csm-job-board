# Project Learnings

Documenting decisions, what worked, what didn't, and what to do differently next time — for any role type.

---

## 1. JSON-LD is the gold standard

Most modern ATS systems (Workday, Greenhouse, Lever, Ashby) publish structured `application/ld+json` with a `JobPosting` schema. It contains `description`, `responsibilities`, `requirements`, `hiringOrganization` — clean, boilerplate-free.

**What to do:** Make JSON-LD extraction the **first** extraction target, before touching any HTML selectors at all.

```python
# Sketch
for script in soup.find_all("script", type=lambda t: t and "ld+json" in t):
    data = json.loads(script.string)
    if data.get("@type") == "JobPosting":
        return data.get("description", "")
```

---

## 2. Build a per-ATS selector map before scraping

Before running at scale, test 5 URLs from each ATS type and note which selector works.

| ATS | Selector / Method | Notes |
|---|---|---|
| Workday | JSON-LD or `[data-automation-id="jobPostingDescription"]` | `jobPostingDescription` div is clean |
| Greenhouse | JSON-LD or `section#content` | sometimes JS-only |
| Lever | JSON-LD or `.content` | usually fine |
| Ashby | JSON-LD or `main` or `article` | frequently JS-rendered |
| Jobgether | JSON-LD + generic fallback | consistently thin/generic descriptions |
| BambooHR | HTML + `main` | usually accessible |
| Workable | JSON-LD | usually clean |

Sites that fail JSON-LD **and** fall back to generic `main` text → flag as likely JS-heavy or blocked. A sample of 10 URLs would have caught most fallouts before the 400+ run.

---

## 3. Runtime math: ~45–60 min for ~400 jobs

With polite scraping (2s global delay, 6s same-host delay), expect roughly:

- 50–60 URLs/hour on a single host
- 400 URLs → ~45 min to 1.5h depending on host distribution

**Async doesn't help much here** — most job URLs cluster on ~20 hosts. You'd need smart per-host concurrency limits to parallelize without getting soft-banned. Sequential is safer and the resumability makes it a non-issue.

**Rule:** Don't promise a fast turnaround. Budget idle time. Use the cache to resume cleanly.

---

## 4. Sentence scoring beats raw extraction

Raw page text is ~80% boilerplate. Simple extraction looks terrible on a job card. The key insight that made cards actually useful:

```
Score each sentence by signals:
  +4  responsibility hints (responsib*, own, manage, drive, partner...)
  +2  requirement hints (experience, skills, knowledge...)
  +4  CS-specific (customer*, adoption, retention, renewal, onboarding...)
  +3  role framing ("you will", "your role", "responsible for"...)
  -8  company boilerplate ("about us", "best workplace", "headquartered"...)
  -1  too short (< 70 chars)
```

Pick the 2 highest-scoring non-duplicate sentences. This works for most CSM/Sales/Marketing roles. For other role types, adjust the dictionaries:

| Role type | Positive signals to add |
|---|---|
| Sales | quota, territory, pipeline, new business, expansion revenue |
| Marketing | campaign, content, SEO, CAC, acquisition channels |
| Engineering | stack, framework, Agile/Scrum, scale, latency, infra |
| Data/Analytics | dashboard, pipeline, model, ETL, SQL, visualization |

---

## 5. Language and encoding edge cases

Some ATS pages return UTF-8 text decoded as Latin-1, producing mojibake:

```
Ãª  →  ê
dÃ©partement → département
activitÃ©s → activités
```

Repair with:

```python
def fix_mojibake(text):
    if not re.search(r"[ÃÂâ]\S", text):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
        if sum(repaired.count(c) for c in "ÃÂâ") < sum(text.count(c) for c in "ÃÂâ"):
            return repaired
    except:
        pass
    return text
```

Run this early in `clean_text()`, before any other processing.

---

## 6. Schema first, UI second

The card template in this project was built before the description field existed. Retrofitting it worked, but a cleaner sequence is:

1. Define the target card schema (what fields do we want to display?)
2. Build the scraper to produce exactly those fields
3. Scaffold the UI to match

---

## 7. Local cache vs. public repo

The raw scraping cache (`data/job-description-cache.json`) was 2.3MB with full extracted text per job. It stays local only:

- ✅ Commit: `data/jobs.json` (376KB, enriched with short descriptions)
- ✅ Commit: `data/job-description-report.json` (4KB, summary stats)
- ❌ Don't commit: raw extraction caches with full page text

The report is the only artifact that needs to be versioned — it gives you ok/fallback/pending counts and timestamps so you know when to re-scan.

---

## 8. Jobgether is consistently bad data

Jobgether consistently produced generic non-descriptions: *"You will manage complex, evolving customer programs where clarity often needs to be built from ambiguity."* This tells you nothing about the actual role.

**Options for next time:**
- Skip Jobgether listings from the CSV entirely
- Or flag them with a `low_quality_source` tag and de-prioritize their descriptions

---

## 9. Stars must survive broken localStorage

Mobile browsers (especially Safari in private mode) can throw when reading/writing `localStorage`. The app must not blank out if this happens:

```javascript
function loadStarredIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STAR_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.warn('Could not read starred ids. Resetting.', error);
    try { localStorage.removeItem(STAR_KEY); } catch (_) {}
    return [];
  }
}
```

Test this by deliberately corrupting the stored JSON in DevTools before claiming it works on mobile.

---

## 10. GitHub Pages deployment is not instant

The Actions workflow runs in ~12s but GitHub Pages propagation can take 30–60s after a successful deploy. Poll the live URL with retries before declaring victory.

```python
for attempt in range(10):
    try:
        data = json.load(urllib.request.urlopen(live_url, timeout=20))
        if data.get('description_enriched_at'):
            break
    except:
        time.sleep(6)
```

---

## 11. What worked well

| Decision | Outcome |
|---|---|
| Resumable scraper (saves after every URL) | Zero data loss when interrupted |
| Conservative dead-link removal (404/410 only) | Kept ambiguous 403s that were actually alive |
| Sentence scoring for summary selection | Cards actually useful vs. raw page noise |
| Separate cache from public data | Repo stays clean; local cache stays private |
| Mobile-first sticky search + filter panel | Works well on phone without clutter |
| `localStorage` for starring | Right trade-off for single-user phone MVP |

---

## 12. What to do differently next time

1. **Dry-run on 10 URLs first** — catch selector failures and encoding issues before the full run
2. **ATS selector map in the scraper** — lookup table by host/domain, not a generic cascade
3. **Role-specific scoring dictionaries** — pass the role type as a parameter
4. **Flag low-quality sources upfront** — skip or de-prioritize Jobgether-class sources
5. **Schema before UI** — define card shape, then build the pipeline to produce it
6. **Budget 1h for 400 URLs** — sequential + polite is correct but not fast
7. **Propagate GitHub Pages** — add retry loop when verifying the live URL
