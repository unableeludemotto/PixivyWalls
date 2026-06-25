"""
PixivyWalls Engine v46 — 75% Outward Fade Edition
======================================================
- Constrains artwork container bounds to exactly 75% scale (1440x810).
- Pins the proportional 16:9 image into the top-right quadrant corner.
- Uses a native alpha mask to bleed the dark spaces smoothly into the poster edges.
- Uses compact typography and consolidated metadata tracks.
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
            font_title = ImageFont.truetype(font_path, 68)
            font_meta  = ImageFont.truetype(font_path, 26)
            font_label = ImageFont.truetype(font_path, 15)
            font_body  = ImageFont.truetype(font_path, 22)
        else:
            font_title = font_meta = font_label = font_body = ImageFont.load_default()

        # 1. Base Layer: Solid Master TV Dark Background (1920x1080)
        canvas = Image.new(mode="RGBA", size=(1920, 1080), color=(5, 6, 8, 255))
        
        # 2. Download and scale backdrop to exactly 75% footprint size (1440x810)
        img_res = requests.get(f"{TMDB_IMG_BASE}{backdrop_path}", timeout=20)
        raw_poster = Image.open(BytesIO(img_res.content)).convert("RGBA")
        
        target_w = 1440
        target_h = 810
        scaled_poster = raw_poster.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # 3. Create a High-Precision Outward Alpha Mask directly mapping the 75% asset dimensions (1440x810)
        alpha_mask = Image.new("L", (1440, 810), 255)
        draw_am = ImageDraw.Draw(alpha_mask)
        
        # Smooth left outward fade (Fades out seamlessly from pixel 0 to 320 for wide cinematic dropoff)
        for x in range(320):
            val = int(255 * (x / 320))
            draw_am.line([(x, 0), (x, 810)], fill=val)
            
        # Smooth bottom outward fade (Fades out seamlessly from pixel 660 down to 810)
        for y in range(660, 810):
            val = int(255 * (1.0 - ((y - 660) / (810 - 660))))
            for x in range(1440):
                current = alpha_mask.getpixel((x, y))
                draw_am.putpixel((x, y), min(current, val))
                
        # Paste the seamlessly masked 75% artwork into the top-right quadrant corner (X=480, Y=0)
        canvas.paste(scaled_poster, (480, 0), alpha_mask)
        draw = ImageDraw.Draw(canvas)
        
        # ─── TYPOGRAPHY GRAPHICS ENGINE ───────────────────────────────────────
        title = details.get("title") if item_type == "movie" else details.get("name")
        if not title:
            title = "Unknown"
            
        release_field = "release_date" if item_type == "movie" else "first_air_date"
        year = (details.get(release_field) or "N/A")[:4]
        genres = "/".join([g["name"] for g in details.get("genres", [])[:2]]) or "General"
        
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
            
        if genres:
            meta_elements.append(genres)
            
        rating = details.get("vote_average", 0.0)
        if rating > 0.0:
            meta_elements.append(f"IMDB: {rating:.1f}")
            
        meta_line = "    •    ".join(meta_elements)

        # Official Studio Logo Compositor (Safe Left Margin Column Alignment)
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
                    
                    max_w, max_h = 380, 120
                    logo_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                    
                    canvas.alpha_composite(logo_img, dest=(60, 80))
                    logo_drawn = True
                except:
                    pass

        if not logo_drawn:
            draw.text((60, 80), title, fill=(255, 255, 255), font=font_title)
        
        draw.text((60, 220), meta_line, fill=(245, 245, 250), font=font_meta)
        
        # Absolute Info Columns (Constrained to a clean 580px text block width lane)
        credits = details.get("credits", {})
        directors_list = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
        directors = ", ".join(directors_list[:1])
        if item_type == "tv" and details.get("created_by"):
            directors = ", ".join([c["name"] for c in details["created_by"]][:1])
            
        cast = ", ".join([c["name"] for c in credits.get("cast", [])[:3]]) or "N/A"
        
        # Directors Block
        draw.text((60, 290), "DIRECTORS", fill=(160, 163, 168), font=font_label)
        draw.text((60, 312), directors if directors else "N/A", fill=(245, 245, 250), font=font_body)
        
        # Cast Block
        draw.text((60, 375), "CAST", fill=(160, 163, 168), font=font_label)
        draw.text((60, 397), cast, fill=(245, 245, 250), font=font_body)
        
        # Summary Block with baseline truncation checks
        draw.text((60, 460), "SUMMARY", fill=(160, 163, 168), font=font_label)
        
        overview = details.get("overview") or "No background summary description details currently available."
        lines = text_wrap(overview, font_body, 580, draw)
        
        y_summary = 482
        max_lines = 4  # Proportional capacity inside the text zone
        
        for idx, line in enumerate(lines):
            if idx >= max_lines or y_summary > 740:
                draw.text((60, y_summary - 30), lines[max_lines-1] + "...", fill=(220, 222, 225), font=font_body)
                break
                
            if idx == max_lines - 1 and len(lines) > max_lines:
                draw.text((60, y_summary), line + "...", fill=(220, 222, 225), font=font_body)
            else:
                draw.text((60, y_summary), line, fill=(220, 222, 225), font=font_body)
                
            y_summary += 30
            
        final_rgb = canvas.convert("RGB")
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
