#!/usr/bin/env python3
"""New launch job runner. Receives parsed project data from Apps Script,
renders the carousel, sends it back to Telegram."""
import json, os, requests
from io import BytesIO
from PIL import Image

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
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return Image.open(BytesIO(r.content))

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

    logo = knockout_background(get_image(job["logo_url"])) if job.get("logo_url") else None
    accent = tuple(job["accent"]) if job.get("accent") else (
        accent_from_logo(logo) if logo is not None else DEFAULT_ACCENT)

    hero = get_image(job["hero_url"])
    amen = get_image(job["amenity_url"])
    mapi = get_image(job["map_url"])
    devs = [knockout_background(get_image(u)) for u in job.get("developer_urls", [])]

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

def notify_failure(err):
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        job = json.loads(os.environ.get("JOB_DATA", "{}"))
        job = job.get("job", job)
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
