#!/usr/bin/env python3
"""SLH New Launch renderer. Builds carousel pages from project data."""
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W, H = 1080, 1350
BG   = (232, 221, 204)
CARD = (244, 238, 234)
INK  = (58, 58, 58)
RADIUS = 34

HANG  = "Hangyaboly.ttf"
BRIC  = "BricolageGrotesque-ExtraBold.otf"
BRICC = "BricolageGrotesque48ptCondensed-ExtraBold.otf"

S_TITLE, S_BODY, S_UNIT, S_BR, S_AMEN, S_LOC, S_LOCHEAD = 105, 47, 43, 64, 38, 40, 54

TITLE_BASE   = 205
# Logo box roughly doubled from the measured original so smaller
# wordmarks do not get lost on the cover.
COVER_LOGO   = (270, 40, 810, 336)
COVER_PHOTO  = (115, 350, 971, 797)
COVER_CARD   = (115, 838, 971, 1244)
COVER_CX, COVER_LINES = 527, (931, 1060, 1189)
UNITS_CARD   = (112, 286, 967, 1287)
UNIT_HEAD_X, UNIT_DOT_X, UNIT_TEXT_X = 180, 164, 192
# Measured from the Canva originals as ink-top to ink-top.
# HEAD_BULLET carries extra air beyond the original 63 for readability.
GAP_HEAD_BULLET, GAP_BULLET, GAP_GROUP = 76, 58, 112
AMEN_PHOTO, AMEN_CARD, AMEN_PITCH, AMEN_CX = (115, 290, 971, 652), (115, 707, 971, 1282), 110, 539
LOC_PHOTO, LOC_CARD, LOC_CX = (115, 292, 971, 738), (115, 790, 971, 1289), 540
DEV_CARD = (115, 293, 971, 1280)

_FONTS = {}
def font(path, size):
    key = (path, size)
    if key not in _FONTS: _FONTS[key] = ImageFont.truetype(path, size)
    return _FONTS[key]

_INKOFF = {}
def ink_offset(path, size):
    """Pixels between the draw origin and where the ink actually starts.
    Differs per typeface, so aligning by ink keeps gaps true across fonts."""
    key = (path, size)
    if key in _INKOFF: return _INKOFF[key]
    f = font(path, size)
    im = Image.new("L", (1600, 400), 255)
    ImageDraw.Draw(im).text((40, 150), "Hxpqjy 123", font=f, fill=0)
    a = np.array(im); r = np.where((a < 128).sum(axis=1) > 0)[0]
    _INKOFF[key] = int(r.min() - 150) if len(r) else 0
    return _INKOFF[key]

def text_ink(d, text, x, ink_y, path, size, fill):
    """Draw so the top of the ink lands exactly on ink_y."""
    d.text((x, ink_y - ink_offset(path, size)), text, font=font(path, size), fill=fill)

def rounded(size, box, radius, colour):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=colour + (255,))
    return layer

def fill_crop(img, box):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    s = max(bw / img.width, bh / img.height)
    im = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    l, t = (im.width - bw) // 2, (im.height - bh) // 2
    return im.crop((l, t, l + bw, t + bh))

def paste_rounded(page, img, box, radius=RADIUS):
    x0, y0, x1, y1 = box
    crop = fill_crop(img, box).convert("RGBA")
    mask = Image.new("L", (x1 - x0 + 1, y1 - y0 + 1), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, x1 - x0, y1 - y0), radius=radius, fill=255)
    page.paste(crop, (x0, y0), mask)

def fit_contain(img, box):
    """Scale to fit inside box without cropping, preserving aspect."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    s = min(bw / img.width, bh / img.height)
    im = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    return im, (x0 + (bw - im.width) // 2, y0 + (bh - im.height) // 2)

def ctext(d, text, cx, baseline, f, fill):
    d.text((cx, baseline), text, font=f, fill=fill, anchor="ms")

def new_page():
    return Image.new("RGBA", (W, H), BG + (255,))

def add_card(page, box):
    page.alpha_composite(rounded((W, H), box, RADIUS, CARD))

def add_title(page, text, accent):
    ctext(ImageDraw.Draw(page), text, W // 2, TITLE_BASE, font(BRIC, S_TITLE), accent)

# ── pages ───────────────────────────────────────────────────────────
def page_cover(logo, photo, address, tenure, top):
    p = new_page()
    if logo is not None:
        im, pos = fit_contain(logo, COVER_LOGO)
        p.alpha_composite(im.convert("RGBA"), pos)
    paste_rounded(p, photo, COVER_PHOTO)
    add_card(p, COVER_CARD)
    d = ImageDraw.Draw(p)
    f = font(HANG, S_BODY)
    for text, base in zip([address, tenure, top], COVER_LINES):
        ctext(d, text, COVER_CX, base, f, INK)
    return p

def units_block_height(groups):
    h = 0
    for i, (_, variants) in enumerate(groups):
        h += GAP_HEAD_BULLET + GAP_BULLET * (len(variants) - 1)
        if i < len(groups) - 1: h += GAP_GROUP
    return h

def page_units(groups, accent):
    p = new_page(); add_title(p, "Units", accent); add_card(p, UNITS_CARD)
    d = ImageDraw.Draw(p)
    cy = (UNITS_CARD[1] + UNITS_CARD[3]) // 2
    y = cy - units_block_height(groups) // 2
    for gi, (label, variants) in enumerate(groups):
        text_ink(d, label, UNIT_HEAD_X, y, BRICC, S_BR, accent)
        y += GAP_HEAD_BULLET
        for vi, v in enumerate(variants):
            d.ellipse((UNIT_DOT_X, y + 13, UNIT_DOT_X + 11, y + 24), fill=INK)
            text_ink(d, v, UNIT_TEXT_X, y, HANG, S_UNIT, INK)
            if vi < len(variants) - 1: y += GAP_BULLET
        if gi < len(groups) - 1: y += GAP_GROUP
    return p

def page_amenities(photo, items, accent):
    p = new_page(); add_title(p, "Amenities", accent)
    paste_rounded(p, photo, AMEN_PHOTO); add_card(p, AMEN_CARD)
    d = ImageDraw.Draw(p); f = font(HANG, S_AMEN)
    cy = (AMEN_CARD[1] + AMEN_CARD[3]) // 2
    y = cy - (AMEN_PITCH * (len(items) - 1)) // 2
    for it in items:
        ctext(d, it, AMEN_CX, y, f, INK); y += AMEN_PITCH
    return p

def page_location(mapimg, mrt, malls, accent):
    p = new_page(); add_title(p, "Location", accent)
    paste_rounded(p, mapimg, LOC_PHOTO); add_card(p, LOC_CARD)
    d = ImageDraw.Draw(p)
    fh, fb = font(BRIC, S_LOCHEAD), font(HANG, S_LOC)
    rows = []
    if mrt:   rows.append(("MRT", mrt))
    if malls: rows.append(("Malls", malls))
    total = 0
    for i, (_, items) in enumerate(rows):
        total += 59 + 55 * (len(items) - 1)
        if i < len(rows) - 1: total += 87
    cy = (LOC_CARD[1] + LOC_CARD[3]) // 2
    y = cy - total // 2
    for ri, (head, items) in enumerate(rows):
        ctext(d, head, LOC_CX - 12, y, fh, accent); y += 59
        for ii, it in enumerate(items):
            ctext(d, it, LOC_CX, y, fb, INK)
            if ii < len(items) - 1: y += 55
        if ri < len(rows) - 1: y += 87
    return p

def page_developers(logos, accent):
    p = new_page(); add_title(p, "Developers", accent); add_card(p, DEV_CARD)
    n = max(1, len(logos))
    top, bot = DEV_CARD[1] + 60, DEV_CARD[3] - 60
    slot = (bot - top) // n
    # Logos sit in a fixed-size box inside each slot rather than filling it,
    # matching the modest scale used in the Canva original.
    MAXW, MAXH = 380, 260
    for i, lg in enumerate(logos):
        scy = top + i * slot + slot // 2
        box = (W // 2 - MAXW // 2, scy - MAXH // 2, W // 2 + MAXW // 2, scy + MAXH // 2)
        im, pos = fit_contain(lg, box)
        p.alpha_composite(im.convert("RGBA"), pos)
    return p


# ── CTA page ────────────────────────────────────────────────────────
# The CTA artwork is identical across every post. Only the headline
# takes the project accent colour, so the base PNG is recoloured in
# place rather than rebuilt, keeping the phone mockup, WhatsApp badge
# and CEA line pixel-exact.
CTA_BASE = "listing_p5.png"
CTA_HEADLINE = (0, 870, W, 1220)   # region holding the three headline lines

def page_cta(accent, base_path=CTA_BASE):
    base = Image.open(base_path).convert("RGB")
    a = np.array(base).astype(float)
    x0, y0, x1, y1 = CTA_HEADLINE
    region = a[y0:y1, x0:x1]

    bg = np.array(BG, dtype=float)
    acc = np.array(accent, dtype=float)

    # How far each pixel is from the background, normalised to 0..1.
    # Black glyph pixels give 1, background gives 0, edges land between,
    # which preserves the original anti-aliasing.
    dist = np.abs(region - bg).sum(axis=2)
    alpha = np.clip(dist / np.abs(np.zeros(3) - bg).sum(), 0, 1)[..., None]

    a[y0:y1, x0:x1] = bg * (1 - alpha) + acc * alpha
    return Image.fromarray(a.round().astype("uint8")).convert("RGBA")


# ── logo handling ───────────────────────────────────────────────────
def knockout_background(img, tol=42):
    """Make a solid flat background transparent.

    Project logos are often shipped white-on-black or black-on-white,
    which looks wrong dropped onto the beige card. Samples the four
    corners, and only knocks out if they agree, so a logo sitting on a
    photo is left untouched rather than mangled."""
    im = img.convert("RGBA")
    a = np.array(im).astype(int)
    h, w = a.shape[:2]
    corners = np.array([a[0, 0, :3], a[0, w-1, :3], a[h-1, 0, :3], a[h-1, w-1, :3]])
    if corners.std(axis=0).max() > 12:
        return im                      # corners disagree, not a flat background
    bgc = corners.mean(axis=0)
    if np.abs(bgc - np.array(BG)).sum() < 40:
        return im                      # already sitting on our beige
    dist = np.abs(a[:, :, :3] - bgc).sum(axis=2)
    alpha = np.clip((dist - tol) * 6, 0, 255)
    a[:, :, 3] = np.minimum(a[:, :, 3], alpha)
    return Image.fromarray(a.astype("uint8"), "RGBA")


DEFAULT_ACCENT = (93, 102, 97)

def accent_from_logo(img, fallback=DEFAULT_ACCENT):
    """Pick the project accent colour from its logo.

    Weights by saturation so a brand colour beats black text, then
    rejects anything too pale, too dark or too grey to read as an
    accent on the beige background."""
    im = img.convert("RGBA").resize((120, 120))
    a = np.array(im).astype(float)
    rgb, alpha = a[:, :, :3], a[:, :, 3]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    lum = rgb.mean(axis=2)

    keep = (alpha > 128) & (sat > 0.18) & (lum > 35) & (lum < 225)
    if keep.sum() < 40:
        return fallback

    # Average only the most saturated quarter. Anti-aliased edges sit at
    # low saturation and would otherwise wash the colour out.
    cand, csat = rgb[keep], sat[keep]
    cut = np.quantile(csat, 0.75)
    core = cand[csat >= cut]
    if len(core) < 10: core = cand
    picked = core.mean(axis=0)
    r, g, b = picked
    p_mx, p_mn = max(r, g, b), min(r, g, b)
    p_sat = (p_mx - p_mn) / max(p_mx, 1)
    p_lum = (r + g + b) / 3
    if p_sat < 0.12 or p_lum < 45 or p_lum > 215:
        return fallback
    return (int(round(r)), int(round(g)), int(round(b)))
