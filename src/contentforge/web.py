"""Web interface for running ContentForge on a server.

Run with:  uvicorn contentforge.web:app --host 0.0.0.0 --port 8000
Protected with HTTP basic auth (APP_USER / APP_PASSWORD). Jobs run one at a time in a
background thread, because video work and a local LLM use the whole CPU.
"""

from __future__ import annotations

import html
import json
import logging
import os
import queue
import secrets
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import pipeline
from .config import Settings, load_dotenv
from .seo import compose_post

load_dotenv()
log = logging.getLogger("contentforge.web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

DATA_DIR = Path(os.environ.get("CONTENTFORGE_DATA", "data")).resolve()
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)
APP_USER = os.environ.get("APP_USER", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

PLATFORMS = {"youtube_shorts": "YouTube Shorts", "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook",
             "telegram": "Telegram", "x": "X", "linkedin": "LinkedIn", "threads": "Threads"}
TARGETS = {"markdown": "Markdown (בלוג סטטי)", "wordpress": "WordPress (טיוטה)", "telegram": "Telegram",
           "youtube": "YouTube (פרטי)", "facebook": "Facebook (לא מפורסם)", "instagram": "Instagram Reels",
           "webhook": "Webhook / n8n"}

security = HTTPBasic()


def require_user(creds: HTTPBasicCredentials = Depends(security)) -> str:
    ok = bool(APP_PASSWORD) and secrets.compare_digest(creds.username, APP_USER) and \
        secrets.compare_digest(creds.password, APP_PASSWORD)
    if not ok:
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return creds.username


# --- job store -------------------------------------------------------------------

def job_dir(job_id: str) -> Path:
    if not job_id.isalnum():
        raise HTTPException(404)
    return JOBS_DIR / job_id


def read_job(job_id: str) -> dict:
    f = job_dir(job_id) / "job.json"
    if not f.exists():
        raise HTTPException(404, "job not found")
    return json.loads(f.read_text(encoding="utf-8"))


def write_job(job: dict) -> None:
    d = job_dir(job["id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "job.json.tmp"
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(d / "job.json")


def update_job(job_id: str, **fields) -> dict:
    job = read_job(job_id)
    job.update(fields)
    write_job(job)
    return job


def list_jobs() -> list[dict]:
    jobs = []
    for f in JOBS_DIR.glob("*/job.json"):
        try:
            jobs.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(jobs, key=lambda j: j.get("created", 0), reverse=True)


class JobLogHandler(logging.Handler):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def emit(self, record):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + record.getMessage() + "\n")


def job_settings(job: dict) -> Settings:
    s = Settings()
    s.output_dir = job_dir(job["id"]) / "output"
    s.language = job["params"].get("language") or s.language
    return s


def run_job(job_id: str) -> None:
    job = update_job(job_id, status="running", started=time.time())
    handler = JobLogHandler(job_dir(job_id) / "log.txt")
    root = logging.getLogger("contentforge")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        p = job["params"]
        pipeline.run(p["source"], p["topics"], job_settings(job), p["platforms"], p["num_clips"], p["max_seconds"],
                     True, p["reframe"], p["article"], p["whisper"])
        update_job(job_id, status="done", finished=time.time())
    except Exception as exc:  # shown to the user on the job page
        log.exception("job %s failed", job_id)
        update_job(job_id, status="error", error=str(exc), finished=time.time())
    finally:
        root.removeHandler(handler)


def run_publish(job_id: str, targets: list[str]) -> None:
    job = read_job(job_id)
    try:
        m = pipeline.load_manifest(job_dir(job_id) / "output" / "manifest.json")
        results = pipeline.publish(m, targets, job_settings(job))
        update_job(job_id, publish=[r.__dict__ for r in results], publishing=False)
    except Exception as exc:
        update_job(job_id, publish=[{"platform": "all", "ok": False, "error": str(exc)}], publishing=False)


work: "queue.Queue[tuple]" = queue.Queue()


def worker() -> None:
    while True:
        fn, args = work.get()
        try:
            fn(*args)
        finally:
            work.task_done()


def ensure_model() -> None:
    llm = pipeline.make_llm(Settings())
    if llm.has_model():
        return
    log.info("pulling model %s into Ollama (first run only)", llm.model)
    try:
        llm.pull()
        log.info("model ready")
    except Exception as exc:
        log.warning("model pull failed: %s", exc)


def startup() -> None:
    if not APP_PASSWORD:
        log.warning("APP_PASSWORD is not set: every request will be refused")
    for job in list_jobs():  # jobs cut off by a restart
        if job.get("status") in ("queued", "running"):
            update_job(job["id"], status="error", error="interrupted by a server restart; submit it again")
        if job.get("publishing"):
            update_job(job["id"], publishing=False)
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=ensure_model, daemon=True).start()


@asynccontextmanager
async def lifespan(_app):
    startup()
    yield


app = FastAPI(title="ContentForge AI", docs_url=None, redoc_url=None, lifespan=lifespan)


# --- pages -----------------------------------------------------------------------

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#14181f;--muted:#5b6472;--line:#e3e6eb;--accent:#2563eb;--ok:#15803d;--err:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#0f1218;--card:#171b23;--text:#e8ebf0;--muted:#9aa3b2;--line:#2a303b;--accent:#60a5fa;--ok:#4ade80;--err:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}h1{font-size:24px;margin:0 0 4px}h2{font-size:19px;margin:28px 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:14px 0}
label{display:block;font-weight:600;margin:12px 0 4px}input[type=text],input[type=number],textarea,select{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);font:inherit}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.checks label{display:inline-flex;gap:6px;font-weight:400;margin:4px 14px 4px 0}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:10px 18px;font:inherit;font-weight:600;cursor:pointer;margin-top:14px}
.muted{color:var(--muted);font-size:14px}a{color:var(--accent)}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid var(--line);text-align:start;vertical-align:top}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;font-size:13px;border:1px solid var(--line)}.done{color:var(--ok)}.error{color:var(--err)}
video{width:100%;max-width:320px;border-radius:10px;background:#000}.clip{display:grid;grid-template-columns:minmax(0,320px) 1fr;gap:18px}
@media(max-width:700px){.clip{grid-template-columns:1fr}}pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;margin:6px 0}
.copy{font-size:13px;padding:4px 10px;margin:0}.post h4{margin:12px 0 2px}
"""

JS = """
document.addEventListener('click',e=>{const b=e.target.closest('[data-copy]');if(!b)return;
navigator.clipboard.writeText(document.getElementById(b.dataset.copy).innerText).then(()=>{b.textContent='הועתק ✓';setTimeout(()=>b.textContent='העתק',1500)})});
"""


def page(title: str, body: str, refresh: bool = False) -> HTMLResponse:
    meta = '<meta http-equiv="refresh" content="10">' if refresh else ""
    return HTMLResponse(f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{html.escape(title)}</title>
<style>{CSS}</style></head><body><main>{body}</main><script>{JS}</script></body></html>""")


def esc(v) -> str:
    return html.escape(str(v or ""))


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def home(user: str = Depends(require_user)):
    plats = "".join(f'<label><input type="checkbox" name="platforms" value="{k}" checked> {v}</label>' for k, v in PLATFORMS.items())
    rows = "".join(
        f'<tr><td><a href="/jobs/{j["id"]}">{esc(j["params"]["source"])[:80]}</a><div class="muted">{esc(", ".join(j["params"]["topics"]) or "רגעים חזקים")}</div></td>'
        f'<td><span class="badge {esc(j["status"])}">{esc(j["status"])}</span></td>'
        f'<td class="muted">{time.strftime("%d/%m %H:%M", time.localtime(j["created"]))}</td></tr>'
        for j in list_jobs()[:50])
    return page("ContentForge AI", f"""
<h1>ContentForge AI</h1><div class="muted">חיתוך סרטונים ארוכים לפי נושאים, SEO ופוסטים — עם מודל AI מקומי</div>
<form class="card" method="post" action="/jobs" enctype="multipart/form-data">
<label>קישור לסרטון</label><input type="text" name="source" placeholder="https://www.youtube.com/watch?v=..." dir="ltr">
<div class="muted">או העלאת קובץ (מומלץ אם האתר חוסם הורדה מהשרת):</div><input type="file" name="upload" accept="video/*">
<label>נושאים (שורה לכל נושא; ריק = הרגעים החזקים בסרטון)</label><textarea name="topics" rows="3"></textarea>
<div class="row">
<div><label>מספר קליפים (בלי נושאים)</label><input type="number" name="num_clips" value="3" min="1" max="10"></div>
<div><label>אורך מקסימלי לקליפ (שניות)</label><input type="number" name="max_seconds" value="90" min="15" max="600"></div>
<div><label>שפת התוכן</label><select name="language"><option value="he">עברית</option><option value="en">English</option><option value="ar">العربية</option><option value="ru">Русский</option></select></div>
<div><label>מסגור אנכי</label><select name="reframe"><option value="auto">מעקב פנים</option><option value="blur">רקע מטושטש</option><option value="crop">חיתוך מרכז</option></select></div>
</div>
<label>פוסטים עבור</label><div class="checks">{plats}</div>
<div class="checks"><label><input type="checkbox" name="article" value="1" checked> גם מאמר לבלוג</label>
<label><input type="checkbox" name="whisper" value="1"> תמלול עם Whisper גם אם יש כתוביות</label></div>
<button type="submit">התחל</button>
<div class="muted">עבודה רצה אחת בכל פעם. סרטון של שעה יכול לקחת זמן רב על מעבד בלי GPU.</div>
</form>
<h2>עבודות</h2><div class="card"><table>{rows or '<tr><td class="muted">אין עדיין</td></tr>'}</table></div>""")


@app.post("/jobs")
def create_job(source: str = Form(""), topics: str = Form(""), num_clips: int = Form(3), max_seconds: float = Form(90),
               language: str = Form("he"), reframe: str = Form("auto"), platforms: list[str] = Form([]),
               article: str = Form(""), whisper: str = Form(""), upload: UploadFile | None = File(None),
               user: str = Depends(require_user)):
    job_id = uuid.uuid4().hex[:12]
    d = job_dir(job_id)
    d.mkdir(parents=True)
    if upload is not None and upload.filename:
        name = Path(upload.filename).name.replace(" ", "_") or "upload.mp4"
        dest = d / "upload" / name
        dest.parent.mkdir()
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f, 1024 * 1024)
        source = str(dest)
    if not source.strip():
        shutil.rmtree(d)
        raise HTTPException(400, "Give a video link or upload a file")
    job = {"id": job_id, "created": time.time(), "status": "queued", "params": {
        "source": source.strip(), "topics": [t.strip() for t in topics.splitlines() if t.strip()],
        "num_clips": max(1, min(num_clips, 10)), "max_seconds": max(15.0, min(max_seconds, 600.0)),
        "language": language, "reframe": reframe if reframe in ("auto", "blur", "crop", "face") else "auto",
        "platforms": [p for p in platforms if p in PLATFORMS] or list(PLATFORMS), "article": bool(article),
        "whisper": bool(whisper)}}
    write_job(job)
    work.put((run_job, (job_id,)))
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


def _file_url(job_id: str, path: str | None) -> str:
    if not path:
        return ""
    rel = Path(path).resolve().relative_to(job_dir(job_id).resolve())
    return f"/files/{job_id}/{rel.as_posix()}"


def _copy_block(uid: str, label: str, text: str) -> str:
    return (f'<div class="post"><h4>{esc(label)} <button class="copy" type="button" data-copy="{uid}">העתק</button></h4>'
            f'<pre id="{uid}">{esc(text)}</pre></div>')


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str, user: str = Depends(require_user)):
    job = read_job(job_id)
    d = job_dir(job_id)
    logtxt = (d / "log.txt").read_text(encoding="utf-8")[-4000:] if (d / "log.txt").exists() else ""
    status = job["status"]
    body = [f'<p><a href="/">← כל העבודות</a></p><h1>{esc(job["params"]["source"])[:90]}</h1>',
            f'<div class="card">מצב: <span class="badge {esc(status)}">{esc(status)}</span>'
            + (f'<pre class="error">{esc(job.get("error"))}</pre>' if job.get("error") else "")
            + (f'<details {"open" if status == "running" else ""}><summary>יומן</summary><pre dir="ltr">{esc(logtxt)}</pre></details>' if logtxt else "")
            + "</div>"]

    manifest_path = d / "output" / "manifest.json"
    if status == "done" and manifest_path.exists():
        m = pipeline.load_manifest(manifest_path)
        for i, c in enumerate(m.clips):
            seo = c.seo
            vid = _file_url(job_id, c.vertical_path or c.video_path)
            parts = [f'<h2>{esc(c.topic)} <span class="muted">({c.duration:.0f} שניות)</span></h2><div class="card clip">',
                     f'<div><video controls preload="metadata" src="{vid}" poster="{_file_url(job_id, c.thumbnail_path)}"></video>'
                     f'<div class="muted"><a href="{vid}" download>הורדת אנכי</a> · <a href="{_file_url(job_id, c.video_path)}" download>הורדת רוחבי</a>'
                     f' · <a href="{_file_url(job_id, c.subtitles_path)}" download>כתוביות</a></div></div><div>']
            if seo:
                parts.append(_copy_block(f"t{i}", "כותרת", seo.title))
                parts.append(_copy_block(f"a{i}", "כותרות חלופיות", "\n".join(seo.alternative_titles)))
                parts.append(_copy_block(f"d{i}", "תיאור מטא", seo.meta_description))
                parts.append(_copy_block(f"k{i}", "מילות מפתח", ", ".join([seo.focus_keyword, *seo.keywords])))
                parts.append(_copy_block(f"h{i}", "האשטאגים", " ".join(f"#{h}" for h in seo.hashtags)))
            for j, p in enumerate(c.posts):
                parts.append(_copy_block(f"p{i}_{j}", PLATFORMS.get(p.platform, p.platform),
                                         compose_post(p.platform, p.text, p.hashtags, p.call_to_action)))
            parts.append("</div></div>")
            body.append("".join(parts))
        if m.article:
            a = m.article
            body.append(f'<h2>מאמר: {esc(a.seo.title)}</h2><div class="card">'
                        + _copy_block("art", "Markdown", a.markdown)
                        + _copy_block("artd", "תיאור מטא", a.seo.meta_description)
                        + _copy_block("artk", "מילות מפתח", ", ".join([a.seo.focus_keyword, *a.seo.keywords])) + "</div>")
        targets = "".join(f'<label><input type="checkbox" name="targets" value="{k}"> {v}</label>' for k, v in TARGETS.items())
        results = "".join(f'<li class="{"done" if r.get("ok") else "error"}">{esc(r.get("platform"))}: '
                          f'{esc(r.get("url") or r.get("id"))} {esc(r.get("error"))}</li>' for r in job.get("publish") or [])
        body.append(f'<h2>פרסום</h2><form class="card" method="post" action="/jobs/{job_id}/publish">'
                    f'<div class="checks">{targets}</div><div class="muted">נוצר כטיוטה / פרטי / לא מפורסם היכן שאפשר. '
                    f'פרטי החשבונות מוגדרים במשתני הסביבה של השרת.</div>'
                    f'<button type="submit" {"disabled" if job.get("publishing") else ""}>{"מפרסם…" if job.get("publishing") else "פרסם"}</button>'
                    f'{"<ul>" + results + "</ul>" if results else ""}</form>')
    return page("ContentForge — עבודה", "".join(body), refresh=status in ("queued", "running") or bool(job.get("publishing")))


@app.post("/jobs/{job_id}/publish")
def publish_job(job_id: str, targets: list[str] = Form([]), user: str = Depends(require_user)):
    job = read_job(job_id)
    chosen = [t for t in targets if t in TARGETS]
    if job["status"] == "done" and chosen and not job.get("publishing"):
        update_job(job_id, publishing=True, publish=[])
        work.put((run_publish, (job_id, chosen)))
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.get("/files/{job_id}/{path:path}")
def files(job_id: str, path: str, user: str = Depends(require_user)):
    base = job_dir(job_id).resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)
