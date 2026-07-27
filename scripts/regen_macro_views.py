#!/usr/bin/env python3
"""Regenerate a macro's LEF and DEF from its GDS.

Geometry (pin ports, obstructions, DEF) is derived *fresh* from gds/<cell>.gds
using Magic (scripts/gen_macro_lef_def.tcl).  Because a GDS carries no netlist,
Magic cannot recover the per-pin semantic attributes (DIRECTION / USE /
ANTENNA*), and it emits obstruction geometry for the long met3/met4 straps that
extend outside the cell's prBoundary.  So we post-process the raw LEF to:

  * clip OBS rectangles to the macro SIZE (drop/trim out-of-bounds blockages),
  * carry the DIRECTION / USE / ANTENNA* attributes over from the existing
    (golden) LEF, keyed by pin name, and keep the golden pin ordering.

Pin *port* geometry and the macro SIZE come entirely from the GDS.

Usage:
    python3 scripts/regen_macro_views.py constant_block xres_buf
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDK_ROOT = os.environ.get("PDK_ROOT", os.path.expanduser("~/.ciel"))
PDK = os.environ.get("PDK", "sky130A")
MAGICRC = os.path.join(PDK_ROOT, PDK, "libs.tech", "magic", f"{PDK}.magicrc")
TCL = os.path.join(ROOT, "scripts", "gen_macro_lef_def.tcl")

# DIRECTION/USE are net semantics (not in a GDS) so we carry them from the
# golden LEF; ANTENNA* areas are geometry-derived and come fresh from Magic.
GOLDEN_ATTR_KEYS = ("DIRECTION", "USE")


def run_magic(cell, out_lef, out_def):
    cmd = [
        "magic", "-dnull", "-noconsole", "-rcfile", MAGICRC, TCL,
    ]
    env = dict(os.environ, PDK_ROOT=PDK_ROOT, PDK=PDK,
               MACRO_CELL=cell, MACRO_OUT_LEF=out_lef, MACRO_OUT_DEF=out_def)
    res = subprocess.run(cmd, cwd=ROOT, env=env,
                         capture_output=True, text=True)
    if f"MAGIC_DONE {cell}" not in res.stdout:
        sys.stderr.write(res.stdout + "\n" + res.stderr + "\n")
        raise RuntimeError(f"magic failed for {cell}")


def block_attrs(block_lines, keys):
    """Extract pin attribute lines matching `keys` (e.g. DIRECTION/USE) from a
    PIN block (list of lines starting with 'PIN name').  At most one line is
    returned per keyword, so a golden file that was previously polluted with
    duplicates still yields a single clean attribute (idempotent re-runs)."""
    attrs = []
    seen = set()
    in_port = False
    for line in block_lines[1:]:
        s = line.strip()
        if s.startswith("PORT"):
            in_port = True
            continue
        if s == "END":
            in_port = False
            continue
        if in_port:
            continue
        for k in keys:
            if s.startswith(k) and k not in seen:
                seen.add(k)
                attrs.append(line.rstrip())
                break
    return attrs


def parse_size(lef_text):
    m = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", lef_text)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def split_macro(lef_text):
    """Split a single-MACRO LEF into (header, pin_blocks{name:lines}, order,
    obs_lines, macro_tail_lines)."""
    lines = lef_text.splitlines()
    header, pins, order, obs, tail = [], {}, [], [], []
    i = 0
    # header up to and including SIZE line
    while i < len(lines):
        header.append(lines[i])
        if lines[i].strip().startswith("SIZE"):
            i += 1
            break
        i += 1
    # body: pins / OBS / END macro
    cur = None
    while i < len(lines):
        s = lines[i].strip()
        m = re.match(r"^PIN\s+(\S+)", s)
        if m:
            cur = m.group(1)
            order.append(cur)
            pins[cur] = [lines[i]]
            i += 1
            while i < len(lines):
                pins[cur].append(lines[i])
                if lines[i].strip() == f"END {cur}":
                    i += 1
                    break
                i += 1
            cur = None
            continue
        if s == "OBS":
            while i < len(lines):
                obs.append(lines[i])
                if lines[i].strip() == "END":
                    i += 1
                    break
                i += 1
            continue
        tail.append(lines[i])
        i += 1
    return header, pins, order, obs, tail


def clip_obs(obs_lines, w, h):
    """Clip OBS RECTs to [0,0,w,h]; drop empty layers."""
    out = ["  OBS"]
    layer = None
    pending_layer = None
    kept_for_layer = []

    def flush():
        nonlocal kept_for_layer, pending_layer
        if pending_layer is not None and kept_for_layer:
            out.append(f"      LAYER {pending_layer} ;")
            out.extend(kept_for_layer)
        pending_layer = None
        kept_for_layer = []

    for line in obs_lines:
        s = line.strip()
        if s in ("OBS", "END"):
            continue
        m = re.match(r"LAYER\s+(\S+)\s*;", s)
        if m:
            flush()
            pending_layer = m.group(1)
            continue
        r = re.match(r"RECT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*;", s)
        if r:
            x1, y1, x2, y2 = map(float, r.groups())
            cx1, cy1 = max(x1, 0.0), max(y1, 0.0)
            cx2, cy2 = min(x2, w), min(y2, h)
            if cx2 - cx1 > 1e-6 and cy2 - cy1 > 1e-6:
                kept_for_layer.append(
                    f"        RECT {cx1:.3f} {cy1:.3f} {cx2:.3f} {cy2:.3f} ;")
    flush()
    out.append("  END")
    return out


def rebuild(magic_lef, golden_pins, golden_order):
    header, pins, order, obs, tail = split_macro(magic_lef)
    w, h = parse_size(magic_lef)

    # Pin emission order: golden order first, then any GDS-only extras.
    seq = [p for p in golden_order if p in pins or p in golden_pins]
    seq += [p for p in order if p not in seq]

    spliced = []
    out = list(header)
    for p in seq:
        if p in pins:
            # Geometry + antenna areas come fresh from the GDS (Magic block);
            # inject only the net-semantic DIRECTION/USE lines from the golden
            # LEF right after the PIN header (dropping any DIRECTION/USE that
            # Magic guessed, to avoid duplicates).
            block = pins[p]
            out.append(block[0])  # "  PIN name"
            out.extend(block_attrs(golden_pins.get(p, []), GOLDEN_ATTR_KEYS))
            in_port = False
            for line in block[1:]:
                s = line.strip()
                if s.startswith("PORT"):
                    in_port = True
                elif s == "END":
                    in_port = False
                if not in_port and any(
                        s.startswith(k) for k in GOLDEN_ATTR_KEYS):
                    continue
                out.append(line)
        else:
            # Magic could not recover this port's shape from the GDS labels
            # (label-purpose text, not pin-purpose); keep the golden block,
            # whose port rects are this layout's actual pin geometry.
            out.extend(golden_pins[p])
            spliced.append(p)
    if obs:
        out.extend(clip_obs(obs, w, h))
    out.extend(tail)
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text, seq, order, spliced


def main(cells):
    for cell in cells:
        gds = os.path.join(ROOT, "gds", f"{cell}.gds")
        if not os.path.exists(gds):
            raise FileNotFoundError(gds)
        golden_lef = os.path.join(ROOT, "lef", f"{cell}.lef")
        out_lef = os.path.join(ROOT, "lef", f"{cell}.lef")
        out_def = os.path.join(ROOT, "def", f"{cell}.def")
        tmp_lef = os.path.join(ROOT, "def", f".{cell}.raw.lef")

        golden_pins, golden_order = {}, []
        if os.path.exists(golden_lef):
            with open(golden_lef) as f:
                _, golden_pins, golden_order, _, _ = split_macro(f.read())

        os.makedirs(os.path.join(ROOT, "def"), exist_ok=True)
        run_magic(cell, tmp_lef, out_def)
        with open(tmp_lef) as f:
            magic_lef = f.read()
        os.remove(tmp_lef)

        text, seq, magic_order, spliced = rebuild(
            magic_lef, golden_pins, golden_order)
        with open(out_lef, "w") as f:
            f.write(text)

        extra = [p for p in magic_order if p not in golden_order]
        print(f"[{cell}] pins={seq}")
        if spliced:
            print(f"[{cell}] port shape kept from golden LEF "
                  f"(label-purpose text in GDS): {spliced}")
        if extra:
            print(f"[{cell}] note: pins in GDS not in golden LEF: {extra}")
        print(f"[{cell}] wrote lef/{cell}.lef  def/{cell}.def")


if __name__ == "__main__":
    main(sys.argv[1:] or ["constant_block", "xres_buf"])
