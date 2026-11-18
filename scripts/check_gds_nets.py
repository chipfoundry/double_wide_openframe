# KLayout batch script: GDS-level check that named nets are whole and separate.
#
#   klayout -b -r scripts/check_gds_nets.py \
#       -rd gds=gds/double_wide_chip_io.gds -rd probes=probes.json
#
# `probes` is a JSON list of pins (instance, pin, netlist net and one or more
# probe points in um with their metal layer), as dumped from the final DEF by
# scripts/net_probe_points.py. The script keeps only the li1..met5 metal / via
# layers, flattens, extracts connectivity, and checks that
#
#   * all pins of one netlist net are on ONE net in the GDS (no opens), and
#   * no two of the netlist nets share a GDS net (no shorts between them).
#
# It works on the streamed GDS, so it sees hand-drawn special wiring and the
# metal inside pad cells exactly as it will be manufactured.
import json
import sys

import pya

gds = globals().get("gds")
probes_path = globals().get("probes")
if not gds or not probes_path:
    sys.exit("usage: klayout -b -r check_gds_nets.py -rd gds=<gds> -rd probes=<json>")

GDS_LAYERS = {  # sky130 drawing layers
    "li1": (67, 20), "mcon": (67, 44), "met1": (68, 20), "via": (68, 44),
    "met2": (69, 20), "via2": (69, 44), "met3": (70, 20), "via3": (70, 44),
    "met4": (71, 20), "via4": (71, 44), "met5": (72, 20),
}
STACK = ["li1", "mcon", "met1", "via", "met2", "via2", "met3", "via3",
         "met4", "via4", "met5"]

ly = pya.Layout()
ly.read(gds)
top = ly.top_cell()
keep = {ly.find_layer(*GDS_LAYERS[n]) for n in STACK}
for li in ly.layer_indexes():
    if li not in keep:
        ly.clear_layer(li)
top.flatten(-1, True)

l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(ly, top, []))
regions = {n: l2n.make_layer(ly.find_layer(*GDS_LAYERS[n]), n) for n in STACK}
for n in STACK:
    if not n.startswith(("via", "mcon")):
        l2n.connect(regions[n])
for a, b in zip(STACK, STACK[1:]):
    l2n.connect(regions[a], regions[b])
l2n.extract_netlist()

probes = json.load(open(probes_path))
clusters = {}   # netlist net -> {GDS cluster id or None: [pin, ...]}
for p in probes:
    cid = None
    for pt in p["points"]:      # first probe point that lies on metal
        net = l2n.probe_net(regions[pt["layer"]], pya.DPoint(pt["x"], pt["y"]))
        if net is not None:
            cid = net.cluster_id
            break
    clusters.setdefault(p["net"], {}).setdefault(cid, []).append(
        f"{p['inst']}/{p['pin']}")

errors = []
owner = {}
for name in sorted(clusters):
    by = clusters[name]
    n_pins = sum(len(v) for v in by.values())
    if None in by:
        errors.append(f"OPEN  {name}: no metal at {by[None][:4]}")
    real = {c: v for c, v in by.items() if c is not None}
    if len(real) > 1:
        parts = sorted(real.values(), key=len, reverse=True)
        errors.append(
            f"OPEN  {name}: {len(real)} separate pieces; largest has "
            f"{len(parts[0])} pins, others e.g. {[p[0] for p in parts[1:5]]}")
    for c in real:
        if c in owner and owner[c] != name:
            errors.append(f"SHORT {name} and {owner[c]} are one net in the GDS")
        owner.setdefault(c, name)
    print(f"  {name}: {n_pins} pins, {len(real)} GDS net(s)")
for e in errors[:40]:
    print("  " + e)
print("PASS" if not errors else f"FAIL ({len(errors)} problem(s))")
sys.exit(0 if not errors else 1)
