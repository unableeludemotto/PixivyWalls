"""
PixivyWalls Engine v49 — Symmetrical Widescreen Guard Edition
=============================================================
- Constrains artwork container to exactly 60% widescreen scale (1152x648).
- Implements hardware-smooth linear gradient masking to remove all rectangular borders.
- Enlarges official movie title logo footprints to 550px for premium presentation.
- Restructured to ONLY fetch Trending, Popular, and Top Rated categories.
- Enforces strict 'original_language' matching to eliminate cross-language leaks.
- Dynamically falls back to TMDB Discover API for regional rows to prevent empty JSON generation.
"""

import os
import json
import time
import shutil
import requests
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

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

# Track exclusively Trending, Popular, and Top Rated tracks
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
    
    endpoint = category.get("endpoint")
    if not endpoint:
        return []
        
    params = {"language": "en-US", "page": 1, "include_adult": "false"}
    
    # SYSTEM SHIFT: If processing regional content, route through the Discover API to force real assets
    if lang["code"] != "en":
        if "trending" in endpoint:
            # Trending doesn't support language filters, so we swap to discover for regional rows
            item_type = "movie" if "movie" in endpoint else "tv"
            endpoint = f"discover/{item_type}"
            params["sort_by"] = "popularity.desc"
            params["with_original_language"] = lang["code"]
        else:
            params["with_original_language"] = lang["code"]
            
    try:
        res = tmdb_get(endpoint, params)
        raw_results = res.get("results", [])
        
        # STRICT LANGUAGE GUARD FILTER: Validates actual raw asset source language metadata
        filtered_results = []
        for item in raw_results:
            orig_lang = item.get("original_language")
            if lang["code"] == "en" and orig_lang == "en":
                filtered_results.append(item)
            elif lang["code"] != "en" and orig_lang == lang["code"]:
                filtered_results.append(item)
                
        return filtered_results[:MAX_PER_BUCKET]
    except Exception as e:
        print(f"    ↳ Fetch warning for {category['label']}-{lang['label']}: {e}")
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
        
        # 2. Process Backdrop scaled strictly to a 60% proportional 16:9 frame (1152x648)
        img_res = requests.get(f"{TMDB_IMG_BASE}{backdrop_path}", timeout=20)
        raw_poster = Image.open(BytesIO(img_res.content)).convert("RGBA")
        
        target_w = 1152
        target_h = 648
        scaled_poster = raw_poster.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # 3. High-Precision Native Gradient Masking (Creates a flawless, soft vignette)
        alpha_mask = Image.new("L", (target_w, target_h), 255)
        
        # Left Outward Fade: Generate an authentic linear gradient canvas channel
        gradient_h = Image.linear_gradient("L").resize((500, target_h), Image.Resampling.BICUBIC)
        alpha_mask.paste(gradient_h, (0, 0))
        
        # Bottom Outward Fade: Vertical linear gradient layer
        gradient_v = Image.linear_gradient("L").rotate(90).resize((target_w, 200), Image.Resampling.BICUBIC)
        gradient_v_flipped = ImageOps.invert(gradient_v)
        
        # Merge horizontal and vertical gradient tracks natively
        v_mask = Image.new("L", (target_w, target_h), 255)
        v_mask.paste(gradient_v_flipped, (0, target_h - 200))
        alpha_mask = Image.darker(alpha_mask, v_mask)
                
        # Paste masked artwork cleanly into the upper-right quadrant (X=768, Y=0)
        canvas.paste(scaled_poster, (768, 0), alpha_mask)
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

        # Official Studio Logo Compositor (Bigger 550px Bounds)
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
                    
                    max_w, max_h = 550, 150
                    logo_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                    
                    canvas.alpha_composite(logo_img, dest=(80, 80))
                    logo_drawn = True
                except:
                    pass

        if not logo_drawn:
            draw.text((80, 80), title, fill=(255, 255, 255), font=font_title)
        
        draw.text((80, 240), meta_line, fill=(245, 245, 250), font=font_meta)
        
        # Absolute Info Columns (Constrained to a highly legible 640px text boundary)
        credits = details.get("credits", {})
        directors_list = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
        directors = ", ".join(directors_list[:1])
        if item_type == "tv" and details.get("created_by"):
            directors = ", ".join([c["name"] for c in details["created_by"]][:1])
            
        cast = ", ".join([c["name"] for c in credits.get("cast", [])[:3]]) or "N/A"
        
        # Directors Block
        draw.text((80, 310), "DIRECTORS", fill=(160, 163, 168), font=font_label)
        draw.text((80, 332), directors if directors else "N/A", fill=(245, 245, 250), font=font_body)
        
        # Cast Block
        draw.text((80, 395), "CAST", fill=(160, 163, 168), font=font_label)
        draw.text((80, 417), cast, fill=(245, 245, 250), font=font_body)
        
        # Summary Block with baseline truncation checks
        draw.text((80, 480), "SUMMARY", fill=(160, 163, 168), font=font_label)
        
        overview = details.get("overview") or "No background summary description details currently available."
        lines = text_wrap(overview, font_body, 640, draw)
        
        y_summary = 502
        max_lines = 4  
        
        for idx, line in enumerate(lines):
            if idx >= max_lines or y_summary > 720:
                draw.text((80, y_summary - 30), lines[max_lines-1] + "...", fill=(220, 222, 225), font=font_body)
                break
                
            if idx == max_lines - 1 and len(lines) > max_lines:
                draw.text((80, y_summary), line + "...", fill=(220, 222, 225), font=font_body)
            else:
                draw.text((80, y_summary), line, fill=(220, 222, 225), font=font_body)
                
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
