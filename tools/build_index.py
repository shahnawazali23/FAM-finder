import os, json, re, time
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

API_KEY = os.environ["YT_API_KEY"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
MAX_VIDS = int(os.environ.get("MAX_VIDS", "120"))
LANGS = ["ar", "en"]

def yt():
    return build("youtube", "v3", developerKey=API_KEY, cache_discovery=False)

def list_channel_videos(channel_id: str, max_vids: int):
    """List recent videos by channelId (no uploads playlist)."""
    vids = []
    page = None
    while True:
        resp = yt().search().list(
            part="id,snippet",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=50,
            pageToken=page
        ).execute()

        for it in resp.get("items", []):
            vid = it["id"]["videoId"]
            sn  = it["snippet"]
            vids.append({
                "id": vid,
                "title": sn.get("title", ""),
                "date": sn.get("publishedAt", "")[:10],
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        page = resp.get("nextPageToken")
        if not page or len(vids) >= max_vids:
            break
    return vids[:max_vids]

def fetch_transcript(video_id: str):
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        # Prefer manual subs in preferred languages
        for lang in LANGS:
            try:
                return transcripts.find_manually_created_transcript([lang]).fetch()
            except Exception:
                pass
        # Fallback to auto-generated
        for lang in LANGS:
            try:
                return transcripts.find_generated_transcript([lang]).fetch()
            except Exception:
                pass
    except (TranscriptsDisabled, NoTranscriptFound):
        return []
    except Exception:
        return []
    return []

def chunk_lines(lines, max_chars=180, max_secs=18):
    chunks, buf, start_t, last_t = [], [], None, None
    for ln in lines:
        text = re.sub(r"\s+", " ", ln.get("text", "")).strip()
        if not text:
            continue
        t   = float(ln.get("start", 0.0))
        dur = float(ln.get("duration", 0.0))
        if start_t is None:
            start_t = t
        buf.append(text)
        last_t = t + dur
        if sum(len(x) for x in buf) > max_chars or (last_t - start_t) > max_secs:
            chunks.append({"t": int(start_t), "text": " ".join(buf)})
            buf, start_t = [], None
    if buf:
        chunks.append({"t": int(start_t), "text": " ".join(buf)})
    return chunks

def main():
    os.makedirs("data", exist_ok=True)
    videos = list_channel_videos(CHANNEL_ID, MAX_VIDS)
    out = []
    for v in videos:
        lines = fetch_transcript(v["id"])
        chunks = chunk_lines(lines)
        out.append({
            "id": v["id"],
            "title": v["title"],
            "series": "",
            "date": v["date"],
            "url": v["url"],
            "lang": "ar",
            "topics": [],
            "terms": [{ "term": "", "t": c["t"], "text": c["text"], "tags": [] } for c in chunks]
        })
    with open("data/index.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()

