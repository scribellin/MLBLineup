# ☕ The Morning Lineup

A self-updating MLB box score page. Rebuilds every morning at 6am ET via GitHub Actions
and publishes to GitHub Pages. No takes. No discourse. Just baseball.

**Live site:** https://scribellin.github.io/MLBLineup

## Stack
- Python + MLB Stats API (free, no key needed)
- GitHub Actions (free tier, runs daily)
- GitHub Pages (free static hosting)

## Local development
```bash
pip install -r requirements.txt
python scraper.py
open docs/index.html
```

## Manually trigger a rebuild
Go to **Actions → Build Morning Lineup → Run workflow**.
