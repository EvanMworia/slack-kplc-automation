import json
import os
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CONFIG     = json.load(open(os.path.join(BASE_DIR, "config.json")))
QUEUE_FILE = os.path.join(BASE_DIR, "queue.json")

client  = WebClient(token=CONFIG["slack_token"])
CHANNEL = CONFIG["channel_id"]

# ── helpers ───────────────────────────────────────────────────────────────────
def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return {"tweet_ids": [], "images": []}
    with open(QUEUE_FILE) as f:
        return json.load(f)

def clear_queue():
    with open(QUEUE_FILE, "w") as f:
        json.dump({"tweet_ids": [], "images": []}, f, indent=2)

def slack_alert(msg):
    """Post an alert message — used when the poster itself hits an error."""
    try:
        client.chat_postMessage(channel=CHANNEL, text=msg)
    except Exception as e:
        with open(os.path.join(BASE_DIR, "error.log"), "a") as log:
            log.write(f"{datetime.now()} | slack_alert failed: {e}\n")

def upload_images(image_paths, caption):
    """
    Upload all images as a single Slack file group so they appear
    together in one message block, not as separate uploads.
    Falls back to individual uploads if the batch API isn't available.
    """
    try:
        # Slack's newer files.getUploadURLExternal / files.completeUploadExternal
        # approach — batch all images into one message
        file_uploads = []
        for path in image_paths:
            if not os.path.exists(path):
                print(f"  [warn] image not found on disk: {path}")
                continue
            filename = os.path.basename(path)
            file_uploads.append({
                "file": path,
                "filename": filename,
            })

        if not file_uploads:
            print("  [warn] no valid image files to upload")
            return

        client.files_upload_v2(
            channel=CHANNEL,
            file_uploads=file_uploads,
            initial_comment=caption,
        )
        print(f"  [posted] {len(file_uploads)} image(s) uploaded as a group")

    except SlackApiError as e:
        # Fallback: post images one by one if batch upload fails
        print(f"  [warn] batch upload failed ({e.response['error']}), trying individually")
        first = True
        for path in image_paths:
            if not os.path.exists(path):
                continue
            try:
                client.files_upload_v2(
                    channel=CHANNEL,
                    file=path,
                    filename=os.path.basename(path),
                    initial_comment=caption if first else "",
                )
                first = False
            except SlackApiError as e2:
                print(f"  [error] failed to upload {path}: {e2.response['error']}")

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] poster started")
    q = load_queue()

    if not q.get("images"):
        print("  [info] queue is empty — nothing to post today")
        return

    
    today_str = datetime.now().strftime("%A, %d %B %Y")   # e.g. Friday, 04 April 2026
    caption   = f"<!channel> ⚡ KPLC power updates — {today_str}"
    print(f"  [info] posting {len(q['images'])} image(s) to Slack")
    print(f"  [info] caption: {caption}")

    try:
        upload_images(q["images"], caption)
        clear_queue()
        print("[done] queue cleared")

    except Exception as e:
        msg = (
            f"⚠️ *KPLC poster failed* — images could not be sent to Slack.\n"
            # f"<@{CONFIG['evans_id']}> <@{CONFIG['brenda_id']}> "
            f"<@{CONFIG['brenda_id']}> "
            f"please share updates manually today.\n"
            f"Error: `{e}`"
        )
        slack_alert(msg)
        print(f"[error] poster failed: {e}")

if __name__ == "__main__":
    main()