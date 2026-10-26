"""Cut a pack-opening clip into a vertical Short with speed ramps, text and original music (no watermarks).

    python tools/pack_edit.py spec.json source.mp4 endcard.mp4 out.mp4

spec.json: {"segments": [[start, end, speed, zoom], ...], "texts": [{"at": out_sec, "until": out_sec|null, "lines": [[text, size, color]...], "y": 0.12}],
            "seed": 7}
Original audio is dropped (sped-up wrapper noise); a generated track from tools/music.py plays under it all, softer on the end card.
"""
import json
import os
import subprocess
import sys

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import music  # noqa: E402

FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1080, 1920


def font(size):
    for p in ("/tmp/fonts/BarlowCondensed-ExtraBold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def text_png(lines, y, path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    yy = int(H * y)
    for txt, size, color in lines:
        f = font(size)
        w = d.textlength(txt, font=f)
        d.text(((W - w) / 2, yy), txt, font=f, fill=color, stroke_width=max(3, size // 14), stroke_fill=(0, 0, 0, 230))
        yy += int(size * 1.08)
    im.save(path)


def run(args):
    r = subprocess.run([FF, "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-1500:])


def main(spec_path, src, endcard, out):
    spec = json.load(open(spec_path))
    tmp = "/tmp/pe"
    os.makedirs(tmp, exist_ok=True)
    parts, t_out = [], 0.0
    for i, (a, b, sp, zoom) in enumerate(spec["segments"]):
        p = f"{tmp}/s{i}.mp4"
        z = f",crop=iw/{zoom}:ih/{zoom},scale={W}:{H}" if zoom and zoom != 1 else ""
        run(["-ss", str(a), "-to", str(b), "-i", src, "-an",
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}{z},setpts=PTS/{sp},fps=30",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", p])
        parts.append(p)
        t_out += (b - a) / sp
    e = f"{tmp}/end.mp4"
    run(["-i", endcard, "-an", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", e])
    parts.append(e)
    open(f"{tmp}/list.txt", "w").write("".join(f"file '{p}'\n" for p in parts))
    body = f"{tmp}/body.mp4"
    run(["-f", "concat", "-safe", "0", "-i", f"{tmp}/list.txt", "-c", "copy", body])
    total = t_out + 3.5
    # text overlays
    inputs, chain, last = ["-i", body], "", "0:v"
    for k, t in enumerate(spec.get("texts", [])):
        png = f"{tmp}/t{k}.png"
        text_png(t["lines"], t.get("y", 0.1), png)
        inputs += ["-i", png]
        until = t.get("until") or t_out
        chain += f"[{last}][{k + 1}:v]overlay=0:0:enable='between(t,{t['at']},{until})'[v{k}];"
        last = f"v{k}"
    wav = f"{tmp}/m.wav"
    music.write(wav, total + 0.5, str(spec.get("seed", "pack")))
    inputs += ["-i", wav]
    ai = len(spec.get("texts", [])) + 1
    afilter = f"[{ai}:a]volume='if(lt(t,{t_out}),1,0.4)':eval=frame,afade=t=out:st={total - 1.2}:d=1.2,atrim=0:{total}[a]"
    run([*inputs, "-filter_complex", chain + afilter, "-map", f"[{last}]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", "-t", str(total), out])
    print(f"pack_edit: {total:.1f}s -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
