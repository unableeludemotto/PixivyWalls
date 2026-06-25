"""
PixivyWalls Bot
=====================================
Automated TMDB asset fetching for Projectivy Launcher (Overflight).
Filters: English output formatting, global deduplication, strict landscape validation, 
and NSFW exclusions. No vertical posters allowed!
"""

import os
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TMDB_API_KEY  = os.environ["TMDB_API_KEY"]
TMDB_BASE     = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/original"
TMDB_W500     = "https://image.tmdb.org/t/p/w500"

OUTPUT_DIR    = Path("docs")
OUTPUT_FILE   = OUTPUT_DIR / "wallpapers.json"
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_PER_BUCKET = 12

# ─── LANGUAGES ───────────────────────────────────────────────────────────────
LANGUAGES = [
    {"code": "en", "label": "English",   "flag": "🇬🇧"},
    {"code": "hi", "label": "Hindi",     "flag": "🇮🇳"},
    {"code": "kn", "label": "Kannada",   "flag": "🏴"},
    {"code": "ml", "label": "Malayalam", "flag": "🏴"},
]

# ─── CATEGORIES ──────────────────────────────────────────────────────────────
CATEGORIES = [
    {"type": "movie", "label": "Movie", "emoji": "🎬", "endpoint": "trending/movie/week", "tag": "Trending"},
    {"type": "movie", "label": "Movie", "emoji": "🎬", "endpoint": "movie/popular",       "tag": "Popular"},
    {"type": "movie", "label": "Movie", "emoji": "🎬", "endpoint": "movie/top_rated",     "tag": "All-Time Top Rated"},
    {"type": "tv",    "label": "Series", "emoji": "📺", "endpoint": "trending/tv/week",    "tag": "Trending"},
    {"type": "tv",    "label": "Series", "emoji": "📺", "endpoint": "tv/popular",          "tag": "Popular"},
    {"type": "tv",    "label": "Series", "emoji": "📺", "endpoint": "tv/top_rated",        "tag": "All-Time Top Rated"},
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def tmdb_get(endpoint: str, params: dict = {}) -> dict:
    url = f"{TMDB_BASE}/{endpoint}"
    p   = {"api_key": TMDB_API_KEY, **params}
    r   = requests.get(url, params=p, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_items(category: dict, lang: dict) -> list:
    # Skip All-Time Top Rated for Malayalam
    if category["tag"] == "All-Time Top Rated" and lang["code"] == "ml":
        return []

    # Enforce English locale responses for text, exclude NSFW
    params = {"language": "en-US", "page": 1, "include_adult": "false"}
    
    if lang["code"] != "en":
        params["with_original_language"] = lang["code"]

    try:
        data = tmdb_get(category["endpoint"], params)
        return data.get("results", [])[:MAX_PER_BUCKET]
    except Exception as e:
        print(f"  ✗ Fetch error ({category['endpoint']}, {lang['code']}): {e}")
        return []

def fetch_details(item_type: str, item_id: int) -> dict:
    endpoint = f"{'movie' if item_type == 'movie' else 'tv'}/{item_id}"
    try:
        return tmdb_get(endpoint, {
            "language": "en-US",
            "append_to_response": "credits"
        })
    except Exception as e:
        print(f"  ✗ Detail fetch failed ({item_id}): {e}")
        return {}

def fmt_runtime(mins) -> str:
    if not mins: return "N/A"
    h, m = divmod(int(mins), 60)
    return f"{h}h {m}m" if h else f"{m}m"

def get_cast(credits: dict, n=5) -> str:
    names = [c["name"] for c in credits.get("cast", [])[:n]]
    return ", ".join(names) or "N/A"

def get_director(credits: dict) -> str:
    dirs = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
    return ", ".join(dirs[:2]) or "N/A"

def get_genres(details: dict) -> str:
    names = [g["name"] for g in details.get("genres", [])[:4]]
    return ", ".join(names) or "N/A"

# ─── OVERFLIGHT JSON BUILDER ─────────────────────────────────────────────────
def build_entry(details: dict, category: dict, lang: dict, item_type: str) -> dict | None:
    if details.get("adult", False):
        return None
    
    # STRICT LANDSCAPE CHECK: Must have backdrop_path. Ignore poster_path completely.
    backdrop = details.get("backdrop_path")
    if not backdrop:
        return None

    title    = details.get("title") if item_type == "movie" else details.get("name")
    title    = title or "Unknown"
    year     = (details.get("release_date") if item_type == "movie" else details.get("first_air_date") or "")[:4] or "N/A"
    rating   = details.get("vote_average", 0)
    credits  = details.get("credits", {})
    author   = get_director(credits) if item_type == "movie" else "TMDB"
    
    display_title = f"{category['emoji']} {title} ({year}) ⭐ {rating:.1f}"

    return {
        "location": f"{category['label']} · {lang['label']} · {category['tag']}",
        "title":    display_title,
        "author":   author if author != "N/A" else "TMDB",
        "url_img":  f"{TMDB_IMG_BASE}{backdrop}"
    }

# ─── MAIN ENGINE ─────────────────────────────────────────────────────────────
def run():
    print(f"\n PixivyWalls Pipeline Launching...")
    seen_ids = set() # Global deduplication tracking map
    entries  = []

    for lang in LANGUAGES:
        print(f"  {lang['flag']} Processing: {lang['label']}")
        for category in CATEGORIES:
            items = fetch_items(category, lang)
            time.sleep(0.2)

            added = 0
            for item in items:
                item_id   = item.get("id")
                item_type = category["type"]
                
                # Global Duplicate Prevention: If already processed this item ID anywhere, skip it!
                if item_id in seen_ids:
                    continue

                details = fetch_details(item_type, item_id)
                time.sleep(0.2)

                if not details:
                    continue

                entry = build_entry(details, category, lang, item_type)
                if entry:
                    entries.append(entry)
                    seen_ids.add(item_id) # Mark item ID as universally saved
                    added += 1

            if added > 0:
                print(f"    └─ [{category['label']} - {category['tag']}]: Generated +{added} configurations")

    # Generate exact array required by Overflight
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    # Generate full companion dataset architecture
    output_full = {
        "_info": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_wallpapers": len(entries),
            "source": "TMDB via PixivyWalls Bot",
            "languages": [l["label"] for l in LANGUAGES],
            "github": "https://github.com/unableeludemotto/PixivyWalls"
        },
        "wallpapers": entries
    }

    meta_file = OUTPUT_DIR / "wallpapers_full.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(output_full, f, ensure_ascii=False, indent=2)

    print(f"\n Pipeline Complete! Managed {len(entries)} unique landscape wallpaper links.\n")

if __name__ == "__main__":
    run()
