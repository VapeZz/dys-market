"""TikTok helpers shared by the social generators.

full_screen(page, slide_paths, out_dir): wraps 1080x1350 slides in a 1080x1920 frame
(brand bar on top, site on the bottom) so they fill a phone screen in TikTok photo mode.
"""
import os

from social import BASE, FONT_CSS

FRAME = """<div class="slide" style="height:1920px;padding:0">
<img src="file://{img}" style="position:absolute;top:170px;left:0;width:1080px;height:1350px;display:block">
<div style="position:absolute;top:1560px;left:0;right:0;text-align:center;font-family:'Barlow Condensed';font-weight:700;font-size:42px;letter-spacing:.06em;text-transform:uppercase;color:#d8d5cf">{foot}</div>
</div>"""
# TikTok covers roughly the top 150px (tabs) and the bottom ~380px (caption, buttons), so the slide sits above that.


def full_screen(page, slide_paths, out_dir, foot="Free card prices · market.driveyourstyle.net"):
    page.set_viewport_size({"width": 1080, "height": 1920})
    base = BASE.replace("height:1350px", "height:1920px")
    tmp = os.path.abspath(os.path.join(out_dir, "_tt.html"))
    outs = []
    for i, src in enumerate(slide_paths, 1):
        open(tmp, "w", encoding="utf-8").write(base % (FONT_CSS, FRAME.format(img=os.path.abspath(src), foot=foot)))
        page.goto("file://" + tmp, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        out = os.path.join(out_dir, f"tt-{i}.jpg")
        page.screenshot(path=out, type="jpeg", quality=90)
        outs.append(out)
    os.remove(tmp)
    page.set_viewport_size({"width": 1080, "height": 1350})
    return outs


def make_short(slide_paths, out_path, per=3.2, fade=0.4, fps=30):
    """Stitch 1080x1920 slides into a vertical MP4 (slow zoom + crossfades) for YouTube Shorts.
    Silent track included so every platform accepts it. Returns out_path, or None if ffmpeg fails."""
    import shutil
    import subprocess
    exe = shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg          # pip wheel with a static ffmpeg (runners don't always ship one)
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            print("make_short: no ffmpeg:", e)
            return None
    if not slide_paths:
        return None
    n = len(slide_paths)
    frames = int((per + fade) * fps)
    args = [exe, "-y", "-loglevel", "error"]
    for p in slide_paths:
        args += ["-i", p]
    args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    f = [f"[{i}:v]scale=2160:3840,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
         f":d={frames}:s=1080x1920:fps={fps},setsar=1,format=yuv420p[v{i}]" for i in range(n)]
    last, t = "v0", per
    for i in range(1, n):
        f.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={t:.2f}[x{i}]")
        last, t = f"x{i}", t + per
    args += ["-filter_complex", ";".join(f), "-map", f"[{last}]", "-map", f"{n}:a", "-shortest",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
             "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out_path]
    try:
        subprocess.run(args, check=True, timeout=600)
        return out_path
    except (subprocess.SubprocessError, OSError) as e:
        print("make_short failed:", e)
        return None
