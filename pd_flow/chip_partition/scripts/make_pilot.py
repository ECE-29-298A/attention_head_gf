#!/usr/bin/env python3
"""make_pilot.py <final_nl.v> <final.def> <outdir> [--relocate relocate.json] [--tag TAG]

Builds the integration-pilot inputs for an all-custom-placed chip:
  <outdir>/pilot.v        structural netlist: the given (signed-off) netlist minus physical-only cells
                          (fill/fillcap/filltie/endcap, re-inserted by the flow) and minus the clock
                          tree (clkbuf_*/clkload*, rebuilt by CTS); every pin on a clock-tree net is
                          reconnected to the clock port. Everything else (synthesis cells at their
                          signed-off masters, repair buffers, ties) is kept verbatim (text-level edit).
  <outdir>/placement.cfg  MACRO_PLACEMENT_CFG: one line per remaining instance (name x y orient), from
                          the DEF, or from --relocate (name -> [x, y, orient]) where given.
  <outdir>/manifest.json  counts, removed cells, hashes.
The flow then marks every listed instance FIRM (LibreLane Odb.ManualMacroPlacement, placers.py).
"""
import json, os, re, sys, hashlib
sys.path.insert(0, os.path.dirname(__file__))
import pdlib

PHYS = re.compile(r"__(fill_\d+|fillcap_\d+|filltie|endcap)$")
CTS = re.compile(r"^(clkbuf_|clkload)")


def main():
    a = sys.argv[1:]
    reloc, presize = {}, {}
    tag = "pilot"
    if "--presize" in a:
        i = a.index("--presize")
        presize = json.load(open(a[i + 1]))
        del a[i:i + 2]
    if "--relocate" in a:
        i = a.index("--relocate")
        reloc = json.load(open(a[i + 1]))
        del a[i:i + 2]
    if "--tag" in a:
        i = a.index("--tag")
        tag = a[i + 1]
        del a[i:i + 2]
    nl, fdef, outdir = a
    os.makedirs(outdir, exist_ok=True)
    txt = open(nl).read()
    D = pdlib.parse_def(fdef, want_routes=False)
    # instance blocks: "<master> <name> (...);"
    inst_re = re.compile(r"^\s*(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\S+)\s*\((.*?)\);\s*$", re.M | re.S)
    removed_phys, removed_cts, kept = [], [], []
    cts_nets = set()
    out_parts, last = [], 0
    for m in inst_re.finditer(txt):
        master, name, body = m.group(1), m.group(2), m.group(3)
        nm = name.replace("\\", "")
        drop = None
        if PHYS.search(master):
            drop = removed_phys
        elif CTS.match(nm):
            drop = removed_cts
            for pin, net in re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", body):
                if pin in ("Z", "ZN") and net:
                    cts_nets.add(net)
        if drop is not None:
            drop.append((nm, master))
            out_parts.append(txt[last:m.start()])
            last = m.end() + 1
        else:
            kept.append((nm, master))
    out_parts.append(txt[last:])
    body = "".join(out_parts)
    # reconnect every pin on a clock-tree net to the clock port
    n_reconn = 0

    def fix(mm):
        nonlocal n_reconn
        if mm.group(2) in cts_nets:
            n_reconn += 1
            return f".{mm.group(1)}(clk)"
        return mm.group(0)
    body = re.sub(r"\.(\w+)\s*\(\s*([^()\s]+)\s*\)", fix, body)
    # drop declarations of the now-unused clock-tree wires
    body = re.sub(r"^\s*wire\s+(" + "|".join(re.escape(n) for n in sorted(cts_nets)) + r")\s*;\s*\n", "", body,
                  flags=re.M) if cts_nets else body
    assert not any(re.search(r"[\s(]" + re.escape(n) + r"[\s)]", body) for n in cts_nets), "clock net left"
    # "assign <port bit> = <net>;" (OpenROAD writes these for ports driven by tie cells) is rejected by
    # LibreLane's Checker.NetlistAssignStatements, and SYNTH_ELABORATE_ONLY keeps every wire, so connect
    # the single driver pin straight to the port bit. Only single-pin nets are rewritten (asserted).
    n_assign = 0
    for lhs, rhs in re.findall(r"^\s*assign\s+(\S+)\s*=\s*(\S+?)\s*;\s*$", body, re.M):
        uses = re.findall(r"\.\w+\s*\(\s*" + re.escape(rhs) + r"\s*\)", body)
        assert len(uses) == 1, (lhs, rhs, uses)
        body = re.sub(r"(\.\w+\s*\()\s*" + re.escape(rhs) + r"\s*\)", lambda mm: mm.group(1) + lhs + ")", body)
        body = re.sub(r"^\s*assign\s+" + re.escape(lhs) + r"\s*=\s*" + re.escape(rhs) + r"\s*;\s*\n", "", body,
                      flags=re.M)
        body = re.sub(r"^\s*wire\s+" + re.escape(rhs) + r"\s*;\s*\n", "", body, flags=re.M)
        n_assign += 1
    assert "assign" not in body
    # pre-sizing (fixed-point loop): swap masters the resizer chose, so it has no reason to resize
    # a FIRM cell in place (the DPL-0033 hazard). Pins are identical across drive strengths (asserted).
    L = pdlib.lef_macros()
    kept_master = dict(kept)
    for inst, newm in presize.items():
        newm = newm if newm.startswith(pdlib.PFX) else pdlib.PFX + newm
        old = kept_master[inst]
        assert set(L[old]["pins"]) == set(L[newm]["pins"]), (inst, old, newm)
        body, k = re.subn(r"(^\s*)" + re.escape(old) + r"(\s+)" + re.escape(inst) + r"(\s*\()",
                          lambda mm: mm.group(1) + newm + mm.group(2) + inst + mm.group(3), body, flags=re.M)
        assert k == 1, (inst, k)
        kept_master[inst] = newm
    kept = [(n, kept_master[n]) for n, _ in kept]
    hdr = (f"// {tag}: generated by pd_flow/chip_partition/scripts/make_pilot.py from\n"
           f"// {nl} (sha256 {pdlib.sha(nl)}): physical-only cells and the clock tree removed,\n"
           f"// clock-tree pins reconnected to clk. Do not edit; regenerate.\n")
    open(os.path.join(outdir, "pilot.v"), "w").write(hdr + body)
    # placement: DEF position, or --relocate; then legality (G1) on the site grid with the chip's
    # fixed taps/endcaps; any cell that overlaps (e.g. a pre-sized, wider master) moves to the nearest gap
    import placelib
    G = placelib.Grid(fdef)
    pos, missing = {}, []
    for nm, master in kept:
        if nm in reloc:
            x, y, o = reloc[nm]
        else:
            c = D["comps"].get(nm)
            if c is None or c["x"] is None:
                missing.append(nm)
                continue
            x, y, o = c["x"], c["y"], c["orient"]
        pos[nm] = [x, y, o]
    assert not missing, missing[:10]
    order = sorted(kept, key=lambda t: (t[0] in presize, t[0]))  # pre-sized cells yield their spot
    clashing = []
    for nm, master in order:
        if G.overlaps(nm, master, pos[nm][0], pos[nm][1]):
            clashing.append((nm, master))
        else:
            G.place(nm, master, pos[nm][0], pos[nm][1])
    moves = []
    cellmap = {nm: [kept_master[nm]] + list(pos[nm]) for nm, _ in kept if (nm, kept_master[nm]) not in clashing}
    for nm, master in clashing:
        frm = list(pos[nm])
        cellmap[nm] = [master] + frm
        res = placelib.slide_insert(G, cellmap, nm, master, frm[0], frm[1])
        if res is None:   # no segment within +-3 rows has capacity: nearest free gap
            del cellmap[nm]
            x, y, o, d = G.find_spot(master, frm[0], frm[1])
            o = {"N": "FN", "FS": "S"}[o] if frm[2] in ("FN", "S") else o
            cellmap[nm] = [master, x, y, o]
            G.place(nm, master, x, y)
            res = (d, [])
        moves.append({"inst": nm, "master": master.replace(pdlib.PFX, ""), "from": frm, "to": cellmap[nm][1:],
                      "displacement_um": round(res[0], 2), "neighbours_slid": res[1]})
    for nm in cellmap:
        pos[nm] = cellmap[nm][1:]
    # G1 assertions: on-site, in-core, row orientation, no overlap (cells, taps, endcaps)
    for nm, master in kept:
        x, y, o = pos[nm]
        r = placelib.to_row(y)
        placelib.to_site(x)
        assert o in (("N", "FN") if r % 2 == 0 else ("FS", "S")), (nm, o, r)
        assert not G.overlaps(nm, master, x, y), (nm, G.overlaps(nm, master, x, y))
    lines = [f"{nm} {pos[nm][0]:.3f} {pos[nm][1]:.3f} {pos[nm][2]}" for nm, _ in kept]
    open(os.path.join(outdir, "placement.cfg"), "w").write("\n".join(lines) + "\n")
    json.dump(moves, open(os.path.join(outdir, "legalize_moves.json"), "w"), indent=1)
    man = {"tag": tag, "source_netlist": nl, "source_netlist_sha256": pdlib.sha(nl, 64),
           "source_def": fdef, "source_def_sha256": pdlib.sha(fdef, 64),
           "kept_instances": len(kept), "removed_physical": len(removed_phys), "removed_clock_tree": len(removed_cts),
           "removed_clock_tree_names": [n for n, _ in removed_cts], "clock_nets_removed": sorted(cts_nets),
           "clock_pins_reconnected": n_reconn, "port_assigns_folded": n_assign, "relocated": len(reloc),
           "presized": presize, "legalize_moves": len(moves),
           "pilot_v_sha256": pdlib.sha(os.path.join(outdir, "pilot.v"), 64),
           "placement_cfg_sha256": pdlib.sha(os.path.join(outdir, "placement.cfg"), 64)}
    json.dump(man, open(os.path.join(outdir, "manifest.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in man.items() if k not in ("removed_clock_tree_names", "clock_nets_removed")}, indent=1))


if __name__ == "__main__":
    main()
