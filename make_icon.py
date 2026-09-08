"""Generate a generic app icon (.ico) for FeasFlow — no external assets."""
from PIL import Image, ImageDraw, ImageFont
import math

SIZE = 512
# Brand palette (matches feas_theme accent/lime)
ACCENT = (37, 99, 122)      # deep teal
ACCENT_DK = (23, 66, 82)
LIME = (132, 204, 22)       # energy-green
WHITE = (255, 255, 255)


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_base(size=SIZE):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded square background with vertical teal gradient
    radius = int(size * 0.22)
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / size
        r = int(ACCENT[0] * (1 - t) + ACCENT_DK[0] * t)
        g = int(ACCENT[1] * (1 - t) + ACCENT_DK[1] * t)
        b = int(ACCENT[2] * (1 - t) + ACCENT_DK[2] * t)
        gd.line([(0, y), (size, y)], fill=(r, g, b, 255))
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)

    # --- Growth bars (feasibility / finance motif) ---
    bar_w = int(size * 0.11)
    gap = int(size * 0.055)
    base_y = int(size * 0.72)
    left = int(size * 0.24)
    heights = [0.16, 0.26, 0.36, 0.48]
    for i, h in enumerate(heights):
        x0 = left + i * (bar_w + gap)
        y0 = base_y - int(size * h)
        col = LIME if i == len(heights) - 1 else WHITE
        rounded_rect(d, [x0, y0, x0 + bar_w, base_y], radius=int(bar_w * 0.35), fill=col)

    # --- Upward trend arrow ---
    pts = []
    for i, h in enumerate(heights):
        x0 = left + i * (bar_w + gap) + bar_w // 2
        y0 = base_y - int(size * h) - int(size * 0.045)
        pts.append((x0, y0))
    d.line(pts, fill=LIME, width=int(size * 0.028), joint="curve")
    # arrow head at last point
    ax, ay = pts[-1]
    ah = int(size * 0.045)
    d.polygon([(ax + ah, ay - ah), (ax - ah * 0.3, ay - ah * 1.1),
               (ax + ah * 1.1, ay + ah * 0.3)], fill=LIME)

    return img


def main():
    base = make_base(SIZE)
    base.save("icon.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    icons[0].save("icon.ico", format="ICO",
                  sizes=[(s, s) for s in sizes],
                  append_images=icons[1:])
    print("Wrote icon.ico and icon.png")


if __name__ == "__main__":
    main()
