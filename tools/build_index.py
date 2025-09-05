import os, json, re, sys, pathlib
from datetime import timedelta
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

MANUAL_PATH = pathlib.Path("data/videos_manual.json")
OUT_PATH    = pathlib.Path("data/index.json")
TRANS_DIR   = pathlib.Path("data/transcripts")

PREFERRED_LANGS = ["ar", "ar-SA", "ar-EG", "en"]

def parse_timestamp_vtt(ts):
    # "MM:SS.mmm" or "HH:MM:SS.mmm"
    parts = ts.split(":")
    if len(parts) == 2:
        m, s = parts
        h = 0
    else:
        h, m, s = parts
    sec = float(s)
    return int(timedelta(hours=int(h), minutes=int(m), seconds=int(sec)).total_seconds())

def parse_timestamp_srt(ts):
    # "HH:MM:SS,mmm"
    hh, mm, rest = ts.split(":")
    ss, _ms = rest.split(",")
    return int(timedelta(hours=int(hh), minutes=int(mm), seconds=int(ss)).total_seconds())

def read_local_transcript(video_id: str):
    TRANS_DIR.mkdir(parents=True, exist_ok=True)
    vtt = TRANS_DIR / f"{video_id}.vtt"
    srt = TRANS_DIR / f"{video_id}.srt"

    if vtt.exists():
        text = vtt.read_text(encoding="utf-8", errors="ignore")
        # WEBVTT cues: timestamps line then one or more text lines until blank
        cues = re.split(r"\n\n+", text.strip(), flags=re.M)
        out = []
        for cue in cues:
            lines = [ln.strip() for ln in cue.splitlines() if ln.strip()]
            if not lines: continue
            if "-->" in lines[0]:
                start, end = [x.strip() for x in lines[0].split("-->")]
                try:
                    t0 = parse_timestamp_vtt(start)
                    t1 = parse_timestamp_vtt(end)
                except Exception:
                    continue
                body = " ".join(lines[1:])
                if body:
                    out.append({"start": float(t0), "duration": float(max(0, t1 - t0)), "text": body})
        if out:
            print(f"  using local .vtt with {len(out)} cues")
        return out

    if srt.exists():
        text = srt.read_text(encoding="utf-8", errors="ignore")
        blocks = re.split(r"\n\s*\n", text.strip(), flags=re.M)
        out = []
        for b in blocks:
            lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
            if len(lines) < 2: continue
            # Optional index on line 0
            time_line = lines[0] if "-->" in lines[0] else (lines[1] if len(lines) > 1 else "")
            if "-->" not in time_line: continue
            start, end = [x.strip() for x in time_line.split("-->")]
            try:
                t0 = parse_timestamp_srt(start)
                t1 = parse_timestamp_srt(end)
            except Exception:
                continue
            body_lines = lines[1:] if "-->" in lines[0] else lines[2:]
            body = " ".join(body_lines)
            if body:
                out.append({"start": float(t0), "duration": float(max(0, t1 - t0)), "text": body})
        if out:
            print(f"  using local .srt with {len(out)} cues")
        return out

    return []

def fetch_youtube_transcript(video_id: str):
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        available = []
        for tr in transcripts:
            tag = f"{tr.language_code}{'*' if tr.is_generated else ''}"
            available.append(tag)
        print(f"  available on YouTube: {', '.join(available) if available else '(none)'}")

        # Preferred langs first
        for lang in PREFERRED_LANGS:
            try:
                return transcripts.find_manually_created_transcript([lang]).fetch()
            except Exception:
                pass
            try:
                return transcripts.find_generated_transcript([lang]).fetch()
            except Exception:
                pass

        # Fallback: any transcript
        for tr in transcripts:
            try:
                return tr.fetch()
            except Exception:
                continue
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
        OUT_PATH.write_text("[]", encoding="utf-8"); sys.exit(1)

    with MANUAL_PATH.open("r", encoding="utf-8") as f:
        manual = json.load(f)
        if not isinstance(manual, list): raise SystemExit("videos_manual.json must be an array")
        if not manual: raise SystemExit("videos_manual.json is empty")

    out = []
    print(f"Found {len(manual)} manual video IDs.")
    for v in manual:
        vid = v.get("id"); 
        if not vid: continue
        title  = v.get("title", f"Video {vid}")
        date   = v.get("date", "")
        url    = v.get("url", f"https://www.youtube.com/watch?v={vid}")
        topics = v.get("topics", [])

        print(f"- {vid}:")
        lines = read_local_transcript(vid)
        if not lines:
            lines = fetch_youtube_transcript(vid)
        chunks = chunk_lines(lines)
        print(f"  chunks: {len(chunks)}")

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
