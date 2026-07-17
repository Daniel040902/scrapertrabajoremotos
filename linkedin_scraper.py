import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

OUTPUT_DIR = Path(os.environ.get("SCRAPER_OUTPUT", str(Path(__file__).parent / "output")))
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "jobs.json"
NEW_JOBS_FILE = OUTPUT_DIR / "new_jobs.json"


def extraer_id_linkedin(url: str) -> str:
    partes = url.rstrip("/").split("/")
    for p in reversed(partes):
        if p.isdigit():
            return p
    return ""


def fetch_linkedin(client: httpx.Client) -> list:
    jobs = []
    busquedas = [
        ("programador junior", "junior"),
        ("desarrollador junior", "junior"),
        ("practicante programacion", "intern"),
        ("intern software developer", "intern"),
        ("trainee developer", "entry"),
        ("becario desarrollo", "intern"),
        ("pasantia desarrollo", "intern"),
        ("junior frontend", "junior"),
        ("junior backend", "junior"),
        ("junior full stack", "junior"),
        ("entry level developer", "entry"),
        ("junior data analyst", "junior"),
        ("intern data science", "intern"),
        ("estudiante programacion", "intern"),
        ("aprendiz desarrollo", "entry"),
    ]

    for keyword, nivel in busquedas:
        try:
            params = {
                "keywords": keyword,
                "location": "remote",
                "start": 0,
                "f_WT": "2",
            }
            # solo remoto = f_WT=2
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{ '&'.join(f'{k}={quote_plus(str(v))}' for k,v in params.items()) }"
            resp = client.get(url, timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                         "Accept": "text/html,application/xhtml+xml",
                         "Accept-Language": "es-ES,es;q=0.9"})
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("li")
                for card in cards:
                    try:
                        title_el = card.select_one("h3.base-search-card__title")
                        company_el = card.select_one("h4.base-search-card__subtitle a")
                        location_el = card.select_one("span.job-search-card__location")
                        link_el = card.select_one("a.base-card__full-link")
                        date_el = card.select_one("time")
                        if not title_el or not company_el or not link_el:
                            continue
                        title = title_el.get_text(strip=True)
                        company = company_el.get_text(strip=True)
                        location = location_el.get_text(strip=True) if location_el else "Remoto - Global"
                        url_job = link_el.get("href", "")
                        posted = date_el.get("datetime", "") if date_el else ""

                        texto = (title + " " + company + " " + location).lower()
                        if not any(p in texto for p in ["program", "develop", "software", "frontend", "backend", "fullstack", "full stack", "data", "engineer", "coder", "coding", "javascript", "python", "java", "react", "angular", "node", "sql", "devops", "cloud", "web", "app"]):
                            continue

                        cat = "pasantia" if nivel == "intern" else "junior"
                        salario = ""
                        sal_el = card.select_one("span.job-search-card__salary-info")
                        if sal_el:
                            salario = sal_el.get_text(strip=True)

                        jobs.append({
                            "title": title,
                            "company": company,
                            "location": location,
                            "url": url_job,
                            "category": cat,
                            "source": "LinkedIn",
                            "posted_date": posted,
                            "salary": salario,
                            "tags": keyword,
                            "is_remote": True,
                        })
                    except Exception:
                        continue
            time.sleep(0.5)
        except Exception as e:
            print(f"  [!] LinkedIn error ({keyword}): {e}")

    return jobs


def fetch_remotejobs_org(client: httpx.Client) -> list:
    jobs = []
    for pagina in range(1, 3):
        try:
            params = {
                "category": "programming",
                "q": "junior OR intern OR trainee OR entry OR pasantia OR practica",
                "limit": 50,
                "offset": (pagina - 1) * 50,
            }
            resp = client.get("https://remotejobs.org/api/v1/jobs", params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    title = (item.get("title") or "").lower()
                    desc = (item.get("description") or "").lower()
                    texto = f"{title} {desc}"
                    if not any(kw in texto for kw in ["junior", "intern", "trainee", "entry", "jr", "graduate", "pasantia", "practica"]):
                        continue
                    if not any(kw in texto for kw in ["program", "develop", "software", "frontend", "backend", "fullstack", "data", "engineer", "coder", "javascript", "python", "java", "react", "angular", "node", "sql", "devops", "web", "app"]):
                        continue
                    cat = "junior" if any(kw in texto for kw in ["junior", "jr", "entry", "graduate"]) else "pasantia"
                    location = "Remoto - Global"
                    if item.get("location"):
                        loc_lower = item["location"].lower()
                        if "remote" in loc_lower or "worldwide" in loc_lower or "anywhere" in loc_lower:
                            location = "Remoto - Global"
                        else:
                            location = item["location"]
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                    company = item.get("company", {})
                    if isinstance(company, dict):
                        company_name = company.get("name", "") or ""
                    else:
                        company_name = str(company) if company else ""
                    job = {
                        "title": item.get("title", ""),
                        "company": company_name,
                        "location": location,
                        "url": item.get("url", ""),
                        "category": cat,
                        "source": "RemoteJobs.org",
                        "posted_date": item.get("posted_at", ""),
                        "salary": salary,
                        "tags": item.get("category", {}).get("name", "") if isinstance(item.get("category"), dict) else "",
                        "is_remote": True,
                    }
                    jobs.append(job)
        except Exception as e:
            print(f"  [!] RemoteJobs.org error: {e}")
    return jobs


def fetch_freehire(client: httpx.Client) -> list:
    jobs = []
    try:
        params = {
            "work_mode": "remote",
            "seniority": "intern,junior",
            "category": "backend,frontend,fullstack,mobile,data_engineering,data_science,data_analytics,ml_ai,qa,devops,security,design,product",
            "limit": 100,
            "offset": 0,
        }
        resp = client.get("https://freehire.dev/api/v1/jobs/search", params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("results", []):
                title = (item.get("role") or "").lower()
                texto = title + " " + (item.get("description") or "").lower()
                if not any(kw in texto for kw in ["program", "develop", "software", "frontend", "backend", "fullstack", "data", "engineer", "coder", "javascript", "python", "java", "react", "angular", "node", "sql", "devops", "web", "app"]):
                    continue
                cat = "junior" if any(kw in texto for kw in ["junior", "jr", "entry", "graduate"]) else "pasantia"
                salary = ""
                if item.get("salary_min") and item.get("salary_max"):
                    salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                location = "Remoto - Global"
                if item.get("location"):
                    loc_lower = item["location"].lower()
                    if "remote" not in loc_lower and "worldwide" not in loc_lower:
                        location = item["location"]
                jobs.append({
                    "title": item.get("role", ""),
                    "company": item.get("company_name", "") or item.get("company", {}).get("name", "") if isinstance(item.get("company"), dict) else str(item.get("company", "")),
                    "location": location,
                    "url": item.get("url", "") or item.get("apply_url", ""),
                    "category": cat,
                    "source": "Freehire",
                    "posted_date": item.get("posted_at", "") or item.get("created_at", ""),
                    "salary": salary,
                    "tags": ", ".join(item.get("skills", [])),
                    "is_remote": True,
                })
    except Exception as e:
        print(f"  [!] Freehire error: {e}")
    return jobs


def fetch_himalayas(client: httpx.Client) -> list:
    jobs = []
    for pagina in range(1, 6):
        try:
            params = {
                "q": "programmer OR developer OR engineer OR data OR frontend OR backend OR fullstack",
                "seniority": "Entry-level",
                "worldwide": "true",
                "page": pagina,
            }
            resp = client.get("https://himalayas.app/jobs/api/search", params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = (item.get("title") or "").lower()
                    texto = title + " " + (item.get("description") or "").lower()
                    if not any(kw in texto for kw in ["program", "develop", "software", "frontend", "backend", "fullstack", "data", "engineer", "coder", "javascript", "python", "java", "react", "angular", "node", "sql", "devops", "web", "app"]):
                        continue
                    cat = "junior"
                    location = "Remoto - Global"
                    salary = ""
                    if item.get("salaryMin") and item.get("salaryMax"):
                        salary = f"${item['salaryMin']:,} - ${item['salaryMax']:,}"
                    jobs.append({
                        "title": item.get("title", ""),
                        "company": item.get("company", {}).get("name", "") if isinstance(item.get("company"), dict) else "",
                        "location": location,
                        "url": item.get("url", ""),
                        "category": cat,
                        "source": "Himalayas",
                        "posted_date": item.get("postedAt", "") or item.get("date", ""),
                        "salary": salary,
                        "tags": ", ".join(item.get("tags", [])) if item.get("tags") else "",
                        "is_remote": True,
                    })
        except Exception as e:
            print(f"  [!] Himalayas error: {e}")
    return jobs


def scrape_all():
    print("=" * 60)
    print("Empleos Junior/Pasantia - Programacion Remoto Global")
    print(f"Hora: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    existing = load_existing_jobs()
    print(f"[*] Empleos existentes: {len(existing)}")

    all_new = []

    with httpx.Client(
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    ) as client:
        print("\n[1/4] Buscando en LinkedIn (real)...")
        linkedin_jobs = fetch_linkedin(client)
        print(f"      -> {len(linkedin_jobs)} empleos")
        all_new.extend(linkedin_jobs)

        print("\n[2/4] Buscando en RemoteJobs.org...")
        remoteorg_jobs = fetch_remotejobs_org(client)
        print(f"      -> {len(remoteorg_jobs)} empleos")
        all_new.extend(remoteorg_jobs)

        print("\n[3/4] Buscando en Freehire...")
        freehire_jobs = fetch_freehire(client)
        print(f"      -> {len(freehire_jobs)} empleos")
        all_new.extend(freehire_jobs)

        print("\n[4/4] Buscando en Himalayas...")
        himalayas_jobs = fetch_himalayas(client)
        print(f"      -> {len(himalayas_jobs)} empleos")
        all_new.extend(himalayas_jobs)

    now = datetime.now(timezone.utc).isoformat()
    for job in all_new:
        job["scraped_at"] = now

    merged = merge_jobs(existing, all_new)
    merged = cleanup_old_jobs(merged, max_dias=7)
    new_only = [j for j in merged if j.get("title") not in {e.get("title") for e in existing}]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    with open(NEW_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_only, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"TOTAL: {len(merged)} empleos unicos")
    print(f"NUEVOS: {len(new_only)} desde ultima ejecucion")
    print(f"Guardados en: {OUTPUT_FILE}")
    print("=" * 60)

    return merged


def load_existing_jobs() -> list:
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def parse_job_date(job) -> datetime | None:
    for campo in ["posted_date", "scraped_at"]:
        val = job.get(campo, "")
        if val:
            try:
                val_clean = val.replace("Z", "+00:00").split(".")[0]
                return datetime.fromisoformat(val_clean)
            except (ValueError, TypeError):
                try:
                    return datetime.strptime(val[:10], "%Y-%m-%d")
                except (ValueError, IndexError):
                    pass
    return None


def cleanup_old_jobs(jobs: list, max_dias: int = 7) -> list:
    ahora = datetime.now(timezone.utc)
    filtrados = []
    for job in jobs:
        fecha = parse_job_date(job)
        if fecha is None:
            filtrados.append(job)
        elif (ahora - fecha).days <= max_dias:
            filtrados.append(job)
    return filtrados


def merge_jobs(existing: list, new_jobs: list) -> list:
    seen = set()
    merged = []
    for job in existing + new_jobs:
        title = job.get("title", "")
        company = job.get("company", "")
        key = f"{title}|{company}".lower().strip()
        if key not in seen and title:
            seen.add(key)
            merged.append(job)
    return merged


if __name__ == "__main__":
    scrape_all()
