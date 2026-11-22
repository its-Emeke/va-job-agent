"""Pull remote jobs from free, ToS-friendly job-board APIs.

We deliberately use public APIs (no scraping of Indeed/LinkedIn, which breaks
their terms and triggers anti-bot blocks). Each fetcher returns a list of
normalized job dicts; the caller filters + stores them.
"""
import re
import html
import httpx

from . import filters, config

TIMEOUT = 20.0
HEADERS = {"User-Agent": "va-job-agent/1.0 (personal job search tool)"}


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)          # strip HTML tags
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_email(*texts: str) -> str | None:
    blob = " ".join(t for t in texts if t)
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", blob)
    if not m:
        return None
    email = m.group(0)
    # Skip obvious no-reply / tracking addresses
    if any(bad in email.lower() for bad in ("noreply", "no-reply", "donotreply")):
        return None
    return email


def fetch_remotive(search: str = "virtual assistant") -> list[dict]:
    url = "https://remotive.com/api/remote-jobs"
    out: list[dict] = []
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as c:
            r = c.get(url, params={"search": search, "limit": 100})
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[remotive] fetch failed: {e}")
        return out

    for j in data.get("jobs", []):
        desc = _clean(j.get("description"))
        out.append({
            "source": "remotive",
            "external_id": j.get("id"),
            "title": j.get("title", ""),
            "company": j.get("company_name"),
            "location": j.get("candidate_required_location", ""),
            "url": j.get("url"),
            "contact_email": _extract_email(desc),
            "description": desc[:4000],
            "posted_at": j.get("publication_date"),
        })
    return out


def fetch_jobicy(search: str = "virtual assistant") -> list[dict]:
    # Jobicy free API supports geo + tag filters.
    url = "https://jobicy.com/api/v2/remote-jobs"
    out: list[dict] = []
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as c:
            r = c.get(url, params={"count": 100, "geo": "usa", "tag": search})
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[jobicy] fetch failed: {e}")
        return out

    for j in data.get("jobs", []):
        desc = _clean(j.get("jobExcerpt") or j.get("jobDescription"))
        out.append({
            "source": "jobicy",
            "external_id": j.get("id"),
            "title": j.get("jobTitle", ""),
            "company": j.get("companyName"),
            "location": j.get("jobGeo", ""),
            "url": j.get("url"),
            "contact_email": _extract_email(desc),
            "description": desc[:4000],
            "posted_at": j.get("pubDate"),
        })
    return out


def fetch_adzuna(search: str = "virtual assistant") -> list[dict]:
    # Big aggregator. Free key: https://developer.adzuna.com/
    if not (config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY):
        print("[adzuna] skipped (no ADZUNA_APP_ID / ADZUNA_APP_KEY set)")
        return []
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    out: list[dict] = []
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as c:
            r = c.get(url, params={
                "app_id": config.ADZUNA_APP_ID,
                "app_key": config.ADZUNA_APP_KEY,
                "what": search,
                "what_or": "remote",
                "results_per_page": 50,
                "content-type": "application/json",
            })
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[adzuna] fetch failed: {e}")
        return out

    for j in data.get("results", []):
        desc = _clean(j.get("description"))
        out.append({
            "source": "adzuna",
            "external_id": j.get("id"),
            "title": j.get("title", ""),
            "company": (j.get("company") or {}).get("display_name"),
            "location": (j.get("location") or {}).get("display_name", ""),
            "url": j.get("redirect_url"),
            "contact_email": _extract_email(desc),
            "description": desc[:4000],
            "posted_at": j.get("created"),
        })
    return out


def fetch_usajobs(search: str = "virtual assistant") -> list[dict]:
    # US federal jobs. Free key: https://developer.usajobs.gov/apirequest/
    if not (config.USAJOBS_API_KEY and config.USAJOBS_EMAIL):
        print("[usajobs] skipped (no USAJOBS_API_KEY / USAJOBS_EMAIL set)")
        return []
    url = "https://data.usajobs.gov/api/search"
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": config.USAJOBS_EMAIL,
        "Authorization-Key": config.USAJOBS_API_KEY,
    }
    out: list[dict] = []
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(url, headers=headers, params={
                "Keyword": search, "ResultsPerPage": 50,
            })
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[usajobs] fetch failed: {e}")
        return out

    items = data.get("SearchResult", {}).get("SearchResultItems", [])
    for it in items:
        d = it.get("MatchedObjectDescriptor", {})
        summary = _clean(d.get("UserArea", {}).get("Details", {}).get("JobSummary"))
        locs = d.get("PositionLocationDisplay") or ", ".join(
            pl.get("LocationName", "") for pl in d.get("PositionLocation", [])
        )
        out.append({
            "source": "usajobs",
            "external_id": d.get("PositionID") or it.get("MatchedObjectId"),
            "title": d.get("PositionTitle", ""),
            "company": d.get("OrganizationName"),
            "location": f"{locs}, United States" if locs else "United States",
            "url": d.get("PositionURI"),
            "contact_email": _extract_email(summary),
            "description": summary[:4000],
            "posted_at": d.get("PublicationStartDate"),
        })
    return out


FETCHERS = [fetch_remotive, fetch_jobicy, fetch_adzuna, fetch_usajobs]


def fetch_all(search: str = "virtual assistant") -> list[dict]:
    """Fetch from every source, keep only US-based remote VA roles."""
    results: list[dict] = []
    for fn in FETCHERS:
        for job in fn(search):
            if filters.matches(job["title"], job.get("location", ""), job.get("description", "")):
                job["score"] = filters.match_score(
                    job["title"], job.get("location", ""), job.get("description", "")
                )
                results.append(job)
    return results
