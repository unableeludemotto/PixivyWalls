# 🎬 CineVault Bot

> Generates a daily TMDB wallpaper feed (JSON) hosted on GitHub Pages,
> consumed directly by the **Overflight plugin** in **Projectivy Launcher** on Android TV.
> **No Reddit. No server. 100% free.**

**Languages:** 🇬🇧 English · 🇮🇳 Hindi · 🏴 Kannada · 🏴 Malayalam  
**Content:** Movies · Series · Documentaries (Trending, Popular, Top Rated)  
**Automation:** GitHub Actions — runs daily at 6 AM IST, free

---

## 🏗️ How It Works

```
GitHub Actions (daily 6AM IST)
  └─► bot.py
        └─► TMDB API  (fetch trending/popular movies, series, documentaries)
              └─► generates docs/wallpapers.json
                    └─► pushed to GitHub Pages (free hosting)
                          └─► Overflight plugin reads JSON URL
                                └─► Projectivy shows wallpapers on TV 🎉
```

---

## 🗂️ Project Structure

```
cinevault-bot/
├── bot.py                          # Main script — fetches TMDB, writes JSON
├── requirements.txt                # requests only (no Reddit needed!)
├── .gitignore
├── docs/
│   ├── index.html                  # GitHub Pages landing page (shows JSON URL)
│   ├── wallpapers.json             # ← Overflight reads THIS (auto-generated daily)
│   └── wallpapers_full.json        # Full metadata version (auto-generated daily)
└── .github/
    └── workflows/
        └── bot.yml                 # GitHub Actions — runs daily at 6 AM IST
```

---

## ✅ Complete Setup Guide

---

### STEP 1 — Get TMDB API Key (Free)

1. Create account at **https://www.themoviedb.org/**
2. Go to **Settings → API → Create → Developer**
3. Fill out the form (personal use is fine, short description OK)
4. Copy your **API Key (v3 auth)** — long hex string

---

### STEP 2 — Create GitHub Repository

1. Go to **https://github.com/new**
2. Repository name: `cinevault-bot`
3. Set to **Public** ← important for GitHub Pages + free Actions minutes
4. Click **Create repository**
5. Upload all project files:
   - `bot.py`
   - `requirements.txt`
   - `.gitignore`
   - `docs/index.html`
   - `.github/workflows/bot.yml`

   **Tip:** Click "uploading an existing file" on the empty repo page, drag all files in.
   Make sure the folder structure is preserved (docs/ and .github/workflows/ subfolders).

---

### STEP 3 — Add GitHub Secret

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add:

| Secret Name    | Value                  |
|:---------------|:-----------------------|
| `TMDB_API_KEY` | Your TMDB v3 API key   |

That's the **only** secret needed. No Reddit credentials at all!

---

### STEP 4 — Enable GitHub Pages

1. Go to repo → **Settings** → **Pages** (left sidebar)
2. Under **Source** → select **Deploy from a branch**
3. Branch: `main` | Folder: `/docs`
4. Click **Save**
5. Wait ~2 minutes → GitHub will show your Pages URL:
   ```
   https://YOUR_USERNAME.github.io/cinevault-bot/
   ```
6. Your wallpapers JSON will be at:
   ```
   https://YOUR_USERNAME.github.io/cinevault-bot/wallpapers.json
   ```

---

### STEP 5 — Run the Bot (First Time)

1. Go to repo → **Actions** tab
2. Click **"I understand my workflows, go ahead and enable them"** if prompted
3. Click **"CineVault Bot"** in the left sidebar
4. Click **"Run workflow"** → **"Run workflow"** (green button)
5. Wait ~5-10 minutes for it to complete
6. Check `docs/wallpapers.json` is now in your repo ✅

---

### STEP 6 — Install Overflight on Android TV

1. On your Android TV, open **Play Store**
2. Search: **Overflight** (by Spocky)
3. Install it
4. Note: Overflight requires **Projectivy Premium** (one-time purchase)

---

### STEP 7 — Configure Projectivy

1. Open **Projectivy Launcher** on Android TV
2. Go to **Settings → Appearance → Wallpaper**
3. Select **Overflight** from the dropdown
4. Open **Overflight settings**
5. Find the **JSON URL** field
6. Enter your URL:
   ```
   https://YOUR_USERNAME.github.io/cinevault-bot/wallpapers.json
   ```
   (Or visit your GitHub Pages site — it shows the exact URL to copy)
7. Save → Done! 🎉

---

## ⏰ Schedule

Runs **daily at 6:00 AM IST** automatically via GitHub Actions.

To change: edit `cron` in `.github/workflows/bot.yml`:
```yaml
- cron: "30 0 * * *"   # 00:30 UTC = 6:00 AM IST
```
Use https://crontab.guru to build custom schedules.

---

## 💰 Cost Breakdown

| Service              | Cost |
|:---------------------|:-----|
| TMDB API             | Free |
| GitHub repository    | Free |
| GitHub Actions       | Free (2,000 min/month; bot uses ~60 min/month) |
| GitHub Pages hosting | Free |
| Reddit               | Not needed ✅ |
| **Total**            | **₹0 / $0** |

---

## 📦 What Gets Included Per Wallpaper

Each wallpaper entry in the JSON contains:
- High-resolution backdrop image URL (from TMDB original)
- Title, year, rating, vote count
- Genres, runtime (movies) / seasons+episodes (series)
- Director / Creator
- Top 5 cast members
- Full overview/description
- Tagline
- Budget & box office (movies)
- Network (series)
- Direct TMDB link

---

## 🐛 Troubleshooting

| Problem | Fix |
|:--------|:----|
| `wallpapers.json` not appearing | Run workflow manually from Actions tab |
| GitHub Pages shows 404 | Check Settings → Pages → Source is set to `/docs` branch `main` |
| TMDB errors in logs | Verify `TMDB_API_KEY` secret is set correctly |
| No Kannada/Malayalam results | Normal — TMDB has fewer entries; English/Hindi will dominate |
| Overflight not showing wallpapers | Make sure JSON URL ends with `wallpapers.json`, no trailing slash |
| Actions not running daily | Check if repo has been inactive (GitHub pauses Actions on inactive repos — just push any change to reactivate) |
