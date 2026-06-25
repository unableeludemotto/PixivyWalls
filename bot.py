import os
import json
import time
import random
import shutil
from pathlib import Path
from io import BytesIO

import requests
from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageOps,
    ImageChops
)

# ==========================================================
# PixivyWalls
# Configuration
# ==========================================================

TMDB_API_KEY = os.environ["TMDB_API_KEY"]

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"

OUTPUT_DIR = Path("docs")
IMAGE_DIR = OUTPUT_DIR / "images"
JSON_FILE = OUTPUT_DIR / "wallpapers.json"

FONT_FILE = Path("assets/Inter-Regular.ttf")

CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080

BACKDROP_WIDTH = 1152
BACKDROP_HEIGHT = 648

BACKGROUND_COLOR = (6, 7, 10)

REQUEST_TIMEOUT = 20

MAX_DISCOVERY_PAGES = 4

DISCOVERY_DELAY = 0.03
DETAIL_DELAY = 0.03

DETAILS_CACHE: dict[tuple[str, int], dict] = {}
IMAGE_CACHE: dict[str, Image.Image] = {}

# Only supported languages
LANGUAGES = [
    ("en", "English"),
    ("hi", "Hindi"),
    ("kn", "Kannada"),
]

# Streaming providers
WATCH_PROVIDERS = "8|119|122|220|237"

# Genres to ignore
EXCLUDED_GENRES = {
    99,      # Documentary
    10763,   # News
    10764,   # Reality
    10766,   # Soap
    10767,   # Talk
}

# Minimum quality requirements
MIN_VOTE_AVERAGE = 6.8
MIN_VOTE_COUNT = 250

session = requests.Session()
session.headers.update({
    "User-Agent": "PixivyWalls/2.0"
})

# ==========================================================
# Workspace
# ==========================================================

def prepare_workspace() -> None:
    """
    Recreate all generated assets from scratch.

    docs/
      ├── images/
      └── wallpapers.json
    """

    print("\n🧹 Preparing fresh workspace...")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    JSON_FILE.write_text(
        "[]",
        encoding="utf-8"
    )

    print("✅ Workspace ready")


prepare_workspace()

# ==========================================================
# TMDB Client
# ==========================================================

def tmdb_get(endpoint: str, **params) -> dict:
    """
    Perform a GET request to TMDB with retries.
    Returns an empty dictionary if all attempts fail.
    """

    url = f"{TMDB_BASE_URL}/{endpoint.lstrip('/')}"

    query = {
        "api_key": TMDB_API_KEY,
        **params,
    }

    for attempt in range(3):
        try:
            response = session.get(
                url,
                params=query,
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()
            return response.json()

        except requests.RequestException as exc:
            print(
                f"⚠️ TMDB request failed "
                f"(attempt {attempt + 1}/3): {endpoint}"
            )

            if attempt < 2:
                time.sleep(1.5)

    return {}


def download_image(path: str) -> Image.Image | None:

    if not path:
        return None

    if path in IMAGE_CACHE:
        return IMAGE_CACHE[path].copy()

    url = f"{TMDB_IMAGE_BASE}{path}"

    for attempt in range(3):

        try:
            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            image = Image.open(
                BytesIO(response.content)
            ).convert("RGBA")

            IMAGE_CACHE[path] = image

            return image.copy()

        except Exception:

            if attempt < 2:
                time.sleep(1)

    return None

# ==========================================================
# Discovery Configuration
# ==========================================================

DISCOVERY_CATEGORIES = [

    # Movies
    {
        "type": "movie",
        "title": "Current Year",
        "endpoint": "discover/movie",
        "params": {
            "primary_release_year": "2026",
            "sort_by": "popularity.desc",
        },
    },

    {
        "type": "movie",
        "title": "Trending",
        "endpoint": "trending/movie/week",
        "params": {},
    },

    {
        "type": "movie",
        "title": "Top Rated",
        "endpoint": "movie/top_rated",
        "params": {},
    },

    # TV Series
    {
        "type": "tv",
        "title": "Currently Running",
        "endpoint": "discover/tv",
        "params": {
            "sort_by": "popularity.desc",
        },
    },

    {
        "type": "tv",
        "title": "Trending",
        "endpoint": "trending/tv/week",
        "params": {},
    },

    {
        "type": "tv",
        "title": "Top Rated",
        "endpoint": "tv/top_rated",
        "params": {},
    },
]

TARGET_ITEMS_PER_CATEGORY = 15

DISCOVER_DEFAULTS = {
    "include_adult": "false",
    "language": "en-US",
    "watch_region": "IN",
    "with_watch_providers": WATCH_PROVIDERS,
}

LANGUAGE_FILTERS = {
    "en": {
        "with_original_language": "en",
    },
    "hi": {
        "with_original_language": "hi",
    },
    "kn": {
        "with_original_language": "kn",
    },
}

# ==========================================================
# Discovery Engine
# ==========================================================

def is_valid_item(item: dict, language: str) -> bool:
    """Apply quality filters before fetching details."""

    if item.get("adult"):
        return False

    if item.get("original_language") != language:
        return False

    if item.get("vote_average", 0) < MIN_VOTE_AVERAGE:
        return False

    if item.get("vote_count", 0) < MIN_VOTE_COUNT:
        return False

    if EXCLUDED_GENRES.intersection(item.get("genre_ids", [])):
        return False

    if not item.get("backdrop_path"):
        return False

    return True

# ==========================================================
# Candidate Ranking
# ==========================================================

def candidate_score(item: dict) -> float:
    """
    Higher score = better wallpaper candidate.
    """

    rating = item.get("vote_average", 0)
    votes = item.get("vote_count", 0)
    popularity = item.get("popularity", 0)

    return (
            rating * 100
            + min(votes, 5000) * 0.05
            + popularity * 0.2
    )

def discover_items(category: dict, language: str) -> list[dict]:
    """
    Discover media for one language/category combination.
    """

    endpoint = category["endpoint"]
    collected = []
    seen = set()

    for page in range(1, MAX_DISCOVERY_PAGES + 1):

        params = {
            **DISCOVER_DEFAULTS,
            **LANGUAGE_FILTERS[language],
            **category["params"],
            "page": page,
        }

        data = tmdb_get(endpoint, **params)

        if not data:
            break

        results = data.get("results", [])

        if not results:
            break

        for item in results:

            if not is_valid_item(item, language):
                continue

            if item["id"] in seen:
                continue

            seen.add(item["id"])
            collected.append(item)

            if len(collected) >= TARGET_ITEMS_PER_CATEGORY:
                return collected

        time.sleep(DISCOVERY_DELAY)

    collected.sort(
        key=candidate_score,
        reverse=True,
    )

    return collected[:TARGET_ITEMS_PER_CATEGORY]

# ==========================================================
# Metadata Fetcher
# ==========================================================

def fetch_details(item_type: str, item_id: int) -> dict:
    """
    Fetch complete metadata required for wallpaper rendering.
    """
    cache_key = (item_type, item_id)

    if cache_key in DETAILS_CACHE:
        return DETAILS_CACHE[cache_key]

    endpoint = f"{item_type}/{item_id}"

    details = tmdb_get(
        endpoint,
        language="en-US",
        append_to_response="credits,images",
        include_image_language="en,null"
    )

    if not details:
        return {}

    # Skip adult content
    if details.get("adult", False):
        return {}

    # Skip excluded genres
    genres = {
        genre["id"]
        for genre in details.get("genres", [])
    }

    if genres.intersection(EXCLUDED_GENRES):
        return {}

    # Backdrop is mandatory
    if not details.get("backdrop_path"):
        return {}

    # Require a meaningful rating
    if details.get("vote_average", 0) < MIN_VOTE_AVERAGE:
        return {}

    if details.get("vote_count", 0) < MIN_VOTE_COUNT:
        return {}

    DETAILS_CACHE[cache_key] = details
    return details


from hashlib import md5

def build_filename(details: dict, item_type: str) -> str:

    title = (
            details.get("title")
            or details.get("name")
            or "media"
    )

    safe = "".join(
        c.lower()
        for c in title
        if c.isalnum()
    )[:20]

    digest = md5(
        f"{item_type}_{details['id']}".encode()
    ).hexdigest()[:6]

    return f"{safe}_{digest}.jpg"

# ==========================================================
# Logo Selection
# ==========================================================

def select_logo(details: dict) -> Image.Image | None:
    """
    Download the best available transparent logo.

    Priority:
    1. English PNG
    2. Language-neutral PNG
    3. Highest-rated PNG
    """

    logos = details.get("images", {}).get("logos", [])

    if not logos:
        return None

    png_logos = [
        logo
        for logo in logos
        if logo.get("file_path", "").lower().endswith(".png")
    ]

    if not png_logos:
        return None

    english = [
        logo
        for logo in png_logos
        if logo.get("iso_639_1") == "en"
    ]

    neutral = [
        logo
        for logo in png_logos
        if logo.get("iso_639_1") is None
    ]

    candidates = english or neutral or png_logos

    candidates.sort(
        key=lambda logo: (
            logo.get("vote_average", 0),
            logo.get("width", 0)
        ),
        reverse=True,
    )

    return download_image(candidates[0]["file_path"])


def resize_logo(logo: Image.Image) -> Image.Image:
    """
    Resize while preserving aspect ratio.
    """

    logo.thumbnail(
        (650, 220),
        Image.Resampling.LANCZOS,
    )

    return logo


def draw_logo(
        canvas: Image.Image,
        details: dict,
        draw: ImageDraw.ImageDraw,
        title_font: ImageFont.FreeTypeFont,
) -> None:
    """
    Draw either the official logo or the title text.
    """

    logo = select_logo(details)

    if logo is not None:
        logo = resize_logo(logo)
        canvas.alpha_composite(
            logo,
            dest=(80, 80),
        )
        return

    title = (
            details.get("title")
            or details.get("name")
            or "Unknown"
    )

    draw.text(
        (80, 80),
        title,
        font=title_font,
        fill=(255, 255, 255),
    )

# ==========================================================
# Font Loader
# ==========================================================

def load_fonts() -> dict:
    """
    Load all fonts used by the renderer.

    Falls back to Pillow's default font if Inter is unavailable.
    """

    sizes = {
        "title": 34,
        "meta": 20,
        "label": 14,
        "body": 18,
    }

    fonts = {}

    for name, size in sizes.items():
        try:
            fonts[name] = ImageFont.truetype(
                str(FONT_FILE),
                size,
            )
        except Exception:
            fonts[name] = ImageFont.load_default()

    return fonts


FONTS = load_fonts()

# ==========================================================
# Canvas & Backdrop Renderer
# ==========================================================

def create_canvas() -> Image.Image:
    """
    Create the base wallpaper canvas.
    """

    return Image.new(
        "RGBA",
        (CANVAS_WIDTH, CANVAS_HEIGHT),
        BACKGROUND_COLOR + (255,)
    )


def create_backdrop_mask() -> Image.Image:
    """
    Create a smooth mask with:
      • left fade
      • bottom fade
    """

    mask = Image.new(
        "L",
        (BACKDROP_WIDTH, BACKDROP_HEIGHT),
        255,
    )

    # -------------------------
    # Left Fade
    # -------------------------

    left = Image.linear_gradient("L")
    left = left.rotate(270)
    left = left.resize(
        (420, BACKDROP_HEIGHT),
        Image.Resampling.BICUBIC,
    )

    mask.paste(left, (0, 0))

    # -------------------------
    # Bottom Fade
    # -------------------------

    bottom = Image.linear_gradient("L")
    bottom = bottom.rotate(90)
    bottom = bottom.resize(
        (BACKDROP_WIDTH, 220),
        Image.Resampling.BICUBIC,
    )

    bottom_mask = Image.new(
        "L",
        (BACKDROP_WIDTH, BACKDROP_HEIGHT),
        255,
    )

    bottom_mask.paste(
        ImageOps.invert(bottom),
        (0, BACKDROP_HEIGHT - 220),
    )

    return ImageChops.darker(mask, bottom_mask)


def render_backdrop(
        canvas: Image.Image,
        details: dict,
) -> bool:
    """
    Download, resize and blend the backdrop.
    """

    backdrop = download_image(
        details.get("backdrop_path")
    )

    if backdrop is None:
        return False

    backdrop = backdrop.resize(
        (BACKDROP_WIDTH, BACKDROP_HEIGHT),
        Image.Resampling.LANCZOS,
    )

    canvas.paste(
        backdrop,
        (768, 0),
        create_backdrop_mask(),
    )

    return True

# ==========================================================
# Text Rendering
# ==========================================================

TEXT_LEFT = 80
TEXT_WIDTH = 640

TITLE_Y = 80
META_Y = 240
DIRECTOR_Y = 310
CAST_Y = 395
SUMMARY_Y = 480


def wrap_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
) -> list[str]:
    """
    Wrap text to fit within max_width.
    """

    if not text:
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:

        candidate = word if not current else f"{current} {word}"

        width = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
        )[2]

        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def draw_label(
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
):
    draw.text(
        (x, y),
        text.upper(),
        font=FONTS["label"],
        fill=(150, 155, 165),
    )


def draw_body(
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
):
    draw.text(
        (x, y),
        text,
        font=FONTS["body"],
        fill=(240, 240, 242),
    )


def draw_summary(
        draw: ImageDraw.ImageDraw,
        overview: str,
):
    """
    Draw up to four wrapped lines.
    """

    draw_label(
        draw,
        "Summary",
        TEXT_LEFT,
        SUMMARY_Y,
    )

    lines = wrap_text(
        draw,
        overview or "No overview available.",
        FONTS["body"],
        TEXT_WIDTH,
        )

    y = SUMMARY_Y + 24

    for index, line in enumerate(lines[:4]):

        if index == 3 and len(lines) > 4:
            line += "..."

        draw_body(
            draw,
            line,
            TEXT_LEFT,
            y,
        )

        y += 30

# ==========================================================
# Metadata Renderer
# ==========================================================

def build_meta_line(details: dict, item_type: str) -> str:
    """
    Build the single-line metadata shown below the logo.
    """

    parts = []

    if item_type == "movie":
        runtime = details.get("runtime", 0)
        if runtime:
            parts.append(f"{runtime} min")
    else:
        seasons = details.get("number_of_seasons", 0)
        if seasons:
            parts.append(
                f"{seasons} Season" if seasons == 1 else f"{seasons} Seasons"
            )

    date = (
            details.get("release_date")
            or details.get("first_air_date")
            or ""
    )

    if date:
        parts.append(date[:4])

    genres = details.get("genres", [])

    if genres:
        parts.append(
            " / ".join(g["name"] for g in genres[:2])
        )

    rating = details.get("vote_average", 0)

    if rating:
        parts.append(f"IMDb {rating:.1f}")

    return "   •   ".join(parts)


def get_director(details: dict, item_type: str) -> str:
    """
    Return director or creator.
    """

    if item_type == "movie":
        crew = details.get("credits", {}).get("crew", [])

        for person in crew:
            if person.get("job") == "Director":
                return person["name"]

    else:
        creators = details.get("created_by", [])

        if creators:
            return creators[0]["name"]

    return "N/A"


def get_cast(details: dict) -> str:
    """
    Return the first three cast members.
    """

    cast = details.get("credits", {}).get("cast", [])

    if not cast:
        return "N/A"

    return ", ".join(
        actor["name"]
        for actor in cast[:3]
    )


def draw_metadata(
        draw: ImageDraw.ImageDraw,
        details: dict,
        item_type: str,
):
    """
    Draw metadata block.
    """

    meta = build_meta_line(
        details,
        item_type,
    )

    draw.text(
        (TEXT_LEFT, META_Y),
        meta,
        font=FONTS["meta"],
        fill=(245, 245, 248),
    )

    draw_label(
        draw,
        "Director" if item_type == "movie" else "Creator",
        TEXT_LEFT,
        DIRECTOR_Y,
    )

    draw_body(
        draw,
        get_director(details, item_type),
        TEXT_LEFT,
        DIRECTOR_Y + 22,
        )

    draw_label(
        draw,
        "Cast",
        TEXT_LEFT,
        CAST_Y,
    )

    draw_body(
        draw,
        get_cast(details),
        TEXT_LEFT,
        CAST_Y + 22,
        )

# ==========================================================
# Wallpaper Composer
# ==========================================================

def create_wallpaper(
        details: dict,
        item_type: str,
        filename: str,
) -> bool:
    """
    Render one complete Netflix-style wallpaper.
    """

    canvas = create_canvas()

    if not render_backdrop(canvas, details):
        return False

    draw = ImageDraw.Draw(canvas)

    # --------------------------------------------------
    # Logo / Title
    # --------------------------------------------------

    draw_logo(
        canvas=canvas,
        details=details,
        draw=draw,
        title_font=FONTS["title"],
    )

    # --------------------------------------------------
    # Metadata
    # --------------------------------------------------

    draw_metadata(
        draw=draw,
        details=details,
        item_type=item_type,
    )

    # --------------------------------------------------
    # Summary
    # --------------------------------------------------

    draw_summary(
        draw=draw,
        overview=details.get("overview", ""),
    )

    # --------------------------------------------------
    # Export
    # --------------------------------------------------

    output_path = IMAGE_DIR / filename

    canvas.convert("RGB").save(
        output_path,
        format="JPEG",
        quality=96,
        optimize=True,
        progressive=True,
        subsampling=0,
    )

    if not validate_wallpaper(output_path):
        output_path.unlink(missing_ok=True)
        return False

    return True

# ==========================================================
# JSON Builder
# ==========================================================

GITHUB_IMAGE_BASE = (
    "https://unableeludemotto.github.io/"
    "PixivyWalls/images"
)


def build_json_entry(
        details: dict,
        item_type: str,
        language_name: str,
        category_name: str,
        filename: str,
) -> dict:
    """
    Build one wallpapers.json entry.

    Format intentionally matches the existing frontend.
    """

    media_type = (
        "Movie"
        if item_type == "movie"
        else "Series"
    )

    return {
        "location": (
            f"{media_type} · "
            f"{language_name} · "
            f"{category_name}"
        ),
        "title": (
                details.get("title")
                or details.get("name")
                or "Unknown"
        ),
        "author": language_name,
        "url_img": (
            f"{GITHUB_IMAGE_BASE}/{filename}"
        ),
    }


def write_json(entries: list[dict]) -> None:
    """
    Write wallpapers.json.
    """

    entries.sort(
        key=lambda item: (
            item["author"],
            item["title"].lower(),
        )
    )

    with open(
            JSON_FILE,
            "w",
            encoding="utf-8",
    ) as fp:
        json.dump(
            entries,
            fp,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"✅ Wrote {len(entries)} entries"
    )

# ==========================================================
# Validation
# ==========================================================

def validate_wallpaper(path: Path) -> bool:
    """
    Ensure the generated wallpaper is valid.
    """

    try:
        with Image.open(path) as img:
            img.verify()

        return path.stat().st_size > 100_000

    except Exception:
        return False


def validate_json(entries: list[dict]) -> bool:
    """
    Basic validation for wallpapers.json.
    """

    required = {
        "location",
        "title",
        "author",
        "url_img",
    }

    for entry in entries:
        if set(entry.keys()) != required:
            return False

    return True

# ==========================================================
# README Generator
# ==========================================================

README_FILE = Path("README.md")


def generate_readme(total_wallpapers: int) -> None:
    """
    Generate README.md after each successful run.
    """

    content = f"""# PixivyWalls

Automatically generated Netflix-style Android TV wallpapers.

## Features

- Netflix-inspired dark layout
- English, Hindi and Kannada
- Movies and TV Series
- High quality TMDB backdrops
- Inter typography
- Generated entirely using GitHub Actions

## Statistics

- Wallpapers: {total_wallpapers}
- Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}

## Data Source

- TMDB API

---

This repository is fully generated automatically.
"""

    README_FILE.write_text(
        content,
        encoding="utf-8",
    )

# ==========================================================
# Main Pipeline
# ==========================================================

def run() -> None:

    print("\n🎬 PixivyWalls Generation Started\n")

    entries = []
    processed = set()

    total_generated = 0

    for language_code, language_name in LANGUAGES:

        print(f"\n🌐 {language_name}")

        for category in DISCOVERY_CATEGORIES:

            print(f"  📂 {category['title']}")

            candidates = discover_items(
                category,
                language_code,
            )

            created = 0

            for item in candidates:

                unique_key = (
                    f"{category['type']}_{item['id']}"
                )

                if unique_key in processed:
                    continue

                processed.add(unique_key)

                details = fetch_details(
                    category["type"],
                    item["id"],
                )

                if not details:
                    continue

                filename = build_filename(
                    details,
                    category["type"],
                )

                success = create_wallpaper(
                    details,
                    category["type"],
                    filename,
                )

                if not success:
                    continue

                entries.append(
                    build_json_entry(
                        details=details,
                        item_type=category["type"],
                        language_name=language_name,
                        category_name=category["title"],
                        filename=filename,
                    )
                )

                created += 1
                total_generated += 1

                print(
                    f"     ✓ "
                    f"{details.get('title') or details.get('name')}"
                )

                time.sleep(DISCOVERY_DELAY)

            print(
                f"     Generated {created} wallpapers"
            )

    if validate_json(entries):
        write_json(entries)
        generate_readme(len(entries))
    else:
        raise RuntimeError("wallpapers.json validation failed")

    print("\n===================================")
    print(f"Generated : {total_generated}")
    print(f"JSON      : {len(entries)} entries")
    print("Finished successfully")
    print("===================================\n")
    print("\nGeneration Summary")
    print("------------------")
    print(f"Wallpapers : {total_generated}")
    print(f"JSON Items : {len(entries)}")
    print(f"Images Dir : {IMAGE_DIR}")

    IMAGE_CACHE.clear()
    DETAILS_CACHE.clear()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nGeneration cancelled.")
