import os, json, re
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

API_KEY = os.environ["YT_API_KEY"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
MAX_VIDS = 50
LANGS = ["ar","en"]

def yt():
    return build("youtube", "v3", developerKey=API_KEY, cache_discovery=False)

def get_uploads_playlist_id():
    resp = yt().channels().list(part="contentDetails", id=CHANNEL_ID).execute()
    return resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

def list_uploads(playlist_id):
    vids, page = [], None
    while True:
        resp = yt().playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page
        ).execute()
        for it in resp.get("items", []):
            vids.append({
                "id": it["contentDetails"]["videoId"],
                "title": it["snippet"]["title"],
                "date": it["contentDetails"]["videoPublishedAt"][:10],
                "url": f"https://www.youtube.com/watch?v={it['contentDetails']['videoId']}"
            })
        page = resp.get("nextPageToken")
        if not page or len(vids) >= MAX_VIDS:
            break
    return vids

def fetch_transcript(video_id):
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in LANGS:
            try: return transcripts.find_manually_created_transcript([lang]).fetch()
            except: pass
        for lang in LANGS:
            try: return transcripts.find_generated_transcript([lang]).fetch()
            except: pass
    except (TranscriptsDisabled, NoTranscriptFound): return []
    return []

def chunk_lines(lines, max_chars=180, max_secs=18):
    chunks, buf, start_t = [], [], None
    last_t = None
    for ln in lines:
        text = re.sub(r"\\s+", " ", ln.get("text","")).strip()
        if not text: continue
        t = float(ln["start"]); dur = float(ln["duration"])
        if start_t is None: start_t = t
        buf.append(text); last_t = t + dur
        if sum(len(x) for x in buf) > max_chars or (last_t - start_t) > max_secs:
            chunks.append({"t": int(start_t), "text": " ".join(buf)})
            buf, start_t = [], None
    if buf: chunks.append({"t": int(start_t), "text": " ".join(buf)})
    return chunks

def main():
    os.makedirs("data", exist_ok=True)
    playlist_id = get_uploads_playlist_id()
    vids = list_uploads(playlist_id)
    out = []
    for v in vids:
        lines = fetch_transcript(v["id"])
        chunks = chunk_lines(lines)
        out.append({
            "id": v["id"], "title": v["title"], "series": "",
            "date": v["date"], "url": v["url"], "lang": "ar", "topics": [],
            "terms": [{ "term":"", "t":c["t"], "text":c["text"], "tags":[] } for c in chunks]
        })
    with open("data/index.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
