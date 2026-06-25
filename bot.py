"""
PixivyWalls Engine v19 — Verified Release
========================================
Eliminates blocky pills, replaces broken emojis, automatically filters out N/A data,
and forces 100% uncompressed text rendering for crystal-clear TV couch legibility.
"""

import os
import json
import time
import shutil
import requests
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TMDB_API_KEY  = os.environ["TMDB_API_KEY"]
TMDB_BASE     = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/original"

OUTPUT_DIR    = Path("docs")
WALLPAPER_DIR = OUTPUT_DIR / "images"
OUTPUT_FILE   = OUTPUT_DIR / "wallpapers.json"

OUTPUT_DIR.mkdir(exist_ok=True)

def cleanup_old_assets():
    print("🧹 Cleaning up legacy movie wallpaper asset directories...")
    if WALLPAPER_DIR.exists():
        try:
            shutil.rmtree(WALLPAPER_DIR)
            print("  ↳ Legacy images folder wiped successfully.")
        except Exception as e:
            print(f"  ↳ Cleanup warning: {e}")
    WALLPAPER_DIR.mkdir(exist_ok=True)

cleanup_old_assets()

MAX_PER_BUCKET = 12

LANGUAGES = [
    {"code": "en", "label": "English"},
    {"code": "hi", "label": "Hindi"},
    {"code": "kn", "label": "Kannada"},
    {"code": "ml", "label": "Malayalam"},
]

CATEGORIES = [
    {"type": "movie", "label": "Movie", "endpoint": "trending/movie/week", "tag": "Trending"},
    {"type": "movie", "label": "Movie", "endpoint": "movie/popular",       "tag": "Popular"},
    {"type": "movie", "label": "Movie", "endpoint": "movie/top_rated",     "tag": "All-Time Top Rated"},
    {"type": "tv",    "label": "Series", "endpoint": "trending/tv/week",    "tag": "Trending"},
    {"type": "tv",    "label": "Series", "endpoint": "tv/popular",          "tag": "Popular"},
    {"type": "tv",    "label": "Series", "endpoint": "tv/top_rated",        "tag": "All-Time Top Rated"},
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def tmdb_get(endpoint: str, params: dict = {}) -> dict:
    url = f"{TMDB_BASE}/{endpoint}"
    p   = {"api_key": TMDB_API_KEY, **params}
    r   = requests.get(url, params=p, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_items(category: dict, lang: dict) -> list:
    if category["tag"] == "All-Time Top Rated" and lang["code"] == "ml":
        return []
    params = {"language": "en-US", "page": 1, "include_adult": "false"}
    if lang["code"] != "en":
        params["with_original_language"] = lang["code"]
    try:
        return tmdb_get(category["endpoint"], params).get("results", [])[:MAX_PER_BUCKET]
    except:
        return []

def fetch_details(item_type: str, item_id: int) -> dict:
    try:
        return tmdb_get(f"{'movie' if item_type == 'movie' else 'tv'}/{item_id}", {
            "language": "en-US", 
            "append_to_response": "credits,images",
            "include_image_language": "en"
        })
    except:
        return {}

def text_wrap(text, font, max_width, draw):
    words = text.split(' ')
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines

# ─── COMPOSITOR ENGINE ───────────────────────────────────────────────────────
def create_composite_card(details, category, lang, item_type, file_name):
    backdrop_path = details.get("backdrop_path")
    if not backdrop_path or details.get("adult", False):
        return None

    try:
        font_path = "assets/Roboto.ttf"
        if os.path.exists(font_path):
            font_title = ImageFont.truetype(font_path, 76)
            font_meta  = ImageFont.truetype(font_path, 28)
            font_label = ImageFont.truetype(font_path, 20)
            font_body  = ImageFont.truetype(font_path, 24)
        else:
            font_title = font_meta = font_label = font_body = ImageFont.load_default()

        img_res = requests.get(f"{TMDB_IMG_BASE}{backdrop_path}", timeout=20)
        base_img = Image.open(BytesIO(img_res.content)).convert("RGBA")
        base_img = base_img.resize((1920, 1080), Image.Resampling.LANCZOS)
        
        # Premium full-bleed vignette shading overlay
        overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        
        for y_pos in range(1080):
            for x_pos in range(1920):
                x_factor = (1.0 - (x_pos / 1100)**1.3) if x_pos <= 1100 else 0
                y_factor = (y_pos / 1080)**2.5
                
                alpha = int(240 * max(x_factor, y_factor))
                if alpha > 240: alpha = 240
                if alpha < 0: alpha = 0
                
                if alpha > 0:
                    draw_ov.point((x_pos, y_pos), fill=(6, 6, 8, alpha))
            
        combined = Image.alpha_composite(base_img, overlay).convert("RGBA")
        draw = ImageDraw.Draw(combined)
        
        title = (details.get("title") if item_type == "movie" else details.get("name")) or "Unknown"
        year = (details.get("release_date") if item_type == "movie" else details.get("first_air_date") or "N/A")[:4]
        
        # Smart Meta Element Filtering Engine
        meta_elements = []
        
        if item_type == "tv":
            seasons_count = details.get("number_of_seasons", 0)
            if seasons_count > 0:
                meta_elements.append(f"{seasons_count} Season" if seasons_count == 1 else f"{seasons_count} Seasons")
        else:
            runtime = details.get("runtime", 0)
            if runtime > 0:
                meta_elements.append(f"{runtime} min")
                
        if year and year != "N/A":
            meta_elements.append(year)
            
        rating = details.get("vote_average", 0.0)
        if rating > 0.0:
            meta_elements.append(f"★ {rating:.1f} IMDB")
            
        meta_line = "    •    ".join(meta_elements)

        # 1. RENDER Dynamic Title Graphic Block
        logo_drawn = False
        logos = details.get("images", {}).get("logos", [])
        
        if logos:
            target_logos =
