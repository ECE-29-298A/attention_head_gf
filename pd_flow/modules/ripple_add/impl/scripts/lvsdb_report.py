# KLayout batch script: summarise a .lvsdb cross-reference.
# Usage: klayout -b -r lvsdb_report.py -rd lvsdb=X.lvsdb -rd out=X.json
import json
import pya

lvs = pya.LayoutVsSchematic()
lvs.read(lvsdb)  # noqa: F821  (set by -rd)
xref = lvs.xref()
St = pya.NetlistCrossReference
names = {St.Match: "Match", St.NoMatch: "NoMatch", St.Skipped: "Skipped",
         St.MatchWithWarning: "MatchWithWarning", St.Mismatch: "Mismatch", St.None_: "None"}
res = {"circuits": []}


def nm(o):
    return o.name if o is not None else None


def dev(o):
    if o is None:
        return None
    return f"{o.expanded_name()}:{o.device_class().name}"


for cp in xref.each_circuit_pair():
    a, b = cp.first(), cp.second()
    st = names.get(cp.status(), str(cp.status()))
    entry = {"layout": nm(a), "schematic": nm(b), "status": st, "nets": [], "devices": [],
             "pins": [], "subcircuits": []}
    for np_ in xref.each_net_pair(cp):
        s = names.get(np_.status(), str(np_.status()))
        if s != "Match":
            entry["nets"].append([np_.first().expanded_name() if np_.first() else None,
                                  np_.second().expanded_name() if np_.second() else None, s])
    for dp in xref.each_device_pair(cp):
        s = names.get(dp.status(), str(dp.status()))
        if s != "Match":
            entry["devices"].append([dev(dp.first()), dev(dp.second()), s])
    for pp in xref.each_pin_pair(cp):
        s = names.get(pp.status(), str(pp.status()))
        if s != "Match":
            entry["pins"].append([pp.first().name() if pp.first() else None,
                                  pp.second().name() if pp.second() else None, s])
    for sp in xref.each_subcircuit_pair(cp):
        s = names.get(sp.status(), str(sp.status()))
        if s != "Match":
            entry["subcircuits"].append([sp.first().expanded_name() if sp.first() else None,
                                         sp.second().expanded_name() if sp.second() else None, s])
    for k in ("nets", "devices", "pins", "subcircuits"):
        entry[f"{k}_nonmatch"] = len(entry[k])
        entry[k] = entry[k][:40]
    res["circuits"].append(entry)

lay, sch = lvs.netlist(), lvs.reference
res["layout_device_count"] = sum(1 for c in lay.each_circuit() for _ in c.each_device())
res["schematic_device_count"] = sum(1 for c in sch.each_circuit() for _ in c.each_device())
res["all_match"] = all(c["status"] in ("Match", "MatchWithWarning") for c in res["circuits"])
with open(out, "w") as f:  # noqa: F821
    json.dump(res, f, indent=1)
for c in res["circuits"]:
    print(c["layout"], c["schematic"], c["status"], "nets", c["nets_nonmatch"], "devices",
          c["devices_nonmatch"], "pins", c["pins_nonmatch"], "subckts", c["subcircuits_nonmatch"])
print("ALL_MATCH" if res["all_match"] else "MISMATCH")
