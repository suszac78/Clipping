#!/usr/bin/env python3
"""Stream -> viral vertical clips with burned-in captions.

Workflow (see CLAUDE.md):
  1. python clipper.py fetch <url>        download + transcribe -> work/<id>/
  2. Claude reads work/<id>/transcript.txt and writes work/<id>/clips.json
  3. python clipper.py render <id>        cut, reframe 9:16, caption -> work/<id>/clips/
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
FONTS = ROOT / "assets" / "fonts"
FONT_NAME = "Inter Display Black"
W, H = 1080, 1920


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd)[:300], file=sys.stderr)
    return subprocess.run(cmd, check=True, **kw)


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    return s["width"], s["height"], float(j["format"]["duration"])


def ts(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_time(v):
    if isinstance(v, (int, float)):
        return float(v)
    parts = [float(p) for p in str(v).split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


# ---------------------------------------------------------------- fetch

def slug(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")[:60] or "video"


def fetch(args):
    src = args.url
    if Path(src).exists():
        vid = args.name or slug(Path(src).stem)
        d = WORK / vid
        d.mkdir(parents=True, exist_ok=True)
        video = d / "source.mp4"
        if not video.exists():
            run(["ffmpeg", "-y", "-i", src, "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "20", "-c:a", "aac", str(video)])
        meta = {"title": Path(src).stem, "url": str(src)}
    else:
        info = json.loads(subprocess.run(
            ["yt-dlp", "--js-runtimes", "node", "-J", "--no-playlist", src],
            check=True, capture_output=True, text=True).stdout)
        vid = args.name or slug(f"{info.get('extractor_key', 'vid')}_{info['id']}")
        d = WORK / vid
        d.mkdir(parents=True, exist_ok=True)
        meta = {"title": info.get("title"), "url": src, "uploader": info.get("uploader"),
                "duration": info.get("duration")}
        video = d / "source.mp4"
        if not video.exists():
            cmd = ["yt-dlp", "--js-runtimes", "node", "--no-playlist",
                   "-f", "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
                   "--merge-output-format", "mp4", "-o", str(video)]
            if args.section:
                cmd += ["--download-sections", f"*{args.section}", "--force-keyframes-at-cuts"]
            run(cmd + [src])
    (d / "meta.json").write_text(json.dumps(meta, indent=2))

    words_path = d / "words.json"
    if not words_path.exists():
        import numpy as np
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1",
                              "-ar", "16000", "-f", "f32le", "-"], check=True,
                             capture_output=True).stdout
        audio = np.frombuffer(raw, dtype=np.float32)
        from faster_whisper import WhisperModel
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio, word_timestamps=True,
                                          vad_filter=True, language=args.lang)
        print(f"language={info.language} duration={info.duration:.0f}s", file=sys.stderr)
        segs = []
        for seg in segments:
            segs.append({"start": seg.start, "end": seg.end, "text": seg.text.strip(),
                         "words": [{"w": w.word.strip(), "s": w.start, "e": w.end}
                                   for w in (seg.words or []) if w.word.strip()]})
            print(f"\r  transcribed {ts(seg.end)} / {ts(info.duration)}", end="",
                  file=sys.stderr, flush=True)
        print(file=sys.stderr)
        words_path.write_text(json.dumps(segs))

    segs = json.loads(words_path.read_text())
    with open(d / "transcript.txt", "w") as f:
        f.write(f"# {meta.get('title')}\n")
        for s in segs:
            f.write(f"[{ts(s['start'])}-{ts(s['end'])}] {s['text']}\n")
    print(f"\nOK -> {d}\n  transcript: {d / 'transcript.txt'} ({len(segs)} segments)")
    print(f"  next: write {d / 'clips.json'} then run: python clipper.py render {vid}")


# ---------------------------------------------------------------- render

def face_center_x(video, start, end, vw, vh):
    """Median horizontal face position (0..1) across sampled frames, or None."""
    try:
        import cv2
    except ImportError:
        return None
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video))
    xs = []
    n = 12
    for i in range(n):
        t = start + (end - start) * (i + 0.5) / n
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scale = 1280 / g.shape[1]
        g = cv2.resize(g, None, fx=scale, fy=scale)
        faces = casc.detectMultiScale(g, 1.1, 6, minSize=(28, 28))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + w / 2) / g.shape[1])
    cap.release()
    if len(xs) < n // 3:
        return None
    xs.sort()
    return xs[len(xs) // 2]


def ass_time(t):
    t = max(t, 0)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words, start, end, title, out, words_per_line=3, y_pos=1350):
    """Word-by-word captions: groups of N words, the spoken word highlighted."""
    ws = []
    for w in words:
        if not (w["e"] > start and w["s"] < end):
            continue
        # whisper splits some words ("old" "-fashioned", "don" "'t"): glue them back
        if ws and (w["w"][0] in "-'’" or not any(ch.isalnum() for ch in w["w"])):
            ws[-1] = {**ws[-1], "w": ws[-1]["w"] + w["w"], "e": w["e"]}
        else:
            ws.append(dict(w))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT_NAME},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1
Style: Title,{FONT_NAME},64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,18,0,8,70,70,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if title:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(3.5, end - start))},Title,,0,0,0,,"
                     f"{{\\3c&H000000&\\fad(150,250)}}{ass_escape(title.upper())}")
    groups = [ws[i:i + words_per_line] for i in range(0, len(ws), words_per_line)]
    for gi, g in enumerate(groups):
        nxt = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else g[-1]["e"] + 0.4
        for wi, w in enumerate(g):
            ws_ = w["s"] - start
            we_ = (g[wi + 1]["s"] if wi + 1 < len(g) else min(nxt, g[-1]["e"] + 0.6)) - start
            if we_ <= ws_:
                continue
            parts = []
            for wj, other in enumerate(g):
                txt = ass_escape(other["w"].upper())
                if wj == wi:
                    parts.append(f"{{\\c&H00E6FF&\\fscx112\\fscy112}}{txt}{{\\c&HFFFFFF&\\fscx100\\fscy100}}")
                else:
                    parts.append(txt)
            pop = "{\\t(0,80,\\fscx108\\fscy108)\\t(80,160,\\fscx100\\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{ass_time(ws_)},{ass_time(we_)},Cap,,0,0,0,,"
                         f"{{\\pos({W // 2},{y_pos})}}{pop}{' '.join(parts)}")
    Path(out).write_text(header + "\n".join(lines) + "\n")


def render(args):
    d = WORK / args.id
    video = d / "source.mp4"
    clips = json.loads((d / "clips.json").read_text())
    if isinstance(clips, dict):
        clips = clips["clips"]
    words = [w for s in json.loads((d / "words.json").read_text()) for w in s["words"]]
    vw, vh, _ = probe(video)
    outdir = d / "clips"
    outdir.mkdir(exist_ok=True)
    only = set(args.only or [])

    for i, c in enumerate(clips, 1):
        if only and i not in only:
            continue
        start, end = parse_time(c["start"]), parse_time(c["end"])
        # snap to speech: begin just before the first word, end just after the last
        inside = [w for w in words if w["s"] >= start - 0.3 and w["e"] <= end + 0.5]
        if inside:
            start = max(inside[0]["s"] - 0.15, 0)
            end = inside[-1]["e"] + 0.45
        name = f"{i:02d}_{slug(c.get('title', 'clip'))}"
        ass = outdir / f"{name}.ass"
        build_ass(words, start, end, c.get("hook") if not args.no_title else None, ass)

        mode = c.get("crop", args.crop)
        cx = c.get("x")
        if mode == "auto" and cx is None:
            cx = face_center_x(video, start, end, vw, vh)
            mode = "face" if cx is not None else "blur"
        if mode in ("face", "center", "left", "right") or cx is not None:
            if cx is None:
                cx = {"center": 0.5, "left": 0.25, "right": 0.75}.get(mode, 0.5)
            cw = int(vh * 9 / 16) // 2 * 2
            x = int(min(max(cx * vw - cw / 2, 0), vw - cw))
            vf = f"crop={cw}:{vh}:{x}:0,scale={W}:{H}"
        else:  # blur: full frame centered over a blurred, zoomed copy
            vf = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},boxblur=30:5,eq=brightness=-0.08[bg];"
                  f"[b]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2")
        vf += f",ass={ass.name}:fontsdir={FONTS}"
        out = outdir / f"{name}.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
             "-i", str(video), "-filter_complex", vf, "-c:v", "libx264", "-preset", "medium",
             "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-movflags", "+faststart", str(out)],
            cwd=outdir)
        print(f"[{i}/{len(clips)}] {out.name}  ({end - start:.0f}s, crop={mode})")
    print(f"done -> {outdir}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download + transcribe a URL or local file")
    f.add_argument("url")
    f.add_argument("--name", help="work folder name")
    f.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium")
    f.add_argument("--lang", default=None, help="force language, e.g. en")
    f.add_argument("--section", help="only download part, e.g. 1:00:00-2:30:00")
    f.set_defaults(fn=fetch)
    r = sub.add_parser("render", help="render clips.json into captioned 9:16 clips")
    r.add_argument("id")
    r.add_argument("--crop", default="auto", choices=["auto", "face", "center", "left", "right", "blur"])
    r.add_argument("--only", type=int, nargs="*", help="render only these clip numbers")
    r.add_argument("--no-title", action="store_true", help="skip the hook title overlay")
    r.set_defaults(fn=render)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
