"""
PixivyWalls
==============================================
Generates standalone 1920x1080 cinematic backdrop wallpapers with movie 
metadata baked directly into the image canvas. Fully compatible with free tiers!
"""

import os
import json
import time
import requests
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TMDB_API_KEY  = os.environ["TMDB_API_KEY"]
TMDB_BASE     = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/original"

OUTPUT_DIR    = Path("docs")
WALLPAPER_DIR = OUTPUT_DIR / "images"
OUTPUT_FILE   = OUTPUT_DIR / "wallpapers.json"

OUTPUT_DIR.mkdir(exist_ok=True)
WALLPAPER_DIR.mkdir(exist_ok=True)

MAX_PER_BUCKET = 12

LANGUAGES = [
    {"code": "en", "label": "English",   "flag": "🇬🇧"},
    {"code": "hi", "label": "Hindi",     "flag": "🇮🇳"},
    {"code": "kn", "label": "Kannada",   "flag": "🏴"},
    {"code": "ml", "label": "Malayalam", "flag": "🏴"},
]

CATEGORIES = [
    {"type": "movie", "label": "Movie", "emoji": "🎬", "endpoint": "trending/movie/week", "tag": "Trending"},
    {"type": "movie", "label": "Movie", "emoji": "🎬", "endpoint": "movie/popular",       "tag": "Popular"},
    {"type": "movie", "label": "Movie", "emoji": "🎬", "endpoint": "movie/top_rated",     "tag": "All-Time Top Rated"},
    {"type": "tv",    "label": "Series", "emoji": "📺", "endpoint": "trending/tv/week",    "tag": "Trending"},
    {"type": "tv",    "label": "Series", "emoji": "📺", "endpoint": "tv/popular",          "tag": "Popular"},
    {"type": "tv",    "label": "Series", "emoji": "📺", "endpoint": "tv/top_rated",        "tag": "All-Time Top Rated"},
]

# ─── TMDB DATA EXTRACTORS ────────────────────────────────────────────────────
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
        return tmdb_get(f"{'movie' if item_type == 'movie' else 'tv'}/{item_id}", {"language": "en-US", "append_to_response": "credits"})
    except:
        return {}

# ─── PILLOW IMAGE INFRASTRUCTURE COMPOSITOR ──────────────────────────────────
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

def create_composite_card(details, category, lang, item_type, file_name):
    backdrop_path = details.get("backdrop_path")
    if not backdrop_path or details.get("adult", False):
        return None

    try:
        # Download Raw Backdrop Widescreen Asset
        img_res = requests.get(f"{TMDB_IMG_BASE}{backdrop_path}", timeout=20)
        base_img = Image.open(BytesIO(img_res.content)).convert("RGBA")
        
        # Enforce True 16:9 1080p Canvas Target Dimensions
        base_img = base_img.resize((1920, 1080), Image.Resampling.LANCZOS)
        
        # Build Overlay Mask Layers (Dark Side-Fade Card Block)
        overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Draw Left-to-Right Alpha Gradient Overlay Block
        for x in range(1200):
            alpha = int(240 * (1.0 - (x / 1100)**1.8)) if x <= 1100 else 0
            if alpha < 0: alpha = 0
            draw.line([(x, 0), (x, 1080)], fill=(10, 10, 12, alpha))
            
        # Composite Base Assets Together
        combined = Image.alpha_composite(base_img, overlay).convert("RGB")
        draw = ImageDraw.Draw(combined)
        
        # Typography Metadata Parsing
        title = (details.get("title") if item_type == "movie" else details.get("name")) or "Unknown Title"
        year = (details.get("release_date") if item_type == "movie" else details.get("first_air_date") or "N/A")[:4]
        rating = f"{details.get('vote_average', 0):.1f}"
        
        genres = ", ".join([g["name"] for g in details.get("genres", [])[:3]]) or "General"
        cast_list = ", ".join([c["name"] for c in details.get("credits", {}).get("cast", [])[:4]]) or "N/A"
        
        director = "TMDB"
        if item_type == "movie":
            dirs = [c["name"] for c in details.get("credits", {}).get("crew", []) if c.get("job") == "Director"]
            if dirs: director = dirs[0]
            
        overview = details.get("overview") or "No background synopsis information available."

        # Typesetting Coordinates Engine (Fallback fonts inside Linux boxes default neatly)
        try:
            font_title = ImageFont.load_default(size=56)
            font_meta  = ImageFont.load_default(size=24)
            font_body  = ImageFont.load_default(size=22)
        except:
            font_title = font_meta = font_body = ImageFont.load_default()

        # Render Text Passes
        draw.text((90, 220), title.upper(), fill=(255, 255, 255), font=font_title)
        
        meta_string = f"🎞️ {genres}  •  📅 {year}  •  ⭐ {rating}/10"
        draw.text((90, 310), meta_string, fill=(229, 9, 20), font=font_meta)
        
        crew_string = f"👥 Cast: {cast_list}\n🎬 Director/Source: {director}"
        draw.text((90, 360), crew_string, fill=(180, 180, 180), font=font_body)
        
        # Paragraph Text Wrapping Wrapper
        y_cursor = 450
        lines = text_wrap(overview, font_body, 850, draw)
        for line in lines[:8]:  # Contain block bounds safety clamp
            draw.text((90, y_cursor), line, fill=(210, 210, 210), font=font_body)
            y_cursor += 32
            
        # Save Flat Composite Asset File Link Output
        combined.save(WALLPAPER_DIR / file_name, "JPEG", quality=92)
        return f"images/{file_name}"
    except Exception as e:
        print(f"      ↳ Composite creation exception: {e}")
        return None

# ─── CORE PIPELINE ENGINE ────────────────────────────────────────────────────
def run():
    print(f"\n PixivyWalls Composite Studio Initializing...")
    seen_ids = set()
    entries  = []

    for lang in LANGUAGES:
        print(f"  {lang['flag']} Processing language: {lang['label']}")
        for category in CATEGORIES:
            items = fetch_items(category, lang)
            time.sleep(0.1)

            added = 0
            for item in items:
                item_id   = item.get("id")
                item_type = category["type"]
                
                if item_id in seen_ids:
                    continue

                details = fetch_details(item_type, item_id)
                time.sleep(0.1)
                if not details: continue

                # Generate clean unique safe naming tags
                safe_title = "".join([c for c in (details.get("title") or details.get("name") or "media") if c.isalnum()]).lower()[:20]
                file_name = f"wall_{item_type}_{item_id}_{safe_title}.jpg"
                
                img_relative_path = create_composite_card(details, category, lang, item_type, file_name)
                
                if img_relative_path:
                    entries.append({
                        "location": f"{category['label']} · {lang['label']} · {category['tag']}",
                        "title": f"{category['emoji']} {details.get('title') if item_type == 'movie' else details.get('name')} ({lang['label']})",
                        "author": lang["label"],
                        "url_img": f"https://unableeludemotto.github.io/PixivyWalls/{img_relative_path}"
                    })
                    seen_ids.add(item_id)
                    added += 1

            if added > 0:
                print(f"    └─ [{category['label']} - {category['tag']}]: Built +{added} composite cards")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        
    print(f"\n Master File Configuration Deployment Complete! Managed {len(entries)} cards.\n")

if __name__ == "__main__":
    run()
