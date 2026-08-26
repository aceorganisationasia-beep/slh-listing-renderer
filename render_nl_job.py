#!/usr/bin/env python3
"""New launch job runner. Receives parsed project data from Apps Script,
renders the carousel, sends it back to Telegram."""
import json, os, socket, time, requests
from io import BytesIO
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# GitHub runners resolve AAAA records but often cannot route IPv6, so a
# connection to a dual-stack host hangs until it times out. Restricting
# resolution to IPv4 avoids that entirely.
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_only

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-SG,en;q=0.9",
    "Referer": "https://www.newlaunches.sg/",
    "Connection": "close",
}

def _session():
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=1.5,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers.update(BROWSER_HEADERS)
    return s

SESSION = _session()

from render_nl import (page_cover, page_units, page_amenities, page_location,
                       page_developers, page_cta, accent_from_logo,
                       knockout_background, DEFAULT_ACCENT)

TG = "https://api.telegram.org/bot{t}"

def msg(token, chat, text):
    try:
        requests.post(f"{TG.format(t=token)}/sendMessage",
                      json={"chat_id": chat, "text": text}, timeout=30)
    except Exception:
        pass

def get_image(url):
    """Fetch an image, retrying on transient failures.

    The photo host is slow to accept connections from CI runners, so
    each attempt gets a short connect timeout and a generous read
    timeout, and we try a few times before giving up."""
    last = None
    for attempt in range(4):
        try:
            r = SESSION.get(url, timeout=(15, 90))
            r.raise_for_status()
            return Image.open(BytesIO(r.content))
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Could not download {url.split('/')[-1]} after 4 tries: {last}")

def send_album(token, chat, images):
    files, media = {}, []
    for i, im in enumerate(images):
        buf = BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=96); buf.seek(0)
        tag = f"p{i+1}"
        files[tag] = (f"page_{i+1}.jpg", buf, "image/jpeg")
        media.append({"type": "document", "media": f"attach://{tag}"})
    r = requests.post(f"{TG.format(t=token)}/sendMediaGroup",
                      data={"chat_id": chat, "media": json.dumps(media)},
                      files=files, timeout=180)
    r.raise_for_status()

def chunk_units(groups, per_page=3):
    """Split BR groups across pages. A page holds at most `per_page`
    groups or 6 total bullet lines, whichever comes first, matching how
    the originals break."""
    pages, cur, lines = [], [], 0
    for g in groups:
        n = len(g[1])
        if cur and (len(cur) >= per_page or lines + n > 6):
            pages.append(cur); cur, lines = [], 0
        cur.append(g); lines += n
    if cur: pages.append(cur)
    return pages

def main():
    job = json.loads(os.environ["JOB_DATA"])
    job = job.get("job", job)
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = job["chat_id"]

    msg(token, chat, f"Rendering {job.get('project','project')}, about a minute...")

    def optional(url):
        if not url: return None
        try: return knockout_background(get_image(url))
        except Exception as e:
            msg(token, chat, f"Note: could not fetch {url.split('/')[-1]}, continuing without it.")
            return None

    logo = optional(job.get("logo_url"))
    accent = tuple(job["accent"]) if job.get("accent") else (
        accent_from_logo(logo) if logo is not None else DEFAULT_ACCENT)

    hero = get_image(job["hero_url"])
    amen = get_image(job["amenity_url"])
    mapi = get_image(job["map_url"])
    devs = [d for d in (optional(u) for u in job.get("developer_urls", [])) if d is not None]

    pages = [page_cover(logo, hero, job["address"], job["tenure"], job["top"])]
    for grp in chunk_units([(g["label"], g["variants"]) for g in job["units"]]):
        pages.append(page_units(grp, accent))
    pages.append(page_amenities(amen, job["facilities"], accent))
    pages.append(page_location(mapi, job.get("mrt", []), job.get("malls", []), accent))
    if devs:
        pages.append(page_developers(devs, accent))
    pages.append(page_cta(accent))

    for i in range(0, len(pages), 10):
        send_album(token, chat, pages[i:i+10])
    msg(token, chat, f"Done. {len(pages)} pages sent.")
    for cap in ("caption_en", "caption_cn"):
        if job.get(cap): msg(token, chat, job[cap])
    report_done(job, True)


def report_done(job, ok=True):
    """Tell Apps Script the render finished, so the watchdog does not
    raise a false alarm on a job that actually succeeded."""
    url = job.get("callback_url")
    secret = job.get("callback_secret")
    if not url or not secret:
        return
    try:
        requests.post(url, json={
            "slh_done": True, "secret": secret,
            "chat_id": job.get("chat_id"), "ok": bool(ok)
        }, timeout=30)
    except Exception:
        pass

def notify_failure(err):
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        job = json.loads(os.environ.get("JOB_DATA", "{}"))
        job = job.get("job", job)
        report_done(job, False)
        if token and job.get("chat_id"):
            msg(token, job["chat_id"],
                "RENDER FAILED\nService: New Launch\n"
                f"Project: {job.get('project','unknown')}\n\n"
                f"{type(err).__name__}: {str(err)[:400]}\n\n"
                "Nothing was sent. Start again with New Launch.")
    except Exception:
        pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        notify_failure(e); raise
