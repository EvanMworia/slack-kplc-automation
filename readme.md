# Latest Version as of 25th/April/2026

# kplc-bot

Automatically scrapes KPLC (@KenyaPower_Care) power interruption notices from X, downloads the attached images, and posts them to a Slack channel — every day, hands-free.

---

## How it works

1. **`scraper.py`** fetches the @KenyaPower_Care RSS feed via Nitter (no X account or API key needed), filters for today's planned-maintenance tweets by keyword, downloads the attached images, and writes them to `queue.json`.
2. **`poster.py`** reads `queue.json`, uploads all queued images to Slack as a single grouped message captioned with tomorrow's date, then clears the queue.
3. Two cron jobs run these scripts automatically — the scraper several times a day, the poster once at night after the last scrape.

---

## Prerequisites

- Python 3.8+
- A Slack bot token with `chat:write`, `files:write` scopes
- The bot invited to your target channel

---

## 1. Set timezone

```bash
sudo timedatectl set-timezone Africa/Nairobi
```

---

## 2. Install Python dependencies

```bash
pip3 install feedparser slack_sdk requests
```

> `twscrape` is no longer used. No X account or API key is required.

---

## 3. Create the bot folder and upload your files

```bash
mkdir -p ~/kplc-bot
# copy scraper.py, poster.py, config.json into ~/kplc-bot/
```

---

## 4. Configure `config.json`

```json
{
	"slack_token": "xoxb-your-bot-token",
	"channel_id": "C0XXXXXXXXX",
	"evans_id": "UXXXXXXXX",
	"brenda_id": "UXXXXXXXX",
	"x_account": "KenyaPower_Care"
}
```

| Key                      | What it is                             |
| ------------------------ | -------------------------------------- |
| `slack_token`            | Your Slack bot OAuth token (`xoxb-…`)  |
| `channel_id`             | The channel to post updates to         |
| `evans_id` / `brenda_id` | Slack user IDs to ping in error alerts |
| `x_account`              | The X handle to monitor (no `@`)       |

> No X credentials needed — the scraper reads the public Nitter RSS feed.

---

## 5. Test the scraper manually

```bash
cd ~/kplc-bot
python3 scraper.py
```

Expected output when KPLC has posted today:

```
[2026-04-25 08:00] scraper started
  [ok] using https://nitter.net — 20 entries
  [queued] tweet 1234567890 — 3 image(s)
[done] 1 new tweet(s) queued | total images: 3
```

Expected output when nothing matches today (no relevant tweets yet):

```
[2026-04-25 08:00] scraper started
  [ok] using https://nitter.net — 20 entries
[done] 0 new tweet(s) queued | total images: 0
```

Inspect what was queued:

```bash
cat queue.json
```

---

## 6. Test the poster manually

```bash
python3 poster.py
```

Expected output:

```
[2026-04-25 08:01] poster started
  [info] posting 3 image(s) to Slack
  [posted] 3 image(s) uploaded as a group
[done] queue cleared
```

Check your Slack channel — the images should appear with the caption:

```
@channel ⚡ KPLC power updates — Sunday, 26 April 2026
```

---

## 7. Testing against a past date

To test against tweets from a specific past date, temporarily change `published_today` in `scraper.py`:

```python
# TESTING — replace datetime.now().date() with a hardcoded date
def published_today(entry):
    try:
        pub = parsedate_to_datetime(entry.published)
        return pub.date() == datetime(2026, 4, 13).date()
    except Exception:
        return False
```

Revert to `datetime.now().date()` when done.

---

## 8. Set up cron jobs

```bash
crontab -e
```

Add these two lines:

```
0 8,12,17,21,23 * * * python3 /home/ubuntu/kplc-bot/scraper.py >> /home/ubuntu/kplc-bot/scraper.log 2>&1
0 1 * * * python3 /home/ubuntu/kplc-bot/poster.py >> /home/ubuntu/kplc-bot/poster.log 2>&1
```

The scraper runs at **8 AM, 12 PM, 5 PM, 9 PM, and 11 PM** to catch updates as KPLC posts them throughout the day. The poster runs at **1 AM** after the final scrape, posting everything collected that day to Slack. The `>>` redirects output to log files for later inspection.

---

## 9. Verify cron is running

```bash
crontab -l
# should show both lines above

tail -f ~/kplc-bot/scraper.log
tail -f ~/kplc-bot/poster.log
```

---

## 10. Nitter instance fallback

The scraper tries these Nitter instances in order, moving to the next if one is down:

```python
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.catsarch.com",
]
```

If **all** instances fail, the bot sends a Slack alert tagging Evans and Brenda to share updates manually.

To add or update instances, edit this list in `scraper.py`. A maintained list of active instances can be found at [github.com/d4brs/nitter-instances](https://github.com/d4brs/nitter-instances).

---

## Folder structure

```
~/kplc-bot/
├── scraper.py        # fetches tweets, queues images
├── poster.py         # posts queued images to Slack
├── config.json       # your secrets — do not commit this
├── queue.json        # auto-created, auto-cleared after each post
├── scraper.log       # auto-created by cron
├── poster.log        # auto-created by cron
├── error.log         # auto-created if Slack alerts fail
└── images/           # auto-created, holds downloaded images
```

---

## Error handling

| Failure                     | What happens                                                 |
| --------------------------- | ------------------------------------------------------------ |
| All Nitter instances down   | Slack alert sent, Evans + Brenda tagged to share manually    |
| Image download fails        | Warning logged, tweet skipped                                |
| Slack upload fails          | Retries individually per image; error alert sent if all fail |
| Queue is empty at post time | Poster exits cleanly, nothing posted                         |
