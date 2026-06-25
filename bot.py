"""
CineVault Bot
=============
Scrapes TMDB for popular/trending movies, series & documentaries
(English, Hindi, Kannada, Malayalam) and generates a wallpapers.json
file compatible with the Projectivy Overflight plugin.

The JSON is pushed to GitHub Pages and read directly by Projectivy.
No Reddit needed!

Output: docs/wallpapers.json  (served via GitHub Pages)
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

OUTPUT_DIR    = Path("docs")          # GitHub Pages serves from /docs
OUTPUT_FILE   = OUTPUT_DIR / "wallpapers.json"
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_PER_BUCKET = 10   # items per language+category combo

# ─── LANGUAGES ───────────────────────────────────────────────────────────────

LANGUAGES = [
    {"code": "en", "label": "English",   "flag": "🇬🇧"},
    {"code": "hi", "label": "Hindi",     "flag": "🇮🇳"},
    {"code": "kn", "label": "Kannada",   "flag": "🏴"},
    {"code": "ml", "label": "Malayalam", "flag": "🏴"},
]

# ─── CATEGORIES ──────────────────────────────────────────────────────────────

CATEGORIES = [
    {"type": "movie", "label": "Movie",       "emoji": "🎬", "endpoint": "trending/movie/week",  "tag": "Trending"},
    {"type": "movie", "label": "Movie",       "emoji": "🎬", "endpoint": "movie/popular",         "tag": "Popular"},
    {"type": "movie", "label": "Movie",       "emoji": "🎬", "endpoint": "movie/top_rated",       "tag": "Top Rated"},
    {"type": "tv",    "label": "Series",      "emoji": "📺", "endpoint": "trending/tv/week",      "tag": "Trending"},
    {"type": "tv",    "label": "Series",      "emoji": "📺", "endpoint": "tv/popular",            "tag": "Popular"},
    {"type": "tv",    "label": "Series",      "emoji": "📺", "endpoint": "tv/top_rated",          "tag": "Top Rated"},
    {"type": "movie", "label": "Documentary", "emoji": "🎥", "endpoint": "discover/movie",        "tag": "Popular",
     "extra_params": {"with_genres": "99", "sort_by": "popularity.desc"}},
    {"type": "tv",    "label": "Documentary", "emoji": "🎥", "endpoint": "discover/tv",           "tag": "Popular",
     "extra_params": {"with_genres": "99", "sort_by": "popularity.desc"}},
]

# ─── TMDB HELPERS ────────────────────────────────────────────────────────────

def tmdb_get(endpoint: str, params: dict = {}) -> dict:
    url = f"{TMDB_BASE}/{endpoint}"
    p   = {"api_key": TMDB_API_KEY, **params}
    r   = requests.get(url, params=p, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_items(category: dict, lang: dict) -> list:
    params = {"language": lang["code"], "page": 1}
    if "extra_params" in category:
        params.update(category["extra_params"])
    if lang["code"] != "en":
        if "discover" in category["endpoint"] or "trending" not in category["endpoint"]:
            params["with_original_language"] = lang["code"]
    try:
        data = tmdb_get(category["endpoint"], params)
        return data.get("results", [])[:MAX_PER_BUCKET]
    except Exception as e:
        print(f"  ✗ Fetch error ({category['endpoint']}, {lang['code']}): {e}")
        return []

def fetch_details(item_type: str, item_id: int, lang_code: str) -> dict:
    endpoint = f"{'movie' if item_type == 'movie' else 'tv'}/{item_id}"
    try:
        return tmdb_get(endpoint, {
            "language": lang_code,
            "append_to_response": "credits"
        })
    except Exception as e:
        print(f"  ✗ Detail fetch failed ({item_id}): {e}")
        return {}

# ─── DATA FORMATTERS ─────────────────────────────────────────────────────────

def fmt_runtime(mins) -> str:
    if not mins: return "N/A"
    h, m = divmod(int(mins), 60)
    return f"{h}h {m}m" if h else f"{m}m"

def fmt_money(amt) -> str:
    if not amt or amt == 0: return "N/A"
    if amt >= 1_000_000_000: return f"${amt/1_000_000_000:.1f}B"
    if amt >= 1_000_000:     return f"${amt/1_000_000:.1f}M"
    return f"${amt:,}"

def get_cast(credits: dict, n=5) -> str:
    names = [c["name"] for c in credits.get("cast", [])[:n]]
    return ", ".join(names) or "N/A"

def get_director(credits: dict) -> str:
    dirs = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
    return ", ".join(dirs[:2]) or "N/A"

def get_creators(details: dict) -> str:
    names = [c["name"] for c in details.get("created_by", [])[:2]]
    return ", ".join(names) or "N/A"

def get_genres(details: dict) -> str:
    names = [g["name"] for g in details.get("genres", [])[:4]]
    return ", ".join(names) or "N/A"

def get_tmdb_url(item_type: str, item_id: int) -> str:
    return f"https://www.themoviedb.org/{'movie' if item_type == 'movie' else 'tv'}/{item_id}"

# ─── OVERFLIGHT JSON BUILDER ─────────────────────────────────────────────────
#
# Overflight JSON format:
# [
#   {
#     "location": "Category / Language",
#     "title":    "Movie Title (Year) ⭐ 8.4",
#     "author":   "Director Name",
#     "url_img":  "https://image.tmdb.org/..."   ← used as wallpaper
#   },
#   ...
# ]

def build_entry_movie(details: dict, category: dict, lang: dict) -> dict | None:
    backdrop = details.get("backdrop_path") or details.get("poster_path")
    if not backdrop:
        return None

    title     = details.get("title", "Unknown")
    orig      = details.get("original_title", "")
    year      = (details.get("release_date") or "")[:4] or "N/A"
    rating    = details.get("vote_average", 0)
    votes     = details.get("vote_count", 0)
    overview  = details.get("overview") or "No description available."
    runtime   = fmt_runtime(details.get("runtime"))
    budget    = fmt_money(details.get("budget"))
    revenue   = fmt_money(details.get("revenue"))
    status    = details.get("status", "N/A")
    tagline   = details.get("tagline", "")
    genres    = get_genres(details)
    credits   = details.get("credits", {})
    cast      = get_cast(credits)
    director  = get_director(credits)
    tmdb_url  = get_tmdb_url("movie", details["id"])

    display_title = f"{category['emoji']} {title} ({year}) ⭐ {rating:.1f}"

    # Rich description shown in Overflight / stored in JSON
    desc_parts = []
    if tagline: desc_parts.append(f'"{tagline}"')
    desc_parts.append(f"📅 {year}  ⭐ {rating:.1f}/10 ({votes:,} votes)  ⏱ {runtime}")
    desc_parts.append(f"🎭 {genres}")
    if orig and orig != title: desc_parts.append(f"Original: {orig}")
    desc_parts.append(f"🎬 Director: {director}")
    desc_parts.append(f"💰 Budget: {budget}  |  Box Office: {revenue}")
    desc_parts.append(f"🎭 Cast: {cast}")
    desc_parts.append(f"📖 {overview[:300]}{'...' if len(overview) > 300 else ''}")
    desc_parts.append(f"🔗 {tmdb_url}")

    return {
        "location": f"{category['label']} · {lang['label']} · {category['tag']}",
        "title":    display_title,
        "author":   director if director != "N/A" else "TMDB",
        "url_img":  f"{TMDB_IMG_BASE}{backdrop}",
        # Extra metadata (Overflight ignores unknown fields, but useful for debugging)
        "_meta": {
            "type":     "movie",
            "language": lang["label"],
            "category": category["label"],
            "tag":      category["tag"],
            "year":     year,
            "rating":   round(rating, 1),
            "votes":    votes,
            "genres":   genres,
            "runtime":  runtime,
            "cast":     cast,
            "director": director,
            "overview": overview,
            "tagline":  tagline,
            "budget":   budget,
            "revenue":  revenue,
            "status":   status,
            "tmdb_url": tmdb_url,
            "poster":   f"{TMDB_W500}{details.get('poster_path', '')}",
        }
    }

def build_entry_tv(details: dict, category: dict, lang: dict) -> dict | None:
    backdrop = details.get("backdrop_path") or details.get("poster_path")
    if not backdrop:
        return None

    name      = details.get("name", "Unknown")
    orig      = details.get("original_name", "")
    year      = (details.get("first_air_date") or "")[:4] or "N/A"
    rating    = details.get("vote_average", 0)
    votes     = details.get("vote_count", 0)
    overview  = details.get("overview") or "No description available."
    seasons   = details.get("number_of_seasons", "N/A")
    episodes  = details.get("number_of_episodes", "N/A")
    status    = details.get("status", "N/A")
    tagline   = details.get("tagline", "")
    genres    = get_genres(details)
    creators  = get_creators(details)
    credits   = details.get("credits", {})
    cast      = get_cast(credits)
    networks  = ", ".join([n["name"] for n in details.get("networks", [])[:2]]) or "N/A"
    tmdb_url  = get_tmdb_url("tv", details["id"])

    display_title = f"{category['emoji']} {name} ({year}) ⭐ {rating:.1f}"

    desc_parts = []
    if tagline: desc_parts.append(f'"{tagline}"')
    desc_parts.append(f"📅 {year}  ⭐ {rating:.1f}/10 ({votes:,} votes)")
    desc_parts.append(f"🎭 {genres}  |  📺 {seasons} seasons · {episodes} episodes")
    if orig and orig != name: desc_parts.append(f"Original: {orig}")
    desc_parts.append(f"🎬 Creator: {creators}  |  📡 {networks}")
    desc_parts.append(f"🎭 Cast: {cast}")
    desc_parts.append(f"📖 {overview[:300]}{'...' if len(overview) > 300 else ''}")
    desc_parts.append(f"🔗 {tmdb_url}")

    return {
        "location": f"{category['label']} · {lang['label']} · {category['tag']}",
        "title":    display_title,
        "author":   creators if creators != "N/A" else "TMDB",
        "url_img":  f"{TMDB_IMG_BASE}{backdrop}",
        "_meta": {
            "type":     "tv",
            "language": lang["label"],
            "category": category["label"],
            "tag":      category["tag"],
            "year":     year,
            "rating":   round(rating, 1),
            "votes":    votes,
            "genres":   genres,
            "seasons":  seasons,
            "episodes": episodes,
            "cast":     cast,
            "creators": creators,
            "networks": networks,
            "overview": overview,
            "tagline":  tagline,
            "status":   status,
            "tmdb_url": tmdb_url,
            "poster":   f"{TMDB_W500}{details.get('poster_path', '')}",
        }
    }

# ─── MAIN ────────────────────────────────────────────────────────────────────

def run():
    print(f"\n{'='*65}")
    print(f"  CineVault Bot — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Output: {OUTPUT_FILE}")
    print(f"{'='*65}\n")

    seen_ids  = set()   # avoid duplicate entries across categories
    entries   = []
    processed = 0
    skipped   = 0
    errors    = 0

    for lang in LANGUAGES:
        print(f"\n  {lang['flag']}  {lang['label']}")
        for category in CATEGORIES:
            print(f"    [{category['label']} | {category['tag']}]", end=" ", flush=True)
            items = fetch_items(category, lang)
            time.sleep(0.3)

            added = 0
            for item in items:
                item_id   = item.get("id")
                item_type = category["type"]
                dedup_key = f"{item_type}_{item_id}_{lang['code']}"

                if dedup_key in seen_ids:
                    skipped += 1
                    continue

                details = fetch_details(item_type, item_id, lang["code"])
                time.sleep(0.25)

                if not details:
                    errors += 1
                    continue

                if item_type == "movie":
                    entry = build_entry_movie(details, category, lang)
                else:
                    entry = build_entry_tv(details, category, lang)

                if entry:
                    entries.append(entry)
                    seen_ids.add(dedup_key)
                    added += 1
                    processed += 1

            print(f"→ +{added}")

    # Write final JSON
    output = {
        "_info": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_wallpapers": len(entries),
            "source": "TMDB via CineVault Bot",
            "languages": [l["label"] for l in LANGUAGES],
            "github": "https://github.com/YOUR_USERNAME/cinevault-bot"
        },
        "wallpapers": entries
    }

    # Also write flat array (Overflight expects plain array at root)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    # Write full metadata version separately
    meta_file = OUTPUT_DIR / "wallpapers_full.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*65}")
    print(f"  ✅ Total wallpapers : {len(entries)}")
    print(f"  ⏭️  Skipped dupes   : {skipped}")
    print(f"  ❌ Errors          : {errors}")
    print(f"  📄 Output          : {OUTPUT_FILE}")
    print(f"{'='*65}\n")

if __name__ == "__main__":
    run()
