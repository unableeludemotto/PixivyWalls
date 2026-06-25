"""
PixivyWalls Engine v35 — The Perfect Hybrid Studio Layout
=========================================================
- Keeps our absolute text & logo grid system for perfect line spacing.
- Uses the organic Subreddit-style curved oval mask for the artwork.
- Guarantees a solid black bottom 25% zone for clean TV app icons.
"""

import os
import json
import time
import shutil
import requests
import math
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
    p = {"api_key": TMDB_API_KEY, **params}
    r = requests.get(url, params=p, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_items(category: dict, lang: dict) -> list:
    if category["tag"] == "All-Time Top Rated" and lang["code"] == "ml":
        return []
    
    endpoint = category.get("endpoint") or category.get("github-actions")
    if not endpoint:
        return []
        
    params = {"language": "en-US", "page": 1, "include_adult": "false"}
    if lang["code"] != "en":
        params["with_original_language"] = lang["code"]
    try:
        res = tmdb_get(endpoint, params)
        return res.get("results", [])[:MAX_PER_BUCKET]
    except:
        return []

def fetch_details(item_type: str, item_id: int) -> dict:
    try:
        endpoint = "movie" if item_type == "movie" else "tv"
        return tmdb_get(f"{endpoint}/{item_id}", {
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
            font_title = ImageFont.truetype(font_path, 80)
            font_meta  = ImageFont.truetype(font_path, 32)
            font_label = ImageFont.truetype(font_path, 20)
            font_body  = ImageFont.truetype(font_path, 28)
        else:
            font_title = font_meta = font_label = font_body = ImageFont.load_default()

        # 1. Download original full-frame poster asset
        img_res = requests.get(f"{TMDB_IMG_BASE}{backdrop_path}", timeout=20)
        base_img = Image.open(BytesIO(img_res.content)).convert("RGBA")
        base_img = base_img.resize((1920, 1080), Image.Resampling.LANCZOS)
        
        # 2. Re-engineer the blend mask with absolute left & bottom solid voids
        overlay = Image.new(mode="RGBA", size=(1920, 1080), color=(0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        
        # Curved spotlight window dimensions
        center_x = 1350
        center_y = 405  # Center point within the upper 75% quadrant
        max_radius = 650
        
        for y_pos in range(1080):
            for x_pos in range(1920):
                # Safe Left 40% Block: Permanent flat dark void for our custom layout text
                if x_pos <= 768:
                    draw_ov.point((x_pos, y_pos), fill=(5, 6, 8, 255))
                    continue
                # Safe Bottom 25% Block: Permanent flat dark void for your TV app icons row
                if y_pos >= 810:
                    draw_ov.point((x_pos, y_pos), fill=(5, 6, 8, 255))
                    continue
                    
                # Curved radial distance calculation for organic feather boundaries
                distance = math.sqrt((x_pos - center_x)**2 + (y_pos - center_y)**2)
                
                if distance < 200:
                    alpha = 0  # Unaltered clear image pocket zone
                elif distance < max_radius:
                    alpha = int(255 * ((distance - 200) / (max_radius - 200)))
                else:
                    alpha = 255
                    
                if alpha > 0:
                    draw_ov.point((x_pos, y_pos), fill=(5, 6, 8, alpha))
            
        combined = Image.alpha_composite(base_img, overlay).convert("RGBA")
        draw = ImageDraw.Draw(combined)
        
        # ─── TYPOGRAPHY GRAPHICS ENGINE ───────────────────────────────────────
        title = details.get("title") if item_type == "movie" else details.get("name")
        if not title:
            title = "Unknown"
            
        release_field = "release_date" if item_type == "movie" else "first_air_date"
        year = (details.get(release_field) or "N/A")[:4]
        
        meta_elements = []
        if item_type == "tv":
            seasons_count = details.get("number_of_seasons", 0)
            if seasons_count > 0:
                lbl = f"{seasons_count} Season" if seasons_count == 1 else f"{seasons_count} Seasons"
                meta_elements.append(lbl)
        else:
            runtime = details.get("runtime", 0)
            if runtime > 0:
                meta_elements.append(f"{runtime} min")
                
        if year and year != "N/A":
            meta_elements.append(year)
            
        rating = details.get("vote_average", 0.0)
        if rating > 0.0:
            meta_elements.append(f"IMDB: {rating:.1f}")
            
        meta_line = "    •    ".join(meta_elements)

        # Custom Logo / Title Compositor (Pinned within the flat 40% margin area)
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
                    
                    max_w, max_h = 580, 160
                    logo_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                    
                    combined.alpha_composite(logo_img, dest=(80, 80))
                    logo_drawn = True
                except:
                    pass

        if not logo_drawn:
            draw.text((80, 80), title, fill=(255, 255, 255), font=font_title)
        
        draw.text((80, 260), meta_line, fill=(245, 245, 250), font=font_meta)
        
        # Absolute Separation Layout (Restricted to a high-readability text boundary of 640px)
        genres = ", ".join([g["name"] for g in details.get("genres", [])[:3]]) or "General"
        credits = details.get("credits", {})
        
        directors_list = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
        directors = ", ".join(directors_list[:1])
        if item_type == "tv" and details.get("created_by"):
            directors = ", ".join([c["name"] for c in details["created_by"]][:1])
            
        cast = ", ".join([c["name"] for c in credits.get("cast", [])[:3]]) or "N/A"
        
        # Genres
        draw.text((80, 330), "GENRES", fill=(160, 163, 168), font=font_label)
        draw.text((80, 358), genres, fill=(245, 245, 250), font=font_body)
        
        # Directors
        draw.text((80, 425), "DIRECTORS", fill=(160, 163, 168), font=font_label)
        draw.text((80, 453), directors if directors else "N/A", fill=(245, 245, 250), font=font_body)
        
        # Cast
        draw.text((80, 520), "CAST", fill=(160, 163, 168), font=font_label)
        draw.text((80, 548), cast, fill=(245, 245, 250), font=font_body)
        
        # Summary
        draw.text((80, 625), "SUMMARY", fill=(160, 163, 168), font=font_label)
        
        overview = details.get("overview") or "No background summary description details currently available."
        lines = text_wrap(overview, font_body, 640, draw)
        
        y_summary = 653
        for line in lines:
            if y_summary > 785:  # Safe breaking cutoff point right before hitting the app icon shelf
                break
            draw.text((80, y_summary), line, fill=(220, 222, 225), font=font_body)
            y_summary += 36
            
        final_rgb = combined.convert("RGB")
        final_rgb.save(
            WALLPAPER_DIR / file_name, 
            "JPEG", 
            quality=100, 
            subsampling=0
        )
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

                t_str = details.get("title") or details.get("name") or "media"
                safe_title = "".join([c for c in t_str if c.isalnum()]).lower()[:20]
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
