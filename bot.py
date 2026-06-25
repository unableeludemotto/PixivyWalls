import os
import json
import time
import random
import shutil
import requests
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageChops

# ─── CONFIGURATION ───────────────────────────────────────────────────────────
TMDB_API_KEY  = os.environ["TMDB_API_KEY"]
TMDB_BASE     = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/original"

OUTPUT_DIR    = Path("docs")
WALLPAPER_DIR = OUTPUT_DIR / "images"
OUTPUT_FILE   = OUTPUT_DIR / "wallpapers.json"

OUTPUT_DIR.mkdir(exist_ok=True)

def reset_directories():
    print("🧹 Wiping legacy assets for a completely fresh generation...")
    if WALLPAPER_DIR.exists():
        try:
            shutil.rmtree(WALLPAPER_DIR)
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")
    WALLPAPER_DIR.mkdir(exist_ok=True)

reset_directories()

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

# Strict filters: Scripted Content and Mainstream Streaming Networks Only
EXCLUDED_GENRE_IDS = {99, 10763, 10764, 10766, 10767}
PREMIUM_PROVIDERS  = "8|119|122|220|237"  # Netflix, Prime, Hotstar, Jio, SonyLIV

# ─── METADATA HARVESTING ─────────────────────────────────────────────────────
def tmdb_get(endpoint: str, params: dict = {}) -> dict:
    url = f"{TMDB_BASE}/{endpoint}"
    p = {"api_key": TMDB_API_KEY, **params}
    r = requests.get(url, params=p, timeout=15)
    r.raise_for_status()
    return r.json()

def gather_target_pool(metric: dict, lang: dict, target_count=15) -> list:
    endpoint = metric["endpoint"]
    collected_items = []
    page = 1
    
    if metric["tag"] == "All-Time Top Rated" and lang["code"] == "ml":
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
            if "discover" in endpoint:
                params["with_watch_providers"] = PREMIUM_PROVIDERS
                params["watch_region"] = "IN"
            
        if metric["tag"] == "Current Year":
            params["primary_release_year" if metric["type"] == "movie" else "first_air_date_year"] = "2026"
        elif metric["tag"] == "All-Time Top Rated" and "discover" in endpoint:
            params["sort_by"] = "vote_average.desc"
            params["vote_count.gte"] = "5"
        elif metric["tag"] == "Currently Running" and metric["type"] == "tv":
            params["air_date.gte"] = "2026-01-01"
            
        try:
            res = tmdb_get(endpoint, params)
            results = res.get("results", [])
            
            if not results and page == 1:
                params.pop("primary_release_year", None)
                params.pop("first_air_date_year", None)
                params.pop("vote_count.gte", None)
                params.pop("air_date.gte", None)
                params["sort_by"] = "popularity.desc"
                params["with_watch_providers"] = PREMIUM_PROVIDERS
                params["watch_region"] = "IN"
                res = tmdb_get(endpoint if "discover" in endpoint else f"discover/{metric['type']}", params)
                results = res.get("results", [])
                
            if not results:
                break
                
            for item in results:
                if item.get("original_language") == lang["code"]:
                    if not set(item.get("genre_ids", [])).intersection(EXCLUDED_GENRE_IDS):
                        if item not in collected_items:
                            collected_items.append(item)
                            if len(collected_items) >= target_count:
                                break
            page += 1
            time.sleep(0.04)
        except:
            break
            
    return collected_items[:target_count]

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

# ─── GRAPHICS COMPOSITOR ENGINE ──────────────────────────────────────────────
def create_composite_card(details, item_type, file_name):
    backdrop_path = details.get("backdrop_path")
    if not backdrop_path or details.get("adult", False):
        return False

    try:
        # Strict Typography Sizing Hierarchy
        font_path = "assets/Roboto.ttf"
        if os.path.exists(font_path):
            font_title = ImageFont.truetype(font_path, 32)  # Compact title size
            font_meta  = ImageFont.truetype(font_path, 20)  # Clean row metrics
            font_label = ImageFont.truetype(font_path, 14)  # Small block tags
            font_body  = ImageFont.truetype(font_path, 18)  # Reduced description line scale
        else:
            font_title = font_meta = font_label = font_body = ImageFont.load_default()

        # 1. Base Layer: Pristine solid black canvas (1920x1080)
        canvas = Image.new(mode="RGBA", size=(1920, 1080), color=(5, 6, 8, 255))
        
        # 2. Backdrop Scale Layer: Perfect 60% widescreen aspect footprint (1152x648)
        img_res = requests.get(f"{TMDB_IMG_BASE}{backdrop_path}", timeout=20)
        scaled_poster = Image.open(BytesIO(img_res.content)).convert("RGBA").resize((1152, 648), Image.Resampling.LANCZOS)
        
        # 3. Direct fitting mask container layer (1152x648)
        direct_mask = Image.new("L", (1152, 648), 255)
        
        # Left edge horizontal fade out
        grad_h = Image.linear_gradient("L").rotate(270).resize((400, 648), Image.Resampling.BICUBIC)
        direct_mask.paste(grad_h, (0, 0))
        
        # Bottom edge vertical fade out
        grad_v = Image.linear_gradient("L").rotate(90).resize((1152, 200), Image.Resampling.BICUBIC)
        direct_mask_v = Image.new("L", (1152, 648), 255)
        direct_mask_v.paste(ImageOps.invert(grad_v), (0, 448))
        
        # Combine alpha operations natively
        final_fitted_mask = ImageChops.darker(direct_mask, direct_mask_v)
        
        # 4. Paste the cleanly masked backdrop box directly onto coordinates (768, 0)
        canvas.paste(scaled_poster, (768, 0), final_fitted_mask)
        draw = ImageDraw.Draw(canvas)
        
        # ─── INTERFACE TEXT RENDERING ────────────────────────────────────────
        title = details.get("title") if item_type == "movie" else details.get("name") or "Unknown"
        year  = (details.get("release_date") or details.get("first_air_date") or "N/A")[:4]
        genres = "/".join([g["name"] for g in details.get("genres", [])[:2]]) or "General"
        
        meta_elements = []
        if item_type == "tv":
            sc = details.get("number_of_seasons", 0)
            if sc > 0: meta_elements.append(f"{sc} Seasons" if sc > 1 else "1 Season")
        else:
            rt = details.get("runtime", 0)
            if rt > 0: meta_elements.append(f"{rt} min")
                
        if year and year != "N/A": meta_elements.append(year)
        if genres: meta_elements.append(genres)
        if details.get("vote_average", 0.0) > 0.0: meta_elements.append(f"IMDB: {details['vote_average']:.1f}")
        meta_line = "    •    ".join(meta_elements)

        # Large Logo Processing Layer
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
                    
                    # Large branding parameters
                    logo_img.thumbnail((650, 240), Image.Resampling.LANCZOS)
                    canvas.alpha_composite(logo_img, dest=(80, 80))
                    logo_drawn = True
                except:
                    pass

        if not logo_drawn:
            draw.text((80, 80), title, fill=(255, 255, 255), font=font_title)
        
        draw.text((80, 240), meta_line, fill=(245, 245, 250), font=font_meta)
        
        # Safe 640px wide text columns
        credits = details.get("credits", {})
        directors = ", ".join([c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"][:1])
        if item_type == "tv" and details.get("created_by"):
            directors = ", ".join([c["name"] for c in details["created_by"]][:1])
        cast = ", ".join([c["name"] for c in credits.get("cast", [])[:3]]) or "N/A"
        
        draw.text((80, 310), "DIRECTORS", fill=(160, 163, 168), font=font_label)
        draw.text((80, 332), directors if directors else "N/A", fill=(245, 245, 250), font=font_body)
        
        draw.text((80, 395), "CAST", fill=(160, 163, 168), font=font_label)
        draw.text((80, 417), cast, fill=(245, 245, 250), font=font_body)
        
        draw.text((80, 480), "SUMMARY", fill=(160, 163, 168), font=font_label)
        overview = details.get("overview") or "No description summary available."
        lines = text_wrap(overview, font_body, 640, draw)
        
        y_summary = 502
        for idx, line in enumerate(lines[:4]):
            if idx == 3 and len(lines) > 4:
                draw.text((80, y_summary), line + "...", fill=(220, 222, 225), font=font_body)
            else:
                draw.text((80, y_summary), line, fill=(220, 222, 225), font=font_body)
            y_summary += 28
            
        canvas.convert("RGB").save(WALLPAPER_DIR / file_name, "JPEG", quality=100, subsampling=0)
        return True
    except Exception as e:
        print(f"      ↳ Composition failure occurred: {e}")
        return False

# ─── CORE PIPELINE RUNNER ────────────────────────────────────────────────────
def run():
    print("\n🎬 PixivyWalls Core Master Rewrite Running...")
    raw_execution_pool = []
    seen_ids = set()

    for lang in LANGUAGES:
        print(f" 📂 Crawling metrics for channel track: {lang['label']}")
        for metric in METRICS:
            pool = gather_target_pool(metric, lang, target_count=15)
            added_count = 0
            for item in pool:
                item_id = item.get("id")
                unique_key = f"{metric['type']}_{item_id}"
                if unique_key not in seen_ids:
                    seen_ids.add(unique_key)
                    raw_execution_pool.append({
                        "item_id": item_id,
                        "item_type": metric["type"],
                        "tag": metric["tag"],
                        "lang": lang
                    })
                    added_count += 1
            print(f"    └─ [{metric['tag']}]: Extracted {added_count} unique items")

    print("\n🔀 Flattening matrices and executing random queue layout shuffle...")
    random.shuffle(raw_execution_pool)

    entries = []
    processed_count = 0
    
    print(f"\n🎬 Processing rendering canvas loops for {len(raw_execution_pool)} elements...")
    for task in raw_execution_pool:
        details = fetch_details(task["item_type"], task["item_id"])
        time.sleep(0.1)
        if not details: continue

        # Secondary filter guard for detailed items
        if set([g["id"] for g in details.get("genres", [])]).intersection(EXCLUDED_GENRE_IDS):
            continue

        t_str = details.get("title") or details.get("name") or "media"
        safe_title = "".join([c for c in t_str if c.isalnum()]).lower()[:20]
        file_name = f"wall_{task['item_type']}_{task['item_id']}_{safe_title}.jpg"
        
        # Composite generation run
        create_composite_card(details, task["item_type"], file_name)
        
        # Unconditional decoupled JSON log write
        lbl_type = "Movie" if task["item_type"] == "movie" else "Series"
        entries.append({
            "location": f"{lbl_type} · {task['lang']['label']} · {task['tag']}",
            "title": f"{t_str}",
            "author": task['lang']['label'],
            "url_img": f"https://unableeludemotto.github.io/PixivyWalls/images/{file_name}"
        })
        processed_count += 1

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 Generation success! Compiled {processed_count} cards cleanly into endpoints.")

if __name__ == "__main__":
    run()
