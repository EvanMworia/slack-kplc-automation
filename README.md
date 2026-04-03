# KPLC Bot – Setup Guide

## 1. Set Timezone

```bash
sudo timedatectl set-timezone Africa/Nairobi
```

## 2. Install Python Dependencies

```bash
pip3 install ntscraper slack_sdk requests
```

## 3. Create Bot Folder and Upload Your Files There

```bash
mkdir -p ~/kplc-bot
```

Copy `scraper.py`, `poster.py`, `config.json` into `~/kplc-bot/`, then fill in `config.json` with your real token, channel ID and user IDs.

## 4. Test the Scraper Manually First

```bash
cd ~/kplc-bot
python3 scraper.py
```

Expected output:

```
[2026-04-04 08:00] scraper started
[queued] tweet 1234567890 — 3 image(s)     ← if KPLC posted today
[done] 1 new tweet(s) queued | total images: 3
```

Check what was queued:

```bash
cat queue.json
```

## 5. Test the Poster Manually

```bash
python3 poster.py
```

Expected output:

```
[2026-04-04 08:01] poster started
[info] posting 3 image(s) to Slack
[posted] 3 image(s) uploaded as a group
[done] queue cleared
```

Check `#06-kplc-updates` in Slack — message should appear.

## 6. Set Up Cron Jobs

```bash
crontab -e
```

Add these two lines, then save:

```
0 8,12,17,21,23 * * * python3 /home/ubuntu/kplc-bot/scraper.py >> /home/ubuntu/kplc-bot/scraper.log 2>&1
0 1 * * *             python3 /home/ubuntu/kplc-bot/poster.py  >> /home/ubuntu/kplc-bot/poster.log  2>&1
```

The `>>` redirects output to log files so you can inspect runs later:

```bash
tail -f ~/kplc-bot/scraper.log
tail -f ~/kplc-bot/poster.log
```

## 7. Verify Cron Is Running

```bash
crontab -l
```

Should show both lines above.

## 8. Folder Structure When Everything Is in Place

```
~/kplc-bot/
├── scraper.py
├── poster.py
├── config.json       ← your secrets
├── queue.json        ← auto-created, auto-cleared
├── scraper.log       ← auto-created by cron
├── poster.log        ← auto-created by cron
├── error.log         ← auto-created if Slack alerts fail
└── images/           ← auto-created, holds downloaded images
```
