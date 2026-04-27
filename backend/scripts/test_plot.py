from pathlib import Path

from core.services.local_estimate_parser import _try_m23_loose_qty, _unit_qty_from_line

lines = Path("_pdf_sample.txt").read_text(encoding="utf-8", errors="replace").splitlines()
chunk = lines[21784:22050]
from core.services.local_estimate_parser import parse_lines_abc

d = set()
out = parse_lines_abc(chunk, d)
plot = [r for r in out if "Площад" in (r.get("name") or "")]
print("rows", len(out), "plot", len(plot))
for r in plot:
    print(r.get("name", "")[:70], r.get("unit"), r.get("quantity"))
# any м2 1.04
m2 = [r for r in out if (r.get("unit") or "").lower().startswith("м2") and r.get("quantity") == 1.04]
print("m2_1.04", len(m2), [x.get("name", "")[:40] for x in m2])

# synthetic merged
acc = "РСНБ РК 2022 грунтов 2. м2 Кзтр и Кэм=1,04 спланирован ной площади 19 242,92"
print("unit_line", _unit_qty_from_line(acc))
print("loose", _try_m23_loose_qty(acc))
