# Clipping

Turns a long stream/video into vertical (9:16) viral clips with word-by-word burned-in captions.
Claude is the "AI" that picks the moments; `clipper.py` does download, transcription and rendering.
Requires `ffmpeg` and `pip install -r requirements.txt`.

## When the user gives a link (or a video file) and asks for clips

1. **Fetch + transcribe**
   ```bash
   python clipper.py fetch "<url-or-path>"            # add --section 1:00:00-2:30:00 to grab only part
   ```
   Creates `work/<id>/` with `source.mp4`, `words.json` (word timestamps) and `transcript.txt`.
   Transcription runs on CPU at ~6x realtime (3h stream ≈ 30 min) — run it in the background for long streams.
   `--model base` is faster, `--model medium` more accurate.

2. **Pick the clips (your job).** Read all of `work/<id>/transcript.txt` and choose the best moments
   (default 10 unless the user says otherwise). What makes a good clip:
   - Opens on a hook in the first 1–2 seconds (bold claim, question, conflict, punchline setup) — never on filler.
   - One complete idea/story with a payoff; ends right after the punchline/reaction.
   - 20–60s typical (max ~90s). Clips must not overlap.
   - Strong emotion, hot takes, funny moments, surprising facts, rage/hype, quotable lines.
   Write `work/<id>/clips.json`:
   ```json
   [
     {"title": "short_slug", "start": "12:04", "end": "12:51", "hook": "He did WHAT?!"},
     {"title": "rage_quit", "start": "1:02:10", "end": "1:02:45", "hook": "Chat was not ready", "crop": "blur"}
   ]
   ```
   - `start`/`end`: `mm:ss`, `h:mm:ss` or seconds. Edges get snapped to the nearest spoken words.
   - `hook`: short punchy title shown for the first 3.5s (keep it < ~30 chars).
   - optional `crop`: `auto` (default: face-tracked, falls back to `blur`), `face`, `center`, `left`, `right`,
     `blur` (whole frame over blurred background — best for gameplay/screens), or `"x": 0.0–1.0` for a manual crop center.
     For streams with a facecam corner + gameplay, look at a frame first and pick accordingly.

3. **Render**
   ```bash
   python clipper.py render <id>             # all clips
   python clipper.py render <id> --only 3 7  # re-render specific ones
   ```
   Output: `work/<id>/clips/NN_title.mp4` (1080x1920, loudness-normalised). Spot-check a few frames
   (`ffmpeg -ss 5 -i clip.mp4 -frames:v 1 frame.png`), then send the clips to the user with SendUserFile
   along with a list of titles, timestamps and suggested captions/hashtags.

## Notes
- YouTube often blocks cloud IPs ("Sign in to confirm you're not a bot"). Don't try to evade it; ask the user
  for another source (Twitch/Kick VOD link, or upload the video file / a direct download link).
- `work/` is git-ignored — clips are deliverables, not source.
- Caption font: `assets/fonts/InterDisplay-Black.otf` (SIL OFL).
