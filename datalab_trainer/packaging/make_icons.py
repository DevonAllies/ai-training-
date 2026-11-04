"""Draw the DataLab icon (three white bars on a blue rounded square) as PNG and ICO.

    python packaging/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def draw(size: int) -> Image.Image:
    s = size / 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=round(7 * s), fill=(47, 111, 223, 255))
    for x, y, h in [(7, 17, 8), (14, 11, 14), (21, 7, 18)]:
        d.rectangle([round(x * s), round(y * s), round((x + 4) * s) - 1, round((y + h) * s) - 1], fill="white")
    return img


if __name__ == "__main__":
    big = draw(512)
    big.save(HERE / "datalab.png")
    big.save(HERE / "datalab.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote datalab.png and datalab.ico")
