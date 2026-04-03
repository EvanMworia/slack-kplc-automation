# ── 1. set timezone ───────────────────────────────────────────────────────────
sudo timedatectl set-timezone Africa/Nairobi

# ── 2. install python dependencies ───────────────────────────────────────────
pip3 install ntscraper slack_sdk requests

# ── 3. create bot folder and upload your files there ─────────────────────────
mkdir -p ~/kplc-bot
# copy scraper.py, poster.py, config.json into ~/kplc-bot/
# then fill in config.json with your real token, channel ID and user IDs

# ── 4. test the scraper manually first ───────────────────────────────────────
cd ~/kplc-bot
python3 scraper.py
# expected output:
#   [2026-04-04 08:00] scraper started
#   [queued] tweet 1234567890 — 3 image(s)     ← if KPLC posted today
#   [done] 1 new tweet(s) queued | total images: 3

# check what was queued
cat queue.json

# ── 5. test the poster manually ──────────────────────────────────────────────
python3 poster.py
# expected output:
#   [2026-04-04 08:01] poster started
#   [info] posting 3 image(s) to Slack
#   [posted] 3 image(s) uploaded as a group
#   [done] queue cleared
# → check #06-kplc-updates in Slack — message should appear

# ── 6. set up cron jobs ───────────────────────────────────────────────────────
crontab -e
# add these two lines, then save:

0 8,12,17,21,23 * * * python3 /home/ubuntu/kplc-bot/scraper.py >> /home/ubuntu/kplc-bot/scraper.log 2>&1
0 1 * * *             python3 /home/ubuntu/kplc-bot/poster.py  >> /home/ubuntu/kplc-bot/poster.log  2>&1

# the >> redirects output to log files so you can inspect runs later:
#   tail -f ~/kplc-bot/scraper.log
#   tail -f ~/kplc-bot/poster.log

# ── 7. verify cron is running ────────────────────────────────────────────────
crontab -l
# should show both lines above

# ── 8. folder structure when everything is in place ──────────────────────────
# ~/kplc-bot/
# ├── scraper.py
# ├── poster.py
# ├── config.json       ← your secrets
# ├── queue.json        ← auto-created, auto-cleared
# ├── scraper.log       ← auto-created by cron
# ├── poster.log        ← auto-created by cron
# ├── error.log         ← auto-created if Slack alerts fail
# └── images/           ← auto-created, holds downloaded images