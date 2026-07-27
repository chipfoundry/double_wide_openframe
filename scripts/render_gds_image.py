"""Render a full-chip GDS screenshot for the datasheet.

Run headless:
  klayout -z -nc -r scripts/render_gds_image.py
"""

import os
import pya

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDS = os.path.join(ROOT, "gds", "double_wide_chip_io.gds")
OUT = os.path.join(ROOT, "docs", "figures", "chip_gds.png")

W, H = 1600, 1160

lv = pya.LayoutView()
lv.load_layout(GDS, 0)
lv.max_hier()
lv.set_config("background-color", "#ffffff")
lv.set_config("grid-visible", "false")
lv.set_config("text-visible", "false")
lv.zoom_fit()
b = lv.box()
lv.zoom_box(b.enlarged(b.width() * 0.02, b.height() * 0.02))
lv.save_image(OUT, W, H)
print("wrote", OUT)
