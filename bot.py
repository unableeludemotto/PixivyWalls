"""
PixivyWalls Engine v51.3 — Telemetry Debug Edition
===================================================
- Injects explicit print logging tracking every API call, URL response, and loop filter.
- Retains full 15-item target counts across movies and series metrics.
- Regional language search loops are safely capped at a 2-page ceiling limit.
- Maintains the signature 60% widescreen layout with native alpha vignette blending.
"""

import os
import json
import time
import random
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
    print("🧹 [SYSTEM] Cleaning up legacy image directories...")
    if WALLPAPER_DIR.exists():
        try:
            shutil.rmtree(WALLPAPER_DIR)
            print("   ↳ Cleaned images directory successfully.")
        except Exception as e:
            print(f"   ↳ Cleanup warning: {e}")
    WALLPAPER_DIR.mkdir(exist_ok=True)

cleanup_old_assets()

LANGUAGES = [
    {"code": "en", "label": "English"},
    {"code": "hi", "label": "Hindi"},
    {"code": "kn", "label": "Kannada"},
    {"code": "ml", "label": "Malayalam"},
]

METRICS = [
    {"type": "movie", "tag": "Current Year",      "endpoint": "discover/movie"},
    {"type": "movie", "tag": "All-Time Top Rated", "endpoint": "movie/top_rated"},
    {"type": "movie", "tag": "Trending Now",       "endpoint": "discover/movie"},
    {"type": "tv",    "tag": "Currently Running",  "endpoint": "discover/tv"},
    {"type": "tv",    "tag": "Popular Releases",   "endpoint": "discover/tv"}
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def tmdb_get(endpoint: str, params: dict = {}) -> dict:
    url = f"{TMDB_BASE}/{endpoint}"
    p = {"api_key": TMDB_API_KEY, **params}
    print(f"🔍 [API REQUEST] URL: {url} | Params: { {k:v for k,v in p.items() if k != 'api_key'} }")
    r = requests.get(url, params=p, timeout=15)
    print(f"📡 [API RESPONSE] Status Code: {r.status_code}")
    r.raise_for_status()
    return r.json()

def gather_target_pool(metric: dict, lang: dict, target_count=15) -> list:
    endpoint = metric["endpoint"]
    collected_items = []
    page = 1
    
    if metric["tag"] == "All-Time Top Rated" and lang["code"] == "ml":
        print(f"⏭️ [SKIP] Malayalam + Top Rated is disabled per criteria bounds.")
        return []

    max_pages = 100 if lang["code"] == "en" else 2

    while len(collected_items) < target_count and page <= max_pages:
        params = {
            "language": "en-US",
            "page": page,
            "include_adult": "false"
        }
        
        if lang["code"] != "en" or "discover" in endpoint:
            params["with_original_language"] = lang["code"]
            params["sort_by"] = "popularity.desc"
            
        if metric["tag"] == "Current Year":
            if metric["type"] == "movie":
                params["primary_release_year"] = "2026"
            else:
                params["first_air_date_year"] = "2026"
        elif metric["tag"] == "All-Time Top Rated" and "discover" in endpoint:
            params["sort_by"] = "vote_average.desc"
            params["vote_count.gte"] = "5"
        elif metric["tag"] == "Currently Running" and metric["type"] == "tv":
            params["air_date.gte"] = "2026-01-01"
            
        try:
            res = tmdb_get(endpoint, params)
            results = res.get("results", [])
            print(f"📊 [DATA HARVEST] Language: {lang['label']} | Metric: {metric['tag']} | Page: {page} | Sourced: {len(results)} items raw")
            
            # Fallback configuration triggers if the target returns nothing on page 1
            if not results and page == 1:
                print(f"⚠️ [FALLBACK ACTIVE] Empty array returned. Dropping date/vote constraints for {lang['label']}...")
                params.pop("primary_release_year", None)
                params.pop("first_air_date_year", None)
                params.pop("vote_count.gte", None)
                params.pop("air_date.gte", None)
                params["sort_by"] = "popularity.desc"
                
                if "discover" not in endpoint:
                    res = tmdb_get(f"discover/{metric['type']}", params)
                else:
                    res = tmdb_get(endpoint, params)
                results = res.get("results", [])
                print(f"🔄 [FALLBACK RESULTS] Extracted {len(results)} items after dropping constraints.")
                
            if not results:
                print(f"🛑 [LOOP BREAK] No further items found on this path thread. Exiting loop.")
                break
                
            for item in results:
                if item.get("original_language") == lang["code"]:
                    if item not in collected_items:
                        collected_items.append(item)
                        if len(collected_items) >= target_count:
                            break
            print(f"📈 [POOL PROGRESS] Language: {lang['label']} | Metric: {metric['tag']} | Current Pool: {len(collected_items)}/{target_count}")
            page += 1
            time.sleep(0.05)
        except Exception as e:
            print(f"❌ [HARVEST ERROR] Exception occurred on pipeline parsing: {e}")
            break
            
    return collected_items[:target_count]

def fetch_details(item_type: str, item_id: int) -> dict:
    try:
        endpoint = "movie" if item_type == "movie" else "tv"
        return tmdb_get(f"{endpoint}/{item_id}", {
            "language": "en-US", 
            "append_to_response": "credits,images",
            "include_image_language": "en"
        })
    except Exception as e:
        print(f"❌ [DETAILS ERROR] Failed parsing item ID {item_id}: {e}")
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
def create_composite_card(details, category_tag, lang, item_type, file_name):
    backdrop_path = details.get("backdrop_path")
    if not backdrop_path or details.get("adult", False):
        print(f"⏩ [COMPOSITOR SKIP] Media item missing backdrop asset or flagged adult.")
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

        canvas = Image.new(mode="RGBA", size=(1920, 1080), color=(5, 6, 8, 255))
        
        img_res = requests.get(f"{TMDB_IMG_BASE}{backdrop_path}", timeout=20)
        raw_poster = Image.open(BytesIO(img_res.content)).convert("RGBA")
        
        target_w, target_h = 1152, 648
        scaled_poster = raw_poster.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        alpha_mask = Image.new("L", (target_w, target_h), 255)
        gradient_h = Image.linear_gradient("L").resize((500, target_h), Image.Resampling.BICUBIC)
        alpha_mask.paste(gradient_h, (0, 0))
        
        gradient_v = Image.linear_gradient("L").rotate(90).resize((target_w, 200), Image.Resampling.BICUBIC)
        gradient_v_flipped = ImageOps.invert(gradient_v)
        
        v_mask = Image.new("L", (target_w, target_h), 255)
        v_mask.paste(gradient_v_flipped, (0, target_h - 200))
        alpha_mask = Image.darker(alpha_mask, v_mask)
                
        canvas.paste(scaled_poster, (768, 0), alpha_mask)
        draw = ImageDraw.Draw(canvas)
        
        title = details.get("title") if item_type == "movie" else details.get("name")
        if not title: title = "Unknown"
            
        release_field = "release_date" if item_type == "movie" else "first_air_date"
        year = (details.get(release_field) or "N/A")[:4]
        genres = "/".join([g["name"] for g in details.get("genres", [])[:2]]) or "General"
        
        meta_elements = []
        if item_type == "tv":
            seasons_count = details.get("number_of_seasons", 0)
            if seasons_count > 0:
                meta_elements.append(f"{seasons_count} Seasons" if seasons_count > 1 else "1 Season")
        else:
            runtime = details.get("runtime", 0)
            if runtime > 0:
                meta_elements.append(f"{runtime} min")
                
        if year and year != "N/A": meta_elements.append(year)
        if genres: meta_elements.append(genres)
            
        rating = details.get("vote_average", 0.0)
        if rating > 0.0: meta_elements.append(f"IMDB: {rating:.1f}")
            
        meta_line = "    •    ".join(meta_elements)

        logo_drawn = False
        logos = details.get("images", {}).get("logos", [])
        if logos:
            target_logos = [l for l in logos if l.get("iso_639_1") == "en" and l.get("file_path", "").endswith(".png")]
            if not target_logos:
                target_logos = [l for l in logos if l.get("file_path", "").endswith(".png")]
            if target_logos:
                try:
                    target_logos.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
                    logo_res = requests.get(f"{TMDB_IMG_BASE}{target_logos[0]['file_path']}", timeout=10)
                    logo_img = Image.open(BytesIO(logo_res.content)).convert("RGBA")
                    logo_img.thumbnail((550, 150), Image.Resampling.LANCZOS)
                    canvas.alpha_composite(logo_img, dest=(80, 80))
                    logo_drawn = True
                except:
                    pass

        if not logo_drawn:
            draw.text((80, 80), title, fill=(255, 255, 255), font=font_title)
        
        draw.text((80, 240), meta_line, fill=(245, 245, 250), font=font_meta)
        
        credits = details.get("credits", {})
        directors_list = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
        directors = ", ".join(directors_list[:1])
        if item_type == "tv" and details.get("created_by"):
            directors = ", ".join([c["name"] for c in details["created_by"]][:1])
            
        cast = ", ".join([c["name"] for c in credits.get("cast", [])[:3]]) or "N/A"
        
        draw.text((80, 310), "DIRECTORS", fill=(160, 163, 168), font=font_label)
        draw.text((80, 332), directors if directors else "N/A", fill=(245, 245, 250), font=font_body)
        
        draw.text((80, 395), "CAST", fill=(160, 163, 168), font=font_label)
        draw.text((80, 417), cast, fill=(245, 245, 250), font=font_body)
        
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
        final_rgb.save(WALLPAPER_DIR / file_name, "JPEG", quality=100, subsampling=0)
        print(f"💾 [SAVED] Rendered card layout successful: {file_name}")
        return f"images/{file_name}"
    except Exception as e:
        print(f"❌ [RENDER FAILURE] Error on composite vector generation: {e}")
        return None

# ─── RUN ENGINE ──────────────────────────────────────────────────────────────
def run():
    print(f"\n🚀 ========================================================")
    print(f"🎬 PixivyWalls Pro Telemetry Core Engine v51.3 Online")
    print(f"🚀 ========================================================\n")
    
    raw_execution_pool = []
    seen_ids = set()

    for lang in LANGUAGES:
        print(f"\n📂 [LANG TRACK] Starting harvesting matrix for: {lang['label'].upper()}")
        for metric in METRICS:
            print(f"  └─ 🟢 Harvesting Metric Category: {metric['tag']} ({metric['type']})")
            pool = gather_target_pool(metric, lang, target_count=15)
            added_count = 0
            
            for item in pool:
                item_id = item.get("id")
                unique_key = f"{metric['type']}_{item_id}"
                
                if unique_key in seen_ids:
                    continue
                    
                seen_ids.add(unique_key)
                raw_execution_pool.append({
                    "item_id": item_id,
                    "item_type": metric["type"],
                    "tag": metric["tag"],
                    "lang": lang
                })
                added_count += 1
            print(f"  └─ ✅ Category Complete. Saved {added_count} unique items to global registry pool.")

    print(f"\n🔀 [POOL HARVEST COMPLETE] Total combined entries collected: {len(raw_execution_pool)}")
    if not raw_execution_pool:
        print("🚨 [CRITICAL ERROR] The global execution pool is completely empty! Aborting engine write run.")
        return

    print("🔀 Executing random position shuffle shift across pool elements...")
    random.shuffle(raw_execution_pool)

    entries = []
    processed_count = 0
    
    print(f"\n🎬 [COMPOSITOR RUN] Starting canvas rendering loop for {len(raw_execution_pool)} cards...")
    for task in raw_execution_pool:
        details = fetch_details(task["item_type"], task["item_id"])
        time.sleep(0.1)
        if not details:
            print(f"⚠️ [SKIP] Details metadata response returned empty for asset ID {task['item_id']}")
            continue

        t_str = details.get("title") or details.get("name") or "media"
        safe_title = "".join([c for c in t_str if c.isalnum()]).lower()[:20]
        file_name = f"wall_{task['item_type']}_{task['item_id']}_{safe_title}.jpg"
        
        img_relative_path = create_composite_card(details, task["tag"], task["lang"], task["item_type"], file_name)
        
        if img_relative_path:
            lbl_type = "Movie" if task["item_type"] == "movie" else "Series"
            entries.append({
                "location": f"{lbl_type} · {task['lang']['label']} · {task['tag']}",
                "title": f"{t_str}",
                "author": task["lang"]["label"],
                "url_img": f"https://unableeludemotto.github.io/PixivyWalls/{img_relative_path}"
            })
            processed_count += 1

    print(f"\n📝 [FILE WRITE] Committing {len(entries)} items into {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 [ENGINE COMPLETE] Vector catalog generation finalized cleanly. Composed {processed_count} cards.")

if __name__ == "__main__":
    run()
