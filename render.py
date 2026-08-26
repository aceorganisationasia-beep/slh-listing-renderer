#!/usr/bin/env python3
"""SLH Listing Bot – GitHub Actions renderer.
Receives job JSON via repository_dispatch, composites carousel pages,
sends finished images back to Telegram.
"""
import json, os, sys, requests, math
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# ── constants ────────────────────────────────────────────────────────
W, H = 1080, 1350
BG = (232, 220, 204)
INK = (60, 54, 50)
FONT_REG = "GlacialIndifference-Regular.otf"
FONT_BOLD = "GlacialIndifference-Bold.otf"
BODY_SIZE = 46.5
CORNER_R = 18

# photo frame boxes  [x0, y0, x1, y1]
# Frames are inflated 3px beyond the Canva placeholder so the photo covers
# the anti-aliased fringe left by the original template art. The overlay
# knockouts are inflated by the same amount, so the two line up exactly.
FRAMES = {
    "p1": [[112, 258, 974, 828]],
    "p2": [[105, 105, 967, 720]],
    "p3": [[105, 105, 967, 720]],
    "p4": [[105, 105, 967, 658], [109, 737, 970, 1290]],
}

# text positions (baseline y for each line)
P1_LINES_Y = [966, 1096, 1226]
P1_CENTER_X = 527
P2_LINES_Y = [921, 1051, 1181]
P2_BULLET_X = 151
P2_TEXT_X = 192
P2_DOT_R = 7

TG_API = "https://api.telegram.org/bot{token}"
TG_FILE = "https://api.telegram.org/file/bot{token}"

# ── helpers ──────────────────────────────────────────────────────────
def font_reg(size=BODY_SIZE):
    return ImageFont.truetype(FONT_REG, int(size))

def font_bold(size=BODY_SIZE):
    return ImageFont.truetype(FONT_BOLD, int(size))

def fill_crop(img, box):
    """Centre-crop img to fill box exactly."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    s = max(bw / img.width, bh / img.height)
    im = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    l = (im.width - bw) // 2
    t = (im.height - bh) // 2
    return im.crop((l, t, l + bw, t + bh))

def round_mask(size, box, radius):
    """Create an alpha mask with a rounded-rect hole."""
    mask = Image.new("L", size, 255)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(box, radius=radius, fill=0)
    return mask

def centered_text(d, text, cx, baseline, fnt, fill=INK):
    tw = d.textlength(text, font=fnt)
    d.text((cx - tw / 2, baseline), text, font=fnt, fill=fill, anchor="ls")

def auto_size_text(d, text, max_w, fnt_path, start_size):
    """Shrink font until text fits max_w."""
    size = start_size
    while size > 20:
        f = ImageFont.truetype(fnt_path, int(size))
        if d.textlength(text, font=f) <= max_w:
            return f
        size -= 1
    return ImageFont.truetype(fnt_path, 20)

def download_tg_file(token, file_id):
    """Download a file from Telegram by file_id."""
    r = requests.get(f"{TG_API.format(token=token)}/getFile", params={"file_id": file_id})
    r.raise_for_status()
    fp = r.json()["result"]["file_path"]
    r2 = requests.get(f"{TG_FILE.format(token=token)}/{fp}")
    r2.raise_for_status()
    return Image.open(BytesIO(r2.content)).convert("RGB")

def send_tg_photo(token, chat_id, img, caption=""):
    """Send a PIL Image as a document (no compression) to Telegram."""
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=96)
    buf.seek(0)
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    r = requests.post(
        f"{TG_API.format(token=token)}/sendDocument",
        data=data,
        files={"document": (f"page.jpg", buf, "image/jpeg")},
    )
    r.raise_for_status()
    return r.json()

def send_tg_album(token, chat_id, images):
    """Send multiple images as a media group (documents)."""
    files = {}
    media = []
    for i, img in enumerate(images):
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=96)
        buf.seek(0)
        attach = f"page_{i+1}"
        files[attach] = (f"page_{i+1}.jpg", buf, "image/jpeg")
        media.append({"type": "document", "media": f"attach://{attach}"})
    r = requests.post(
        f"{TG_API.format(token=token)}/sendMediaGroup",
        data={"chat_id": chat_id, "media": json.dumps(media)},
        files=files,
    )
    r.raise_for_status()

def send_tg_message(token, chat_id, text):
    requests.post(
        f"{TG_API.format(token=token)}/sendMessage",
        json={"chat_id": chat_id, "text": text},
    )

# ── page builders ────────────────────────────────────────────────────
def build_p1(job, photos, tpl_type):
    """Page 1: hero photo + title card."""
    page = Image.new("RGBA", (W, H), BG + (255,))
    # photo
    cropped = fill_crop(photos[0], FRAMES["p1"][0])
    page.paste(cropped, (FRAMES["p1"][0][0], FRAMES["p1"][0][1]))
    # overlay
    ov = Image.open(f"{tpl_type}_p1.png").convert("RGBA")
    page.alpha_composite(ov)
    d = ImageDraw.Draw(page)
    # text lines
    lines = [
        f"{job['property_name']} ({job['district']})",
        f"{job['beds']} Bed {job['baths']} Bath Unit",
        f"{job['sqft']} Square Foot",
    ]
    card_w = 971 - 115 - 40  # usable card width with padding
    for text, by in zip(lines, P1_LINES_Y):
        f = auto_size_text(d, text, card_w, FONT_REG, BODY_SIZE)
        centered_text(d, text, P1_CENTER_X, by, f)
    return page.convert("RGB")

def build_bullet_page(job, photos, photo_idx, bullets, tpl_type, page_num):
    """Pages 2 and 3: one photo + three bullet lines."""
    page = Image.new("RGBA", (W, H), BG + (255,))
    frame = FRAMES[f"p{page_num}"][0]
    cropped = fill_crop(photos[photo_idx], frame)
    page.paste(cropped, (frame[0], frame[1]))
    ov = Image.open(f"{tpl_type}_p{page_num}.png").convert("RGBA")
    page.alpha_composite(ov)
    d = ImageDraw.Draw(page)
    f = font_reg()
    for text, by in zip(bullets, P2_LINES_Y):
        # bullet dot
        d.ellipse(
            (P2_BULLET_X, by - P2_DOT_R * 2, P2_BULLET_X + P2_DOT_R * 2, by),
            fill=INK,
        )
        d.text((P2_TEXT_X, by), text, font=f, fill=INK, anchor="ls")
    return page.convert("RGB")

def build_double_page(photos, idx_top, idx_bot, tpl_type):
    """Page 4+: two photos, no text."""
    page = Image.new("RGBA", (W, H), BG + (255,))
    frames = FRAMES["p4"]
    for frame, pi in zip(frames, [idx_top, idx_bot]):
        cropped = fill_crop(photos[pi], frame)
        page.paste(cropped, (frame[0], frame[1]))
    ov = Image.open(f"{tpl_type}_p4.png").convert("RGBA")
    page.alpha_composite(ov)
    return page.convert("RGB")

def build_cta(tpl_type):
    """Last page: static CTA, no compositing needed."""
    return Image.open(f"{tpl_type}_p5.png").convert("RGB")

# ── main ─────────────────────────────────────────────────────────────
def main():
    # parse job from env
    raw = json.loads(os.environ["JOB_DATA"])
    # Payload is nested under "job" to stay within GitHub's 10-property cap.
    job = raw.get("job", raw)
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = job["chat_id"]

    send_tg_message(token, chat_id, "Rendering your listing, hang on...")

    tpl_type = job["type"]  # "listing" or "rental"
    photo_ids = job["photo_file_ids"]  # list of telegram file_ids

    # download all photos
    photos = []
    for fid in photo_ids:
        try:
            photos.append(download_tg_file(token, fid))
        except Exception as e:
            send_tg_message(token, chat_id, f"Failed to download photo {len(photos)+1}: {e}")
            return

    n = len(photos)
    if n < 3:
        send_tg_message(token, chat_id, "Need at least 3 photos. Job cancelled.")
        return

    pages = []

    # PAGE 1: hero
    pages.append(build_p1(job, photos, tpl_type))

    # PAGE 2: highlights
    pages.append(build_bullet_page(job, photos, 1, job["highlights"], tpl_type, 2))

    # PAGE 3: amenities (distance lines)
    pages.append(build_bullet_page(job, photos, 2, job["amenities"], tpl_type, 3))

    # PAGES 4+: double photo pages for remaining photos
    remaining = list(range(3, n))
    while len(remaining) >= 2:
        pages.append(build_double_page(photos, remaining[0], remaining[1], tpl_type))
        remaining = remaining[2:]

    # if one photo left over, build a single-photo filler
    if remaining:
        idx = remaining[0]
        page = Image.new("RGBA", (W, H), BG + (255,))
        frame = FRAMES["p4"][0]  # use top frame position
        cropped = fill_crop(photos[idx], frame)
        page.paste(cropped, (frame[0], frame[1]))
        ov = Image.open(f"{tpl_type}_p4.png").convert("RGBA")
        page.alpha_composite(ov)
        pages.append(page.convert("RGB"))

    # LAST PAGE: CTA
    pages.append(build_cta(tpl_type))

    # send back via Telegram
    try:
        # send as album in batches of 10
        for i in range(0, len(pages), 10):
            batch = pages[i : i + 10]
            send_tg_album(token, chat_id, batch)
        send_tg_message(token, chat_id, f"Done. {len(pages)} pages sent.")
        for key in ("caption", "caption_cn"):
            if job.get(key):
                send_tg_message(token, chat_id, job[key])
    except Exception as e:
        send_tg_message(token, chat_id, f"Render complete but failed to send: {e}")
        # save locally as fallback
        for i, p in enumerate(pages):
            p.save(f"page_{i+1}.jpg", quality=96)
        print(f"Saved {len(pages)} pages locally")

def notify_failure(err):
    """Last-resort reporter. If the render dies, say so in Telegram
    rather than leaving the job to vanish silently."""
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        raw = json.loads(os.environ.get("JOB_DATA", "{}"))
        job = raw.get("job", raw)
        chat_id = job.get("chat_id")
        name = job.get("property_name", "your listing")
        if token and chat_id:
            send_tg_message(
                token, chat_id,
                "RENDER FAILED\n"
                f"Service: Listing / Rental\n"
                f"Project: {name}\n\n"
                f"{type(err).__name__}: {str(err)[:400]}\n\n"
                "Nothing was sent. Start again with /new."
            )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        notify_failure(e)
        raise
