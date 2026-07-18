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


SENIOR_KEYWORDS = [
    "senior", "sr.", "sr-", " sr ", "lead", "principal", "staff", "expert",
    "manager", "head ", "director", "chief", "vp ", "vice president",
    "architect", "staff", "principal", "gestion", "gerente", "jefe",
    "coordinador", "supervisor", "encargado", "lider", "líder", "head of",
    "manager ", "management", "experienced", "3+ years", "4+ years",
    "5+ years", "6+ years", "7+ years", "8+ years", "9+ years",
    "10+ years", "seniority", "mid-level", "mid level",
]

KEYWORDS_TECH = [
    "programador", "programmer", "developer", "desarrollador", "software",
    "frontend", "front-end", "front end", "backend", "back-end", "back end",
    "fullstack", "full-stack", "full stack", "data", "engineer",
    "coder", "coding", "javascript", "python", "java", "react", "angular",
    "vue", "node", "sql", "devops", "cloud", "web", "app", "mobile",
    "qa", "test", "testing", "tester", "aws", "azure", "gcp",
    "linux", "it ", "tech", "tecnico", "técnico", "soporte", "support",
    "sistemas", "redes", "ciberseguridad", "security", "cyber",
    "helpdesk", "administrador", "diseñador", "diseño", "designer", "design",
    "ux", "ui", "wordpress", "php", "ruby", "go ", "golang",
    "kotlin", "swift", "flutter", "dart", "django", "flask", "spring",
    "docker", "kubernetes", "machine learning", "ml ", "ai ",
    "inteligencia artificial", "big data", "blockchain", "sap", "oracle",
    "mysql", "postgresql", "mongodb", "git", "api", "rest",
    "microservicios", "microservices", "scrum", "agile", "automation",
    "digital", "typescript", "html", "css", "sass", "less",
    "bootstrap", "tailwind", "next.js", "nextjs", "express",
    "nestjs", "graphql", "redis", "elasticsearch", "kafka",
    "ci/cd", "jenkins", "github", "gitlab", "terraform", "ansible",
    "power bi", "tableau", "analytics", "scientist", "analysis",
    "rpa", "low code", "no code", "salesforce", "servicenow",
    "sharepoint", "dynamics", "erp", "crm", "bi ", "etl",
    "data warehouse", "data lake", "data engineer", "data analyst",
    "data science", "data entry", "informatico", "informática",
    "computacion", "computación", "sistemas", "software developer",
    "web developer", "app developer", "full stack developer",
    "ios", "android", "windows", "macos", "c++", "c#", ".net",
    "csharp", "vb", "powershell", "bash", "shell", "unix",
    "mainframe", "cobol", "delphi", "visual basic", "scala",
    "rust", "perl", "haskell", "lua", "matlab", "r ",
    "snowflake", "databricks", "airflow", "spark", "hadoop",
]

BUSQUEDAS_LINKEDIN = [
    ("junior programador", "junior"), ("junior desarrollador", "junior"),
    ("junior frontend", "junior"), ("junior backend", "junior"),
    ("junior full stack", "junior"), ("junior java", "junior"),
    ("junior python", "junior"), ("junior javascript", "junior"),
    ("junior developer", "junior"), ("junior software", "junior"),
    ("junior it", "junior"), ("junior data", "junior"),
    ("junior qa", "junior"), ("junior devops", "junior"),
    ("junior web", "junior"), ("junior mobile", "junior"),
    ("jr programmer", "junior"), ("jr developer", "junior"),
    ("entry level developer", "entry"), ("entry level programmer", "entry"),
    ("entry level software", "entry"), ("entry level it", "entry"),
    ("trainee programador", "entry"), ("trainee developer", "entry"),
    ("trainee informatica", "entry"), ("trainee it", "entry"),
    ("recien graduado programacion", "entry"),
    ("graduate developer", "entry"), ("graduate programmer", "entry"),
    ("practicante programacion", "intern"),
    ("practicante desarrollo", "intern"),
    ("practicante informatica", "intern"), ("practicante it", "intern"),
    ("becario programacion", "intern"), ("becario informatica", "intern"),
    ("becario desarrollo", "intern"), ("becario it", "intern"),
    ("pasantia programacion", "intern"), ("pasantia desarrollo", "intern"),
    ("pasantia informatica", "intern"), ("pasantia it", "intern"),
    ("intern developer", "intern"), ("intern programmer", "intern"),
    ("intern software", "intern"), ("intern it", "intern"),
    ("internship developer", "intern"), ("internship programmer", "intern"),
    ("internship software", "intern"),
    ("estudiante programacion", "intern"),
    ("estudiante informatica", "intern"), ("estudiante it", "intern"),
    ("aprendiz programacion", "entry"), ("aprendiz informatica", "entry"),
    ("practicas programacion", "intern"), ("practicas informatica", "intern"),
    ("practicas desarrollo", "intern"), ("practicas it", "intern"),
]


def es_senior(title: str, desc: str = "") -> bool:
    texto = (title + " " + desc).lower()
    for kw in SENIOR_KEYWORDS:
        if kw in texto:
            return True
    # Skip if title explicitly says senior but check it's not just "junior" in same title
    return False


def linkedin_search(client: httpx.Client, keyword: str, nivel: str, location: str = "remote", f_WT: str = "2", max_pages: int = 1) -> list:
    jobs = []
    try:
        params = {"keywords": keyword, "location": location, "start": 0}
        if f_WT:
            params["f_WT"] = f_WT
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{'&'.join(f'{k}={quote_plus(str(v))}' for k,v in params.items())}"
        resp = client.get(url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                     "Accept": "text/html,application/xhtml+xml",
                     "Accept-Language": "es-ES,es;q=0.9"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("li"):
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

                    if es_senior(title):
                        continue

                    texto = (title + " " + company + " " + location).lower()
                    if not any(p in texto for p in KEYWORDS_TECH):
                        continue

                    cat = "pasantia" if nivel == "intern" else "junior"
                    salario = ""
                    sal_el = card.select_one("span.job-search-card__salary-info")
                    if sal_el:
                        salario = sal_el.get_text(strip=True)

                    jobs.append({
                        "title": title, "company": company, "location": location,
                        "url": url_job, "category": cat, "source": "LinkedIn",
                        "posted_date": posted, "salary": salario, "tags": keyword,
                        "is_remote": f_WT == "2",
                    })
                except Exception:
                    continue
    except Exception as e:
        pass
    return jobs


CIUDADES_ES = [
    "Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao",
    "Málaga", "Zaragoza", "Alicante", "Murcia", "Palma",
    "Las Palmas", "Granada", "Valladolid", "A Coruña",
    "Gijón", "Pamplona", "San Sebastián", "Córdoba",
    "Salamanca", "Castellón", "Vigo", "Tarragona",
    "Lleida", "Huelva", "Almería",
]

def es_busqueda_es(keyword: str) -> bool:
    kw = keyword.lower()
    return any(p in kw for p in ["programador", "desarrollador", "becario", "practicante",
        "pasantia", "informatica", "practicas", "estudiante", "aprendiz",
        "recien", "trainee"])

def fetch_linkedin(client: httpx.Client) -> list:
    jobs = []
    for keyword, nivel in BUSQUEDAS_LINKEDIN:
        result = linkedin_search(client, keyword, nivel, location="remote", f_WT="2")
        jobs.extend(result)
        time.sleep(0.1)
        result2 = linkedin_search(client, keyword, nivel, location="Spain", f_WT="")
        jobs.extend(result2)
        time.sleep(0.1)
        if es_busqueda_es(keyword):
            for ciudad in CIUDADES_ES[:3]:
                result3 = linkedin_search(client, keyword, nivel, location=ciudad, f_WT="")
                jobs.extend(result3)
                time.sleep(0.08)
    return jobs


def fetch_remotejobs_org(client: httpx.Client) -> list:
    jobs = []
    for pagina in range(1, 4):
        try:
            params = {
                "category": "programming",
                "q": "junior OR intern OR trainee OR entry OR pasantia OR practica OR becario OR jr OR graduate OR estudiante OR aprendiz",
                "limit": 50,
                "offset": (pagina - 1) * 50,
            }
            resp = client.get("https://remotejobs.org/api/v1/jobs", params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    title = (item.get("title") or "").lower()
                    desc = (item.get("description") or "").lower()
                    if es_senior(title, desc):
                        continue
                    texto = f"{title} {desc}"
                    if not any(kw in texto for kw in ["junior", "intern", "trainee", "entry", "jr", "graduate", "pasantia", "practica", "becario", "estudiante", "aprendiz", "entry-level"]):
                        continue
                    if not any(kw in texto for kw in KEYWORDS_TECH):
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
                    jobs.append({
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
                    })
        except Exception as e:
            print(f"  [!] RemoteJobs.org error: {e}")
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
                    desc = (item.get("description") or "").lower()
                    if es_senior(title, desc):
                        continue
                    texto = title + " " + desc
                    if not any(kw in texto for kw in KEYWORDS_TECH):
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


def fetch_remotive(client: httpx.Client) -> list:
    jobs = []
    try:
        resp = client.get("https://remotive.com/api/remote-jobs?category=software-dev&limit=200", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("jobs", []):
                try:
                    title = (item.get("title") or "").lower()
                    desc = (item.get("description") or "").lower()
                    if es_senior(title, desc):
                        continue
                    texto = f"{title} {desc}"
                    if not any(kw in texto for kw in ["junior", "intern", "trainee", "entry", "jr", "graduate", "pasantia", "practica", "becario", "estudiante", "aprendiz", "entry-level", "júnior"]):
                        continue
                    if not any(kw in texto for kw in KEYWORDS_TECH):
                        continue
                    cat = "junior" if any(kw in texto for kw in ["junior", "jr", "entry", "graduate", "entry-level"]) else "pasantia"
                    salary = ""
                    if item.get("salary"):
                        salary = str(item["salary"])
                    elif item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                    company_name = item.get("company_name", "") or ""
                    location_raw = item.get("candidate_required_location", "") or "Remoto - Global"
                    location = "Remoto - Global" if any(w in location_raw.lower() for w in ["remote", "worldwide", "anywhere"]) else location_raw
                    jobs.append({
                        "title": item.get("title", ""),
                        "company": company_name,
                        "location": location,
                        "url": item.get("url", "") or item.get("apply_url", ""),
                        "category": cat,
                        "source": "Remotive",
                        "posted_date": item.get("publication_date", "") or "",
                        "salary": salary,
                        "tags": ", ".join(item.get("tags", [])),
                        "is_remote": True,
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"  [!] Remotive error: {e}")
    return jobs


def fetch_arbeitnow(client: httpx.Client) -> list:
    jobs = []
    try:
        resp = client.get("https://arbeitnow.com/api/job-board-api", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data", []):
                try:
                    title = (item.get("title") or "").lower()
                    desc = (item.get("description") or "").lower()
                    tags = " ".join(item.get("tags", [])).lower()
                    texto = f"{title} {desc} {tags}"
                    if es_senior(title, desc):
                        continue
                    if not any(kw in texto for kw in ["junior", "intern", "trainee", "entry", "jr", "graduate", "entry-level"]):
                        continue
                    if not any(kw in texto for kw in KEYWORDS_TECH):
                        continue
                    cat = "junior" if any(kw in texto for kw in ["junior", "jr", "entry", "graduate"]) else "pasantia"
                    salary = ""
                    location = item.get("location", "") or "Remoto - Global"
                    if any(w in location.lower() for w in ["remote", "worldwide", "anywhere"]):
                        location = "Remoto - Global"
                    company_name = item.get("company_name", "") or ""
                    url_job = f"https://arbeitnow.com/jobs/{item.get('slug', '')}" if item.get("slug") else (item.get("url") or "")
                    jobs.append({
                        "title": item.get("title", ""),
                        "company": company_name,
                        "location": location,
                        "url": url_job,
                        "category": cat,
                        "source": "Arbeitnow",
                        "posted_date": item.get("created_at", "") or "",
                        "salary": salary,
                        "tags": ", ".join(item.get("tags", [])),
                        "is_remote": True,
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"  [!] Arbeitnow error: {e}")
    return jobs


def fetch_jobsbase(client: httpx.Client) -> list:
    jobs = []
    try:
        seen = set()
        cursor = None
        for _ in range(3):
            url = "https://jobsbase.io/api/v1/jobs?workplace=remote&limit=100"
            if cursor:
                url += f"&cursor={cursor}"
            resp = client.get(url, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            for item in data.get("jobs", []):
                try:
                    jid = item.get("id", "")
                    if jid in seen:
                        continue
                    seen.add(jid)
                    title = (item.get("title") or "").lower()
                    desc = (item.get("description") or "").lower()
                    seniority = (item.get("seniority_level") or "").lower()
                    texto = f"{title} {desc} {seniority}"
                    if seniority not in ("internship", "entry") and not any(kw in texto for kw in ["junior", "jr", "entry", "graduate", "trainee", "intern", "pasantia", "practica", "becario", "estudiante", "aprendiz"]):
                        continue
                    if es_senior(title, desc):
                        continue
                    if not any(kw in texto for kw in KEYWORDS_TECH):
                        continue
                    cat = "junior" if any(kw in texto for kw in ["junior", "jr", "entry", "graduate"]) else "pasantia"
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                    location = item.get("display_location", "") or "Remoto - Global"
                    if item.get("workplace") == "remote":
                        location = "Remoto - Global"
                    skills = ", ".join(item.get("skills", []))
                    jobs.append({
                        "title": item.get("title", ""),
                        "company": item.get("company", ""),
                        "location": location,
                        "url": item.get("job_url", ""),
                        "category": cat,
                        "source": "JobsBase",
                        "posted_date": item.get("posted_at", "") or "",
                        "salary": salary,
                        "tags": skills,
                        "is_remote": True,
                    })
                except Exception:
                    continue
            cursor = data.get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        print(f"  [!] JobsBase error: {e}")
    return jobs


def fetch_remoteok(client: httpx.Client) -> list:
    jobs = []
    try:
        resp = client.get("https://remoteok.com/api?tag=junior", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            # First item is metadata, skip it
            start = 1 if len(data) > 0 and "last_updated" in data[0] else 0
            for item in data[start:]:
                try:
                    title = (item.get("position") or "").lower()
                    desc = (item.get("description") or "").lower()
                    tags = " ".join(item.get("tags", [])).lower()
                    texto = f"{title} {desc} {tags}"
                    if es_senior(title, desc):
                        continue
                    if not any(kw in texto for kw in ["junior", "intern", "trainee", "entry", "jr", "graduate", "entry-level"]):
                        continue
                    if not any(kw in texto for kw in KEYWORDS_TECH):
                        continue
                    cat = "junior" if any(kw in texto for kw in ["junior", "jr", "entry", "graduate"]) else "pasantia"
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                    location = item.get("location", "") or "Remoto - Global"
                    if any(w in location.lower() for w in ["remote", "worldwide", "anywhere", "global"]):
                        location = "Remoto - Global"
                    company_name = item.get("company", "") or ""
                    url_job = item.get("apply_url", "") or item.get("url", "") or f"https://remoteok.com/remote-jobs/{item.get('slug', '')}"
                    posted = item.get("date", "") or ""
                    jobs.append({
                        "title": item.get("position", ""),
                        "company": company_name,
                        "location": location,
                        "url": url_job,
                        "category": cat,
                        "source": "RemoteOK",
                        "posted_date": posted,
                        "salary": salary,
                        "tags": ", ".join(item.get("tags", [])),
                        "is_remote": True,
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"  [!] RemoteOK error: {e}")
    return jobs


def fetch_computrabajo(client: httpx.Client) -> list:
    jobs = []
    keywords = [
        "programador+junior", "practicante+programacion", "becario+informatica",
        "desarrollador+junior", "trainee+programacion", "estudiante+informatica",
        "practicas+programacion", "pasantia+desarrollo", "junior+frontend",
        "junior+python", "soporte+tecnico", "analista+junior",
    ]
    seen_urls = set()
    for kw in keywords:
        for intento in range(2):
            if intento == 0:
                url = f"https://es.computrabajo.com/trabajo-de-{kw}-remoto"
            else:
                url = f"https://es.computrabajo.com/ofertas-de-trabajo/?q={kw.replace('+',' ')}&s=1"
            try:
                resp = client.get(url, timeout=10)
                if resp.status_code != 200 or len(resp.text) < 5000:
                    continue
                import re
                ofertas = re.findall(r'/oferta/([^/\"\'\\?]+)', resp.text)
                for oferta in ofertas[:10]:
                    url_job = f"https://es.computrabajo.com/oferta/{oferta}"
                    if url_job in seen_urls:
                        continue
                    seen_urls.add(url_job)
                    title_match = re.search(r'class="[^"]*title[^"]*"[^>]*>([^<]+)', resp.text)
                    company_match = re.search(r'class="[^"]*company[^"]*"[^>]*>([^<]+)', resp.text)
                    title = title_match.group(1).strip() if title_match else f"Oferta {kw}"
                    company = company_match.group(1).strip() if company_match else ""
                    jobs.append({
                        "title": title, "company": company, "location": "Remoto - España",
                        "url": url_job, "category": "junior", "source": "Computrabajo ES",
                        "posted_date": "", "salary": "", "tags": kw.replace("+", " "),
                        "is_remote": True,
                    })
            except Exception:
                continue
        time.sleep(0.2)
    return jobs


def fetch_tecnoempleo(client: httpx.Client) -> list:
    jobs = []
    keywords = [
        "programador+junior", "practicante+programacion", "becario+informatica",
        "desarrollador+junior", "trainee+it", "soporte+tecnico",
    ]
    seen_urls = set()
    for kw in keywords:
        for intento in range(2):
            if intento == 0:
                url = f"https://www.tecnoempleo.com/ofertas-trabajo/?keyword={kw}&teletrabajo=1"
            else:
                url = f"https://www.tecnoempleo.com/ofertas-empleo-{kw}-remoto.php"
            try:
                resp = client.get(url, timeout=10)
                if resp.status_code != 200 or len(resp.text) < 3000:
                    continue
                import re
                ofertas = re.findall(r'/empleo-[^/\"\'\\?<>]+\.html', resp.text)
                for oferta in ofertas[:10]:
                    url_job = f"https://www.tecnoempleo.com{oferta}" if oferta.startswith('/') else oferta
                    if url_job in seen_urls:
                        continue
                    seen_urls.add(url_job)
                    title_match = re.search(r'<h2[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)', resp.text)
                    company_match = re.search(r'class="[^"]*company[^"]*"[^>]*>([^<]+)', resp.text)
                    title = title_match.group(1).strip() if title_match else f"Oferta {kw}"
                    company = company_match.group(1).strip() if company_match else ""
                    jobs.append({
                        "title": title, "company": company, "location": "Remoto - España",
                        "url": url_job, "category": "junior", "source": "Tecnoempleo",
                        "posted_date": "", "salary": "", "tags": kw.replace("+", " "),
                        "is_remote": True,
                    })
            except Exception:
                continue
        time.sleep(0.2)
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
        print("\n[1/9] Buscando en LinkedIn...")
        linkedin_jobs = fetch_linkedin(client)
        print(f"      -> {len(linkedin_jobs)} empleos")
        all_new.extend(linkedin_jobs)

        print("\n[2/9] Buscando en RemoteJobs.org...")
        remoteorg_jobs = fetch_remotejobs_org(client)
        print(f"      -> {len(remoteorg_jobs)} empleos")
        all_new.extend(remoteorg_jobs)

        print("\n[3/9] Buscando en Himalayas...")
        himalayas_jobs = fetch_himalayas(client)
        print(f"      -> {len(himalayas_jobs)} empleos")
        all_new.extend(himalayas_jobs)

        print("\n[4/9] Buscando en Remotive...")
        remotive_jobs = fetch_remotive(client)
        print(f"      -> {len(remotive_jobs)} empleos")
        all_new.extend(remotive_jobs)

        print("\n[5/9] Buscando en Arbeitnow...")
        arbeitnow_jobs = fetch_arbeitnow(client)
        print(f"      -> {len(arbeitnow_jobs)} empleos")
        all_new.extend(arbeitnow_jobs)

        print("\n[6/9] Buscando en RemoteOK...")
        remoteok_jobs = fetch_remoteok(client)
        print(f"      -> {len(remoteok_jobs)} empleos")
        all_new.extend(remoteok_jobs)

        print("\n[7/9] Buscando en JobsBase...")
        jobsbase_jobs = fetch_jobsbase(client)
        print(f"      -> {len(jobsbase_jobs)} empleos")
        all_new.extend(jobsbase_jobs)

        print("\n[8/9] Buscando en Computrabajo ES...")
        computrabajo_jobs = fetch_computrabajo(client)
        print(f"      -> {len(computrabajo_jobs)} empleos")
        all_new.extend(computrabajo_jobs)

        print("\n[9/9] Buscando en Tecnoempleo...")
        tecnoempleo_jobs = fetch_tecnoempleo(client)
        print(f"      -> {len(tecnoempleo_jobs)} empleos")
        all_new.extend(tecnoempleo_jobs)

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

    cats = {}
    srcs = {}
    for j in merged:
        c = j.get("category", "?")
        s = j.get("source", "?")
        cats[c] = cats.get(c, 0) + 1
        srcs[s] = srcs.get(s, 0) + 1
    print(f"  Categorias: {cats}")
    print(f"  Fuentes: {srcs}")

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
                dt = datetime.fromisoformat(val_clean)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                try:
                    return datetime.strptime(val[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
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
