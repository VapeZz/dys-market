"""Preview of the voice-over videos (test branch only). Publishes nothing.

    python tools/voice_preview.py <gh-pages checkout> <out>

Re-renders today's two Cards of the Day posts (the cards already in the live feeds) with the new video:
the Pokémon post in two voices, the other-TCG post in one. Writes each video, its frames, the voice track,
today's live video for comparison, and report.json: what was said on each frame, how the names were sounded
out, and what a speech-to-text model heard back (a check that the words come out right).
"""
import json
import os
import shutil
import sys

os.environ["DYS_KEEP_VOICE"] = "1"

import daily_card as dc
import voice as v

JOBS = [("social-daily", "af_heart"), ("social-daily-other", "af_heart")]   # the voice Keo picked
_ear = None


def heard(wav):
    """What a speech-to-text model makes of the voice track."""
    global _ear
    try:
        from faster_whisper import WhisperModel
        import wave
        import numpy as np
        _ear = _ear or WhisperModel("base.en", compute_type="int8")
        with wave.open(wav) as w:   # handed over as samples at 16 kHz, so no audio decoder is needed
            x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
            rate = w.getframerate()
        x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 16000 / rate)), np.arange(len(x)), x).astype(np.float32)
        segs, _ = _ear.transcribe(x, beam_size=5)
        return " ".join(s.text.strip() for s in segs)
    except Exception as e:
        return f"(no transcript: {e!r})"[:300]


def main(pages, out):
    report = []
    for feed, who in JOBS:
        post = json.load(open(os.path.join(pages, feed, "latest.json")))
        cards, theme, game = post["cards"], post["theme"], post["game"]
        period = "this week" if "this week" in post["caption"] else "lately"
        name = f"{game}-{who.split('_')[1]}"
        d = os.path.join(out, name, post["date"])
        os.makedirs(d, exist_ok=True)
        v.VOICE = who
        n, video, info = dc.render(os.path.join(pages, "data"), cards, theme, period, game, d)
        row = {"name": name, "feed": feed, "date": post["date"], "game": game, "theme": theme, "slides": n,
               "video": bool(video), "voice": info.get("voice"), "seconds": info.get("seconds"),
               "said": info.get("said"), "sounds": [v.sounds(ln) for _, ln in info.get("said") or []]}
        wav = os.path.join(d, "short-voice.wav")
        if os.path.exists(wav):
            row["heard"] = heard(wav)
        if video:
            shutil.copy(video, os.path.join(out, f"{name}.mp4"))
        live = os.path.join(pages, feed, post["date"], "short.mp4")
        if os.path.exists(live):
            shutil.copy(live, os.path.join(out, f"{game}-now.mp4"))
        report.append(row)
        print(f"{name}: voice {info.get('voice')}, {info.get('seconds')} s")
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1, ensure_ascii=False)
    ok = sum(1 for r in report if r["voice"])
    print(f"voice preview: {ok} of {len(report)} videos have the voice-over; " + ", ".join(f"{r['name']} {r['seconds']} s" for r in report))
    if ok < len(report):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
