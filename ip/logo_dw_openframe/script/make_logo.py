#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate the logo_dw_openframe GDS / LEF / PNG from the chipIgnite wordmark.

The source raster (src/chipignite_src.png) is thresholded to a single-colour
silhouette and traced into polygons. The mark is split by the whitespace gap
between the two words: "chip" is drawn on met5 (72:20) and "ignite" (with its
flame accent) on met4 (71:20). It is drawn landscape and kept short (total
height <= 60 um) so it sits in the top pad-ring branding gap.
"""

import gzip
import shutil
from pathlib import Path

import gdstk
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CELL = "logo_dw_openframe"
SRC = ROOT / "src" / "chipignite_src.png"

MET4 = (71, 20)  # sky130 met4 drawing -> "ignite"
MET5 = (72, 20)  # sky130 met5 drawing -> "chip"

# Geometry (um). Total height stays under 60 um.
PAD_UM = 2.0            # blank border around the artwork
CONTENT_H_UM = 50.0     # glyph height -> total height = 54 um
RASTER_H = 220          # rows the mark is resampled to before tracing
THRESHOLD = 180         # luminance below this becomes metal
# Fraction of the width at which "chip" ends and "ignite" begins (centre of the
# empty column gap between the two words in the source art).
SPLIT_FRAC = 249.5 / 619

# Preview colours (RGB) so the layer split is visible.
CHIP_RGB = (70, 70, 70)     # met5
IGNITE_RGB = (37, 99, 235)  # met4

BOUNDARIES = [
    (235, 4),  # prBoundary
    (62, 24),
    (105, 52),
    (107, 24),
    (112, 4),
    (117, 4),
    # omit 67/10 — Magic stream-in rejects gdstk BOUNDARY on LIBLOCK
]


def load_mask():
    """Return a boolean array (rows x cols), True = metal, cropped to content."""
    img = Image.open(SRC).convert("RGBA")
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    gray = Image.alpha_composite(white, img).convert("L")

    arr = np.asarray(gray)
    dark = arr < THRESHOLD
    ys, xs = np.where(dark)
    if len(xs) == 0:
        raise SystemExit("source image has no dark pixels above threshold")
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    crop = gray.crop((x0, y0, x1, y1))

    scale = RASTER_H / crop.height
    new_w = max(1, round(crop.width * scale))
    crop = crop.resize((new_w, RASTER_H), Image.LANCZOS)
    return np.asarray(crop) < THRESHOLD


def split_column(mask):
    """Column index separating "chip" (left) from "ignite" (right).

    Snap to the nearest fully-empty column to the target so no glyph is cut.
    """
    cols = mask.shape[1]
    target = round(SPLIT_FRAC * cols)
    empty = np.where(mask.sum(axis=0) == 0)[0]
    if len(empty):
        return int(empty[np.argmin(np.abs(empty - target))])
    return target


def mask_to_polygons(mask, split_col):
    """Trace the mask into merged polygons, split onto met5 / met4 by column."""
    rows, cols = mask.shape
    px = CONTENT_H_UM / rows  # um per pixel
    chip_rects, ignite_rects = [], []

    def add(a, b, ry0, ry1):
        # Split a run [a, b) at the word boundary, then emit on each layer.
        for lo, hi, bucket, lay in (
            (a, min(b, split_col), chip_rects, MET5),
            (max(a, split_col), b, ignite_rects, MET4),
        ):
            if hi > lo:
                bucket.append(
                    gdstk.rectangle(
                        (PAD_UM + lo * px, ry0),
                        (PAD_UM + hi * px, ry1),
                        layer=lay[0],
                        datatype=lay[1],
                    )
                )

    for j in range(rows):
        row = mask[j]
        ry1 = PAD_UM + (rows - j) * px  # y grows upward; row 0 is the top
        ry0 = PAD_UM + (rows - j - 1) * px
        x = 0
        while x < cols:
            if row[x]:
                x2 = x
                while x2 < cols and row[x2]:
                    x2 += 1
                add(x, x2, ry0, ry1)
                x = x2
            else:
                x += 1

    chip = gdstk.boolean(chip_rects, [], "or", layer=MET5[0], datatype=MET5[1])
    ignite = gdstk.boolean(ignite_rects, [], "or", layer=MET4[0], datatype=MET4[1])
    width = PAD_UM * 2 + cols * px
    height = PAD_UM * 2 + rows * px
    return chip, ignite, width, height


def main():
    mask = load_mask()
    split = split_column(mask)
    chip, ignite, width, height = mask_to_polygons(mask, split)

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = lib.new_cell(CELL)
    for p in chip + ignite:
        cell.add(p)
    for bl, bd in BOUNDARIES:
        cell.add(gdstk.rectangle((0, 0), (width, height), layer=bl, datatype=bd))

    gds_dir = ROOT / "gds"
    gds_dir.mkdir(parents=True, exist_ok=True)
    gds_path = gds_dir / f"{CELL}.gds"
    gz_path = gds_dir / f"{CELL}.gds.gz"
    lib.write_gds(str(gds_path))
    with open(gds_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    gds_path.unlink()

    # Preview PNG straight from the mask so it matches GDS; the two metal
    # layers are coloured differently to show the chip/ignite split.
    scale = 6
    rows, cols = mask.shape
    canvas = np.full((rows, cols, 3), 255, dtype=np.uint8)
    xidx = np.arange(cols)
    chip_mask = mask & (xidx[None, :] < split)
    ignite_mask = mask & (xidx[None, :] >= split)
    canvas[chip_mask] = CHIP_RGB
    canvas[ignite_mask] = IGNITE_RGB
    prev = Image.fromarray(canvas, "RGB").resize(
        (cols * scale, rows * scale), Image.NEAREST
    )
    img_dir = ROOT / "image"
    img_dir.mkdir(parents=True, exist_ok=True)
    prev.save(img_dir / f"{CELL}.png")

    lef_dir = ROOT / "lef"
    lef_dir.mkdir(parents=True, exist_ok=True)
    # OBS only on the artwork metals (met4 + met5). Full li1..met5 OBS would
    # block the pad-ring abutment bus in the com_bus_slice fillers under the
    # mid-gap branding placement and stall detailed routing.
    (lef_dir / f"{CELL}.lef").write_text(
        f"""VERSION 5.7 ;
  NOWIREEXTENSIONATPIN ON ;
  DIVIDERCHAR "/" ;
  BUSBITCHARS "[]" ;
MACRO {CELL}
  CLASS BLOCK ;
  FOREIGN {CELL} ;
  ORIGIN 0.000 0.000 ;
  SIZE {width:.3f} BY {height:.3f} ;
  OBS
      LAYER met4 ;
        RECT 0.0 0.0 {width:.3f} {height:.3f} ;
      LAYER met5 ;
        RECT 0.0 0.0 {width:.3f} {height:.3f} ;
  END
END {CELL}
END LIBRARY
"""
    )
    vh_dir = ROOT / "vh"
    vh_dir.mkdir(parents=True, exist_ok=True)
    (vh_dir / f"{CELL}.vh").write_text(f"(* keep *)\nmodule {CELL};\nendmodule\n")
    print(
        f"Wrote {gz_path}  ({width:.3f} x {height:.3f} um) "
        f"chip/met5={len(chip)} ignite/met4={len(ignite)} polygons"
    )


if __name__ == "__main__":
    main()
