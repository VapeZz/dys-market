"""Original background music for the Shorts, so every post sounds different and is copyright-safe.

    python tools/music.py out.wav 20 [seed]

Each track is synthesized from scratch (no samples): a style (lo-fi, trap, house, synthwave, ...),
key, tempo, chord progression and patterns all come from the seed. make_short() picks the seed from
the post's date + kind, and the style rotates by day so back-to-back posts never share a vibe.
"""
import hashlib
import re
import sys
import wave
from datetime import date

import numpy as np

SR = 44100
STYLES = ["lofi", "trap", "house", "synthwave", "pluck", "funk", "drill", "ambient"]
STYLE_CFG = {   # tempo range, swing, drum pattern kind, chord voice, lead voice, scale
    "lofi":      ((70, 88),   0.18, "boom",  "keys",  "pluck", "minor"),
    "trap":      ((130, 150), 0.0,  "trap",  "pad",   "bell",  "minor"),
    "house":     ((118, 126), 0.0,  "four",  "stab",  "pluck", "minor"),
    "synthwave": ((95, 110),  0.0,  "eight", "saw",   "saw",   "minor"),
    "pluck":     ((96, 112),  0.08, "boom",  "keys",  "bell",  "major"),
    "funk":      ((100, 112), 0.12, "funk",  "stab",  "saw",   "dorian"),
    "drill":     ((138, 146), 0.0,  "drill", "pad",   "bell",  "minor"),
    "ambient":   ((80, 92),   0.0,  "soft",  "pad",   "bell",  "major"),
}
SCALES = {"minor": [0, 2, 3, 5, 7, 8, 10], "major": [0, 2, 4, 5, 7, 9, 11], "dorian": [0, 2, 3, 5, 7, 9, 10]}
PROGS = [[0, 5, 3, 4], [0, 3, 5, 4], [0, 5, 2, 6], [5, 3, 0, 4], [0, 6, 5, 4], [0, 2, 5, 3], [3, 4, 0, 0], [0, 4, 5, 3]]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)                 # one-pole, done as an exponential-decay convolution
    k = a ** np.arange(int(SR * 6 / max(cutoff, 30)) + 1)
    k = k * (1 - a)
    if len(x) * len(k) < 2e7:
        return np.convolve(x, k)[: len(x)]
    m = 1 << int(np.ceil(np.log2(len(x) + len(k))))       # FFT convolution for long buffers
    return np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(k, m), m)[: len(x)]


def env(n, a=0.005, d=0.3, curve=4.0):
    t = np.arange(n) / SR
    e = np.minimum(t / a, 1.0) if a > 0 else np.ones(n)
    return e * np.exp(-curve * t / max(d, 1e-3))


def osc(kind, f, n, rng, detune=0.0):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for dt in ([0.0] if not detune else [-detune, 0.0, detune]):
        ph = 2 * np.pi * f * (1 + dt) * t + rng.uniform(0, 2 * np.pi)
        if kind == "sine":
            out += np.sin(ph)
        elif kind == "tri":
            out += 2 / np.pi * np.arcsin(np.sin(ph))
        elif kind == "saw":
            out += 2 * ((ph / (2 * np.pi)) % 1.0) - 1
        elif kind == "sq":
            out += np.sign(np.sin(ph)) * 0.6
    return out / (1 if not detune else 3)


def add(buf, sig, at):
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


def kick(rng, hard=False):
    n = int(SR * (0.5 if hard else 0.35))
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t * (28 if hard else 40))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (5 if hard else 9))
    return np.tanh(s * (2.2 if hard else 1.6))


def snare(rng, soft=False):
    n = int(SR * 0.22)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - lowpass(noise, 1500)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return (noise * np.exp(-t * (24 if soft else 16)) * 0.55 + body * 0.5) * (0.6 if soft else 1)


def hat(rng, open_=False):
    n = int(SR * (0.18 if open_ else 0.05))
    x = rng.standard_normal(n)
    x = x - lowpass(x, 7000)
    return x * env(n, 0.001, 0.12 if open_ else 0.02) * 0.22


def clap(rng):
    n = int(SR * 0.2)
    x = rng.standard_normal(n)
    x = x - lowpass(x, 1200)
    t = np.arange(n) / SR
    e = sum(np.exp(-((t - o) * 90).clip(0)) * (t >= o) for o in (0, 0.012, 0.024)) * np.exp(-t * 14)
    return x * e * 0.6


def drums(kind, buf, steps, step_t, swing, rng, bars):
    K, Kh, S, Ss, H, Ho, C = kick(rng), kick(rng, True), snare(rng), snare(rng, True), hat(rng), hat(rng, True), clap(rng)
    for s in range(steps):
        b, pos = divmod(s, 16)
        at = s * step_t + (swing * step_t if s % 2 else 0)
        fill = b % 4 == 3
        if kind == "boom":
            if pos in (0, 7, 10) or (fill and pos == 14): add(buf, K * 0.9, at)
            if pos in (4, 12): add(buf, S * 0.7, at)
            if pos % 2 == 0: add(buf, H * (0.8 if pos % 4 == 0 else 0.5), at)
        elif kind == "trap":
            if pos in (0, 6, 10) or (fill and pos == 15): add(buf, Kh * 0.9, at)
            if pos in (8,): add(buf, C, at)
            add(buf, H * (0.6 if pos % 2 == 0 else 0.35), at)
            if fill and pos >= 12: add(buf, H * 0.3, at + step_t / 2)
        elif kind == "drill":
            if pos in (0, 3, 10) or (b % 2 and pos == 13): add(buf, Kh * 0.9, at)
            if pos in (6, 14): add(buf, S * 0.8, at)
            if pos in (0, 3, 6, 8, 10, 12, 15): add(buf, H * 0.5, at)
        elif kind == "four":
            if pos % 4 == 0: add(buf, K, at)
            if pos in (4, 12): add(buf, C * 0.7, at)
            if pos % 4 == 2: add(buf, Ho * 0.7, at)
        elif kind == "eight":
            if pos in (0, 8) or (fill and pos == 14): add(buf, K, at)
            if pos in (4, 12): add(buf, S * 0.8, at)
            if pos % 2 == 0: add(buf, H * 0.5, at)
        elif kind == "funk":
            if pos in (0, 3, 10, 11): add(buf, K * 0.85, at)
            if pos in (4, 12): add(buf, S * 0.8, at)
            if pos in (7, 15): add(buf, Ss * 0.4, at)
            add(buf, H * (0.55 if pos % 2 == 0 else 0.3), at)
        elif kind == "soft":
            if pos == 0 and b % 2 == 0: add(buf, K * 0.6, at)
            if pos in (4, 12) and b >= 2: add(buf, Ss * 0.4, at)
            if pos % 4 == 2 and b >= 1: add(buf, H * 0.3, at)


def voice(kind, freqs, n, rng):
    if kind == "keys":
        s = sum(osc("tri", f, n, rng) + 0.3 * osc("sine", f * 2, n, rng) for f in freqs)
        return lowpass(s, 2200) * env(n, 0.01, 1.2, 1.5)
    if kind == "pad":
        s = sum(osc("saw", f, n, rng, 0.004) for f in freqs)
        e = np.minimum(np.arange(n) / (0.25 * SR), 1) * np.minimum((n - np.arange(n)) / (0.2 * SR), 1)
        return lowpass(s, 1400) * e * 0.8
    if kind == "stab":
        s = sum(osc("saw", f, n, rng, 0.003) for f in freqs)
        return lowpass(s, 2600) * env(n, 0.003, 0.18, 3)
    if kind == "saw":
        s = sum(osc("saw", f, n, rng, 0.006) for f in freqs)
        return lowpass(s, 1800) * env(n, 0.04, 2.0, 1)
    if kind == "bell":
        s = sum(osc("sine", f, n, rng) + 0.4 * osc("sine", f * 3.01, n, rng) * env(n, 0.001, 0.15) for f in freqs)
        return s * env(n, 0.002, 0.9, 3)
    if kind == "pluck":                                    # Karplus-Strong string
        out = np.zeros(n)
        for f in freqs:
            p = max(2, int(SR / f))
            line = rng.uniform(-1, 1, p)
            y = np.zeros(n)
            for i in range(0, n, p):
                seg = line[: min(p, n - i)]
                y[i:i + len(seg)] = seg
                line = 0.5 * (line + np.roll(line, -1)) * 0.996
            out += y
        return out * 0.8
    return np.zeros(n)


def track(seconds, seed):
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    rng = np.random.default_rng(h % (2 ** 32))
    style = seed.split("|")[0] if seed.split("|")[0] in STYLES else STYLES[h % len(STYLES)]
    (lo, hi), swing, dk, cv, lv, sc = STYLE_CFG[style]
    bpm = int(rng.integers(lo, hi + 1))
    scale = SCALES[sc]
    root = 45 + int(rng.integers(0, 12))                   # A2..G#3
    prog = PROGS[int(rng.integers(0, len(PROGS)))]
    step_t = 60 / bpm / 4
    bar_t = step_t * 16
    bars = int(np.ceil(seconds / bar_t)) + 1
    n = int(SR * seconds)
    drum_buf, bass_buf, chord_buf, lead_buf = (np.zeros(n + SR) for _ in range(4))

    def deg(d, octave=0):
        return root + scale[d % 7] + 12 * (d // 7 + octave)

    drums(dk, drum_buf, bars * 16, step_t, swing, rng, bars)
    bass_pat = [[0, 10], [0, 3, 8, 11], [0, 6, 8, 14], [0, 8]][int(rng.integers(0, 4))]
    lead_rhythm = sorted(set(int(x) for x in rng.choice(16, size=int(rng.integers(4, 8)), replace=False)))
    motif = [int(x) for x in rng.integers(0, 5, size=len(lead_rhythm))]
    for b in range(bars):
        d = prog[b % len(prog)]
        chord = [hz(deg(d, 1)), hz(deg(d + 2, 1)), hz(deg(d + 4, 1))] + ([hz(deg(d + 6, 1))] if style in ("lofi", "pluck", "funk") else [])
        bt = b * bar_t
        if cv == "stab":
            for s in (2, 6, 10, 14) if style == "house" else (0, 3, 6, 10):
                add(chord_buf, voice("stab", chord, int(step_t * 2 * SR), rng), bt + s * step_t)
        else:
            add(chord_buf, voice(cv, chord, int(bar_t * SR), rng), bt)
        for s in bass_pat:
            ln = int(step_t * (3 if style in ("trap", "drill") else 2) * SR)
            f = hz(deg(d, -1))
            if style in ("trap", "drill"):                  # 808 with a little glide
                t = np.arange(ln * 2) / SR
                sig = np.sin(2 * np.pi * np.cumsum(f * (1 + 0.5 * np.exp(-t * 25))) / SR) * np.exp(-t * 2.2)
                sig = np.tanh(sig * 1.8)
            else:
                sig = lowpass(osc("saw" if style in ("house", "synthwave", "funk") else "tri", f, ln, rng), 500) * env(ln, 0.005, 0.5, 2)
            add(bass_buf, sig, bt + s * step_t)
        if b >= 1:                                          # lead enters on bar 2
            for i, s in enumerate(lead_rhythm):
                m = deg(d + motif[i] + (2 if b % 2 else 0), 2)
                add(lead_buf, voice(lv, [hz(m)], int(step_t * 3 * SR), rng), bt + s * step_t + (swing * step_t if s % 2 else 0))
    if style == "lofi":
        chord_buf = lowpass(chord_buf, 1600)
        crackle = (rng.random(len(chord_buf)) > 0.9993) * rng.uniform(-0.6, 0.6, len(chord_buf))
        chord_buf += crackle * 0.3
    mix = (0.9 * drum_buf + 0.75 * bass_buf + 0.32 * chord_buf + 0.22 * lead_buf)[:n]
    echo = np.zeros_like(mix)                               # light stereo-ish echo on the lead
    dly = int(step_t * 3 * SR)
    echo[dly:] = (0.22 * lead_buf[:n])[:-dly] * 0.35
    mix = mix + echo
    mix = 0.6 * lowpass(mix, 7000) + 0.4 * lowpass(mix, 12000)   # tame harsh highs
    mix = np.tanh(mix / (np.percentile(np.abs(mix), 99.5) + 1e-9) * 0.9)
    fi, fo = int(0.4 * SR), int(1.2 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    return (mix * 0.85).astype(np.float32), style, bpm


def write(path, seconds, seed):
    x, style, bpm = track(seconds, seed)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return style, bpm


def seed_for(out_path):
    """Style rotates by day (different posts on the same day get different styles); the rest varies by post."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", out_path)
    day = date.fromisoformat(m.group(1)).toordinal() if m else date.today().toordinal()
    kind = int(hashlib.md5(re.sub(r"\d{4}-\d{2}-\d{2}", "", out_path).encode()).hexdigest(), 16)
    style = STYLES[(day * 3 + kind) % len(STYLES)]
    return f"{style}|{out_path}|{day}"


if __name__ == "__main__":
    print(write(sys.argv[1], float(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "x"))
