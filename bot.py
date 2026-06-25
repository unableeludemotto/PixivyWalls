"""
PixivyWalls Engine
======================================================
Optimized for couch legibility, fixes alpha-flattening bugs, 
uses universal character formatting, and applies custom thematic font coloring.
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

def draw_stremio_row(draw, label_font, badge_font, start_x, y, label, items):
    if not items:
        return 0
    # Premium Cinematic Slate Amber for headers
    draw.text((start_x, y), label.upper(), fill=(212, 175, 55), font=label_font)
    
    current_x = start_x
    badge_y = y + 32
    
    for item in items:
        bbox = draw.textbbox((0, 0), item, font=badge_font)
        tw = bbox[2] - bbox[0]
        badge_w = tw + 32
        badge_h = 44
        
        # Muted dark obsidian pill containment
        draw.rounded_rectangle(
            [current_x, badge_y, current_x + badge_w, badge_y + badge_h],
            radius=8,
            fill=(32, 32, 36),
            outline=None
        )
        # Soft metallic silver font inside the pills
        draw.text((current_x + 16, badge_y + 8), item, fill=(224, 224, 229), font=badge_font)
        current_x += badge_w + 12
        
    return 86

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
        
        overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        
        for y_pos in range(1080):
            for x_pos in range(1920):
                x_factor = (1.0 - (x_pos / 1350)**1.4) if x_pos <= 1350 else 0
                y_factor = 1.0 if y_pos >= 680 else ((y_pos - 460) / 220)**1.2 if y_pos >= 460 else 0
                
                alpha = int(252 * max(x_factor, y_factor))
                if alpha > 252: alpha = 252
                if alpha < 0: alpha = 0
                
                if alpha > 0:
                    draw_ov.point((x_pos, y_pos), fill=(8, 8, 10, alpha))
            
        combined = Image.alpha_composite(base_img, overlay).convert("RGBA")
        draw = ImageDraw.Draw(combined)
        
        title = (details.get("title") if item_type == "movie" else details.get("name")) or "Unknown"
        year = (details.get("release_date") if item_type == "movie" else details.get("first_air_date") or "N/A")[:4]
        rating = f"{details.get('vote_average', 0):.1f}"
        
        if item_type == "tv":
            seasons_count = details.get("number_of_seasons", 1)
            runtime = f"{seasons_count} Season" if seasons_count == 1 else f"{seasons_count} Seasons"
        else:
            runtime = "N/A"
            if details.get("runtime"):
                runtime = f"{details['runtime']} min"

        # 1. SCALE TITLE LOGO
        logo_drawn = False
        logos = details.get("images", {}).get("logos", [])
        
        if logos:
            target_logos = [l for l in logos if l.get("iso_639_1") == "en" and l.get("file_path", "").endswith(".png")]
            if not target_logos:
                target_logos = [l for l in logos if l.get("file_path", "").endswith(".png")]
                
            if target_logos:
                try:
                    target_logos.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
                    logo_path = target_logos[0]["file_path"]
                    logo_res = requests.get(f"{TMDB_IMG_BASE}{logo_path}", timeout=10)
                    logo_img = Image.open(BytesIO(logo_res.content)).convert("RGBA")
                    
                    max_w, max_h = 650, 160
                    logo_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                    
                    combined.alpha_composite(logo_img, dest=(90, 80))
                    logo_drawn = True
                except:
                    pass

        if not logo_drawn:
            draw.text((90, 80), title, fill=(255, 255, 255), font=font_title)
        
        # Swapped broken rectangle emoji for a high-compatibility star text icon
        meta_line = f"{runtime}    •    {year}    •    ★ {rating} IMDB"
        draw.text((90, 260), meta_line, fill=(240, 240, 245), font=font_meta)
        
        # 2. RENDER THE BADGE ROWS
        y_cursor = 310
        genres = [g["name"] for g in details.get("genres", [])[:3]]
        if genres:
            y_cursor += draw_stremio_row(draw, font_label, font_body, 90, y_cursor, "genres", genres)
            
        credits = details.get("credits", {})
        directors = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"][:1]
        if item_type == "tv" and details.get("created_by"):
            directors = [c["name"] for c in details["created_by"]][:1]
        if directors:
            y_cursor += draw_stremio_row(draw, font_label, font_body, 90, y_cursor, "directors", directors)
            
        cast = [c["name"] for c in credits.get("cast", [])[:3]]
        if cast:
            y_cursor += draw_stremio_row(draw, font_label, font_body, 90, y_cursor, "cast", cast)
            
        # 3. SUMMARY
        y_cursor += 10
        draw.text((90, y_cursor), "SUMMARY", fill=(212, 175, 55), font=font_label)
        
        overview = details.get("overview") or "No background summary details available."
        y_cursor += 32
        lines = text_wrap(overview, font_body, 860, draw)
        
        for line in lines[:3]:
            if y_cursor > 615:
                break
            draw.text((90, y_cursor), line, fill=(245, 245, 250), font=font_body)
            y_cursor += 34
            
        final_rgb = combined.convert("RGB")
        final_rgb.save(WALLPAPER_DIR / file_name, "JPEG", quality=92)
        return f"images/{file_name}"
    except Exception as e:
        print(f"      ↳ Exception: {e}")
        return None

def run():
    print(f"\n PixivyWalls Stremio-Pro Engine Initiating...")
    seen_ids = set()
    entries  = []

    for lang in LANGUAGES:
        print(f"  Language: {lang['label']}")
        for category in CATEGORIES:
            items = fetch_items(category, lang)
            time.sleep(0.1)

            added = 0
            for item in items:
                item_id   = item.get("id")
                item_type = category["type"]
                if item_id in seen_ids: continue

                details = fetch_details(item_type, item_id)
                time.sleep(0.1)
                if not details: continue

                safe_title = "".join([c for c in (details.get("title") or details.get("name") or "media") if c.isalnum()]).lower()[:20]
                file_name = f"wall_{item_type}_{item_id}_{safe_title}.jpg"
                
                img_relative_path = create_composite_card(details, category, lang, item_type, file_name)
                
                if img_relative_path:
                    entries.append({
                        "location": f"{category['label']} · {lang['label']} · {category['tag']}",
                        "title": f"{details.get('title') if item_type == 'movie' else details.get('name')}",
                        "author": lang["label"],
                        "url_img": f"https://unableeludemotto.github.io/PixivyWalls/{img_relative_path}"
                    })
                    seen_ids.add(item_id)
                    added += 1

            if added > 0:
                print(f"    └─ [{category['label']} - {category['tag']}]: Built +{added} vectors")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
