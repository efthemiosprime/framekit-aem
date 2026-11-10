"""Raster crop/resize through the system's image tool (no Python dependencies).
Uses `sips` (macOS) or ImageMagick `magick`, whichever is installed."""
import shutil
import subprocess

from .config import ConfigError


def size(path):
    if shutil.which("sips"):
        out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
                             check=True, capture_output=True, text=True).stdout
        values = [int(line.split()[-1]) for line in out.splitlines() if "pixel" in line]
        return values[0], values[1]
    if shutil.which("magick"):
        out = subprocess.run(["magick", "identify", "-format", "%w %h", str(path)],
                             check=True, capture_output=True, text=True).stdout
        w, h = out.split()
        return int(w), int(h)
    raise ConfigError("Cropping needs `sips` (macOS) or ImageMagick `magick` on PATH")


def crop(src, dst, rect, out_width=None):
    x, y, w, h = rect
    if shutil.which("sips"):
        subprocess.run(["sips", "-c", str(h), str(w), "--cropOffset", str(y), str(x), str(src), "--out", str(dst)],
                       check=True, capture_output=True)
        if out_width and out_width != w:
            subprocess.run(["sips", "--resampleWidth", str(out_width), str(dst)], check=True, capture_output=True)
        return
    if shutil.which("magick"):
        geometry = f"{w}x{h}+{x}+{y}"
        cmd = ["magick", str(src), "-crop", geometry, "+repage"]
        if out_width:
            cmd += ["-resize", f"{out_width}x"]
        subprocess.run(cmd + [str(dst)], check=True, capture_output=True)
        return
    raise ConfigError("Cropping needs `sips` (macOS) or ImageMagick `magick` on PATH")
