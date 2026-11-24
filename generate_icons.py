"""Regenerate the PWA icons (192x192 and 512x512 PNG) with Pillow.

Why this file exists: the GitHub snapshot-upload API only accepts UTF-8
text files, so the binary icon PNGs cannot be pushed that way. Instead the
icons are generated from code — at app startup (see app.py) and at Render
build time (see render.yaml) — so the deployed PWA always has its icons,
even though no PNG is stored in the repository.
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ICON_DIR = os.path.join(BASE_DIR, "static", "icons")
TEAL = (15, 118, 110)      # #0F766E, matches the app theme
WHITE = (255, 255, 255)


def _font(size):
    try:
        from PIL import ImageFont
        for path in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ):
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def generate_icons():
    from PIL import Image, ImageDraw

    os.makedirs(ICON_DIR, exist_ok=True)
    for size in (192, 512):
        path = os.path.join(ICON_DIR, f"icon-{size}.png")
        if os.path.exists(path):
            continue
        img = Image.new("RGB", (size, size), TEAL)
        draw = ImageDraw.Draw(img)
        # Rounded-corner effect: a slightly lighter inner square.
        pad = size // 12
        draw.rounded_rectangle(
            [pad, pad, size - pad, size - pad],
            radius=size // 8, fill=(17, 141, 131),
        )
        font = _font(size // 3)
        text = "AT"
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]),
                  text, font=font, fill=WHITE)
        img.save(path, "PNG")
        print(f"Generated {path}")


if __name__ == "__main__":
    generate_icons()
