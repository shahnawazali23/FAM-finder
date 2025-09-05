import os, json, re, sys, pathlib
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

MANUAL_PATH = pathlib.Path("data/videos_manual.json")
OUT_PATH    = pathlib.Path("data/index.json")
LANGS = ["ar", "en"]

def fetch_transcript(video_id: str):
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in LANGS:
            try: return transcripts.find_manually_created_transcript([lang]).fetch()
            except Exception: pass
        for lang in LANGS:
            try: return transcripts.find_generated_transcript([lang]).fetch()
            except Exception: pass
    except (TranscriptsDisabled, NoTranscriptFound):
        return []
    except Exception:
        return []
    return []

def chunk_lines(lines, max_chars=180, max_secs=18):
    chunks, buf, start_t, last_t = [], [], None, None
    for ln in lines:
        text = re.sub(r"\s+", " ", ln.get("text","")).strip()
        if not text: continue
        t   = float(ln.get("start",0.0)); dur = float(ln.get("duration",0.0))
        if start_t is None: start_t = t
        buf.append(text); last_t = t + dur
        if sum(len(x) for x in buf) > max_chars or (last_t - start_t) > max_secs:
            chunks.append({"t": int(start_t), "text": " ".join(buf)})
            buf, start_t = [], None
    if buf: chunks.append({"t": int(start_t), "text": " ".join(buf)})
    return chunks

def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not MANUAL_PATH.exists():
        print(f"ERROR: {MANUAL_PATH} not found.", file=sys.stderr)
        OUT_PATH.write_text("[]", encoding="utf-8")
        sys.exit(1)

    with MANUAL_PATH.open("r", encoding="utf-8") as f:
        try:
            manual = json.load(f)
        except Exception as e:
            raise SystemExit(f"videos_manual.json invalid JSON: {e}")
        if not isinstance(manual, list):
            raise SystemExit("videos_manual.json must be a JSON array")
        if not manual:
            raise SystemExit("videos_manual.json is empty — add at least one {\"id\":\"...\"}.")

    out = []
    print(f"Found {len(manual)} manual video IDs.")
    for v in manual:
        vid = v.get("id")
        if not vid: continue
        title  = v.get("title", f"Video {vid}")
        date   = v.get("date", "")
        url    = v.get("url", f"https://www.youtube.com/watch?v={vid}")
        topics = v.get("topics", [])

        lines  = fetch_transcript(vid)
        chunks = chunk_lines(lines)
        print(f"- {vid}: {len(chunks)} chunks")

        out.append({
            "id": vid, "title": title, "series": "",
            "date": date, "url": url, "lang": "ar", "topics": topics,
            "terms": [{ "term": "", "t": c["t"], "text": c["text"], "tags": [] } for c in chunks]
        })

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} with {len(out)} videos")

if __name__ == "__main__":
    main()
