# KLayout batch script: GDS-level connectivity check of the porb_h distribution.
#
#   klayout -b -r scripts/check_porb_net.py \
#       -rd gds=gds/double_wide_chip_io.gds -rd probes=probes.json
#
# `probes` is a JSON list of pin probe points (one per pin, um, with its metal
# layer, instance, master, pin and netlist net), e.g. as dumped from the final
# DEF by scripts/porb_probe_points.py. The script keeps only the li1..met5
# metal / via layers, flattens, extracts connectivity, and checks:
#
#   * simple_por porb_h, the wrapper porb_h pin and every GPIO / reset pad
#     ENABLE_H / ENABLE_VDDA_H pin are ONE net (the openframe-style loop);
#   * no TIE_HI_ESD, HLD_H_N, por_l or porb_l pin is on that net.
#
# This works on the streamed GDS, so it sees the simple_por porb_h "collar"
# (GDS-only geometry) that LibreLane's LEF-based Magic extraction cannot.
import json
import sys

import pya

gds = globals().get("gds")
probes_path = globals().get("probes")
if not gds or not probes_path:
    sys.exit("usage: klayout -b -r check_porb_net.py -rd gds=<gds> -rd probes=<json>")

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
net_of = {}
for p in probes:
    x, y = p["x"], p["y"]
    if p["master"] == "double_wide_openframe_project_wrapper":
        # probe the wrapper's own pin metal, inside the wrapper boundary,
        # not the simple_por collar it abuts
        x = p["rect"][2] - 0.04
    net = l2n.probe_net(regions[p["layer"]], pya.DPoint(x, y))
    key = (p["inst"], p["pin"])
    net_of[key] = net.cluster_id if net is not None else None

ref = net_of.get(("por", "porb_h"))
errors = []
if ref is None:
    errors.append("no metal at simple_por porb_h")
porb = [p for p in probes if p.get("net") == "porb_h"]
other = [p for p in probes if p.get("net") != "porb_h"]
on = [p for p in porb if net_of[(p["inst"], p["pin"])] == ref]
for p in porb:
    if net_of[(p["inst"], p["pin"])] != ref:
        errors.append(f"OPEN  {p['inst']}/{p['pin']} not on simple_por porb_h")
for p in other:
    if ref is not None and net_of[(p["inst"], p["pin"])] == ref:
        errors.append(f"SHORT {p['inst']}/{p['pin']} ({p.get('net')}) on porb_h")

kinds = {}
for p in on:
    k = f"{p['master']}/{p['pin']}"
    kinds[k] = kinds.get(k, 0) + 1
print(f"porb_h GDS net: {len(on)} of {len(porb)} porb_h pins connected")
for k in sorted(kinds):
    print(f"  {kinds[k]:3d} x {k}")
print(f"checked {len(other)} other pins (TIE_HI_ESD, HLD_H_N, por_l, porb_l) for shorts")
for e in errors[:40]:
    print("  " + e)
print("PASS" if not errors else f"FAIL ({len(errors)} problem(s))")
sys.exit(0 if not errors else 1)
