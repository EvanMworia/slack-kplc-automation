import json
import os
import asyncio
import requests
from datetime import datetime, timedelta
from twscrape import API, gather
from twscrape.logger import set_log_level

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CONFIG     = json.load(open(os.path.join(BASE_DIR, "config.json")))
QUEUE_FILE = os.path.join(BASE_DIR, "queue.json")
IMG_DIR    = os.path.join(BASE_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)

# ── queue helpers ─────────────────────────────────────────────────────────────
def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return {"tweet_ids": [], "images": []}
    with open(QUEUE_FILE) as f:
        return json.load(f)

def save_queue(q):
    with open(QUEUE_FILE, "w") as f:
        json.dump(q, f, indent=2)

# ── date helpers ──────────────────────────────────────────────────────────────
def ordinal(n):
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"

def tomorrow_variants():
    t     = datetime.now() + timedelta(days=1)
    d, m, y = t.day, t.month, t.year
    mn_full  = t.strftime("%B")
    mn_short = t.strftime("%b")
    dd, mm   = f"{d:02d}", f"{m:02d}"
    od       = ordinal(d)
    return [
        f"{dd}.{mm}.{y}", f"{d}.{m}.{y}",
        f"{dd}/{mm}/{y}", f"{d}/{m}/{y}",
        f"{dd}-{mm}-{y}",
        f"{od} {mn_full} {y}", f"{od} {mn_short} {y}",
        f"{d} {mn_full} {y}", f"{d} {mn_short} {y}",
        f"{mn_full} {d} {y}", f"{mn_full} {od} {y}",
        f"{mn_short} {d} {y}", f"{mn_short} {od} {y}",
        f"{dd}{mm}{y}",
    ]

def matches_tomorrow(text):
    tl = text.lower()
    return any(v.lower() in tl for v in tomorrow_variants())

def matches_keyword(text):
    keywords = [
        "listed areas will be under planned maintenance",
        "listed areas will be under planned maintainance",
        "following areas are scheduled for planned power maintenance",
        "scheduled for planned power maintenance tomorrow",
        "we regret any inconvenience that may occur during operations",
        "we regret any inconvenience that may occur during interruptions",
        "planned power interruption",
        "planned maintenance tomorrow",
    ]
    tl = text.lower()
    return any(k in tl for k in keywords)

# ── slack alert (errors only) ─────────────────────────────────────────────────
def slack_alert(msg):
    from slack_sdk import WebClient
    try:
        WebClient(token=CONFIG["slack_token"]).chat_postMessage(
            channel=CONFIG["channel_id"], text=msg
        )
    except Exception as e:
        with open(os.path.join(BASE_DIR, "error.log"), "a") as log:
            log.write(f"{datetime.now()} | slack_alert failed: {e}\n")

# ── image download ────────────────────────────────────────────────────────────
def download_image(url, tweet_id, idx):
    ext  = url.split("?")[0].split(".")[-1] or "jpg"
    name = f"{tweet_id}_{idx}.{ext}"
    path = os.path.join(IMG_DIR, name)
    if os.path.exists(path):
        return path
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
        return path
    except Exception as e:
        print(f"  [warn] could not download {url}: {e}")
        return None

# ── core scrape logic (async) ─────────────────────────────────────────────────
async def scrape():
    set_log_level("ERROR")       # suppress twscrape verbose output
    api = API()                  # uses accounts.db in current directory

    # Add account only if the DB is fresh (won't duplicate on repeat runs)
    await api.pool.add_account(
        username = CONFIG["x_username"],
        password = CONFIG["x_password"],
        email    = CONFIG["x_email"],
        email_password = CONFIG["x_email_password"],
        cookies={
        "auth_token": CONFIG["auth_token"],
        "ct0": CONFIG["ct0"],
    }
    )
    await api.pool.login_all()

    # Resolve the target account's numeric user ID from their username
    target_user = await api.user_by_login(CONFIG["x_account"])
    if not target_user:
        raise RuntimeError(f"Could not resolve user: {CONFIG['x_account']}")

    # Fetch the 40 most recent tweets from that account
    tweets = await gather(api.user_tweets(target_user.id, limit=40))
    return tweets

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] scraper started")
    q = load_queue()

    try:
        tweets = asyncio.run(scrape())
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

    new_count = 0
    for tw in tweets:
        tid  = str(tw.id)
        text = tw.rawContent or ""

        if tid in q["tweet_ids"]:
            continue
        if not matches_keyword(text):
            continue
        if not matches_tomorrow(text):
            continue

        # Grab all media attached to this tweet
        media_items = tw.media.photos if tw.media and tw.media.photos else []
        # Also check videos/gifs thumbnails in case they ever use those
        if not media_items and tw.media and tw.media.videos:
            # use the thumbnail of any video as fallback
            media_items = [v for v in tw.media.videos]

        if not media_items:
            print(f"  [warn] matched tweet {tid} has no images — skipping")
            continue

        paths = []
        for idx, item in enumerate(media_items):
            # twscrape photo objects have a .url attribute
            url = item.url if hasattr(item, "url") else str(item)
            p   = download_image(url, tid, idx)
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