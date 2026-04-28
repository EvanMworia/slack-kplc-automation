import json
import os
import requests
import feedparser
from datetime import datetime
from email.utils import parsedate_to_datetime

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CONFIG     = json.load(open(os.path.join(BASE_DIR, "config.json")))
QUEUE_FILE = os.path.join(BASE_DIR, "queue.json")
IMG_DIR    = os.path.join(BASE_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)

# ── nitter instances to try in order ─────────────────────────────────────────
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.catsarch.com",
]

# ── queue helpers ─────────────────────────────────────────────────────────────
def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return {"tweet_ids": [], "images": []}
    with open(QUEUE_FILE) as f:
        return json.load(f)

def save_queue(q):
    with open(QUEUE_FILE, "w") as f:
        json.dump(q, f, indent=2)

# ── keyword matching (your proven list) ──────────────────────────────────────
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

# ── date check: only tweets published TODAY ───────────────────────────────────
def published_today(entry):
    try:
        pub = parsedate_to_datetime(entry.published)
        return pub.date() == datetime.now().date()
        # return pub.date() == datetime(2026, 4, 14).date()
    except Exception:
        return False


# ── slack alert ───────────────────────────────────────────────────────────────
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
    # Nitter serves images from its own domain — resolve to original if possible
    # but downloading from Nitter's proxy works fine too
    ext  = url.split("?")[0].split(".")[-1] or "jpg"
    name = f"{tweet_id}_{idx}.{ext}"
    path = os.path.join(IMG_DIR, name)
    if os.path.exists(path):
        return path
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
        return path
    except Exception as e:
        print(f"  [warn] could not download {url}: {e}")
        return None

# ── extract image urls from an RSS entry ─────────────────────────────────────
def extract_images(entry, base_url):
    images = []

    # Method 1: media_content (standard RSS media extension)
    if hasattr(entry, "media_content"):
        for m in entry.media_content:
            url = m.get("url", "")
            if url:
                images.append(url)

    # Method 2: enclosures
    if not images and hasattr(entry, "enclosures"):
        for enc in entry.enclosures:
            url = enc.get("href", "")
            if url:
                images.append(url)

    # Method 3: parse <img> tags from the HTML summary
    if not images and hasattr(entry, "summary"):
        import re
        found = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
        for url in found:
            # Nitter serves images as relative paths sometimes — make absolute
            if url.startswith("/"):
                url = base_url + url
            images.append(url)

    return images

# ── fetch RSS, try each instance until one works ─────────────────────────────
def fetch_rss():
    account = CONFIG["x_account"].lstrip("@")
    last_err = None

    for instance in NITTER_INSTANCES:
        url = f"{instance}/{account}/rss"
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                print(f"  [skip] {instance} returned {resp.status_code}")
                continue
            feed = feedparser.parse(resp.content)
            if not feed.entries:
                print(f"  [skip] {instance} returned empty feed")
                continue
            print(f"  [ok] using {instance} — {len(feed.entries)} entries")
            return feed, instance
        except Exception as e:
            last_err = e
            print(f"  [skip] {instance} failed: {e}")
            continue

    raise RuntimeError(f"All Nitter instances failed. Last error: {last_err}")

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] scraper started")
    q = load_queue()

    try:
        feed, base_url = fetch_rss()
    except Exception as e:
        msg = (
            f"⚠️ *KPLC scraper is down* — all Nitter instances failed.\n"
            f"<@{CONFIG['evans_id']}> <@{CONFIG['brenda_id']}> "
            f"please share updates manually until fixed.\n"
            f"Error: `{e}`"
        )
        slack_alert(msg)
        print(f"[error] {e}")
        return

    new_count = 0
    for entry in feed.entries:

        # derive a stable tweet ID from the URL, e.g. nitter.net/x/status/12345
        tweet_id = entry.get("id", entry.get("link", "")).rstrip("/").split("/")[-1]
        text     = entry.get("title", "") + " " + entry.get("summary", "")

        if tweet_id in q["tweet_ids"]:
            continue
        if not published_today(entry):
            continue
        if not matches_keyword(text):
            continue

        images = extract_images(entry, base_url)
        if not images:
            print(f"  [warn] matched tweet {tweet_id} has no images — skipping")
            continue

        paths = []
        for idx, url in enumerate(images):
            p = download_image(url, tweet_id, idx)
            if p:
                paths.append(p)

        if paths:
            q["tweet_ids"].append(tweet_id)
            q["images"].extend(paths)
            new_count += 1
            print(f"  [queued] tweet {tweet_id} — {len(paths)} image(s)")

    save_queue(q)
    print(f"[done] {new_count} new tweet(s) queued | total images: {len(q['images'])}")

if __name__ == "__main__":
    main()