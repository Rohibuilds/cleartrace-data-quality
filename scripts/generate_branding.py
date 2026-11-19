"""ClearTrace — Branding & Icon Generation Suite.

Generates the new official ClearTrace geometric identity assets:
1. cleartrace-logo.svg (Primary horizontal logo, light background)
2. cleartrace-logo-dark.svg (Primary horizontal logo, dark background)
3. cleartrace-symbol.svg (Compact symbol-only SVG, light background)
4. cleartrace-symbol-dark.svg (Compact symbol-only SVG, dark background)
5. favicon-32.png (32x32 pixel-perfect browser favicon)
6. apple-touch-icon.png (180x180 iOS home screen touch icon)
7. icon-192.png (192x192 standard PWA launcher icon)
8. icon-512.png (512x512 high-resolution PWA store icon)
9. icon-maskable-192.png (192x192 Android adaptive maskable icon with 20% safe zone)
10. icon-maskable-512.png (512x512 Android adaptive maskable icon with 20% safe zone)
"""

from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw

STATIC_DIR = Path("static")
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# ── 1. Generate SVG Logos ────────────────────────────────────────────────────

SYMBOL_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
  <defs>
    <linearGradient id="ctBgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0B1528" />
      <stop offset="100%" stop-color="#15294A" />
    </linearGradient>
    <linearGradient id="ctTraceGrad" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#0D9488" />
      <stop offset="45%" stop-color="#24A99A" />
      <stop offset="85%" stop-color="#38BDF8" />
      <stop offset="100%" stop-color="#F59E0B" />
    </linearGradient>
    <linearGradient id="ctSubtleGrid" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#24A99A" stop-opacity="0.15" />
      <stop offset="100%" stop-color="#38BDF8" stop-opacity="0.05" />
    </linearGradient>
    <filter id="ctGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.2" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>

  <!-- Precision Squircle Frame -->
  <rect x="1" y="1" width="46" height="46" rx="12" fill="url(#ctBgGrad)" stroke="#1E3A5F" stroke-width="1.2" />

  <!-- Background Precision Lattice -->
  <path d="M12 12 H36 M12 24 H36 M12 36 H36 M12 12 V36 M24 12 V36 M36 12 V36" stroke="url(#ctSubtleGrid)" stroke-width="0.8" stroke-dasharray="1 3" />

  <!-- Verification Checkpoint Trace Path -->
  <!-- Weaves from data intake (12, 28) down to verification node (21, 35) up to verified check apex (36, 13) -->
  <path d="M12 27.5 L20.5 35 L36.5 13.5" fill="none" stroke="url(#ctTraceGrad)" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round" filter="url(#ctGlow)" />

  <!-- Auxiliary Telemetry Line -->
  <path d="M12 16.5 L22 16.5 L28 22.5" fill="none" stroke="#24A99A" stroke-width="1.8" stroke-linecap="round" stroke-dasharray="2 3" opacity="0.65" />

  <!-- Data Nodes -->
  <!-- Input Node -->
  <circle cx="12" cy="27.5" r="2.4" fill="#0B1528" stroke="#24A99A" stroke-width="1.8" />
  <!-- Checkpoint Pivot Node -->
  <circle cx="20.5" cy="35" r="2.8" fill="#24A99A" stroke="#FFFFFF" stroke-width="1.2" />
  <!-- Upper Auxiliary Node -->
  <circle cx="12" cy="16.5" r="1.6" fill="#38BDF8" />
  <circle cx="28" cy="22.5" r="1.8" fill="#38BDF8" />
  <!-- Verification Apex Node (Gold Star of Trust) -->
  <circle cx="36.5" cy="13.5" r="3.2" fill="#F59E0B" stroke="#FFFFFF" stroke-width="1.4" />
  <circle cx="36.5" cy="13.5" r="1.2" fill="#FFFFFF" />
</svg>"""

LOGO_HORIZONTAL_LIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 48" fill="none">
  <!-- Symbol Embedded -->
  <g transform="translate(0, 0)">
    <defs>
      <linearGradient id="ctBgL" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#0B1528" />
        <stop offset="100%" stop-color="#15294A" />
      </linearGradient>
      <linearGradient id="ctTraceL" x1="0%" y1="100%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#0D9488" />
        <stop offset="45%" stop-color="#24A99A" />
        <stop offset="85%" stop-color="#38BDF8" />
        <stop offset="100%" stop-color="#F59E0B" />
      </linearGradient>
    </defs>
    <rect x="2" y="2" width="44" height="44" rx="11" fill="url(#ctBgL)" stroke="#1E3A5F" stroke-width="1" />
    <path d="M12 27.5 L20.5 35 L36.5 13.5" fill="none" stroke="url(#ctTraceL)" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />
    <circle cx="12" cy="27.5" r="2.2" fill="#0B1528" stroke="#24A99A" stroke-width="1.6" />
    <circle cx="20.5" cy="35" r="2.5" fill="#24A99A" stroke="#FFFFFF" stroke-width="1" />
    <circle cx="36.5" cy="13.5" r="3" fill="#F59E0B" stroke="#FFFFFF" stroke-width="1.2" />
  </g>

  <!-- Typography: Clear (Navy) + Trace (Teal) -->
  <g transform="translate(58, 28)">
    <text font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif" font-size="22" font-weight="800" letter-spacing="-0.03em" fill="#0F1D35">Clear<tspan fill="#0D9488" font-weight="800">Trace</tspan></text>
  </g>
  <g transform="translate(59, 41)">
    <text font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif" font-size="8.5" font-weight="700" letter-spacing="0.14em" fill="#57759B">DATA INTELLIGENCE</text>
  </g>
  <!-- Verification Badge -->
  <g transform="translate(202, 18)">
    <circle cx="6" cy="6" r="5" fill="#EEFAF8" stroke="#24A99A" stroke-width="1" />
    <path d="M3.5 6 L5.2 7.8 L8.5 4.2" fill="none" stroke="#0D9488" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
  </g>
</svg>"""

LOGO_HORIZONTAL_DARK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 48" fill="none">
  <!-- Symbol Embedded -->
  <g transform="translate(0, 0)">
    <defs>
      <linearGradient id="ctBgD" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#0F1D35" />
        <stop offset="100%" stop-color="#1E3A5F" />
      </linearGradient>
      <linearGradient id="ctTraceD" x1="0%" y1="100%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#14B8A6" />
        <stop offset="45%" stop-color="#2DD4BF" />
        <stop offset="85%" stop-color="#38BDF8" />
        <stop offset="100%" stop-color="#F59E0B" />
      </linearGradient>
    </defs>
    <rect x="2" y="2" width="44" height="44" rx="11" fill="url(#ctBgD)" stroke="#2B4C74" stroke-width="1" />
    <path d="M12 27.5 L20.5 35 L36.5 13.5" fill="none" stroke="url(#ctTraceD)" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />
    <circle cx="12" cy="27.5" r="2.2" fill="#0F1D35" stroke="#2DD4BF" stroke-width="1.6" />
    <circle cx="20.5" cy="35" r="2.5" fill="#2DD4BF" stroke="#FFFFFF" stroke-width="1" />
    <circle cx="36.5" cy="13.5" r="3" fill="#F59E0B" stroke="#FFFFFF" stroke-width="1.2" />
  </g>

  <!-- Typography: Clear (White) + Trace (Teal) -->
  <g transform="translate(58, 28)">
    <text font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif" font-size="22" font-weight="800" letter-spacing="-0.03em" fill="#FFFFFF">Clear<tspan fill="#2DD4BF" font-weight="800">Trace</tspan></text>
  </g>
  <g transform="translate(59, 41)">
    <text font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif" font-size="8.5" font-weight="700" letter-spacing="0.14em" fill="#8BA2BF">DATA INTELLIGENCE</text>
  </g>
  <!-- Verification Badge -->
  <g transform="translate(202, 18)">
    <circle cx="6" cy="6" r="5" fill="#133838" stroke="#2DD4BF" stroke-width="1" />
    <path d="M3.5 6 L5.2 7.8 L8.5 4.2" fill="none" stroke="#2DD4BF" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
  </g>
</svg>"""

(STATIC_DIR / "cleartrace-symbol.svg").write_text(SYMBOL_SVG, encoding="utf-8")
(STATIC_DIR / "cleartrace-symbol-dark.svg").write_text(SYMBOL_SVG, encoding="utf-8")
(STATIC_DIR / "cleartrace-logo.svg").write_text(LOGO_HORIZONTAL_LIGHT, encoding="utf-8")
(STATIC_DIR / "cleartrace-logo-dark.svg").write_text(LOGO_HORIZONTAL_DARK, encoding="utf-8")
print("Saved SVG logo files successfully.")


# ── 2. Pixel-Perfect Bitmap Icon Renderer (Pillow) ───────────────────────────

def draw_cleartrace_icon(
    size: int,
    padding_ratio: float = 0.08,
    is_maskable: bool = False,
    bg_color: tuple[int, int, int] = (11, 21, 40),
) -> Image.Image:
    """Renders the official ClearTrace geometric identity at arbitrary dimensions.
    
    Supports:
    - Standard launcher icons (padding_ratio=0.08)
    - Android Adaptive Maskable icons (padding_ratio=0.20 per Google specification)
    - High-density anti-aliased super-sampling (4x supersampling)
    """
    scale = 4
    canvas_size = size * scale
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = int(canvas_size * padding_ratio)
    box = (pad, pad, canvas_size - pad, canvas_size - pad)
    width = box[2] - box[0]
    height = box[3] - box[1]

    if is_maskable:
        # Maskable icons fill entire 100% canvas with deep navy background
        draw.rectangle([0, 0, canvas_size, canvas_size], fill=(11, 21, 40, 255))
        # Subtle ambient radial glow in center
        glow_box = (
            int(canvas_size * 0.2), int(canvas_size * 0.2),
            int(canvas_size * 0.8), int(canvas_size * 0.8)
        )
        draw.ellipse(glow_box, fill=(21, 41, 74, 255))
    else:
        # Squircle background container
        rx = int(width * 0.25)
        draw.rounded_rectangle(box, radius=rx, fill=bg_color, outline=(30, 58, 95), width=int(2 * scale))

    # Grid lattice within content box
    grid_color = (36, 169, 154, 40)
    for step in (0.25, 0.5, 0.75):
        gx = box[0] + int(width * step)
        gy = box[1] + int(height * step)
        draw.line([(gx, box[1] + int(height * 0.15)), (gx, box[3] - int(height * 0.15))], fill=grid_color, width=max(1, int(1 * scale)))
        draw.line([(box[0] + int(width * 0.15), gy), (box[2] - int(width * 0.15), gy)], fill=grid_color, width=max(1, int(1 * scale)))

    # Compute key geometric coordinates (based on 48-unit design)
    # Intake: (12/48, 27.5/48)
    # Checkpoint: (20.5/48, 35/48)
    # Apex: (36.5/48, 13.5/48)
    def map_pt(rx_val: float, ry_val: float) -> tuple[int, int]:
        return (
            box[0] + int(width * (rx_val / 48.0)),
            box[1] + int(height * (ry_val / 48.0)),
        )

    p_in = map_pt(12.0, 27.5)
    p_chk = map_pt(20.5, 35.0)
    p_apex = map_pt(36.5, 13.5)
    p_aux1 = map_pt(12.0, 16.5)
    p_aux2 = map_pt(22.0, 16.5)
    p_aux3 = map_pt(28.0, 22.5)

    # Auxiliary dashed telemetry line
    draw.line([p_aux1, p_aux2, p_aux3], fill=(36, 169, 154, 160), width=max(1, int(2 * scale)))

    # Primary verification check trace line
    stroke_w = max(2, int(4 * scale))
    # Draw segment 1 (Teal)
    draw.line([p_in, p_chk], fill=(20, 184, 166, 255), width=stroke_w)
    # Draw segment 2 (Teal to Gold apex)
    draw.line([p_chk, p_apex], fill=(56, 189, 248, 255), width=stroke_w)

    # Data node circles
    r_node = int(3 * scale)
    r_chk = int(3.5 * scale)
    r_apex = int(4.5 * scale)

    # Input node (Navy center, teal ring)
    draw.ellipse([p_in[0] - r_node, p_in[1] - r_node, p_in[0] + r_node, p_in[1] + r_node], fill=(11, 21, 40), outline=(36, 169, 154), width=int(1.8 * scale))
    # Auxiliary nodes
    r_sm = int(2 * scale)
    draw.ellipse([p_aux1[0] - r_sm, p_aux1[1] - r_sm, p_aux1[0] + r_sm, p_aux1[1] + r_sm], fill=(56, 189, 248))
    draw.ellipse([p_aux3[0] - r_sm, p_aux3[1] - r_sm, p_aux3[0] + r_sm, p_aux3[1] + r_sm], fill=(56, 189, 248))

    # Checkpoint node (Solid teal with white core)
    draw.ellipse([p_chk[0] - r_chk, p_chk[1] - r_chk, p_chk[0] + r_chk, p_chk[1] + r_chk], fill=(36, 169, 154), outline=(255, 255, 255), width=int(1.2 * scale))

    # Apex verification node (Warm Gold with white center beacon)
    draw.ellipse([p_apex[0] - r_apex, p_apex[1] - r_apex, p_apex[0] + r_apex, p_apex[1] + r_apex], fill=(245, 158, 11), outline=(255, 255, 255), width=int(1.6 * scale))
    r_center = int(1.8 * scale)
    draw.ellipse([p_apex[0] - r_center, p_apex[1] - r_center, p_apex[0] + r_center, p_apex[1] + r_center], fill=(255, 255, 255))

    # High-quality anti-aliased downsampling (LANCZOS)
    return img.resize((size, size), Image.Resampling.LANCZOS)


# Generate All Target Formats
print("Generating 32x32 Favicon...")
draw_cleartrace_icon(32, padding_ratio=0.06).save(STATIC_DIR / "favicon-32.png", format="PNG")
draw_cleartrace_icon(32, padding_ratio=0.06).save(STATIC_DIR / "favicon.ico", format="ICO")

print("Generating 180x180 Apple Touch Icon...")
draw_cleartrace_icon(180, padding_ratio=0.10).save(STATIC_DIR / "apple-touch-icon.png", format="PNG")

print("Generating 192x192 Standard PWA Icon...")
draw_cleartrace_icon(192, padding_ratio=0.08).save(STATIC_DIR / "icon-192.png", format="PNG")

print("Generating 512x512 High-Res PWA Icon...")
draw_cleartrace_icon(512, padding_ratio=0.08).save(STATIC_DIR / "icon-512.png", format="PNG")

print("Generating 192x192 Maskable Android Icon (Safe Zone = 20%)...")
draw_cleartrace_icon(192, padding_ratio=0.20, is_maskable=True).save(STATIC_DIR / "icon-maskable-192.png", format="PNG")

print("Generating 512x512 Maskable Android Icon (Safe Zone = 20%)...")
draw_cleartrace_icon(512, padding_ratio=0.20, is_maskable=True).save(STATIC_DIR / "icon-maskable-512.png", format="PNG")

print("All ClearTrace brand icons generated successfully.")
