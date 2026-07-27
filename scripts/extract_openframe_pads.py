#!/usr/bin/env python3
"""Extract the caravel openframe pad ring and generate the double-wide project.

Parses caravel/mag/chip_io_openframe.mag, classifies every functional pad
(signal gpiov2 pads and power clamp pads) by which die edge it sits on, then
builds the *double-wide* ring:

  * West (left) and East (right): kept exactly as openframe.
  * North (top) and South (bottom): duplicated -> two copies side by side, the
    second copy shifted by +HALF_WIDTH in x (continuous rows, only 4 corners).

From that inventory it generates, so that RTL / pad tables / pin map never drift:

  * verilog/rtl/double_wide_chip_io.v                 (padframe RTL + POR/reset)
  * verilog/rtl/double_wide_openframe_project_wrapper.v (empty user-area wrapper)
  * verilog/rtl/por_reset_blackboxes.v                (POR / xres / constant bb)
  * verilog/rtl/dw_defines.vh                         (pad-count defines)
  * librelane/padframe/pad_pos.tcl                    (bond-pad-center coords)
  * librelane/padframe/pad_lists.yaml                 (PAD_* ordered inst lists)
  * pad_summary.json                                  (counts + gpio index map)

Magic transform "transform a b c d e f" maps a child point (x,y) to parent:
    x' = a*x + b*y + c ;  y' = d*x + e*y + f
The per-use "box" line is the child-space bbox.
"""
import argparse
import json
import os
import re
import sys

UNIT_UM = 0.005            # calibrated: 717600 magic units == 3588 um
OF_W_UM = 3588.0           # openframe die width
OF_H_UM = 5188.0           # openframe die height
HALF_UM = OF_W_UM          # x-offset applied to the second top/bottom copy
DW_W_UM = 2 * OF_W_UM      # 7176 double-wide width
DW_H_UM = OF_H_UM          # 5188 unchanged height

# Openframe user wrapper is 3166.63 x 4766.63 inside the 3588 x 5188 die
# (a 210.685 um margin on every edge). Preserve that margin for the double-wide.
WRAP_MARGIN_UM = (OF_W_UM - 3166.63) / 2.0   # 210.685
WRAP_W_UM = DW_W_UM - 2 * WRAP_MARGIN_UM     # 6754.63
WRAP_H_UM = DW_H_UM - 2 * WRAP_MARGIN_UM     # 4766.63

# POR / reset support (openframe-style), baked into every padframe reharden.
# simple_por: dw_openframe GDS + LEF abstract with pin-access collar (SIZE 63.72).
# X locked to Mag west-gap column; Y nudged so signal-pin centers sit on met3
# tracks (LibreLane orient E = OpenROAD R270).
POR_INST = "por"
POR_LOCATION_UM = (55.300, 733.780)
POR_ORIENT = "E"

# Master reset pad: openframe Mag south edge (bond-pad center X).
RESET_INST = "master_resetb_pad"
RESET_SIDE = "S"
RESET_BOND_UM = 700.447

# Level-shifter + constant one for ENABLE_VDDIO (openframe Mag / Jul-14 places).
XRES_BUF_INST = "rstb_level"
XRES_BUF_LOCATION_UM = (742.915, 80.355)
XRES_BUF_ORIENT = "N"   # flip in place: horizontal mirror of the openframe FN
XRES_BUF_NUDGE_UM = (0.0, 2.0)
CONSTANT_INST = "constant_value_xres_inst"
CONSTANT_LOCATION_UM = (739.080, 200.240)
# South (bottom) const block: extended power straps must point outward toward the
# pad-ring power (local +Y -> -Y), i.e. orientation S. See SIDE_CONST_ORIENT.
CONSTANT_ORIENT = "S"

# Per-side orientation for the per-gpio constant_block. The block's extended
# met3/met4 power straps run in local +Y (GDS reaches y=57.33 vs the 14x13
# prBoundary); they must point OUTWARD toward the pad-ring power rails, not
# inward into the wrapper/core. That makes each side a pure rotation:
#   S -> S (+Y->-Y, down/out)   N -> N (+Y->+Y, up/out)
#   W -> W (+Y->-X, left/out)   E -> E (+Y->+X, right/out)
# The LEF SIZE (14x13, or 13x14 rotated) is identical for each flip pair
# (FN/S, FS/N, FE/W, FW/E), so the bbox-LL 'location' is unchanged; only the
# overhang direction flips.
SIDE_CONST_ORIENT = {"S": "S", "N": "N", "W": "W", "E": "E"}

# Shift every const block outward (toward the pad ring) by this much so its
# extended power straps abut the correct pad-ring power rail instead of landing
# across two rails and shorting supplies. Outward is -Y on south, +Y on north,
# -X on west, +X on east.
CONST_BLOCK_OUTWARD_SHIFT_UM = 1.53
SIDE_OUTWARD = {"S": (0.0, -1.0), "N": (0.0, 1.0), "W": (-1.0, 0.0), "E": (1.0, 0.0)}

# Additional per-side fine placement adjustments (um), applied on top of the
# outward shift, to line the power straps up precisely with the ring rails.
SIDE_FINE_ADJUST_UM = {
    "S": (0.0, 0.67),      # bottom: north +1.02 for 1.27um nwell clearance (was -0.35)
    "N": (0.0, -3.74),     # top blocks: move south (-3.465 fit + 0.16 + 0.115 DRC)
    "W": (-0.58, 0.0),     # left blocks: move left (-0.065 + 0.515 DRC)
    "E": (-4.94, 0.0),     # right: west -0.61 more for 1.27um nwell clearance (was -4.33)
}

# Pad-ring routing obstruction (keep DRT out of the pad interior) + the two
# windows we cut through it so TritonRoute can actually wire the reset / POR
# cluster (instead of marking those nets SPECIAL and never filling the metal).
#   * South window: the xres pad / xres_buf / constant_block column and the
#     wrapper resetb_h/resetb_l pins (all near x ~ 700-762).
#   * West window : the simple_por cell and the wrapper porb_h/por_l/porb_l
#     pin band (near y ~ 735-740).
ROUTE_OBS_DEPTH_UM = 198.5
ROUTE_OBS_LAYERS = ("met1", "met2", "met3", "met4", "met5")
RESET_ROUTE_WINDOW_S_UM = (655.0, 800.0)   # x gap on the south edge
POR_ROUTE_WINDOW_W_UM = (695.0, 820.0)     # y gap on the west edge

# Per-pad routing obstructions: the reset/POR windows cut through the pad-ring
# obstruction let DRT route *under* the pads sitting in those windows. Stamp an
# OBS box over every pad's footprint (all metal layers) so DRT is confined to the
# inter-pad gaps (where the reset/POR nets actually run) and never routes beneath
# a pad. Widths from the sky130 IO LEF SIZEs (gpio 80, clamp/xres 75); the bond
# center is offset ~2-3um from the cell center, so widen each box by a margin.
PAD_WIDTH_GPIO_UM = 80.0
PAD_WIDTH_CLAMP_UM = 75.0
PAD_WIDTH_RESET_UM = 75.0
PAD_OBS_MARGIN_UM = 4.0

# gpiov2 core-facing signal pins protrude ~2.035um past the pad body into the
# core (LEF pin RECTs at y in [-2.035, 0]); the pad-body OBS above (depth
# ROUTE_OBS_DEPTH_UM) only covers the top 0.535um of them, leaving a crowded
# ~1.5um "pin-tip strip" where DRT drops every net's met2 stub right next to its
# neighbours. That is where KLayout's stricter m2.2 (0.14um) flags 0.08-0.09um
# near-misses (all on the short DM[0] tip stub). Fix: extend the OBS over the pin
# strip on met2, but cut a notch at every pin so DRT drops straight down onto each
# pin (no sideways met2) -- i.e. the obstruction surrounds each pin, notched to
# touch it. Only met2 is walled (that is the violating layer); met1/met3 pins keep
# a notch too so their routes can still transition down through the strip.
PIN_STRIP_DEPTH_UM = 200.5     # OBS reaches this deep only in the notched pin band
PIN_NOTCH_HALF_UM = 0.45       # half-width of each pin access notch (0.90um opening)
# Per-side DM[0] notch half-width. W/E clear fully at 0.45; the N/S residual is a
# vertical 0.07um near-miss at the DM[0] tip, so tighten N/S to force a straighter
# drop (0.30 broke DRT access -> 2 routing errors; 0.38 is the asymmetric middle).
DM0_NOTCH_HALF_BY_SIDE = {"N": 0.38, "S": 0.38, "E": 0.45, "W": 0.45}
# Minimal DM[0] isolation: all 39 m2.2 near-misses are the DM[0] met2 tip stub
# (LEF cx 49.985). Walling the *whole* pin strip shorts DRT (it fans out ~25 pins
# there); instead wall only the two small gaps flanking DM[0], and only in the
# deep pin-tip band (DM0_WALL_D0..PIN_STRIP_DEPTH_UM), so the fan-out above stays
# open. This forces the DM[0] route straight down through its notch, off the pad
# met2 it currently grazes to 0.09um.
DM0_CX_UM = 49.985             # DM[0] pin along-edge center (LEF local x)
DM0_WALL_D0_UM = 199.0         # deep pin-tip band start (fan-out above stays open)
DM0_WALL_LEFT_UM = 3.0         # wall span toward DM[1] (open gap, no met2 pin near)
DM0_WALL_RIGHT_UM = 4.1        # wall span toward INP_DIS (stops ~0.5um short of it)
# The pad-ring placer aligns each pad's *bond* center (pad_pos.tcl, == Signal.coord)
# ~3um inboard of the cell center; the cell's cx=0 edge lands 43.0um from the bond
# center along the edge (offset 37.0um bond->cell-LL, +80um cell width - see the DEF
# calibration). Every side maps along = cell_LL + (80 - cx), so a pin at LEF-local
# cx sits at (coord + GPIO_BOND_TO_EDGE_UM - cx) along the edge.
GPIO_BOND_TO_EDGE_UM = 43.0
# gpiov2 core-facing signal-pin along-edge centers (LEF local x, um), every pin
# that reaches the pin-tip strip and gets routed. Walls between these notches keep
# adjacent nets' met2 apart.
GPIO_PIN_CX_UM = (
    0.710, 3.490, 5.535, 12.885, 16.440, 22.485, 26.730, 28.620, 30.880,
    31.945, 35.590, 38.520, 45.375, 46.030, 49.985, 62.560, 63.355, 66.965,
    68.600, 76.600, 77.740, 78.745, 78.805, 79.405, 79.815,
)
GPIO_PAD_WIDTH_UM = 80.0       # gpiov2 LEF SIZE width (along-edge span of the pins)

# Openframe POR place Y (E); used to shift wrapper POR pins with our POR Y.
OF_POR_LOCATION_Y_UM = 472.460

# Frame -> user-wrapper control signals (openframe_project_wrapper set).
# West met3: POR trio abutting simple_por's Y-band. South met2: resetb_*.
WRAPPER_POR_PINS_WEST = ("porb_h", "por_l", "porb_l")  # bottom -> top
WRAPPER_RESET_PINS_SOUTH = ("resetb_h", "resetb_l")    # left -> right
WRAPPER_CONTROL_PINS = WRAPPER_POR_PINS_WEST + WRAPPER_RESET_PINS_SOUTH

# Openframe wrapper-local pin centers (um), before POR-Y shift / as-is for south.
OF_WRAP_POR_Y_UM = (265.910, 267.035, 268.150)   # porb_h, por_l, porb_l
OF_WRAP_RESET_X_UM = (498.020, 550.960)          # resetb_h, resetb_l

GPIO_MASTER = "sky130_ef_io__gpiov2_pad"
XRES_MASTER = "sky130_fd_io__top_xres4v2"
SLICE_MASTER = "sky130_ef_io__connect_vcchib_vccd_and_vswitch_vddio_slice_20um"
CLAMP_RE = re.compile(r"sky130_ef_io__(vddio|vssio|vdda|vssa|vccd|vssd)_(hvc|lvc)_clamped(3)?_pad")
CORNER_MASTER = "sky130_ef_io__corner_pad"
DEFAULT_EF_IO_V = os.path.expanduser(
    "~/.ciel/sky130A/libs.ref/sky130_fd_io/verilog/sky130_ef_io.v"
)


# --------------------------------------------------------------------------- #
# Magic parsing
# --------------------------------------------------------------------------- #
class Use:
    __slots__ = ("master", "inst", "xf", "box", "cx", "cy", "side", "domain")

    def __init__(self, master, inst):
        self.master, self.inst = master, inst
        self.xf = self.box = None


def parse_mag(path):
    uses, cur = [], None
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("use "):
                p = line.split()
                cur = Use(p[1], p[2])
                uses.append(cur)
            elif cur is not None and line.startswith("transform "):
                cur.xf = [int(v) for v in line.split()[1:7]]
            elif cur is not None and line.startswith("box "):
                cur.box = [int(v) for v in line.split()[1:5]]
    return uses


def xform_bbox(xf, box):
    a, b, c, d, e, f = xf
    llx, lly, urx, ury = box
    xs, ys = [], []
    for (x, y) in [(llx, lly), (urx, lly), (urx, ury), (llx, ury)]:
        xs.append(a * x + b * y + c)
        ys.append(d * x + e * y + f)
    return min(xs), min(ys), max(xs), max(ys)


def classify(uses):
    W, H = OF_W_UM / UNIT_UM, OF_H_UM / UNIT_UM
    for u in uses:
        if u.xf is None or u.box is None:
            continue
        minx, miny, maxx, maxy = xform_bbox(u.xf, u.box)
        u.cx = (minx + maxx) / 2.0 * UNIT_UM
        u.cy = (miny + maxy) / 2.0 * UNIT_UM
        d = {"S": miny, "N": H - maxy, "W": minx, "E": W - maxx}
        u.side = min(d, key=d.get)


# --------------------------------------------------------------------------- #
# Inventory model
# --------------------------------------------------------------------------- #
GPIO_DOMAIN_BY_SIDE = {"W": "user2", "E": "user1", "N": "user1", "S": "user0"}
# analog rail suffix per domain
DOM_SUF = {"user0": "", "user1": "1", "user2": "2"}


def clamp_info(u):
    """Return (base, domain, pkgnet, clamped3) for a clamp use, else None."""
    m = CLAMP_RE.match(u.master)
    if not m:
        return None
    base, _, three = m.group(1), m.group(2), m.group(3)
    if u.inst.startswith("user1"):
        dom = "user1"
    elif u.inst.startswith("user2"):
        dom = "user2"
    else:
        dom = "user0"
    # package net: vddio/vssio never get a domain suffix; vdda/vssa/vccd/vssd do
    if base in ("vddio", "vssio"):
        pkg = base
    else:
        pkg = base + DOM_SUF[dom]
    return dict(base=base, domain=dom, pkg=pkg, clamped3=bool(three), master=u.master)


def _orient(xf):
    """Decode a Magic 6-int transform into a LibreLane/OpenROAD orientation."""
    a, b, c, d, e, f = xf
    return {
        (1, 0, 0, 1): "N", (0, -1, 1, 0): "R90", (-1, 0, 0, -1): "R180",
        (0, 1, -1, 0): "R270", (-1, 0, 0, 1): "FN", (1, 0, 0, -1): "FS",
        (0, 1, 1, 0): "FE", (0, -1, -1, 0): "FW",
    }[(a, b, d, e)]


class Signal:
    def __init__(self, side, domain, coord):
        self.side, self.domain, self.coord = side, domain, coord
        self.g = None
        self.inst = None
        # openframe per-pad constant_block placement: dict(llx, lly, orient).
        self.cb = None


class Clamp:
    def __init__(self, side, coord, ci):
        self.side, self.coord = side, coord
        self.__dict__.update(ci)
        self.k = None       # index within its package-net vector
        self.inst = None


def build_inventory(uses):
    gpio = [u for u in uses if u.master == GPIO_MASTER]
    clamps = [u for u in uses if CLAMP_RE.match(u.master)]
    # Per-gpio constant_block instances (openframe: one per pad). The xres one
    # (constant_value_xres_inst) is placed separately via CONSTANT_* constants.
    cblk = [u for u in uses if u.master == "constant_block"
            and u.inst.startswith("constant_value_inst")]

    sig_by_side = {s: [] for s in "WENS"}
    clp_by_side = {s: [] for s in "WENS"}
    cb_by_side = {s: [] for s in "WENS"}

    for u in gpio:
        axis = u.cx if u.side in "NS" else u.cy
        sig_by_side[u.side].append(Signal(u.side, GPIO_DOMAIN_BY_SIDE[u.side], axis))
    for u in clamps:
        axis = u.cx if u.side in "NS" else u.cy
        clp_by_side[u.side].append(Clamp(u.side, axis, clamp_info(u)))
    for u in cblk:
        minx, miny, _, _ = xform_bbox(u.xf, u.box)
        axis = u.cx if u.side in "NS" else u.cy
        cb_by_side[u.side].append(
            dict(coord=axis, llx=minx * UNIT_UM, lly=miny * UNIT_UM,
                 orient=_orient(u.xf)))

    for s in "WENS":
        sig_by_side[s].sort(key=lambda o: o.coord)
        clp_by_side[s].sort(key=lambda o: o.coord)
        cb_by_side[s].sort(key=lambda d: d["coord"])
        # openframe has exactly one constant_block per gpio pad; attach each to
        # its pad in the same per-side coord order.
        for o, cb in zip(sig_by_side[s], cb_by_side[s]):
            o.cb = dict(llx=cb["llx"], lly=cb["lly"], orient=cb["orient"])

    # East ring is kept as openframe but shifted to the double-wide east edge;
    # its constant_blocks move with it (+HALF in x, the perpendicular axis).
    for o in sig_by_side["E"]:
        if o.cb:
            o.cb["llx"] += HALF_UM

    # Reference for synthesizing the mid-seam const blocks (N/S have no openframe
    # counterpart): fixed perpendicular coord + along-edge delta from pad center.
    seam_cb = {}
    for s in "NS":
        r = sig_by_side[s][0]
        seam_cb[s] = dict(dalong=r.cb["llx"] - r.coord,
                          perp=r.cb["lly"], orient=r.cb["orient"])

    # ---- duplicate north/south ------------------------------------------- #
    def dup(objs, cls_axis_only=False):
        out = []
        for o in objs:                      # left copy (original x)
            out.append(o)
        for o in objs:                      # right copy (+HALF)
            if isinstance(o, Signal):
                n = Signal(o.side, o.domain, o.coord + HALF_UM)
                if o.cb:
                    n.cb = dict(o.cb)
                    n.cb["llx"] += HALF_UM
            else:
                n = Clamp(o.side, o.coord + HALF_UM,
                          dict(base=o.base, domain=o.domain, pkg=o.pkg,
                               clamped3=o.clamped3, master=o.master))
            out.append(n)
        out.sort(key=lambda o: o.coord)
        return out

    sig_by_side["N"] = dup(sig_by_side["N"])
    sig_by_side["S"] = dup(sig_by_side["S"])
    clp_by_side["N"] = dup(clp_by_side["N"])
    clp_by_side["S"] = dup(clp_by_side["S"])

    # ---- fill N/S mid-seam with extra GPIOs at the existing pitch -------- #
    # Duplicating left/right openframe halves leaves an empty seam around
    # X=3588. Branding moves into left-half gaps; these pads occupy the seam.
    # North: after left-half gpio @ 3169.977, pitch 257 -> 3426.977, 3683.977
    # South: after left-half clamp_vdda @ 3151.500, pitch 274 -> 3425.500, 3699.500
    for coord in (3426.977, 3683.977):
        sig_by_side["N"].append(Signal("N", GPIO_DOMAIN_BY_SIDE["N"], coord))
    for coord in (3425.500, 3699.500):
        sig_by_side["S"].append(Signal("S", GPIO_DOMAIN_BY_SIDE["S"], coord))
    sig_by_side["N"].sort(key=lambda o: o.coord)
    sig_by_side["S"].sort(key=lambda o: o.coord)

    # Synthesize constant_block placement for the mid-seam pads (openframe has
    # none there): same perpendicular + orientation as the side, along-edge
    # position offset from the seam pad center like the openframe pads.
    for s in "NS":
        r = seam_cb[s]
        for o in sig_by_side[s]:
            if o.cb is None:
                o.cb = dict(llx=o.coord + r["dalong"], lly=r["perp"],
                            orient=r["orient"])

    # ---- assign global gpio index (W, E, N, S) --------------------------- #
    g = 0
    for s in "WENS":
        for o in sig_by_side[s]:
            o.g = g
            o.inst = f"gpio_{s.lower()}[{sum(1 for x in sig_by_side[s][:sig_by_side[s].index(o)])}].u"
            g += 1
    # re-do per-side local index cleanly
    for s in "WENS":
        for i, o in enumerate(sig_by_side[s]):
            o.inst = f"gpio_{s.lower()}[{i}].u"
    n_gpio = g

    # ---- assign clamp package-net vector indices ------------------------- #
    pkg_counts = {}
    # deterministic order: by side W,E,N,S then coord
    for s in "WENS":
        for c in clp_by_side[s]:
            c.k = pkg_counts.get(c.pkg, 0)
            pkg_counts[c.pkg] = c.k + 1
            c.inst = f"clamp_{c.pkg}_{c.k}"

    return dict(
        sig=sig_by_side,
        clp=clp_by_side,
        n_gpio=n_gpio,
        pkg_counts=pkg_counts,
        reset=dict(side=RESET_SIDE, coord=RESET_BOND_UM, inst=RESET_INST),
    )


# --------------------------------------------------------------------------- #
# RTL emission helpers
# --------------------------------------------------------------------------- #
def abut(domain):
    """Inline gpiov2/clamp/corner abutment power pins.

    The analog rails (VSSA/VDDA), like the rest of the sky130 IO ring
    (AMUXBUS/VDDIO_Q/VSSIO_Q/VCCHIB/VSWITCH/VDDIO/VCCD/VSSIO/VSSD), run
    continuously through every pad, corner and filler cell. They therefore
    form a single ring net each and are wired to the global vssa/vdda nodes.
    The per-domain analog grounds (vssa1/vssa2/vdda1/vdda2) are simply extra
    bond pads onto this same ring, and the isolated multi-domain power that the
    openframe preserves is the *core* power (vccd/vssd/vccd1/... ), which is not
    on the abutment ring but carried by the clamped3 cells and the user wrapper.
    The `domain` argument is retained for call-site clarity but no longer alters
    the ring nets (doing so made connect_by_abutment reject the domain seams).
    """
    del domain
    return (
        "        .AMUXBUS_A(analog_a), .AMUXBUS_B(analog_b),\n"
        "`ifdef USE_POWER_PINS\n"
        "        .VSSA(vssa), .VDDA(vdda), .VSWITCH(vddio), .VDDIO_Q(vddio_q),\n"
        "        .VCCHIB(vccd), .VDDIO(vddio), .VCCD(vccd), .VSSIO(vssio),\n"
        "        .VSSD(vssd), .VSSIO_Q(vssio_q),\n"
        "`endif\n"
    )


def emit_signal_loop(side, sigs):
    """Emit one generate loop of gpiov2 pass-through pads for a side."""
    if not sigs:
        return ""
    dom = sigs[0].domain
    n = len(sigs)
    base = sigs[0].g
    sl = side.lower()
    return f"""
    // ---- {side} side signal pads ({n}) : domain {dom} ----
    generate for (genvar i = 0; i < {n}; i = i + 1) begin : gpio_{sl}
        wire tie_hi, tie_lo;
        // openframe per-pad constant one/zero (buffered 1.8V). `one` drives the
        // pad ENABLE_VDDIO; both are exported to the user wrapper for loopback.
        constant_block const_val (
`ifdef USE_POWER_PINS
            .vccd(vccd),
            .vssd(vssd),
`endif
            .one(gpio_loopback_one[{base} + i]),
            .zero(gpio_loopback_zero[{base} + i])
        );
        sky130_ef_io__gpiov2_pad u (
{abut(dom)}\
`ifndef TOP_ROUTING
            .PAD(gpio_pad[{base} + i]),
`endif
            .OUT(gpio_out[{base} + i]),
            .OE_N(gpio_oeb[{base} + i]),
            .HLD_H_N(tie_hi),
            // ENABLE_H/VDDA_H: openframe ties these to porb_h. Automated DRT
            // cannot fan porb_h out from simple_por's tiny met3 nub to every
            // pad, so keep local tie-offs here (the south reset pad's ENABLE_H
            // is tied locally the same way).
            .ENABLE_H(tie_hi),
            .ENABLE_INP_H(tie_lo),
            .ENABLE_VDDA_H(tie_hi),
            .ENABLE_VSWITCH_H(tie_lo),
            .ENABLE_VDDIO(gpio_loopback_one[{base} + i]),
            .INP_DIS(gpio_inp_dis[{base} + i]),
            .IB_MODE_SEL(gpio_ib_mode_sel[{base} + i]),
            .VTRIP_SEL(gpio_vtrip_sel[{base} + i]),
            .SLOW(gpio_slow_sel[{base} + i]),
            .HLD_OVR(gpio_holdover[{base} + i]),
            .ANALOG_EN(gpio_analog_en[{base} + i]),
            .ANALOG_SEL(gpio_analog_sel[{base} + i]),
            .ANALOG_POL(gpio_analog_pol[{base} + i]),
            .DM({{gpio_dm2[{base} + i], gpio_dm1[{base} + i], gpio_dm0[{base} + i]}}),
            .PAD_A_NOESD_H(analog_noesd_io[{base} + i]),
            .PAD_A_ESD_0_H(analog_io[{base} + i]),
            .PAD_A_ESD_1_H(),
            .IN(gpio_in[{base} + i]),
            .IN_H(gpio_in_h[{base} + i]),
            .TIE_HI_ESD(tie_hi),
            .TIE_LO_ESD(tie_lo)
        );
    end endgenerate
"""


HV_FN = {"vddio": "VDDIO_PAD", "vssio": "VSSIO_PAD",
         "vdda": "VDDA_PAD", "vssa": "VSSA_PAD"}
LV_FN = {"vccd": "VCCD_PAD", "vssd": "VSSD_PAD"}


def emit_clamp(c):
    """Emit a single power clamp pad instance."""
    padport_line = ""
    extra = ""
    if c.base in HV_FN:
        fn = HV_FN[c.base]
        padport_line = f"        .{fn}({c.pkg}_pad[{c.k}])\n"
    else:
        fn = LV_FN[c.base]
        if c.clamped3:
            d = c.domain
            # VCCD1/VSSD1 are the core-side power pins of the clamped3 cell.
            # They must be guarded by USE_POWER_PINS: in the (non power-aware)
            # synthesis pass the pad cells come from Liberty blackboxes, whose
            # pg_pins are NOT exposed as module ports, so connecting them there
            # is an error. The power-aware passes (JSON header) parse the full
            # Verilog models and do expose these pins.
            extra = (f"`ifdef USE_POWER_PINS\n"
                     f"        .VCCD1(vccd{DOM_SUF[d]}), .VSSD1(vssd{DOM_SUF[d]}),\n"
                     f"`endif\n")
        padport_line = f"        .{fn}({c.pkg}_pad[{c.k}])\n"
    # The analog ESD/ground abutment rail (VSSA/VDDA) is continuous within a
    # side, so its domain must follow the pad's physical side, not the clamp's
    # instance name. Domain-agnostic clamps (vssio/vddio) would otherwise inject
    # an isolated foreign-domain net between same-domain neighbours, which the
    # padring's connect_by_abutment rejects.
    return f"""
    sky130_ef_io__{c.master.split('__')[1]} {c.inst} (
{abut(GPIO_DOMAIN_BY_SIDE[c.side])}\
{extra}\
`ifndef TOP_ROUTING
{padport_line}\
`endif
    );
"""


def emit_corner(idx):
    return f"""
    sky130_ef_io__corner_pad corner_{idx} (
`ifndef TOP_ROUTING
        .VSSIO(vssio), .VDDIO(vddio), .VDDIO_Q(vddio_q), .VSSIO_Q(vssio_q),
        .AMUXBUS_A(analog_a), .AMUXBUS_B(analog_b),
        .VSSD(vssd), .VSSA(vssa), .VSWITCH(vddio), .VDDA(vdda),
        .VCCD(vccd), .VCCHIB(vccd)
`endif
    );
"""


# --------------------------------------------------------------------------- #
# Full RTL generation
# --------------------------------------------------------------------------- #
GPIO_VEC_SIGS_IN = [   # driven by the user-area wrapper -> pad
    "gpio_out", "gpio_oeb", "gpio_inp_dis", "gpio_ib_mode_sel", "gpio_vtrip_sel",
    "gpio_slow_sel", "gpio_holdover", "gpio_analog_en", "gpio_analog_sel",
    "gpio_analog_pol", "gpio_dm0", "gpio_dm1", "gpio_dm2",
]
GPIO_VEC_SIGS_OUT = [  # pad -> user-area wrapper
    "gpio_in", "gpio_in_h",
]
GPIO_VEC_SIGS_INOUT = ["analog_io", "analog_noesd_io"]
# Per-pad buffered constant one/zero (openframe constant_block outputs). Driven
# inside the padframe by one constant_block per GPIO; pad -> wrapper (wrapper
# input) so the user project can loop them back to any pad control.
GPIO_VEC_SIGS_LOOPBACK = ["gpio_loopback_one", "gpio_loopback_zero"]

# gpiov2 core-side signal pins in ascending pad-local-x order (extracted from
# sky130_ef_io__gpiov2_pad.lef). Used to arrange the user-wrapper boundary pins
# so every pad->wrapper net is a straight, non-crossing hop.
GPIO_PAD_PIN_ORDER = [
    "gpio_in_h", "gpio_oeb", "gpio_ib_mode_sel", "gpio_vtrip_sel", "gpio_out",
    "gpio_holdover", "gpio_dm2", "gpio_analog_sel", "gpio_inp_dis",
    "gpio_analog_pol", "gpio_dm0", "gpio_analog_en", "analog_noesd_io",
    "gpio_dm1", "analog_io", "gpio_slow_sel", "gpio_in",
]

CORE_RAILS = ["vddio", "vssio", "vccd", "vssd", "vdda", "vssa",
              "vdda1", "vssa1", "vccd1", "vssd1",
              "vdda2", "vssa2", "vccd2", "vssd2"]


def emit_por():
    """Power-on-reset macro (placed via LibreLane MACROS at fixed coords)."""
    return f"""
    // ---- power-on-reset (simple_por; fixed MACROS placement) ----
    // All three POR outputs (porb_h, porb_l, por_l) go to the user wrapper
    // (west-edge pins abutting the POR Y-band). porb_h no longer crosses to the
    // south reset pad -- that pad's ENABLE_H is tied locally (see master reset).
    wire porb_h, porb_l, por_l;

    simple_por {POR_INST} (
`ifdef USE_POWER_PINS
        .vdd3v3(vddio),
        .vdd1v8(vccd),
        .vss3v3(vssio),
        .vss1v8(vssd),
`endif
        .porb_h(porb_h),
        .porb_l(porb_l),
        .por_l(por_l)
    );
"""


def emit_reset_subsystem():
    """Openframe master reset: constant_block + xres4v2 + xres_buf -> wrapper."""
    return f"""
    // ---- master reset (south xres4v2; openframe connectivity) ----
    wire xres_loopback_one, xres_loopback_zero;
    wire xresloop, xres_vss_loop, xres_tie_hi;
    wire resetb_h, resetb_l;

    constant_block {CONSTANT_INST} (
`ifdef USE_POWER_PINS
        .vccd(vccd),
        .vssd(vssd),
`endif
        .one(xres_loopback_one),
        .zero(xres_loopback_zero)
    );

    {XRES_MASTER} {RESET_INST} (
{abut("user0")}\
`ifndef TOP_ROUTING
        .PAD(resetb_pad),
`endif
        .TIE_WEAK_HI_H(xresloop),
        .TIE_HI_ESD(xres_tie_hi),
        .TIE_LO_ESD(xres_vss_loop),
        .PAD_A_ESD_H(xresloop),
        .XRES_H_N(resetb_h),
        .DISABLE_PULLUP_H(xres_vss_loop),
        // ENABLE_H: openframe ties this to porb_h, but porb_h lives on the west
        // POR and cannot be auto-routed across the die to this south pad. Tie it
        // locally to the pad's own ESD-safe high (same pattern as the GPIO pads);
        // a reset input pad is fine always-enabled. porb_h now only feeds the wrapper.
        .ENABLE_H(xres_tie_hi),
        .EN_VDDIO_SIG_H(xres_vss_loop),
        .INP_SEL_H(xres_vss_loop),
        .FILT_IN_H(xres_vss_loop),
        .PULLUP_H(xres_vss_loop),
        .ENABLE_VDDIO(xres_loopback_one)
    );

    // 3.3V resetb_h -> 1.8V resetb_l for the user wrapper
    xres_buf {XRES_BUF_INST} (
`ifdef USE_POWER_PINS
        .VPWR(vddio),
        .LVPWR(vccd),
        .LVGND(vssd),
        .VGND(vssio),
`endif
        .A(resetb_h),
        .X(resetb_l)
    );
"""


def gen_padframe_rtl(inv):
    n = inv["n_gpio"]
    pkg = inv["pkg_counts"]

    # top-level bond-pad ports
    pad_ports = [f"    inout [{n-1}:0] gpio_pad"]
    pad_ports.append("    inout resetb_pad")
    for name in sorted(pkg):
        pad_ports.append(f"    inout [{pkg[name]-1}:0] {name}_pad")

    # wrapper-facing internal wires
    body = []
    body.append("    // Internal analog / quiet-rail nets")
    body.append("    wire analog_a, analog_b, vddio_q, vssio_q;")
    body.append("")
    body.append("    // Core-side power rails (driven by clamps, shared with user area)")
    body.append("`ifdef USE_POWER_PINS")
    body.append("    wire " + ", ".join(CORE_RAILS) + ";")
    body.append("`endif")
    body.append("")
    for s in GPIO_VEC_SIGS_IN:
        body.append(f"    wire [{n-1}:0] {s};")
    for s in GPIO_VEC_SIGS_OUT:
        body.append(f"    wire [{n-1}:0] {s};")
    for s in GPIO_VEC_SIGS_INOUT:
        body.append(f"    wire [{n-1}:0] {s};")
    for s in GPIO_VEC_SIGS_LOOPBACK:
        body.append(f"    wire [{n-1}:0] {s};")
    body.append("")

    # POR before reset/GPIO: reset ENABLE_H and (openframe) gpio ENABLE use porb_h.
    body.append(emit_por())
    body.append(emit_reset_subsystem())

    # signal pad loops
    for s in "WENS":
        body.append(emit_signal_loop(s, inv["sig"][s]))

    # clamp pads
    body.append("    // ---- power clamp pads (preserved multi-domain) ----")
    for s in "WENS":
        for c in inv["clp"][s]:
            body.append(emit_clamp(c))

    # corner cells: NOT instantiated in RTL. In the LibreLane Chip flow the 4
    # outer corners are created physically by `place_corners` in pad_cfg.tcl and
    # tied into the ring by `connect_by_abutment` (same approach as the
    # sky130-fabulous-testchip), so they must not appear in the netlist.
    body.append("    // ---- corner cells: placed physically by pad_cfg.tcl "
                "(place_corners), not instantiated here ----")

    # power-domain bridge slices (VCCHIB<->VCCD, VSWITCH<->VDDIO), 2 per side.
    # Wire the full LEF pin list (not the 4-pin sky130_ef_io.v stub) so LibreLane
    # / netgen agree with Magic abstract extract of the LEF view.
    body.append("""
    // ---- power-domain bridge slices ----
    generate for (genvar i = 0; i < 8; i = i + 1) begin : vcchib_vccd_and_vswitch_vddio_slices
        (* keep *)
        sky130_ef_io__connect_vcchib_vccd_and_vswitch_vddio_slice_20um u (
            .AMUXBUS_A(analog_a),
            .AMUXBUS_B(analog_b),
`ifdef USE_POWER_PINS
            .VSSA(vssa),
            .VDDA(vdda),
            .VSWITCH(vddio),
            .VDDIO_Q(vddio_q),
            .VCCHIB(vccd),
            .VDDIO(vddio),
            .VCCD(vccd),
            .VSSIO(vssio),
            .VSSD(vssd),
            .VSSIO_Q(vssio_q)
`endif
        );
    end endgenerate
""")

    # user-area wrapper instance
    conn = []
    conn.append("`ifdef USE_POWER_PINS")
    conn.append("        .vddio(vddio), .vssio(vssio), .vccd(vccd), .vssd(vssd),")
    # Every wrapper power pin connects to its identically-named net. This is a
    # hard requirement of Odb.SetPowerConnections: it re-applies the JSON-netlist
    # power connections onto the placed macro, and OpenROAD's addGlobalConnect
    # only succeeds when the pin is already bound to that same net (macro power
    # pins are auto-bound by name during floorplan, which reads the non-powered
    # netlist). Wiring e.g. pin `vdda1` to net `vdda` makes 0 connections -> error.
    #
    # The multi-domain *core* supplies (vccd/vccd1/vccd2, vssd/vssd1/vssd2) are
    # genuinely isolated and sourced by the clamped3 pads. The per-domain analog
    # rails (vdda1/vdda2/vssa1/vssa2) are their own nets here; the sky130 corner
    # cell bridges VSSA/VDDA across sides, so the *abutment* ESD ring is a single
    # vdda/vssa net (see abut()), and these per-domain analog pins terminate on
    # the user wrapper (their PDN ring is built from PDN_MACRO_CONNECTIONS).
    conn.append("        .vdda(vdda), .vssa(vssa),")
    conn.append("        .vdda1(vdda1), .vssa1(vssa1), .vccd1(vccd1), .vssd1(vssd1),")
    conn.append("        .vdda2(vdda2), .vssa2(vssa2), .vccd2(vccd2), .vssd2(vssd2),")
    conn.append("`endif")
    for p in WRAPPER_CONTROL_PINS:
        conn.append(f"        .{p}({p}),")
    all_vecs = (GPIO_VEC_SIGS_OUT + GPIO_VEC_SIGS_IN + GPIO_VEC_SIGS_INOUT
                + GPIO_VEC_SIGS_LOOPBACK)
    conn += [f"        .{v}({v})," for v in all_vecs]
    conn[-1] = conn[-1].rstrip(",")
    body.append(f"""
    // ---- user-area wrapper (the double-wide openframe user project) ----
    double_wide_openframe_project_wrapper user_project (
{os.linesep.join(conn)}
    );
""")

    # Branding macros: pinless keep-instances placed via LibreLane MACROS in the
    # left-half north/south pad-ring gaps (mid-seam holds extra GPIOs).
    body.append("""
    // ---- branding (placed by LibreLane MACROS; no electrical pins) ----
    (* keep *) open_source open_source ();
    (* keep *) project_id_textblock project_id_textblock ();
    (* keep *) logo_dw_openframe logo_dw_openframe ();
""")

    ports = ",\n".join(pad_ports)
    return f"""// AUTO-GENERATED by scripts/extract_openframe_pads.py  --  do not edit by hand.
//
// Double-wide openframe padframe: pad ring + openframe-style POR / reset.
// Left/right sides replicate the caravel openframe; top/bottom rows are the
// openframe rows duplicated across the doubled width. simple_por sits in the
// west ring gap; the xres4v2 reset pad is on the south edge (bond @
// {RESET_BOND_UM:.3f} um) with constant_block + xres_buf like openframe.
//
// {n} signal GPIOs total + resetb_pad.

`default_nettype none

`include "dw_defines.vh"

module double_wide_chip_io (
{ports}
);
{os.linesep.join(body)}
endmodule

`default_nettype wire
"""


def gen_wrapper_rtl(inv, empty=True):
    n = inv["n_gpio"]
    lines = []
    lines.append("// AUTO-GENERATED by scripts/extract_openframe_pads.py")
    lines.append("//")
    lines.append("// Empty double-wide openframe user-area wrapper (pin template).")
    lines.append("// Users instantiate their design inside this module, keeping the port")
    lines.append("// list and cell footprint identical, then re-harden and cell-swap.")
    lines.append("")
    lines.append("`default_nettype none")
    lines.append("")
    lines.append("module double_wide_openframe_project_wrapper (")
    lines.append("`ifdef USE_POWER_PINS")
    lines.append("    inout vddio, vssio, vccd, vssd, vdda, vssa,")
    lines.append("    inout vdda1, vssa1, vccd1, vssd1,")
    lines.append("    inout vdda2, vssa2, vccd2, vssd2,")
    lines.append("`endif")
    lines.append("    // Frame POR / reset (openframe-compatible)")
    for p in WRAPPER_CONTROL_PINS:
        lines.append(f"    input  {p},")
    for s in GPIO_VEC_SIGS_OUT:      # pad -> wrapper => wrapper input
        lines.append(f"    input  [{n-1}:0] {s},")
    for s in GPIO_VEC_SIGS_LOOPBACK:  # constant one/zero: pad -> wrapper input
        lines.append(f"    input  [{n-1}:0] {s},")
    for s in GPIO_VEC_SIGS_IN:       # wrapper -> pad => wrapper output
        lines.append(f"    output [{n-1}:0] {s},")
    io = ",\n".join(f"    inout  [{n-1}:0] {s}" for s in GPIO_VEC_SIGS_INOUT)
    lines.append(io)
    lines.append(");")
    lines.append("")
    if empty:
        lines.append("    // Empty template: drive all pads to a safe high-impedance input state.")
        lines.append(f"    assign gpio_out       = {n}'b0;")
        lines.append(f"    assign gpio_oeb       = {{{n}{{1'b1}}}};   // output disabled")
        lines.append(f"    assign gpio_inp_dis   = {n}'b0;")
        lines.append(f"    assign gpio_ib_mode_sel = {n}'b0;")
        lines.append(f"    assign gpio_vtrip_sel = {n}'b0;")
        lines.append(f"    assign gpio_slow_sel  = {n}'b0;")
        lines.append(f"    assign gpio_holdover  = {n}'b0;")
        lines.append(f"    assign gpio_analog_en = {n}'b0;")
        lines.append(f"    assign gpio_analog_sel = {n}'b0;")
        lines.append(f"    assign gpio_analog_pol = {n}'b0;")
        lines.append(f"    assign gpio_dm0       = {{{n}{{1'b1}}}};")
        lines.append(f"    assign gpio_dm1       = {n}'b0;")
        lines.append(f"    assign gpio_dm2       = {n}'b0;")
    lines.append("")
    lines.append("endmodule")
    lines.append("")
    lines.append("`default_nettype wire")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# LibreLane pad tables
# --------------------------------------------------------------------------- #
SIDE_NAME = {"S": "PAD_SOUTH", "E": "PAD_EAST", "N": "PAD_NORTH", "W": "PAD_WEST"}


def side_ordered(inv, s):
    """Return list of (coord, inst_name) for all real pads on side s, sorted."""
    items = []
    for o in inv["sig"][s]:
        items.append((o.coord, o.inst))
    for c in inv["clp"][s]:
        items.append((c.coord, c.inst))
    rst = inv.get("reset")
    if rst and rst["side"] == s:
        items.append((rst["coord"], rst["inst"]))
    items.sort(key=lambda t: t[0])
    return items


def tcl_escape(inst):
    # gpio_w[0].u -> gpio_w\\[0\\].u  (for pad_cfg findInst)
    return inst.replace("[", "\\[").replace("]", "\\]")


def gen_pad_pos_tcl(inv):
    lines = ["# AUTO-GENERATED bond-pad-center coordinates (um) for the double-wide ring.",
             "set caravel_pad_pos [dict create]", ""]
    for s in "SENW":
        coords = [f"{c:.3f}" for (c, _) in side_ordered(inv, s)]
        lines.append(f"dict set caravel_pad_pos {SIDE_NAME[s]} \"\\")
        for c in coords:
            lines.append(f"    {c} \\")
        lines.append("\"")
        lines.append("")
    return "\n".join(lines)


def gen_pad_lists_yaml(inv):
    lines = ["# AUTO-GENERATED per-side ordered pad instance lists (match pad_pos.tcl)."]
    for s in "SENW":
        lines.append(f"{SIDE_NAME[s]}: [")
        items = side_ordered(inv, s)
        for i, (_, inst) in enumerate(items):
            esc = inst.replace("[", "\\\\[").replace("]", "\\\\]")
            comma = "," if i < len(items) - 1 else ""
            lines.append(f'    "{esc}"{comma}')
        lines.append("]")
    return "\n".join(lines)


def _yaml_pad_block(inv, s):
    items = side_ordered(inv, s)
    out = [f"{SIDE_NAME[s]}: ["]
    for i, (_, inst) in enumerate(items):
        esc = inst.replace("[", "\\\\[").replace("]", "\\\\]")
        comma = "," if i < len(items) - 1 else ""
        out.append(f'  "{esc}"{comma}')
    out.append("]")
    return "\n".join(out)


# Corner-aware std-cell liberty map for OpenROAD STA. Pad cells are blackboxed
# via PAD_VERILOG_MODELS (not behavioral sky130_ef_io.v in VERILOG_FILES) so
# Yosys/OpenROAD keep ef_io composites as single LEF instances; listing pad
# .lib here makes Yosys liberty blackboxes that omit pg_pin ports. PAD_LIBS is
# cleared so LibreLane 3.0.x does not pass corner-key dict entries to OpenROAD.
_SCL_LIB = "pdk_dir::libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__{}.lib"


def _verilog_files_block():
    # Blackboxes first (LEF-accurate port lists), then design RTL. Clear
    # PAD_VERILOG_MODELS so the PDK sky130_ef_io.v stubs (e.g. 4-pin connect)
    # do not override or clash with our blackboxes.
    return "\n".join(
        [
            "VERILOG_FILES:",
            "- dir::../../verilog/rtl/pad_ef_io_blackboxes.v",
            "- dir::../../verilog/rtl/por_reset_blackboxes.v",
            "- dir::../../verilog/rtl/double_wide_chip_io.v",
            "",
            "PAD_VERILOG_MODELS: []",
        ]
    )


def _ef_io_pad_modules(inv):
    mods = {GPIO_MASTER, SLICE_MASTER}
    for side in "WENS":
        for c in inv["clp"][side]:
            mods.add(c.master)
    return sorted(mods)


def gen_por_reset_blackboxes_v():
    """Blackboxes for POR / reset macros + the xres4v2 pad cell."""
    return f"""// AUTO-GENERATED by scripts/extract_openframe_pads.py -- do not edit by hand.
// Blackboxes for simple_por, xres_buf, constant_block, and sky130_fd_io__top_xres4v2.

`default_nettype none

module simple_por (
`ifdef USE_POWER_PINS
    inout vdd3v3,
    inout vdd1v8,
    inout vss3v3,
    inout vss1v8,
`endif
    output porb_h,
    output porb_l,
    output por_l
);
endmodule

module constant_block (
`ifdef USE_POWER_PINS
    inout vccd,
    inout vssd,
`endif
    output one,
    output zero
);
endmodule

module xres_buf (
`ifdef USE_POWER_PINS
    inout VPWR,
    inout LVPWR,
    inout LVGND,
    inout VGND,
`endif
    input  A,
    output X
);
endmodule

module {XRES_MASTER} (
    XRES_H_N, AMUXBUS_A, AMUXBUS_B, PAD, DISABLE_PULLUP_H, ENABLE_H,
    EN_VDDIO_SIG_H, INP_SEL_H, FILT_IN_H, PULLUP_H, ENABLE_VDDIO,
    PAD_A_ESD_H, TIE_HI_ESD, TIE_LO_ESD, TIE_WEAK_HI_H,
    VCCD, VCCHIB, VDDA, VDDIO, VDDIO_Q, VSSA, VSSD, VSSIO, VSSIO_Q, VSWITCH
);
  output XRES_H_N;
  inout  AMUXBUS_A, AMUXBUS_B, PAD, PULLUP_H, PAD_A_ESD_H, TIE_WEAK_HI_H;
  input  DISABLE_PULLUP_H, ENABLE_H, EN_VDDIO_SIG_H, INP_SEL_H, FILT_IN_H, ENABLE_VDDIO;
  output TIE_HI_ESD, TIE_LO_ESD;
  inout  VCCD, VCCHIB, VDDA, VDDIO, VDDIO_Q, VSSA, VSSD, VSSIO, VSSIO_Q, VSWITCH;
endmodule

`default_nettype wire
"""


def _parse_ef_io_module_ports(ef_io_v, module_name):
    with open(ef_io_v) as f:
        text = f.read()
    m = re.search(
        rf"module\s+{re.escape(module_name)}\s*\((.*?)\)\s*;",
        text,
        re.DOTALL,
    )
    if not m:
        raise KeyError(f"{module_name} not found in {ef_io_v}")
    return [p.strip() for p in re.split(r"[,\n]", m.group(1)) if p.strip()]


def _parse_ef_io_module_port_widths(ef_io_v, module_name):
    """Return port -> bus range (e.g. '[2:0]') from sky130_ef_io.v body declarations."""
    with open(ef_io_v) as f:
        text = f.read()
    m = re.search(
        rf"module\s+{re.escape(module_name)}\s*\(.*?\)\s*;\s*(.*?)\nendmodule",
        text,
        re.DOTALL,
    )
    if not m:
        raise KeyError(f"{module_name} body not found in {ef_io_v}")
    widths = {}
    for line in m.group(1).splitlines():
        line = line.split("//")[0].strip()
        decl = re.match(
            r"(?:input|output|inout)\s+((?:\[[^\]]+\]\s*)?)([A-Za-z0-9_,\s]+)\s*;",
            line,
        )
        if not decl:
            continue
        bus = decl.group(1).strip()
        for port in decl.group(2).split(","):
            port = port.strip()
            if port:
                widths[port] = bus
    return widths


# LEF pin order for cells whose sky130_ef_io.v stub is incomplete (connect has
# only 4 ports in verilog but 12 in LEF). Prefer LEF so PnR + abstract LVS match.
_LEF_PIN_OVERRIDES = {
    "sky130_ef_io__connect_vcchib_vccd_and_vswitch_vddio_slice_20um": [
        "AMUXBUS_A", "AMUXBUS_B", "VSSA", "VDDA", "VSWITCH", "VDDIO_Q",
        "VCCHIB", "VDDIO", "VCCD", "VSSIO", "VSSD", "VSSIO_Q",
    ],
    "sky130_ef_io__com_bus_slice_1um": [
        "AMUXBUS_A", "AMUXBUS_B", "VSSA", "VDDA", "VSWITCH", "VDDIO_Q",
        "VCCHIB", "VDDIO", "VCCD", "VSSIO", "VSSD", "VSSIO_Q",
    ],
    "sky130_ef_io__com_bus_slice_5um": [
        "AMUXBUS_A", "AMUXBUS_B", "VSSA", "VDDA", "VSWITCH", "VDDIO_Q",
        "VCCHIB", "VDDIO", "VCCD", "VSSIO", "VSSD", "VSSIO_Q",
    ],
    "sky130_ef_io__com_bus_slice_10um": [
        "AMUXBUS_A", "AMUXBUS_B", "VSSA", "VDDA", "VSWITCH", "VDDIO_Q",
        "VCCHIB", "VDDIO", "VCCD", "VSSIO", "VSSD", "VSSIO_Q",
    ],
    "sky130_ef_io__com_bus_slice_20um": [
        "AMUXBUS_A", "AMUXBUS_B", "VSSA", "VDDA", "VSWITCH", "VDDIO_Q",
        "VCCHIB", "VDDIO", "VCCD", "VSSIO", "VSSD", "VSSIO_Q",
    ],
    "sky130_ef_io__corner_pad": [
        "AMUXBUS_A", "AMUXBUS_B", "VSSA", "VDDA", "VSWITCH", "VDDIO_Q",
        "VCCHIB", "VDDIO", "VCCD", "VSSIO", "VSSD", "VSSIO_Q",
    ],
}


def gen_pad_ef_io_blackboxes_v(inv, ef_io_v=DEFAULT_EF_IO_V):
    lines = [
        "// AUTO-GENERATED by scripts/extract_openframe_pads.py -- do not edit by hand.",
        "// Empty ef_io composite-pad blackboxes for Yosys/OpenROAD (-lib read).",
        "// Ports from sky130_ef_io.v, with LEF overrides where the verilog stub is short.",
        "",
        "`default_nettype none",
        "",
    ]
    modules = set(_ef_io_pad_modules(inv)) | set(_LEF_PIN_OVERRIDES)
    for module in sorted(modules):
        if module in _LEF_PIN_OVERRIDES:
            ports = _LEF_PIN_OVERRIDES[module]
            widths = {}
        else:
            ports = _parse_ef_io_module_ports(ef_io_v, module)
            widths = _parse_ef_io_module_port_widths(ef_io_v, module)
        port_csv = ", ".join(ports)
        lines.append(f"module {module} ({port_csv});")
        for port in ports:
            bus = widths.get(port, "")
            if bus:
                lines.append(f"  inout {bus} {port};")
            else:
                lines.append(f"  inout {port};")
        lines.append("endmodule")
        lines.append("")
    lines.append("`default_nettype wire")
    lines.append("")
    return "\n".join(lines)


def _routing_obstructions_yaml(inv):
    """Pad-ring OBS with west (POR) + south (reset) windows cut for DRT.

    The reset / POR cluster is routed by TritonRoute rather than marked SPECIAL,
    so the full-ring obstruction is split on the west and south edges to leave a
    gap over the POR cell / porb pin band and the xres pad / xres_buf column.
    """
    d = ROUTE_OBS_DEPTH_UM
    sx0, sx1 = RESET_ROUTE_WINDOW_S_UM
    wy0, wy1 = POR_ROUTE_WINDOW_W_UM
    dw = "expr::$DIE_AREA[2]"
    dh = "expr::$DIE_AREA[3]"
    lines = ["ROUTING_OBSTRUCTIONS:"]
    for L in ROUTE_OBS_LAYERS:      # West edge, split around the POR window
        lines.append(f"- [{L}, 0, 0, {d}, {wy0}]")
        lines.append(f'- [{L}, 0, {wy1}, {d}, "{dh}"]')
    for L in ROUTE_OBS_LAYERS:      # East edge, full height
        lines.append(f'- [{L}, "expr::$DIE_AREA[2] - {d}", 0, "{dw}", "{dh}"]')
    for L in ROUTE_OBS_LAYERS:      # South edge, split around the reset window
        lines.append(f"- [{L}, 0, 0, {sx0}, {d}]")
        lines.append(f'- [{L}, {sx1}, 0, "{dw}", {d}]')
    for L in ROUTE_OBS_LAYERS:      # North edge, full width
        lines.append(f'- [{L}, 0, "expr::$DIE_AREA[3] - {d}", "{dw}", "{dh}"]')
    lines.extend(_pad_obstruction_lines(inv))
    # NOTE: _pad_pin_notch_lines() (walling the *whole* pin-tip strip on met2,
    # notched per pin) shorts DRT (72 shorts) -- the strip carries the dense 25-pin
    # fan-out. Use the minimal DM[0]-only version instead.
    lines.extend(_pad_dm0_wall_lines(inv))
    return "\n".join(lines)


def _pad_dm0_wall_lines(inv):
    """met2 walls flanking each gpio pad's DM[0] pin, in the deep pin-tip band.

    All the m2.2 near-misses are the DM[0] met2 tip stub. Wall the two small gaps
    on either side of DM[0]'s notch (deep band only) so the DM[0] route drops
    straight down through the notch instead of grazing the pad met2 to 0.09um. The
    rest of the strip (and the shallower fan-out region) stays open.
    """
    d0 = DM0_WALL_D0_UM
    d1 = PIN_STRIP_DEPTH_UM
    lines = ["# Per-pad DM[0] flank walls (deep pin-tip band) to clear m2.2 at DM[0]."]
    for s in "WENS":
        nhw = DM0_NOTCH_HALF_BY_SIDE.get(s, PIN_NOTCH_HALF_UM)
        for o in inv["sig"][s]:
            dm0 = o.coord + GPIO_BOND_TO_EDGE_UM - DM0_CX_UM
            # two flank walls, notch [dm0-nhw, dm0+nhw] left open
            for wlo, whi in ((dm0 - DM0_WALL_LEFT_UM, dm0 - nhw),
                             (dm0 + nhw, dm0 + DM0_WALL_RIGHT_UM)):
                if s == "S":
                    lines.append(f"- [met2, {wlo:.3f}, {d0}, {whi:.3f}, {d1}]")
                elif s == "N":
                    lines.append(f'- [met2, {wlo:.3f}, "expr::$DIE_AREA[3] - {d1}", {whi:.3f}, "expr::$DIE_AREA[3] - {d0}"]')
                elif s == "W":
                    lines.append(f"- [met2, {d0}, {wlo:.3f}, {d1}, {whi:.3f}]")
                else:  # E
                    lines.append(f'- [met2, "expr::$DIE_AREA[2] - {d1}", {wlo:.3f}, "expr::$DIE_AREA[2] - {d0}", {whi:.3f}]')
    return lines


def _pad_pin_notch_lines(inv):
    """met2 walls over each gpio pad's pin-tip strip, notched at every pin.

    Extends the pad OBS over the exposed pin protrusion (depth ROUTE_OBS_DEPTH_UM
    -> PIN_STRIP_DEPTH_UM) on met2 only, leaving a PIN_NOTCH_HALF_UM notch at each
    core-facing pin so DRT drops straight down onto it. The walls between notches
    stop adjacent nets' met2 from crowding to <0.14um (the m2.2 near-misses).
    """
    d0 = ROUTE_OBS_DEPTH_UM
    d1 = PIN_STRIP_DEPTH_UM
    nhw = PIN_NOTCH_HALF_UM
    half = GPIO_PAD_WIDTH_UM / 2.0 + PAD_OBS_MARGIN_UM
    lines = ["# Per-pad pin-strip met2 walls, notched at each pin (fix m2.2 at DM[0])."]
    for s in "WENS":
        for o in inv["sig"][s]:
            c = o.coord
            # notch intervals (merged) in along-edge coords, within [c-half, c+half].
            # Every side: pin along-edge = coord + (GPIO_BOND_TO_EDGE_UM - cx).
            centers = sorted(c + GPIO_BOND_TO_EDGE_UM - cx for cx in GPIO_PIN_CX_UM)
            notches = []
            for ct in centers:
                lo, hi = ct - nhw, ct + nhw
                if notches and lo <= notches[-1][1]:
                    notches[-1][1] = max(notches[-1][1], hi)
                else:
                    notches.append([lo, hi])
            # walls = [c-half, c+half] minus the notch openings
            walls = []
            cur = c - half
            for lo, hi in notches:
                if lo > cur:
                    walls.append((cur, lo))
                cur = max(cur, hi)
            if cur < c + half:
                walls.append((cur, c + half))
            for wlo, whi in walls:
                if whi - wlo < 0.03:
                    continue
                if s == "S":
                    lines.append(f"- [met2, {wlo:.3f}, {d0}, {whi:.3f}, {d1}]")
                elif s == "N":
                    lines.append(f'- [met2, {wlo:.3f}, "expr::$DIE_AREA[3] - {d1}", {whi:.3f}, "expr::$DIE_AREA[3] - {d0}"]')
                elif s == "W":
                    lines.append(f"- [met2, {d0}, {wlo:.3f}, {d1}, {whi:.3f}]")
                else:  # E
                    lines.append(f'- [met2, "expr::$DIE_AREA[2] - {d1}", {wlo:.3f}, "expr::$DIE_AREA[2] - {d0}", {whi:.3f}]')
    return lines


def _pad_footprints(inv):
    """(side, along-edge center, pad width) for every real pad in the ring."""
    pads = []
    for s in "WENS":
        for o in inv["sig"][s]:
            pads.append((s, o.coord, PAD_WIDTH_GPIO_UM))
        for c in inv["clp"][s]:
            pads.append((s, c.coord, PAD_WIDTH_CLAMP_UM))
    rst = inv.get("reset")
    if rst:
        pads.append((rst["side"], rst["coord"], PAD_WIDTH_RESET_UM))
    return pads


def _pad_obstruction_lines(inv):
    """OBS boxes over each pad footprint (all metal layers) to keep DRT from
    routing under pads through the reset/POR windows."""
    d = ROUTE_OBS_DEPTH_UM
    m = PAD_OBS_MARGIN_UM
    dw = "expr::$DIE_AREA[2]"
    dh = "expr::$DIE_AREA[3]"
    lines = ["# Per-pad OBS: block routing under the pads in the reset/POR windows."]
    for s, c, w in _pad_footprints(inv):
        lo = c - w / 2.0 - m
        hi = c + w / 2.0 + m
        for L in ROUTE_OBS_LAYERS:
            if s == "S":
                lines.append(f"- [{L}, {lo:.3f}, 0, {hi:.3f}, {d}]")
            elif s == "N":
                lines.append(f'- [{L}, {lo:.3f}, "expr::$DIE_AREA[3] - {d}", {hi:.3f}, "{dh}"]')
            elif s == "W":
                lines.append(f"- [{L}, 0, {lo:.3f}, {d}, {hi:.3f}]")
            else:  # E
                lines.append(f'- [{L}, "expr::$DIE_AREA[2] - {d}", {lo:.3f}, "{dw}", {hi:.3f}]')
    return lines


# Per-instance placement nudges (um) to clear localized detailed-routing DRCs.
# The E const block sits in a narrow channel (west edge ~1.7um off the wrapper,
# east side against the pad ring / east routing obstruction), so it can only be
# nudged along the edge (Y). gpio_e[13] otherwise leaves a single met3 short at
# its south edge against its own pad's gpio_in_h[27] fanout; shift it north.
CONST_BLOCK_NUDGE_UM = {
    "gpio_e[13].const_val": (0.0, 6.0),
}


def _gpio_const_block_instances(inv):
    """YAML instance entries for the 63 per-gpio constant_block placements.

    Placed exactly like the caravel openframe (each just inside the pad ring at
    its pad, extended metal reaching inward toward the wrapper), transformed to
    the double-wide ring (east +HALF, north/south duplicated, mid-seam
    synthesized). Instance names match the RTL generate blocks: gpio_<s>[i].const_val.
    A few instances carry a small along-edge nudge (CONST_BLOCK_NUDGE_UM) to
    clear localized detailed-routing DRCs.
    """
    lines = []
    for s in "WENS":
        ux, uy = SIDE_OUTWARD[s]
        fx, fy = SIDE_FINE_ADJUST_UM[s]
        ox = ux * CONST_BLOCK_OUTWARD_SHIFT_UM + fx
        oy = uy * CONST_BLOCK_OUTWARD_SHIFT_UM + fy
        for o in inv["sig"][s]:
            name = o.inst.replace("].u", "].const_val")
            cb = o.cb
            dx, dy = CONST_BLOCK_NUDGE_UM.get(name, (0.0, 0.0))
            llx = cb["llx"] + ox + dx
            lly = cb["lly"] + oy + dy
            lines.append(f"      {name}:")
            lines.append(f"        location: [{llx:.3f}, {lly:.3f}]")
            lines.append(f"        orientation: {SIDE_CONST_ORIENT[s]}")
    return "\n".join(lines)


def gen_config_yaml(inv):
    pad_blocks = "\n".join(_yaml_pad_block(inv, s) for s in "SENW")
    routing_obs = _routing_obstructions_yaml(inv)
    gpio_const_insts = _gpio_const_block_instances(inv)
    return f"""# AUTO-GENERATED by scripts/extract_openframe_pads.py -- do not edit by hand.
# Double-wide openframe padframe, LibreLane 3 Chip flow (sky130-fabulous-testchip style).
meta:
  version: 3
  flow: Chip
  substituting_steps:

    # Magic reports some overlaps which can be ignored
    Checker.IllegalOverlap: null

    # Disable KLayout DRC
    #KLayout.DRC: null
    #Checker.KLayoutDRC: null

    # Disable magic DRC
    Magic.DRC: null
    Checker.MagicDRC: null
    KLayout.DRC: null
    Checker.KLayoutDRC: null
    KLayout.XOR: null
    Checker.XOR: null
    Netgen.LVS: null
    Checker.LVS: null

    # Disable KLayout antenna check
    #KLayout.Antenna: null
    #Checker.KLayoutAntenna: null

    # Disable KLayout density check
    #KLayout.Density: null
    #Checker.KLayoutDensity: null

    # Save time
    #OpenROAD.IRDropReport: null
    #KLayout.XOR: null
    #Netgen.LVS: null
    #Checker.LVS: null

    # Disable chip finishing
    # KLayout.Antenna: null
    # Checker.KLayoutAntenna: null
    # KLayout.SealRing: null
    # KLayout.Filler: null
    # KLayout.Density: null
    # Checker.KLayoutDensity: null

    # Because of hierarchy
    Checker.YosysUnmappedCells: null

    # Macro-only padframe: wrapper fills the core, no std-cell rows / PDN rails.
    Odb.AddPDNObstructions: null
    OpenROAD.GeneratePDN: null
    Odb.RemovePDNObstructions: null
    Checker.PowerGridViolations: null
    OpenROAD.GlobalPlacementSkipIO: null
    OpenROAD.GlobalPlacement: null
    Odb.ManualGlobalPlacement: null
    OpenROAD.RepairDesignPostGPL: null
    OpenROAD.DetailedPlacement: null
    OpenROAD.CTS: null
    OpenROAD.ResizerTimingPostCTS: null
    OpenROAD.FillInsertion: null
    OpenROAD.IRDropReport: null
    OpenROAD.CheckAntennas*: null

    # Most of the reset/POR cluster (porb_h, resetb_h, resetb_l, xres*) is routed
    # by TritonRoute through the west/south obstruction windows (see
    # ROUTING_OBSTRUCTIONS). The two simple_por level-shifter outputs por_l/porb_l
    # sit on thin met3 pins ~113um from the wrapper that never get a routing
    # access point (DRT-0419 -> crash), so Padframe.ResetSpecialNets marks just
    # those two SPECIAL; DRT leaves them alone and they connect at integrate.
    -OpenROAD.GlobalRouting: Padframe.ResetSpecialNets
    +OpenROAD.GlobalRouting: Odb.InsertECODiodes

    # After detailed routing, each gpio_dm0[i] route reaches its own DM[0] pad pin
    # (a short met2 tip stub) but stops 0.07-0.13um short of the pin metal, leaving
    # a *same-net* met2 gap that KLayout flags as m2.2. Bridge each with a small
    # same-net met2 patch (electrically a no-op; only gpio_dm0 metal is present
    # there) so the shapes merge and the gap disappears.
    +OpenROAD.DetailedRouting: Padframe.BridgeDM0

DESIGN_NAME: double_wide_chip_io
{_verilog_files_block()}

SYNTH_HIERARCHY_MODE: keep

# Macro-only padframe: pads + placed wrapper macro, no std-cell logic to map.
SYNTH_ELABORATE_ONLY: true

RUN_CTS: false
RUN_TAP_ENDCAP_INSERTION: false
RUN_FILL_INSERTION: false
RUN_IRDROP_REPORT: false
RUN_ANTENNA_REPAIR: false
RUN_HEURISTIC_DIODE_INSERTION: false

PRIMARY_GDSII_STREAMOUT_TOOL: klayout

LINTER_DISABLE_WARNINGS:
- DECLFILENAME
- EOFNEWLINE
- PINCONNECTEMPTY
- PINMISSING
- UNUSEDSIGNAL

PAD_CFG: dir::pad_cfg.tcl

# PDK PAD_LEFS is only sky130_ef_io.lef; the openframe reset pad lives in
# sky130_fd_io.lef (sky130_fd_io__top_xres4v2).
EXTRA_LEFS:
- pdk_dir::libs.ref/sky130_fd_io/lef/sky130_fd_io.lef

# Macro-only padframe (no std-cell rows); keep SCL global-connects off.
PDN_ENABLE_GLOBAL_CONNECTIONS: false

# PDK default omits clamped3 / vdda / vssa HVC clamps — without these their
# bond nets get no DEF PORT / GDS pin label and padframe LVS fails pin matching.
PAD_PLACE_IO_TERMINALS:
- sky130_ef_io__gpiov2_pad/PAD
- sky130_fd_io__top_xres4v2/PAD
- sky130_ef_io__vccd_lvc_clamped_pad/VCCD_PAD
- sky130_ef_io__vccd_lvc_clamped3_pad/VCCD_PAD
- sky130_ef_io__vssd_lvc_clamped_pad/VSSD_PAD
- sky130_ef_io__vssd_lvc_clamped3_pad/VSSD_PAD
- sky130_ef_io__vddio_hvc_clamped_pad/VDDIO_PAD
- sky130_ef_io__vssio_hvc_clamped_pad/VSSIO_PAD
- sky130_ef_io__vdda_hvc_clamped_pad/VDDA_PAD
- sky130_ef_io__vssa_hvc_clamped_pad/VSSA_PAD

{pad_blocks}

# No functional clock in the passive frame; provide SDCs for the STA steps.
PNR_SDC_FILE: dir::chip.sdc
SIGNOFF_SDC_FILE: dir::chip.sdc
FALLBACK_SDC: dir::chip.sdc

# Floorplan: double-wide die (2 x 3588 um) x (5188 um), height unchanged.
FP_SIZING: absolute
DIE_AREA: [0, 0, {DW_W_UM:.0f}, {DW_H_UM:.0f}]
CORE_AREA: [{WRAP_MARGIN_UM:.3f}, {WRAP_MARGIN_UM:.3f}, "expr::$DIE_AREA[2] - {WRAP_MARGIN_UM:.3f}", "expr::$DIE_AREA[3] - {WRAP_MARGIN_UM:.3f}"]

# Keep routing outside the pad ring. Pad cells (e.g. gpiov2) extend ~197.965 um
# from the die edge. Cut-in is 198.5 um: still far tighter than the 197.0 value
# that let the router into the pad interior (met2 spacing m2.2), but loose
# enough for west/east met3 IN_H pin-access vias near x≈199.18 — both a 199.7
# cut-in (met3 short) and a 199.0 cut-in (met3 spacing vs obstruction) flagged
# deferred DRT on gpio_in_h[3].
#
# Pad-ring OBS with windows cut on the west (POR) and south (reset) edges so
# TritonRoute can wire the reset/POR cluster (resetb_h/resetb_l/porb_*/por_l).
# East/north stay full-depth; see _routing_obstructions_yaml().
{routing_obs}

# Power / ground nets (preserved multi-domain). LibreLane 3 only accepts the
# plural VDD_NETS/GND_NETS; the singular VDD_NET/GND_NET keys abort the flow.
VDD_NETS: [vccd, vccd1, vccd2, vddio, vdda, vdda1, vdda2]
GND_NETS: [vssd, vssd1, vssd2, vssio, vssa, vssa1, vssa2]

# PDN is intentionally omitted from the padframe -- it will be drawn manually
# later. The OpenROAD.GeneratePDN / Odb.AddPDNObstructions steps are dropped in
# meta.substituting_steps above, so all PDN_* knobs and PDN_CFG are left unset.

IGNORE_DISCONNECTED_MODULES:
- sky130_fd_io__top_power_hvc_wpad
- sky130_fd_io__top_ground_hvc_wpad
- sky130_fd_io__top_power_lvc_wpad
- sky130_fd_io__top_ground_lvc_wpad
- open_source
- project_id_textblock
- logo_dw_openframe

# Multiple power pads share one domain net.
MAGIC_EXT_UNIQUE: notopports

# The double-wide user-area wrapper, placed centered in the die.
# Branding sits in left-half N/S pad-ring gaps; mid-seam holds extra GPIOs.
# POR sits in the west ring gap (fixed reharden coords).
MACROS:
  double_wide_openframe_project_wrapper:
    gds:
    - dir::../../build/wrapper/gds/double_wide_openframe_project_wrapper.gds
    lef:
    - dir::../../build/wrapper/lef/double_wide_openframe_project_wrapper.lef
    pnl:
    - dir::../../verilog/gl/double_wide_openframe_project_wrapper.v
    instances:
      user_project:
        location: [{WRAP_MARGIN_UM:.3f}, {WRAP_MARGIN_UM:.3f}]
        orientation: N

  # West-gap Mag drop-in (dw_openframe GDS); X locked, Y free.
  simple_por:
    gds:
    - dir::../../gds/simple_por.gds
    lef:
    - dir::../../lef/simple_por.lef
    instances:
      {POR_INST}:
        location: [{POR_LOCATION_UM[0]:.3f}, {POR_LOCATION_UM[1]:.3f}]
        orientation: {POR_ORIENT}

  # South-edge reset level shifter + constant one (openframe Mag places).
  xres_buf:
    gds:
    - dir::../../gds/xres_buf.gds
    lef:
    - dir::../../lef/xres_buf.lef
    instances:
      {XRES_BUF_INST}:
        location: [{XRES_BUF_LOCATION_UM[0] + XRES_BUF_NUDGE_UM[0]:.3f}, {XRES_BUF_LOCATION_UM[1] + XRES_BUF_NUDGE_UM[1]:.3f}]
        orientation: {XRES_BUF_ORIENT}

  constant_block:
    gds:
    - dir::../../gds/constant_block.gds
    lef:
    - dir::../../lef/constant_block.lef
    instances:
      {CONSTANT_INST}:
        location: [{CONSTANT_LOCATION_UM[0]:.3f}, {CONSTANT_LOCATION_UM[1] - CONST_BLOCK_OUTWARD_SHIFT_UM:.3f}]
        orientation: {CONSTANT_ORIENT}
{gpio_const_insts}

  # North left gap between gpio_n[5] (cell ends ~2002) and gpio_n[6] (starts ~2367).
  # Logo only (198.4 x 54), centered in the clear filler span with margin from both
  # pad cells; com_bus_slice filler underneath (artwork met4/met5 OBS).
  logo_dw_openframe:
    gds:
    - dir::../../ip/logo_dw_openframe/gds/logo_dw_openframe.gds.gz
    lef:
    - dir::../../ip/logo_dw_openframe/lef/logo_dw_openframe.lef
    vh:
    - dir::../../ip/logo_dw_openframe/vh/logo_dw_openframe.vh
    instances:
      logo_dw_openframe:
        location: [2085.300, 5095.200]
        orientation: N

  # Clean mid-south gap (~3742-3982), away from the reset pad / xres cluster and
  # the south reset routing window. open_source is 141.4 wide -> centered here.
  open_source:
    gds:
    - dir::../../ip/open_source/gds/open_source.gds.gz
    lef:
    - dir::../../ip/open_source/lef/open_source.lef
    vh:
    - dir::../../ip/open_source/vh/open_source.vh
    instances:
      open_source:
        location: [3791.300, 35.000]
        orientation: N

  # Large clean mid-south gap (~4057-4523), away from the reset/xres cluster.
  # project_id_textblock is 173.75 wide -> centered here.
  project_id_textblock:
    gds:
    - dir::../../ip/project_id_textblock/gds/project_id_textblock.gds.gz
    lef:
    - dir::../../ip/project_id_textblock/lef/project_id_textblock.lef
    vh:
    - dir::../../ip/project_id_textblock/vh/project_id_textblock.vh
    instances:
      project_id_textblock:
        location: [4203.100, 44.020]
        orientation: N

GRT_ALLOW_CONGESTION: true
PL_TARGET_DENSITY_PCT: 40
"""


def gen_pin_template_def(inv):
    """Emit a pins-only DEF template for the user-area wrapper.

    Each GPIO owns 17 pad signals (13 control outputs, 2 inputs, 2 analog
    inouts) plus 2 buffered-constant inputs (gpio_loopback_one/zero from its
    constant_block).  We pin every one of them on the die edge *directly facing*
    that GPIO's pad, clustered around the pad's along-edge coordinate.  Consumed via
    FP_DEF_TEMPLATE + Odb.ApplyDEFTemplate when hardening the wrapper, this
    replaces the pin-placement algorithm with exact, pad-aligned locations so
    the padframe's pad<->wrapper nets are short straight hops instead of long
    detours across a congested channel.

    N/S pins sit on a vertical routing layer (met2), E/W on the horizontal
    layer (met3): sky130 preferred directions are vertical for met2/met4 and
    horizontal for met3, so each edge's pins align with the axis the padframe
    router uses to reach them.
    """
    UPM = 1000                       # DEF database units per micron
    GRID = 5                         # sky130 manufacturing grid (nm)

    def nm(um):
        return int(round(um * UPM))

    def snap(v):
        return int(round(v / GRID)) * GRID

    WW, HH = nm(WRAP_W_UM), nm(WRAP_H_UM)
    OFF = nm(WRAP_MARGIN_UM)          # wrapper origin offset inside the die
    PW = 400                          # pin width, across the wire      (0.40 um)
    PL = 1000                         # pin length, into the die        (1.00 um)
    PITCH = 4000                      # spacing between a gpio's pins    (4.00 um)
    HLAYER, VLAYER = "met3", "met2"

    # Order each GPIO's 17 pins to mirror the gpiov2 pad's physical core-pin
    # layout so the pad->wrapper nets run as a clean parallel bundle instead of
    # a crossing fan. Every pad side (R180/R270/MY/MYR90) maps ascending pad-
    # local-x to *descending* die along-edge coordinate (verified by probing the
    # routed padframe), so along the increasing wrapper coordinate we emit the
    # reverse of GPIO_PAD_PIN_ORDER -- identical for all four sides.
    _inout = set(GPIO_VEC_SIGS_INOUT)
    _wr_in = set(GPIO_VEC_SIGS_OUT)   # pad -> wrapper == wrapper INPUT

    def _pin_dir(sig):
        if sig in _inout:
            return "INOUT"
        if sig in _wr_in:
            return "INPUT"
        return "OUTPUT"

    sig_dirs = [(s, _pin_dir(s)) for s in reversed(GPIO_PAD_PIN_ORDER)]
    halfspan = (len(sig_dirs) - 1) * PITCH // 2

    pins = []   # (name, direction, layer, x1, y1, x2, y2)
    for s in "WENS":
        edge_len = WW if s in "NS" else HH
        lo = halfspan + PL + GRID
        hi = edge_len - halfspan - PL - GRID
        for o in inv["sig"][s]:
            center = snap(nm(o.coord) - OFF)
            center = max(lo, min(hi, center))
            start = center - halfspan
            for j, (sig, direction) in enumerate(sig_dirs):
                c = snap(start + j * PITCH)
                name = f"{sig}[{o.g}]"
                if s == "S":
                    layer, box = VLAYER, (c - PW // 2, 0, c + PW // 2, PL)
                elif s == "N":
                    layer, box = VLAYER, (c - PW // 2, HH - PL, c + PW // 2, HH)
                elif s == "W":
                    layer, box = HLAYER, (0, c - PW // 2, PL, c + PW // 2)
                else:  # E
                    layer, box = HLAYER, (WW - PL, c - PW // 2, WW, c + PW // 2)
                pins.append((name, direction, layer) + box)

    # Per-gpio buffered-constant pins (gpio_loopback_one / gpio_loopback_zero).
    # Each gpio's constant_block is placed just inside the ring at that pad with
    # its one/zero metal extended inward; land a wrapper input pin on the same
    # edge, centered on the constant_block (its drawn box is 14um along the edge,
    # so the along-edge center is LL_along + 7). The two pins straddle the center
    # by one pitch. Layer follows the side, matching the padframe approach axis.
    for s in "WENS":
        edge_len = WW if s in "NS" else HH
        for o in inv["sig"][s]:
            along_um = (o.cb["llx"] if s in "NS" else o.cb["lly"]) + 7.0
            center = snap(nm(along_um) - OFF)
            center = max(PL + GRID + PITCH, min(edge_len - PL - GRID - PITCH, center))
            for j, sig in enumerate(GPIO_VEC_SIGS_LOOPBACK):
                c = snap(center + j * PITCH - PITCH // 2)
                name = f"{sig}[{o.g}]"
                if s == "S":
                    layer, box = VLAYER, (c - PW // 2, 0, c + PW // 2, PL)
                elif s == "N":
                    layer, box = VLAYER, (c - PW // 2, HH - PL, c + PW // 2, HH)
                elif s == "W":
                    layer, box = HLAYER, (0, c - PW // 2, PL, c + PW // 2)
                else:  # E
                    layer, box = HLAYER, (WW - PL, c - PW // 2, WW, c + PW // 2)
                pins.append((name, "INPUT", layer) + box)

    # POR pins (west met3): openframe geometry, Y shifted with our POR place so
    # they abut the simple_por pin band. Order porb_h / por_l / porb_l.
    # Openframe pin: LAYER met3 (-1.150,-0.175)-(1.150,0.175) PLACED (-0.850, y)
    # → absolute box (-2.000, y-0.175)-(0.300, y+0.175).
    dy = POR_LOCATION_UM[1] - OF_POR_LOCATION_Y_UM
    for sig, y_of in zip(WRAPPER_POR_PINS_WEST, OF_WRAP_POR_Y_UM):
        y = snap(nm(y_of + dy))
        pins.append((sig, "INPUT", HLAYER, -2000, y - 175, 300, y + 175))

    # Reset pins (south met2): openframe X facing the south xres pad / xres_buf.
    # Openframe: LAYER met2 (-0.140,-1.140)-(0.140,1.140) PLACED (x, -0.860)
    # → absolute box (x-0.140, -2.000)-(x+0.140, 0.280).
    for sig, x_of in zip(WRAPPER_RESET_PINS_SOUTH, OF_WRAP_RESET_X_UM):
        x = snap(nm(x_of))
        pins.append((sig, "INPUT", VLAYER, x - 140, -2000, x + 140, 280))

    out = [
        "VERSION 5.8 ;",
        'DIVIDERCHAR "/" ;',
        'BUSBITCHARS "[]" ;',
        "DESIGN double_wide_openframe_project_wrapper ;",
        f"UNITS DISTANCE MICRONS {UPM} ;",
        f"DIEAREA ( 0 0 ) ( {WW} {HH} ) ;",
        f"PINS {len(pins)} ;",
    ]
    for name, direction, layer, x1, y1, x2, y2 in pins:
        out.append(f"- {name} + NET {name} + DIRECTION {direction} + USE SIGNAL")
        out.append(f"  + LAYER {layer} ( {x1} {y1} ) ( {x2} {y2} ) + PLACED ( 0 0 ) N ;")
    out.append("END PINS")
    out.append("END DESIGN")
    out.append("")
    return "\n".join(out)


def gen_summary(inv):
    n = inv["n_gpio"]
    gmap = []
    for s in "WENS":
        for o in inv["sig"][s]:
            gmap.append(dict(g=o.g, side=s, domain=o.domain,
                             coord=round(o.coord, 3), inst=o.inst))
    gmap.sort(key=lambda d: d["g"])
    counts = {s: dict(gpio=len(inv["sig"][s]), clamp=len(inv["clp"][s])) for s in "WENS"}
    return dict(
        n_gpio=n,
        die_um=[DW_W_UM, DW_H_UM],
        counts_per_side=counts,
        pkg_counts=inv["pkg_counts"],
        gpio_index_map=gmap,
        reset=inv.get("reset"),
        por=dict(
            inst=POR_INST,
            location_um=list(POR_LOCATION_UM),
            orientation=POR_ORIENT,
        ),
    )


# --------------------------------------------------------------------------- #
def analyze(inv):
    print(f"n_gpio = {inv['n_gpio']}  die = {DW_W_UM} x {DW_H_UM} um")
    for s in "WENS":
        print(f"  {s}: gpio={len(inv['sig'][s])}  clamp={len(inv['clp'][s])}")
    print("  package nets:", inv["pkg_counts"])


def write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    print(f"  wrote {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mag", required=True)
    ap.add_argument("--out-tcl")
    ap.add_argument("--out-yaml")
    ap.add_argument("--out-json")
    ap.add_argument("--out-rtl")
    ap.add_argument("--out-wrapper")
    ap.add_argument("--out-defines")
    ap.add_argument("--out-config")
    ap.add_argument("--out-def-template")
    ap.add_argument("--out-pad-blackboxes")
    ap.add_argument("--out-por-reset-blackboxes")
    ap.add_argument(
        "--ef-io-v",
        default=DEFAULT_EF_IO_V,
        help="PDK sky130_ef_io.v (used to copy ef_io composite pad port lists)",
    )
    ap.add_argument("--analyze", action="store_true")
    args = ap.parse_args()

    uses = parse_mag(args.mag)
    classify(uses)
    inv = build_inventory(uses)
    analyze(inv)

    if args.analyze:
        return 0
    if args.out_tcl:
        write(args.out_tcl, gen_pad_pos_tcl(inv))
    if args.out_yaml:
        write(args.out_yaml, gen_pad_lists_yaml(inv))
    if args.out_json:
        write(args.out_json, json.dumps(gen_summary(inv), indent=2))
    if args.out_rtl:
        write(args.out_rtl, gen_padframe_rtl(inv))
    if args.out_wrapper:
        write(args.out_wrapper, gen_wrapper_rtl(inv, empty=True))
    if args.out_config:
        write(args.out_config, gen_config_yaml(inv))
    if args.out_pad_blackboxes:
        write(args.out_pad_blackboxes, gen_pad_ef_io_blackboxes_v(inv, args.ef_io_v))
    if args.out_por_reset_blackboxes:
        write(args.out_por_reset_blackboxes, gen_por_reset_blackboxes_v())
    if args.out_def_template:
        write(args.out_def_template, gen_pin_template_def(inv))
    if args.out_defines:
        write(args.out_defines,
              "// AUTO-GENERATED\n"
              "`ifndef DW_DEFINES_VH\n`define DW_DEFINES_VH\n"
              f"`define DW_OPENFRAME_IO_PADS {inv['n_gpio']}\n"
              "`endif\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
