#!/usr/bin/env python3
"""Cautiously scan job offer URLs and remove confidently dead ones.

Conservative by design: only removes strong 404/410/expired signals.
Network errors, timeouts, 403/429, and ambiguous pages are kept.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "jobs.json"
REPORT_PATH = ROOT / "data" / "dead-jobs-report.json"

UA = "Mozilla/5.0 (compatible; CSMJobBoardDeadLinkCheck/1.0; +https://github.com/jeanclawde/csm-job-board)"
TIMEOUT = (6, 14)
GLOBAL_DELAY = 0.35
HOST_DELAY = 1.25
MAX_BYTES = 160_000

DEAD_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"this job (posting|opening|position) (is no longer available|has expired|has been closed|is closed)",
        r"(job|posting|position|opening) (not found|no longer exists|is no longer active)",
        r"sorry, this job (is no longer available|has expired)",
        r"the job you are looking for (is no longer available|could not be found)",
        r"we couldn't find this job",
        r"404\s*(error|not found)",
        r"not found\s*[–-]\s*404 error",
        r"this opening is no longer available",
    ]
]

# Some ATS custom 404 pages are huge but still have a clean 404 status.
DEAD_STATUSES = {404, 410}
KEEP_STATUSES = {401, 403, 429, 500, 502, 503, 504}


def fetch(session: requests.Session, url: str) -> tuple[str, int | None, str, str]:
    """Return status: alive/dead/keep, http_status, reason, final_url."""
    try:
        with session.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True, stream=True) as r:
            status = r.status_code
            final_url = r.url
            chunks = []
            total = 0
            for chunk in r.iter_content(chunk_size=8192, decode_unicode=False):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= MAX_BYTES:
                    break
            text = b"".join(chunks).decode(r.encoding or "utf-8", errors="ignore")
    except requests.RequestException as exc:
        return "keep", None, f"network_error:{exc.__class__.__name__}", url

    text_sample = re.sub(r"\s+", " ", text[:MAX_BYTES])
    lowered_final = final_url.lower()

    if status in DEAD_STATUSES:
        return "dead", status, f"http_{status}", final_url
    if status in KEEP_STATUSES:
        return "keep", status, f"ambiguous_http_{status}", final_url
    if any(marker in lowered_final for marker in ["/404", "not-found", "notfound"]):
        # Only remove if the page text also supports it.
        if any(p.search(text_sample) for p in DEAD_PATTERNS):
            return "dead", status, "404_final_url_and_text", final_url
    for pattern in DEAD_PATTERNS:
        if pattern.search(text_sample):
            return "dead", status, f"text:{pattern.pattern[:60]}", final_url
    return "alive", status, "ok_or_ambiguous_alive", final_url


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    session = requests.Session()
    last_host: dict[str, float] = defaultdict(float)
    results = []

    for i, job in enumerate(jobs, 1):
        url = job.get("job_url", "")
        host = urlparse(url).netloc.lower()
        wait = max(0, HOST_DELAY - (time.monotonic() - last_host[host]))
        if wait:
            time.sleep(wait)
        status, http_status, reason, final_url = fetch(session, url)
        last_host[host] = time.monotonic()
        results.append({
            "id": job["id"],
            "company": job.get("company"),
            "title": job.get("title"),
            "url": url,
            "final_url": final_url,
            "scan_status": status,
            "http_status": http_status,
            "reason": reason,
        })
        print(f"[{i:03d}/{len(jobs)}] {status:5s} {http_status or '-':>3} {job.get('company')} — {job.get('title')[:70]}", flush=True)
        time.sleep(GLOBAL_DELAY)

    dead_ids = {r["id"] for r in results if r["scan_status"] == "dead"}
    kept = [j for j in jobs if j["id"] not in dead_ids]
    removed = [j for j in jobs if j["id"] in dead_ids]

    report = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "original_count": len(jobs),
        "removed_count": len(removed),
        "kept_count": len(kept),
        "status_counts": Counter(r["scan_status"] for r in results),
        "http_counts": Counter(str(r["http_status"]) for r in results),
        "removed": [r for r in results if r["scan_status"] == "dead"],
        "kept_ambiguous": [r for r in results if r["scan_status"] == "keep"],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    data["jobs"] = kept
    data["count"] = len(kept)
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    data["dead_link_scan"] = {
        "scanned_at": report["scanned_at"],
        "removed_count": len(removed),
        "report": "data/dead-jobs-report.json",
    }
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"original": len(jobs), "removed": len(removed), "kept": len(kept)}, indent=2))


if __name__ == "__main__":
    main()
