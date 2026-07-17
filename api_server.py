import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

OUTPUT_DIR = Path(os.environ.get("SCRAPER_OUTPUT", str(Path(__file__).parent / "output")))
OUTPUT_FILE = OUTPUT_DIR / "jobs.json"
NEW_JOBS_FILE = OUTPUT_DIR / "new_jobs.json"

app = FastAPI(title="LinkedIn Jobs Monitor API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_jobs() -> list:
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def load_new_jobs() -> list:
    if NEW_JOBS_FILE.exists():
        try:
            with open(NEW_JOBS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


@app.get("/api/jobs")
def get_jobs(
    category: str = Query(None, description="Filter: junior, pasantia"),
    source: str = Query(None, description="Filter: RemoteOK, Jobicy, Arbeitnow"),
    search: str = Query(None, description="Search in title, company, tags"),
    limit: int = Query(500, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    jobs = load_jobs()

    if category:
        jobs = [j for j in jobs if j.get("category") == category]

    if source:
        jobs = [j for j in jobs if j.get("source", "").lower() == source.lower()]

    if search:
        q = search.lower()
        jobs = [
            j for j in jobs
            if q in j.get("title", "").lower()
            or q in j.get("company", "").lower()
            or q in j.get("tags", "").lower()
            or q in j.get("location", "").lower()
        ]

    total = len(jobs)
    paginated = jobs[offset: offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "jobs": paginated,
    }


@app.get("/api/jobs/new")
def get_new_jobs(since: str = Query(None)):
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            all_jobs = load_jobs()
            new_jobs = [
                j for j in all_jobs
                if j.get("scraped_at", "") > since
            ]
            return {"total": len(new_jobs), "jobs": new_jobs}
        except ValueError:
            return JSONResponse({"error": "Invalid timestamp"}, status_code=400)
    return {"total": 0, "jobs": load_new_jobs()}


@app.get("/api/jobs/categories")
def get_categories():
    jobs = load_jobs()
    categories = {}
    for job in jobs:
        cat = job.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"count": 0, "label": "Pasantía" if cat == "pasantia" else "Junior"}
        categories[cat]["count"] += 1
    return {"categories": categories}


@app.get("/api/jobs/sources")
def get_sources():
    jobs = load_jobs()
    sources = {}
    for job in jobs:
        src = job.get("source", "unknown")
        if src not in sources:
            sources[src] = {"count": 0}
        sources[src]["count"] += 1
    return {"sources": sources}


@app.get("/api/jobs/stats")
def get_stats():
    jobs = load_jobs()
    new = load_new_jobs()
    categories = {}
    sources = {}
    for job in jobs:
        cat = job.get("category", "unknown")
        src = job.get("source", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
        sources[src] = sources.get(src, 0) + 1

    return {
        "total_jobs": len(jobs),
        "new_jobs": len(new),
        "categories": categories,
        "sources": sources,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/scrape")
def trigger_scrape():
    scraper_path = Path(__file__).parent / "linkedin_scraper.py"
    if not scraper_path.exists():
        return JSONResponse({"error": "Scraper not found"}, status_code=404)

    def run_scraper():
        subprocess.run([sys.executable, str(scraper_path)], cwd=str(Path(__file__).parent))

    thread = Thread(target=run_scraper, daemon=True)
    thread.start()

    return {"status": "scraping_started", "message": "Scraping job started in background"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "linkedin-jobs-monitor-api", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8600)
