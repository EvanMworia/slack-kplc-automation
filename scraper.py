import json
import os
import requests
from datetime import datetime, timedelta
from ntscraper import Nitter

# ── paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CONFIG     = json.load(open(os.path.join(BASE_DIR, "config.json")))
QUEUE_FILE = os.path.join(BASE_DIR, "queue.json")
IMG_DIR    = os.path.join(BASE_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)

# ── helpers ───────────────────────────────────────────────────────────────────
def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return {"tweet_ids": [], "images": []}
    with open(QUEUE_FILE) as f:
        return json.load(f)

def save_queue(q):
    with open(QUEUE_FILE, "w") as f:
        json.dump(q, f, indent=2)

def ordinal(n):
    """Return ordinal string for a day number: 1 -> '1st', 4 -> '4th' etc."""
    s = ["th","st","nd","rd"] + ["th"] * 16
    return f"{n}{s[n % 20] if n % 20 <= 3 else 'th'}"

def tomorrow_variants():
    """
    Build every date format KPLC has been observed to use,
    for tomorrow's date.  Case-insensitive matching is used later.
    """
    t = datetime.now() + timedelta(days=1)
    d, m, y = t.day, t.month, t.year
    mn_full  = t.strftime("%B")          # April
    mn_short = t.strftime("%b")          # Apr
    dd       = f"{d:02d}"
    mm       = f"{m:02d}"
    od       = ordinal(d)                # 4th, 21st …

    return [
        f"{dd}.{mm}.{y}",               # 04.04.2026
        f"{d}.{m}.{y}",                 # 4.4.2026
        f"{dd}/{mm}/{y}",               # 04/04/2026
        f"{d}/{m}/{y}",                 # 4/4/2026
        f"{dd}-{mm}-{y}",               # 04-04-2026
        f"{od} {mn_full} {y}",          # 4th April 2026
        f"{od} {mn_short} {y}",         # 4th Apr 2026
        f"{d} {mn_full} {y}",           # 4 April 2026
        f"{d} {mn_short} {y}",          # 4 Apr 2026
        f"{mn_full} {d} {y}",           # April 4 2026
        f"{mn_full} {od} {y}",          # April 4th 2026
        f"{mn_short} {d} {y}",          # Apr 4 2026
        f"{mn_short} {od} {y}",         # Apr 4th 2026
        f"{dd}{mm}{y}",                 # 04042026 (rare but seen)
    ]

def matches_tomorrow(text):
    text_lower = text.lower()
    return any(v.lower() in text_lower for v in tomorrow_variants())

def matches_keyword(text):
    keywords = [
        "listed areas will be under planned maintenance",
        "listed areas will be under planned maintainance",   # KPLC typo variant
        "following areas are scheduled for planned power maintenance",
        "scheduled for planned power maintenance tomorrow",
        "we regret any inconvenience that may occur during operations",
        "we regret any inconvenience that may occur during interruptions",
        "planned power interruption",
        "planned maintenance tomorrow",
    ]
    text_lower = text.lower()
    return any(k.lower() in text_lower for k in keywords)

def slack_alert(msg):
    """Post a plain-text alert to the channel (used for scraper errors)."""
    from slack_sdk import WebClient
    client = WebClient(token=CONFIG["slack_token"])
    try:
        client.chat_postMessage(channel=CONFIG["channel_id"], text=msg)
    except Exception as e:
        # Last-resort: write to a local log so it isn't silently swallowed
        with open(os.path.join(BASE_DIR, "error.log"), "a") as log:
            log.write(f"{datetime.now()} | slack_alert failed: {e}\n")

def download_image(url, tweet_id, idx):
    """Download one image and return its local file path, or None on failure."""
    ext  = url.split("?")[0].split(".")[-1] or "jpg"
    name = f"{tweet_id}_{idx}.{ext}"
    path = os.path.join(IMG_DIR, name)
    if os.path.exists(path):
        return path                       # already downloaded
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
        return path
    except Exception as e:
        print(f"  [warn] could not download {url}: {e}")
        return None

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] scraper started")
    q = load_queue()

    try:
        scraper = Nitter(log_level=1, skip_instance_check=False)
        tweets  = scraper.get_tweets(CONFIG["x_account"], mode="user", number=40)
    except Exception as e:
        msg = (
            f"⚠️ *KPLC scraper is down* — could not reach X.\n"
            f"<@{CONFIG['evans_id']}> <@{CONFIG['brenda_id']}> "
            f"please share updates manually until fixed.\n"
            f"Error: `{e}`"
        )
        slack_alert(msg)
        print(f"[error] scraper failed: {e}")
        return

    if not tweets or "tweets" not in tweets:
        print("  [info] no tweets returned — skipping")
        return

    new_count = 0
    for tw in tweets.get("tweets", []):
        tid  = tw.get("link", "").split("/")[-1] or tw.get("id", "")
        text = tw.get("text", "")

        if not tid or tid in q["tweet_ids"]:
            continue
        if not matches_keyword(text):
            continue
        if not matches_tomorrow(text):
            continue

        # Collect all media from this tweet
        media_items = tw.get("pictures", []) or tw.get("media", []) or []
        if not media_items:
            print(f"  [warn] matched tweet {tid} has no images — skipping")
            continue

        paths = []
        for idx, item in enumerate(media_items):
            # ntscraper returns either a string URL or a dict with a 'url' key
            url = item if isinstance(item, str) else item.get("url", "")
            if not url:
                continue
            p = download_image(url, tid, idx)
            if p:
                paths.append(p)

        if paths:
            q["tweet_ids"].append(tid)
            q["images"].extend(paths)
            new_count += 1
            print(f"  [queued] tweet {tid} — {len(paths)} image(s)")

    save_queue(q)
    print(f"[done] {new_count} new tweet(s) queued | total images: {len(q['images'])}")

if __name__ == "__main__":
    main()