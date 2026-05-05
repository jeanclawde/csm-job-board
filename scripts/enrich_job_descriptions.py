#!/usr/bin/env python3
"""Cautiously fetch job offer pages and add short 2-sentence descriptions.

Resumable by design:
- raw fetched/extracted records are saved to data/job-description-cache.json after each URL
- enriched data is written to data/jobs.enriched.json, then can replace data/jobs.json
- ambiguous HTTP errors are not treated as dead jobs; a fallback summary is kept
"""
from __future__ import annotations

import argparse
import html
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
JOBS_PATH = ROOT / "data" / "jobs.json"
CACHE_PATH = ROOT / "data" / "job-description-cache.json"
OUT_PATH = ROOT / "data" / "jobs.enriched.json"
REPORT_PATH = ROOT / "data" / "job-description-report.json"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36; csm-job-board-enricher/1.0"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}

BOILERPLATE_PATTERNS = [
    r"equal opportunity employer.*",
    r"we are an equal opportunity.*",
    r"all qualified applicants.*",
    r"privacy notice.*",
    r"cookie[s]? policy.*",
    r"this website uses cookies.*",
    r"reasonable accommodation.*",
]

RESPONSIBILITY_HINTS = re.compile(
    r"\b(responsib|own|manage|drive|lead|partner|help|support|ensure|deliver|adopt|renew|retain|onboard|success|relationship|portfolio|accounts|customers?)\b",
    re.I,
)
REQUIREMENT_HINTS = re.compile(
    r"\b(experience|skills?|knowledge|background|fluent|english|french|saas|b2b|customer success|csm|crm|salesforce|stakeholder|communication|analytical|technical)\b",
    re.I,
)

@dataclass
class CacheEntry:
    id: str
    url: str
    fetched_at: str
    status: str
    http_status: int | None
    final_url: str | None
    extraction_source: str | None
    raw_description: str
    short_description: str
    error: str | None = None


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def strip_html(value: str) -> str:
    value = html.unescape(value or "")
    soup = BeautifulSoup(value, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(" ")
    return clean_text(text)


def fix_mojibake(text: str) -> str:
    """Repair common UTF-8-as-Latin-1 mojibake seen on some ATS pages."""
    if not text or not re.search(r"[ÃÂâ]\S", text):
        return text
    try:
        repaired = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
        # Only keep the repair if it clearly reduced mojibake markers.
        if sum(repaired.count(ch) for ch in "ÃÂâ") < sum(text.count(ch) for ch in "ÃÂâ"):
            return repaired
    except Exception:
        pass
    return text


def clean_text(text: str) -> str:
    text = fix_mojibake(html.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    for pat in BOILERPLATE_PATTERNS:
        text = re.sub(pat, "", text, flags=re.I | re.S)
    # Remove common navigation/framing fragments that poison summaries.
    text = re.sub(r"\b(skip to main content|careers home|apply now|back to jobs|share this job|job description[: ]*)\b", "", text, flags=re.I)
    text = re.sub(r"\bour people make all the difference in our success\. ?", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def extract_jsonld(soup: BeautifulSoup) -> tuple[str, str] | None:
    for script in soup.find_all("script", type=lambda t: t and "ld+json" in t):
        raw = script.string or script.get_text(" ")
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            # Some pages contain multiple JSON objects or invalid escaping.
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            typ = item.get("@type") or item.get("type")
            types = typ if isinstance(typ, list) else [typ]
            if any(str(t).lower() == "jobposting" for t in types):
                desc = item.get("description") or item.get("responsibilities") or ""
                desc = strip_html(desc if isinstance(desc, str) else " ".join(map(str, desc)))
                if len(desc) > 80:
                    return desc, "jsonld:JobPosting"
            for key in ("@graph", "graph", "itemListElement"):
                if key in item:
                    stack.append(item[key])
    return None


def extract_from_html(html_text: str) -> tuple[str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "header", "footer", "nav"]):
        tag.decompose()

    jsonld = extract_jsonld(BeautifulSoup(html_text, "html.parser"))
    if jsonld:
        return jsonld

    selectors = [
        '[data-automation-id="jobPostingDescription"]',
        '[data-testid="job-description"]',
        '[class*="job-description"]',
        '[class*="jobDescription"]',
        '[id*="job-description"]',
        '[id*="jobDescription"]',
        '[class*="description"]',
        'main',
        'article',
        'body',
    ]
    best = ""
    best_sel = "body"
    for sel in selectors:
        for el in soup.select(sel)[:5]:
            text = clean_text(el.get_text(" "))
            if len(text) > len(best):
                best = text
                best_sel = sel
        if len(best) > 600 and sel != "body":
            break

    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if meta and len(best) < 120:
        m = clean_text(meta.get("content", ""))
        if len(m) > len(best):
            best = m
            best_sel = "meta:description"
    return best[:12000], f"html:{best_sel}"


def split_sentences(text: str) -> list[str]:
    # Normalize bullets into sentence-ish chunks before splitting.
    text = re.sub(r"\s*[•·]\s*", ". ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    cleaned = []
    bad = re.compile(r"\b(cookie|privacy|terms|captcha|sign in|login|equal opportunity|accommodation|benefits? package|posted|workday|our people make)\b", re.I)
    for p in parts:
        p = clean_text(p).strip(" -–—•")
        if 45 <= len(p) <= 260 and not bad.search(p):
            cleaned.append(p)
    return cleaned


def sentence_score(sentence: str) -> int:
    score = 0
    if RESPONSIBILITY_HINTS.search(sentence): score += 4
    if REQUIREMENT_HINTS.search(sentence): score += 2
    if re.search(r"\b(customer success|customers?|clients?|accounts?|adoption|retention|renewal|onboarding|stakeholders?)\b", sentence, re.I): score += 4
    if re.search(r"\b(you will|you'll|your role|responsible for|mission|as a)\b", sentence, re.I): score += 3
    if re.search(r"\b(about us|about the company|who we are|founded|headquartered|benefits|salary|compensation|best workplace|company you.?ll join|growth and development|professional goals|actual hiring salaries|nasdaq|culture has been recognized)\b", sentence, re.I): score -= 8
    if len(sentence) < 70: score -= 1
    return score


def trim_sentence(s: str, max_chars: int = 210) -> str:
    s = clean_text(s)
    if len(s) <= max_chars:
        return s.rstrip(".;") + "."
    cut = s[:max_chars].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def fallback_summary(job: dict[str, Any], reason: str = "") -> str:
    loc = job.get("location") or "the listed location"
    company = job.get("company") or "the company"
    title = job.get("title") or "Customer Success role"
    if reason:
        return f"{company} is hiring for {title} in {loc}. The original posting could not be fully extracted yet ({reason}), so open the offer for details."
    return f"{company} is hiring for {title} in {loc}. Open the original posting for the full responsibilities, requirements, and benefits."


def summarize(job: dict[str, Any], text: str) -> str:
    text = clean_text(text)
    if len(text) < 80:
        return fallback_summary(job, "limited page text")

    sentences = split_sentences(text)
    if not sentences:
        return fallback_summary(job, "limited page text")

    # Pick the most role-relevant sentence first, then a complementary requirement/responsibility sentence.
    ranked = sorted(sentences, key=sentence_score, reverse=True)
    first = ranked[0]
    second_pool = [s for s in sentences if s != first and REQUIREMENT_HINTS.search(s)] or [s for s in ranked[1:] if s != first]
    second = second_pool[0] if second_pool else ""

    company = job.get("company") or "The company"
    title = job.get("title") or "this Customer Success role"
    prefix = f"{company} is hiring for {title}."

    out = []
    if sentence_score(first) >= 3:
        out.append(trim_sentence(first))
    else:
        out.append(prefix)
    if second and sentence_score(second) >= 3:
        out.append(trim_sentence(second))
    elif out[0] != prefix:
        out.append(prefix)
    summary = " ".join(out[:2])
    # Hard cap for card layout.
    if len(summary) > 430:
        summary = summary[:430].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return summary


def fetch(session: requests.Session, url: str, timeout: int) -> tuple[int | None, str | None, str | None, str | None]:
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        ctype = resp.headers.get("content-type", "")
        if "text" not in ctype and "html" not in ctype and resp.text[:100].lstrip().startswith("{") is False:
            return resp.status_code, resp.url, None, f"non-html content-type: {ctype}"
        return resp.status_code, resp.url, resp.text, None
    except Exception as e:
        return None, None, None, type(e).__name__ + ": " + str(e)[:300]


def enrich_one(session: requests.Session, job: dict[str, Any], timeout: int) -> CacheEntry:
    now = datetime.now(timezone.utc).isoformat()
    http_status, final_url, body, err = fetch(session, job["job_url"], timeout)
    if err or not body:
        short = fallback_summary(job, err or f"HTTP {http_status}")
        return CacheEntry(job["id"], job["job_url"], now, "fallback", http_status, final_url, None, "", short, err)
    desc, source = extract_from_html(body)
    short = summarize(job, desc)
    status = "ok" if len(desc) >= 120 else "fallback"
    if status == "fallback":
        short = fallback_summary(job, "limited page text")
    return CacheEntry(job["id"], job["job_url"], now, status, http_status, final_url, source, desc[:8000], short, None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--host-delay", type=float, default=6.0)
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    data = load_json(JOBS_PATH, {})
    jobs = data.get("jobs", [])
    cache_raw = load_json(CACHE_PATH, {"entries": {}})
    entries: dict[str, Any] = cache_raw.get("entries", {})
    session = requests.Session()
    session.headers.update(HEADERS)
    last_host: dict[str, float] = {}

    processed = 0
    for idx, job in enumerate(jobs, 1):
        jid = job["id"]
        if not args.force and jid in entries and entries[jid].get("short_description"):
            continue
        if args.limit is not None and processed >= args.limit:
            break
        host = urlparse(job["job_url"]).netloc
        wait = args.host_delay - (time.monotonic() - last_host.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        if processed:
            time.sleep(args.delay)
        print(f"[{idx}/{len(jobs)}] {job.get('company')} — {job.get('title')} — {host}", flush=True)
        entry = enrich_one(session, job, args.timeout)
        entries[jid] = asdict(entry)
        last_host[host] = time.monotonic()
        processed += 1
        save_json(CACHE_PATH, {"generated_at": datetime.now(timezone.utc).isoformat(), "entries": entries})

    # Merge descriptions back into jobs.
    ok = fallback = errors = 0
    for job in jobs:
        e = entries.get(job["id"], {})
        if e.get("short_description"):
            job["short_description"] = e["short_description"]
            job["description_status"] = e.get("status")
            job["description_source"] = e.get("extraction_source")
            if e.get("status") == "ok":
                ok += 1
            else:
                fallback += 1
            if e.get("error"):
                errors += 1
        else:
            job["short_description"] = fallback_summary(job, "not scanned yet")
            job["description_status"] = "pending"

    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    data["description_enriched_at"] = data["generated_at"]
    save_json(OUT_PATH, data)
    report = {
        "generated_at": data["generated_at"],
        "total_jobs": len(jobs),
        "cached_entries": len(entries),
        "ok": ok,
        "fallback": fallback,
        "errors": errors,
        "pending": sum(1 for j in jobs if j.get("description_status") == "pending"),
    }
    save_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2), flush=True)

if __name__ == "__main__":
    main()
