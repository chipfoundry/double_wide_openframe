# Double-Wide OpenFrame — Documentation

Customer-facing technical reference for the **double-wide sky130 openframe
padframe** (`double_wide_chip_io`). This is what you need to design inside the
user area.

| Document | Contents |
|----------|----------|
| [**Datasheet**](datasheet.md) | Summary, I/O map, power domains, GPIO/reset interface, integration, deliverables |
| [**Pinout**](pinout.md) | Full GPIO index map, bond coordinates, power bond pads |
| [`../pad_summary.json`](../pad_summary.json) | Machine-readable GPIO ↔ pad map |

## Figures

| Figure | File | Source |
|--------|------|--------|
| Full-chip GDS | [`figures/chip_gds.png`](figures/chip_gds.png) | `scripts/render_gds_image.py` (KLayout) |
| I/O map | [`figures/io_map.svg`](figures/io_map.svg) | `scripts/gen_datasheet_figures.py` |
| Power domains | [`figures/power_domains.svg`](figures/power_domains.svg) | d2 (`generated/power_domains.d2`) |
| Boundary signals | [`figures/boundary.svg`](figures/boundary.svg) | d2 (`generated/boundary.d2`) |

## Regenerating

Figures and pinout tables are generated from the padframe source data, so they
never drift:

```bash
# I/O map + power/boundary diagrams (needs `d2`) + pinout tables
python3 scripts/gen_datasheet_figures.py

# Full-chip GDS screenshot (needs KLayout)
klayout -z -nc -r scripts/render_gds_image.py
```

Diagrams use [d2](https://d2lang.com/); the GDS screenshot uses KLayout.
