#!/usr/bin/env python3
"""Generate datasheet figures and pinout tables from the padframe source data.

Outputs (all under docs/):
  figures/io_map.svg        floorplan + I/O map (all pads, per-side organization)
  figures/power_domains.svg d2-rendered power/domain map
  figures/boundary.svg      d2-rendered user-area boundary signals
  pinout.md                 GPIO index map + per-side ordered pads
  generated/*.d2            d2 sources (rendered to SVG if `d2` is installed)

Run:
  python3 scripts/gen_datasheet_figures.py

Authoritative inputs: pad_summary.json, librelane/padframe/pad_lists.yaml,
librelane/padframe/pad_pos.tcl (all produced by `make pads`).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "pad_summary.json"
PAD_LISTS = ROOT / "librelane" / "padframe" / "pad_lists.yaml"
PAD_POS = ROOT / "librelane" / "padframe" / "pad_pos.tcl"
OUT_FIG = ROOT / "docs" / "figures"
OUT_GEN = ROOT / "docs" / "generated"

DIE_W, DIE_H = 7176.0, 5188.0
CORE = (210.685, 210.685, 6965.315, 4977.315)
WRAP_W, WRAP_H = 6754.63, 4766.63

SIDE_ORDER = ("PAD_WEST", "PAD_EAST", "PAD_NORTH", "PAD_SOUTH")
SIDE_SHORT = {"PAD_WEST": "W", "PAD_EAST": "E", "PAD_NORTH": "N", "PAD_SOUTH": "S"}

# Apple-ish palette to match the reference I/O map style.
INK = "#1d1d1f"
MUTE = "#86868b"
BLUE = "#0070f3"
ORANGE = "#bf4800"
LINE = "#d2d2d7"
FILL = "#fafafa"
USERFILL = "#eef5ea"


def parse_pad_lists(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for side in SIDE_ORDER:
        m = re.search(rf"{side}:\s*\[(.*?)\]\s*(?:\n|$)", text, re.S)
        if not m:
            raise SystemExit(f"missing {side} in pad_lists.yaml")
        names = re.findall(r'"([^"]+)"', m.group(1))
        out[side] = [n.replace("\\", "") for n in names]
    return out


def parse_pad_pos(text: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for side in SIDE_ORDER:
        m = re.search(
            rf'dict set caravel_pad_pos {side} "(.*?)"\s*$', text, re.S | re.M
        )
        if not m:
            raise SystemExit(f"missing {side} in pad_pos.tcl")
        out[side] = [float(x) for x in m.group(1).replace("\\", " ").split()]
    return out


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------- #
# I/O map (floorplan with all pads + per-side organization)
# --------------------------------------------------------------------------- #
def write_io_map_svg(path: Path, summary: dict) -> None:
    by_side: dict[str, list[dict]] = {"W": [], "E": [], "N": [], "S": []}
    for e in summary["gpio_index_map"]:
        by_side[e["side"]].append(e)
    for v in by_side.values():
        v.sort(key=lambda e: e["coord"])

    reset = summary["reset"]

    # Canvas / die placement
    VW, VH = 1040.0, 780.0
    die_w = 600.0
    die_h = die_w * DIE_H / DIE_W
    x0 = (VW - die_w) / 2
    y0 = 180.0
    sx = die_w / DIE_W
    sy = die_h / DIE_H

    def px(dx: float) -> float:
        return x0 + dx * sx

    def py(dy: float) -> float:
        return y0 + (DIE_H - dy) * sy  # flip: north (high dy) at top

    P: list[str] = []
    P.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VW:g} {VH:g}" '
        'font-family="-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif" '
        'font-size="12" role="img" aria-label="Double-wide openframe I/O map">'
    )
    P.append(f'<rect width="{VW:g}" height="{VH:g}" fill="#ffffff"/>')
    P.append(
        f'<text x="{VW/2:g}" y="42" text-anchor="middle" font-size="18" '
        f'font-weight="600" fill="{INK}">Double-Wide OpenFrame — I/O Map</text>'
    )
    P.append(
        f'<text x="{VW/2:g}" y="62" text-anchor="middle" font-size="11" fill="{MUTE}">'
        "63 GPIOs · indexed West → East → North → South</text>"
    )

    # Die + user area
    P.append(
        f'<rect x="{px(0):g}" y="{py(DIE_H):g}" width="{die_w:g}" height="{die_h:g}" '
        f'fill="{FILL}" stroke="{INK}" stroke-width="2"/>'
    )
    P.append(
        f'<rect x="{px(CORE[0]):g}" y="{py(CORE[3]):g}" '
        f'width="{(CORE[2]-CORE[0])*sx:g}" height="{(CORE[3]-CORE[1])*sy:g}" '
        f'fill="{USERFILL}" stroke="#3a6b3d" stroke-width="1.2"/>'
    )
    cx, cy = px(DIE_W / 2), py(DIE_H / 2)
    P.append(
        f'<text x="{cx:g}" y="{cy-8:g}" text-anchor="middle" font-size="15" '
        f'font-weight="600" fill="#5a5a5f">User project area</text>'
    )
    P.append(
        f'<text x="{cx:g}" y="{cy+10:g}" text-anchor="middle" font-size="11" '
        f'fill="{MUTE}">6.75 × 4.77 mm</text>'
    )
    P.append(
        f'<text x="{cx:g}" y="{cy+26:g}" text-anchor="middle" font-size="10" '
        f'fill="{MUTE}">die 7.18 × 5.19 mm</text>'
    )

    # Pad ticks
    tick = 9.0
    P.append(f'<g stroke="{INK}" stroke-width="1" fill="none">')
    for e in by_side["W"]:
        y = py(e["coord"])
        P.append(f'<line x1="{px(0)-tick:g}" y1="{y:g}" x2="{px(0):g}" y2="{y:g}"/>')
    for e in by_side["E"]:
        y = py(e["coord"])
        P.append(
            f'<line x1="{px(DIE_W):g}" y1="{y:g}" x2="{px(DIE_W)+tick:g}" y2="{y:g}"/>'
        )
    for e in by_side["N"]:
        x = px(e["coord"])
        P.append(f'<line x1="{x:g}" y1="{py(DIE_H)-tick:g}" x2="{x:g}" y2="{py(DIE_H):g}"/>')
    for e in by_side["S"]:
        x = px(e["coord"])
        P.append(f'<line x1="{x:g}" y1="{py(0):g}" x2="{x:g}" y2="{py(0)+tick:g}"/>')
    P.append("</g>")

    # Direction arrows (index increases along each edge)
    P.append(
        f'<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{BLUE}"/></marker></defs>'
    )
    P.append(f'<g stroke="{BLUE}" stroke-width="1.4" fill="none" stroke-dasharray="3 3">')
    # West: bottom -> top
    P.append(
        f'<line x1="{px(0)-16:g}" y1="{py(by_side["W"][0]["coord"]):g}" '
        f'x2="{px(0)-16:g}" y2="{py(by_side["W"][-1]["coord"]):g}" marker-end="url(#ar)"/>'
    )
    # East: bottom -> top
    P.append(
        f'<line x1="{px(DIE_W)+16:g}" y1="{py(by_side["E"][0]["coord"]):g}" '
        f'x2="{px(DIE_W)+16:g}" y2="{py(by_side["E"][-1]["coord"]):g}" marker-end="url(#ar)"/>'
    )
    # North: left -> right
    P.append(
        f'<line x1="{px(by_side["N"][0]["coord"]):g}" y1="{py(DIE_H)-18:g}" '
        f'x2="{px(by_side["N"][-1]["coord"]):g}" y2="{py(DIE_H)-18:g}" marker-end="url(#ar)"/>'
    )
    # South: left -> right
    P.append(
        f'<line x1="{px(by_side["S"][0]["coord"]):g}" y1="{py(0)+18:g}" '
        f'x2="{px(by_side["S"][-1]["coord"]):g}" y2="{py(0)+18:g}" marker-end="url(#ar)"/>'
    )
    P.append("</g>")

    def endpoint(dx: float, dy: float, side: str, label: str, sub: str = "") -> None:
        x, y = px(dx), py(dy)
        if side == "W":
            lx, ly = px(0) - 34, y
            P.append(f'<line x1="{px(0)-tick:g}" y1="{y:g}" x2="{lx:g}" y2="{y:g}" stroke="{INK}"/>')
            P.append(f'<text x="{lx-4:g}" y="{y+4:g}" text-anchor="end" font-size="12.5" font-weight="600" fill="{INK}">{label}</text>')
            if sub:
                P.append(f'<text x="{lx-4:g}" y="{y+17:g}" text-anchor="end" font-size="9.5" fill="{MUTE}">{sub}</text>')
        elif side == "E":
            lx = px(DIE_W) + 34
            P.append(f'<line x1="{px(DIE_W)+tick:g}" y1="{y:g}" x2="{lx:g}" y2="{y:g}" stroke="{INK}"/>')
            P.append(f'<text x="{lx+4:g}" y="{y+4:g}" font-size="12.5" font-weight="600" fill="{INK}">{label}</text>')
            if sub:
                P.append(f'<text x="{lx+4:g}" y="{y+17:g}" font-size="9.5" fill="{MUTE}">{sub}</text>')
        elif side == "N":
            ly = py(DIE_H) - 34
            P.append(f'<line x1="{x:g}" y1="{py(DIE_H)-tick:g}" x2="{x:g}" y2="{ly:g}" stroke="{INK}"/>')
            P.append(f'<text x="{x:g}" y="{ly-4:g}" text-anchor="middle" font-size="12.5" font-weight="600" fill="{INK}">{label}</text>')
        else:  # S
            ly = py(0) + 34
            P.append(f'<line x1="{x:g}" y1="{py(0)+tick:g}" x2="{x:g}" y2="{ly:g}" stroke="{INK}"/>')
            P.append(f'<text x="{x:g}" y="{ly+12:g}" text-anchor="middle" font-size="12.5" font-weight="600" fill="{INK}">{label}</text>')
            if sub:
                P.append(f'<text x="{x:g}" y="{ly+25:g}" text-anchor="middle" font-size="9.5" fill="{BLUE}">{sub}</text>')

    endpoint(0, by_side["W"][0]["coord"], "W", "GPIO[0]", "start")
    endpoint(0, by_side["W"][-1]["coord"], "W", "GPIO[13]")
    endpoint(DIE_W, by_side["E"][0]["coord"], "E", "GPIO[14]")
    endpoint(DIE_W, by_side["E"][-1]["coord"], "E", "GPIO[28]")
    endpoint(by_side["N"][0]["coord"], DIE_H, "N", "GPIO[29]")
    endpoint(by_side["N"][-1]["coord"], DIE_H, "N", "GPIO[48]")
    endpoint(by_side["S"][0]["coord"], 0, "S", "GPIO[49]")
    endpoint(by_side["S"][-1]["coord"], 0, "S", "GPIO[62]", "last GPIO")

    # POR (west gap) + reset (south) markers
    por = summary.get("por", {})
    por_y = por.get("location_um", [55.3, 733.78])[1]
    pyc = py(por_y)
    lab_y = pyc + 22  # push clear of the GPIO[0] label just above
    P.append(f'<circle cx="{px(0):g}" cy="{pyc:g}" r="3.4" fill="{ORANGE}"/>')
    P.append(f'<line x1="{px(0)-tick:g}" y1="{pyc:g}" x2="{px(0)-34:g}" y2="{lab_y-4:g}" stroke="{ORANGE}"/>')
    P.append(f'<text x="{px(0)-38:g}" y="{lab_y:g}" text-anchor="end" font-size="12" font-weight="600" fill="{ORANGE}">POR</text>')
    P.append(f'<text x="{px(0)-38:g}" y="{lab_y+13:g}" text-anchor="end" font-size="9.5" fill="{MUTE}">porb_h · porb_l · por_l</text>')

    rx = px(reset["coord"])
    ryc = py(0)
    P.append(f'<circle cx="{rx:g}" cy="{ryc:g}" r="3.4" fill="{ORANGE}"/>')
    P.append(f'<line x1="{rx:g}" y1="{ryc+tick:g}" x2="{rx-24:g}" y2="{ryc+52:g}" stroke="{ORANGE}"/>')
    P.append(f'<text x="{rx-28:g}" y="{ryc+52:g}" text-anchor="end" font-size="12" font-weight="600" fill="{ORANGE}">reset pad</text>')
    P.append(f'<text x="{rx-28:g}" y="{ryc+65:g}" text-anchor="end" font-size="9.5" fill="{MUTE}">resetb_h · resetb_l</text>')

    # Edge callouts (range + count + domain), each near its own edge.
    P.append(f'<text x="{px(0)-96:g}" y="{cy-30:g}" text-anchor="end" font-size="11" font-weight="600" fill="{INK}">West edge</text>')
    P.append(f'<text x="{px(0)-96:g}" y="{cy-15:g}" text-anchor="end" font-size="11" fill="{MUTE}">GPIO[0]–[13] · user2</text>')
    P.append(f'<text x="{px(0)-96:g}" y="{cy-1:g}" text-anchor="end" font-size="11" fill="{MUTE}">14 GPIOs, bottom→top</text>')
    P.append(f'<text x="{px(DIE_W)+96:g}" y="{cy-30:g}" font-size="11" font-weight="600" fill="{INK}">East edge</text>')
    P.append(f'<text x="{px(DIE_W)+96:g}" y="{cy-15:g}" font-size="11" fill="{MUTE}">GPIO[14]–[28] · user1</text>')
    P.append(f'<text x="{px(DIE_W)+96:g}" y="{cy-1:g}" font-size="11" fill="{MUTE}">15 GPIOs, bottom→top</text>')
    P.append(f'<text x="{VW/2:g}" y="108" text-anchor="middle" font-size="11" fill="{MUTE}">North edge — GPIO[29]–[48] — 20 GPIOs — user1 — left→right</text>')
    P.append(f'<text x="{VW/2:g}" y="{VH-24:g}" text-anchor="middle" font-size="11" fill="{MUTE}">South edge — GPIO[49]–[62] — 14 GPIOs — user0 — left→right</text>')

    # Legend
    P.append(f'<g transform="translate(40,{VH-42:g})">')
    P.append(f'<rect width="250" height="30" fill="none" stroke="{LINE}" rx="4"/>')
    P.append(f'<line x1="14" y1="15" x2="26" y2="15" stroke="{INK}" stroke-width="1.4"/>')
    P.append(f'<text x="32" y="19" font-size="11" fill="{INK}">GPIO pad</text>')
    P.append(f'<circle cx="120" cy="15" r="3.4" fill="{ORANGE}"/>')
    P.append(f'<text x="130" y="19" font-size="11" fill="{INK}">POR / reset pad</text>')
    P.append("</g>")

    P.append("</svg>")
    path.write_text("\n".join(P) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# d2 diagrams
# --------------------------------------------------------------------------- #
POWER_D2 = """\
# AUTO-GENERATED by scripts/gen_datasheet_figures.py
vars: { d2-config: { theme-id: 0; sketch: false } }
grid-rows: 3
horizontal-gap: 60
vertical-gap: 50

shared: Shared pad-ring rails {
  grid-columns: 3
  style.fill: "#eef2f7"
  a: "vddio / vssio\\n3.3 V I/O" { style.fill: "#ffffff" }
  b: "vccd / vssd\\n1.8 V" { style.fill: "#ffffff" }
  c: "vdda / vssa\\nanalog" { style.fill: "#ffffff" }
}

domains: Per-side user domains {
  grid-columns: 3
  style.fill: "#fbfbfd"
  user2: "user2 — West\\nGPIO 0–13\\nvccd2 / vssd2\\nvdda2 / vssa2" { style.fill: "#f7e2c8" }
  user1: "user1 — East + North\\nGPIO 14–48\\nvccd1 / vssd1\\nvdda1 / vssa1" { style.fill: "#d6e4f7" }
  user0: "user0 — South\\nGPIO 49–62\\nvccd1 / vssd1\\nvdda / vssa" { style.fill: "#d8ecd8" }
}

note: "Connect your digital logic to vccd1 / vssd1" {
  style: { fill: "#fff8e6"; stroke: "#b58900"; bold: true }
}
"""

BOUNDARY_D2 = """\
# AUTO-GENERATED by scripts/gen_datasheet_figures.py
vars: { d2-config: { theme-id: 0; sketch: false } }
direction: right

ring: Pad ring {
  style.fill: "#e3eefc"
  gpio: "63 × GPIO pads"
  rst: "reset + POR pads"
}

user: "Your design — user project wrapper" {
  style: { fill: "#e6f2e0"; stroke: "#2f5d32" }
  data: "gpio_in / gpio_in_h [62:0]\\ngpio_out / gpio_oeb [62:0]" { style.fill: "#ffffff" }
  cfg: "gpio_dm0/1/2, vtrip, slow,\\nanalog_en/sel/pol … [62:0]" { style.fill: "#ffffff" }
  ana: "analog_io / analog_noesd_io [62:0]" { style.fill: "#ffffff" }
  por: "porb_h, porb_l, por_l\\nresetb_h, resetb_l" { style.fill: "#ffffff" }
  pwr: "14 power pins" { style.fill: "#ffffff" }
}

ring.gpio -> user.data: digital
ring.gpio -> user.cfg: config
ring.gpio -> user.ana: analog
ring.rst -> user.por: reset / POR
"""


def render_d2(src: Path, out_svg: Path) -> bool:
    d2 = shutil.which("d2") or str(Path.home() / ".local" / "bin" / "d2")
    if not Path(d2).exists():
        print(f"  ! d2 not found; wrote source only: {src.name}")
        return False
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}:" + env.get("PATH", "")
    subprocess.run([d2, "--pad", "24", str(src), str(out_svg)], check=True, env=env)
    return True


# --------------------------------------------------------------------------- #
# Pinout tables
# --------------------------------------------------------------------------- #
def classify(name: str) -> str:
    if name == "master_resetb_pad":
        return "reset"
    if name.startswith("clamp_"):
        return re.sub(r"_\d+$", "", name[len("clamp_"):]).upper()
    return name


def write_pinout_page(
    path: Path, summary: dict, sides: dict[str, list[str]], coords: dict[str, list[float]]
) -> None:
    gmap = {e["g"]: e for e in summary["gpio_index_map"]}
    inst2g = {e["inst"]: e["g"] for e in summary["gpio_index_map"]}
    L = [
        "# Double-Wide OpenFrame — Pinout",
        "",
        "GPIO indices and package bond-pad centers. Machine-readable source:",
        "[`../pad_summary.json`](../pad_summary.json).",
        "",
        "![I/O map](figures/io_map.svg)",
        "",
        "<!-- Tables below are AUTO-GENERATED by scripts/gen_datasheet_figures.py -->",
        "",
        "## GPIO index map",
        "",
        "Bond coordinate is the edge-local axis in µm (origin at die southwest):",
        "West/East give **Y**, North/South give **X**.",
        "",
        "| Index | Side | Domain | Bond coord (µm) |",
        "|------:|:----:|:------:|----------------:|",
    ]
    for g in range(summary["n_gpio"]):
        e = gmap[g]
        L.append(f"| {g} | {e['side']} | {e['domain']} | {e['coord']:.3f} |")

    rst = summary["reset"]
    L += [
        "",
        "## Dedicated pads",
        "",
        "| Pad | Side | Bond coord (µm) | Notes |",
        "|-----|:----:|----------------:|-------|",
        f"| `resetb_pad` | {rst['side']} | {rst['coord']:.3f} | External reset (3.3 V), level-shifted to 1.8 V |",
        "",
        "## Power bond pads",
        "",
        "| Net | Bond pads | Net | Bond pads |",
        "|-----|----------:|-----|----------:|",
    ]
    pkg = summary["pkg_counts"]
    items = sorted(pkg.items())
    for i in range(0, len(items), 2):
        left = f"| `{items[i][0]}` | {items[i][1]} "
        if i + 1 < len(items):
            right = f"| `{items[i+1][0]}` | {items[i+1][1]} |"
        else:
            right = "|  |  |"
        L.append(left + right)
    L += [
        "",
        f"**Total power bond pads:** {sum(pkg.values())}.",
        "",
        "## Ordered pad ring (per side)",
        "",
        "Physical pad order around the ring (matches the manufacturing bond map).",
        "",
    ]
    for side in SIDE_ORDER:
        L += [
            f"### {SIDE_SHORT[side]} — {side.split('_')[1].title()}",
            "",
            "| # | Bond (µm) | Pad |",
            "|--:|----------:|-----|",
        ]
        for i, (name, c) in enumerate(zip(sides[side], coords[side])):
            if name in inst2g:
                kind = f"GPIO[{inst2g[name]}]"
            else:
                kind = classify(name)
            L.append(f"| {i} | {c:.3f} | {kind} |")
        L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    OUT_FIG.mkdir(parents=True, exist_ok=True)
    OUT_GEN.mkdir(parents=True, exist_ok=True)

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    sides = parse_pad_lists(PAD_LISTS.read_text(encoding="utf-8"))
    coords = parse_pad_pos(PAD_POS.read_text(encoding="utf-8"))

    write_io_map_svg(OUT_FIG / "io_map.svg", summary)

    (OUT_GEN / "power_domains.d2").write_text(POWER_D2, encoding="utf-8")
    (OUT_GEN / "boundary.d2").write_text(BOUNDARY_D2, encoding="utf-8")
    render_d2(OUT_GEN / "power_domains.d2", OUT_FIG / "power_domains.svg")
    render_d2(OUT_GEN / "boundary.d2", OUT_FIG / "boundary.svg")

    write_pinout_page(ROOT / "docs" / "pinout.md", summary, sides, coords)

    print(f"Figures → {OUT_FIG}")
    print(f"Pinout  → {ROOT / 'docs' / 'pinout.md'}")


if __name__ == "__main__":
    main()
