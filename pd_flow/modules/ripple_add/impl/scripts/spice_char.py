#!/usr/bin/env python3
"""Post-layout ngspice simulation of the Magic-extracted ripple_add block (devices + parasitic C).

Usage: spice_char.py N CORNER OUTDIR [tests...] [--netlist FILE]
  tests: func delay energy leak cin (default all)
  --netlist FILE  simulate FILE instead of the Magic PEX netlist (used to run the pre-layout
                  schematic built from the PDK cell SPICE, n<N>/lvs/ripple_add_n<N>.spice, for the
                  parasitic decomposition)
  CORNER: tt (typical, 25 C, 3.3 V) | ss (ss, 125 C, 3.0 V) | ff (ff, -40 C, 3.6 V)
          (the same PVT as the Liberty corners tt_025C_3v30 / ss_125C_3v00 / ff_n40C_3v60).

Boundary (stated in every result): ideal voltage-source inputs with a linear 0-100 % ramp of
0.375 ns (= 0.30 ns 10-90 %, = 0.15 ns 30-70 %, i.e. 0.30 ns in the GF180 Liberty slew convention
of 30-70 % with slew_derate_from_library 0.5); every output s[i] loaded with CLOAD = 20 fF to ground
(the Phase 2 module boundary: 0.30 ns, 0.02 pF). Delays at 50 % VDD. Output slews reported as
10-90 %, 30-70 % and Liberty-equivalent (30-70 % / 0.5).

Results: OUTDIR/<corner>_<test>.json (+ the .cir deck and ngspice log). Golden model:
verif/model/golden_model.py (ref, ref_sub).
"""
import json
import random
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMPL = HERE.parent
sys.path.insert(0, str(IMPL.parent / "verif" / "model"))
from golden_model import ref, ref_sub  # noqa: E402

PDKV = "/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee"
NGLIB = f"{PDKV}/gf180mcuD/libs.tech/ngspice"
CORNERS = {"tt": ("typical", 25, 3.3), "ss": ("ss", 125, 3.0), "ff": ("ff", -40, 3.6)}
RAMP = 0.375e-9
CLOAD = 20e-15
PERIOD = {"tt": 40e-9, "ss": 90e-9, "ff": 30e-9}   # > 2x the worst Liberty chain delay per corner


def ports_of(pex):
    m = re.search(r"^\.subckt ripple_add (.*?)\n(?!\+)", pex.read_text(), re.S | re.M | re.I)
    return m.group(1).replace("\n+", " ").split()


class Deck:
    def __init__(self, n, corner, pex):
        self.n, self.corner, self.pex = n, corner, pex
        self.lib, self.temp, self.vdd = CORNERS[corner]
        self.ports = ports_of(pex)
        self.pex_rel = None   # set by main(): path relative to OUTDIR (project path has a space)
        self.inputs = [f"a[{i}]" for i in range(n)] + [f"b[{i}]" for i in range(n)] + ["cin"]
        self.outputs = [f"s[{i}]" for i in range(n)]
        assert sorted(self.ports) == sorted(self.inputs + self.outputs + ["VPWR", "VGND"])

    @staticmethod
    def node(p):
        return p.replace("[", "_").replace("]", "")

    def header(self, title):
        x = " ".join(self.node(p) if p not in ("VPWR", "VGND") else ("vpwr" if p == "VPWR" else "0")
                     for p in self.ports)
        lines = [f"* {title}", f".include {NGLIB}/design.ngspice",
                 f".lib {NGLIB}/sm141064.ngspice {self.lib}", f".include {self.pex_rel}",
                 f".temp {self.temp}", ".options method=gear reltol=1e-4 abstol=1e-13",
                 f"VDD vpwr 0 {self.vdd}", f"X1 {x} ripple_add"]
        lines += [f"C_{self.node(o)} {self.node(o)} 0 {CLOAD}" for o in self.outputs]
        return lines

    def pwl(self, name, events, init):
        """events: list of (t, value_bit). Linear ramps of RAMP starting at t."""
        v = self.vdd
        pts, cur = [(0.0, init * v)], init
        for t, b in events:
            if b == cur:
                continue
            pts += [(t, cur * v), (t + RAMP, b * v)]
            cur = b
        return f"V_{self.node(name)} {self.node(name)} 0 PWL(" + " ".join(f"{t:.6e} {y:.4f}" for t, y in pts) + ")"

    def vector_sources(self, vecs, period, t0=2e-9):
        """vecs: list of (a, b, cin); vector k applied at t0 + k*period."""
        out = []
        for name in self.inputs:
            if name == "cin":
                bits = [c for _, _, c in vecs]
            else:
                k, i = name[0], int(name[2:-1])
                bits = [((a if k == "a" else b) >> i) & 1 for a, b, _ in vecs]
            ev = [(t0 + j * period, bits[j]) for j in range(1, len(vecs))]
            out.append(self.pwl(name, ev, bits[0]))
        return out


def run(deck_lines, path):
    path.write_text("\n".join(deck_lines + [".end", ""]))
    p = subprocess.run(["ngspice", "-b", path.name], capture_output=True, text=True, timeout=3600,
                       cwd=str(path.parent))
    log = path.with_suffix(".log")
    log.write_text(p.stdout + p.stderr)
    meas = {}
    for m in re.finditer(r"^(\w+)\s*=\s*([-+0-9.eE]+)", p.stdout, re.M):
        meas[m.group(1).lower()] = float(m.group(2))
    if p.returncode != 0 or "error" in (p.stderr or "").lower() and not meas:
        raise SystemExit(f"ngspice failed ({p.returncode}) on {path}; see {log}")
    return meas, p.stdout


def bits_of(n, vals, prefix):
    return sum((1 << i) for i in range(n) if vals[f"{prefix}{i}"] > 0.5)


def test_func(d, out):
    n, mask = d.n, (1 << d.n) - 1
    rng = random.Random(20261126)
    vecs, kinds = [], []

    def add(a, b, c, kind):
        vecs.append((a & mask, b & mask, c))
        kinds.append(kind)
    add(0, 0, 0, "zero")
    add(mask, 0, 0, "a=all-ones, cin=0 (carry-propagate setup)")
    add(mask, 0, 1, "full carry ripple: cin 0->1 with a=all-ones (s -> 0)")
    add(mask, 0, 0, "full carry ripple back: cin 1->0")
    add(0, mask, 1, "b=all-ones, cin=1 (s -> 0)")
    add(mask, mask, 1, "a=b=all-ones, cin=1")
    add(1, mask, 0, "carry from a[0]: 1 + all-ones")
    for a, x in ((1000, 1234), (0x2AAAAA & mask, 0x155555 & mask), (5, 5), (0, 1)):
        add(a, ~x & mask, 1, f"subtract form a + ~x + 1, a={a}, x={x} (golden ref_sub)")
    for _ in range(8):
        add(rng.getrandbits(n), rng.getrandbits(n), rng.getrandbits(1), "random (seed 20261126)")
    per = PERIOD[d.corner]
    t0 = 2e-9
    lines = d.header(f"ripple_add N={n} functional, corner {d.corner}") + d.vector_sources(vecs, per, t0)
    for k in range(len(vecs)):
        ts = t0 + (k + 1) * per - 0.5e-9
        for i in range(n):
            lines.append(f".meas tran v{k}_s{i} FIND v({d.node(f's[{i}]')}) AT={ts:.6e}")
    tstop = t0 + len(vecs) * per
    lines.append(f".tran 20p {tstop:.6e}")
    meas, _ = run(lines, out / f"{d.corner}_func.cir")
    rows, ok = [], True
    for k, (a, b, c) in enumerate(vecs):
        vals = {f"s{i}": meas[f"v{k}_s{i}"] / d.vdd for i in range(n)}
        got = bits_of(n, vals, "s")
        exp = ref(a, b, c, n)
        if "subtract" in kinds[k]:
            x = (~b) & mask
            assert ref_sub(a, x, n) == exp
        margin = max(min(v, 1 - v) for v in vals.values())   # worst distance from a rail
        good = got == exp and margin < 0.1
        ok &= good
        rows.append({"k": k, "kind": kinds[k], "a": hex(a), "b": hex(b), "cin": c, "expected": hex(exp),
                     "spice": hex(got), "pass": good,
                     "worst_logic_level_error_frac_vdd": round(margin, 4)})
    res = {"test": "functional", "corner": d.corner, "pvt": CORNERS[d.corner], "N": n,
           "period_ns": per * 1e9, "sample": "0.5 ns before the next vector",
           "vectors": len(vecs), "pass": ok, "rows": rows}
    return res


def test_delay(d, out):
    n, mask = d.n, (1 << d.n) - 1
    per = PERIOD[d.corner]
    t0 = 2e-9
    hv = d.vdd / 2
    # scenario: (driving input, static a, static b, static cin); the input toggles 0->1->0
    scen = [("cin", mask, 0, None), ("a[0]", mask & ~1, 0, 1), ("b[0]", mask & ~1, 0, 1)]
    out_res = {"test": "delay", "corner": d.corner, "pvt": CORNERS[d.corner], "N": n,
               "boundary": {"input_ramp_0_100_ns": RAMP * 1e9, "input_slew_10_90_ns": RAMP * 0.8e9,
                            "liberty_equiv_input_slew_ns": RAMP * 0.4e9 / 0.5, "cload_fF": CLOAD * 1e15},
               "arcs": {}}
    for drv, a, b, c in scen:
        lines = d.header(f"ripple_add N={n} carry-chain delay from {drv}, corner {d.corner}")
        for name in d.inputs:
            if name == drv:
                lines.append(d.pwl(name, [(t0 + per, 1), (t0 + 2 * per, 0)], 0))
                continue
            if name == "cin":
                bit = c
            else:
                k, i = name[0], int(name[2:-1])
                bit = ((a if k == "a" else b) >> i) & 1
            lines.append(d.pwl(name, [], bit))
        dn = d.node(drv)
        for edge, tw in (("rise", t0 + per), ("fall", t0 + 2 * per)):
            ed = "RISE" if edge == "rise" else "FALL"
            for i in range(n):
                s = d.node(f"s[{i}]")
                lines.append(f".meas tran d_{edge}_s{i} TRIG v({dn}) VAL={hv} {ed}=1 TD={tw - 1e-9:.6e} "
                             f"TARG v({s}) VAL={hv} CROSS=1 TD={tw - 1e-9:.6e}")
                for lo, hi, tag in ((0.1, 0.9, "1090"), (0.3, 0.7, "3070")):
                    # the output edge opposite to the driving edge for s[N-1]; CROSS-based for others
                    lines.append(f".meas tran tl{tag}_{edge}_s{i} WHEN v({s})={lo * d.vdd} CROSS=1 "
                                 f"TD={tw - 1e-9:.6e}")
                    lines.append(f".meas tran th{tag}_{edge}_s{i} WHEN v({s})={hi * d.vdd} CROSS=1 "
                                 f"TD={tw - 1e-9:.6e}")
        lines.append(f".tran 10p {t0 + 3 * per:.6e}")
        meas, _ = run(lines, out / f"{d.corner}_delay_{dn}.cir")
        arc = {}
        for edge in ("rise", "fall"):
            per_bit, slews = [], []
            for i in range(n):
                dl = meas.get(f"d_{edge}_s{i}")
                s1090 = abs(meas.get(f"th1090_{edge}_s{i}", float("nan")) - meas.get(f"tl1090_{edge}_s{i}", float("nan")))
                s3070 = abs(meas.get(f"th3070_{edge}_s{i}", float("nan")) - meas.get(f"tl3070_{edge}_s{i}", float("nan")))
                per_bit.append(None if dl is None else round(dl * 1e9, 4))
                slews.append((round(s1090 * 1e9, 4), round(s3070 * 1e9, 4)))
            msb = per_bit[n - 1]
            arc[edge] = {"to_s_msb_ns": msb,
                         "per_bit_delay_ns": per_bit,
                         "s_msb_slew_10_90_ns": slews[n - 1][0], "s_msb_slew_30_70_ns": slews[n - 1][1],
                         "s_msb_slew_liberty_equiv_ns": round(slews[n - 1][1] / 0.5, 4),
                         "max_output_slew_10_90_ns": max(s[0] for s in slews),
                         "max_output_slew_liberty_equiv_ns": round(max(s[1] for s in slews) / 0.5, 4)}
        out_res["arcs"][f"{drv}->s[{n-1}]"] = arc
    worst = max((v[e]["to_s_msb_ns"], k, e) for k, v in out_res["arcs"].items() for e in ("rise", "fall"))
    out_res["worst"] = {"delay_ns": worst[0], "arc": worst[1], "input_edge": worst[2]}
    return out_res


def test_energy(d, out):
    n = d.n
    per = PERIOD[d.corner]
    t0 = 2e-9
    rng = random.Random(7)
    m = 40
    vecs = [(rng.getrandbits(n), rng.getrandbits(n), rng.getrandbits(1)) for _ in range(m + 1)]
    mask = (1 << n) - 1
    # worst-case ripple events appended: a=all-ones,b=0 with cin toggling
    vecs += [(mask, 0, 0), (mask, 0, 1), (mask, 0, 0)]
    lines = d.header(f"ripple_add N={n} energy, corner {d.corner}") + d.vector_sources(vecs, per, t0)
    for k in range(1, len(vecs)):
        ta = t0 + k * per
        lines.append(f".meas tran q{k} INTEG i(VDD) FROM={ta - 0.2e-9:.6e} TO={ta + per - 0.2e-9:.6e}")
    lines.append(f".tran 20p {t0 + len(vecs) * per:.6e}")
    meas, _ = run(lines, out / f"{d.corner}_energy.cir")
    e = [-meas[f"q{k}"] * d.vdd for k in range(1, len(vecs))]      # J per operation (VDD source)
    rand = e[:m]
    toggles = [sum(bin(vecs[k][j] ^ vecs[k - 1][j]).count("1") for j in range(3)) for k in range(1, m + 1)]
    return {"test": "energy", "corner": d.corner, "pvt": CORNERS[d.corner], "N": n,
            "activity": "each operation draws a, b, cin independently uniform (seed 7): every input bit "
                        "toggles with probability 0.5; 40 operations",
            "window": f"one period ({per * 1e9:.0f} ns) per operation, includes leakage over it",
            "includes": "energy from VDD only: internal + output-load (20 fF each) switching; input pin "
                        "charge comes from the ideal input sources and is NOT included",
            "mean_energy_per_op_pJ": round(sum(rand) / m * 1e12, 4),
            "min_pJ": round(min(rand) * 1e12, 4), "max_pJ": round(max(rand) * 1e12, 4),
            "mean_input_toggles_per_op": sum(toggles) / m,
            "full_ripple_cin_rise_pJ": round(e[m + 1] * 1e12, 4),
            "full_ripple_cin_fall_pJ": round(e[m + 2] * 1e12, 4)}


def test_leak(d, out):
    n, mask = d.n, (1 << d.n) - 1
    rng = random.Random(3)
    states = {"all_zero": (0, 0, 0), "all_one": (mask, mask, 1), "a_ones_b0_cin0": (mask, 0, 0),
              "random_1": (rng.getrandbits(n), rng.getrandbits(n), 1),
              "random_2": (rng.getrandbits(n), rng.getrandbits(n), 0)}
    res = {"test": "leakage", "corner": d.corner, "pvt": CORNERS[d.corner], "N": n, "states": {},
           "options": "gmin=1e-15 abstol=1e-18 (default gmin 1e-12 dominates the result; see header comment)"}
    for nm, (a, b, c) in states.items():
        lines = d.header(f"ripple_add N={n} leakage {nm}, corner {d.corner}")
        # ngspice's default gmin (1e-12 S across every junction) alone draws ~0.7 nA at 3.3 V here,
        # 25x the real tt leakage; gmin 1e-15 / abstol 1e-18 is converged (1e-18 changes < 6%).
        lines = [(".options method=gear reltol=1e-4 abstol=1e-18 gmin=1e-15" if l.startswith(".options") else l)
                 for l in lines]
        for name in d.inputs:
            bit = c if name == "cin" else (((a if name[0] == "a" else b) >> int(name[2:-1])) & 1)
            lines.append(f"V_{d.node(name)} {d.node(name)} 0 {bit * d.vdd}")
        lines += [".control", "op", "print -i(VDD)", ".endc"]
        _, stdout = run(lines, out / f"{d.corner}_leak_{nm}.cir")
        mm = re.search(r"-i\(vdd\)\s*=\s*([-+0-9.eE]+)", stdout, re.I)
        i = float(mm.group(1))
        res["states"][nm] = {"I_nA": round(i * 1e9, 5), "P_nW": round(i * d.vdd * 1e9, 5)}
    vals = [v["P_nW"] for v in res["states"].values()]
    res["mean_P_nW"] = round(sum(vals) / len(vals), 5)
    res["max_P_nW"] = max(vals)
    return res


def test_cin(d, out):
    n = d.n
    slot = 6e-9
    t0 = 2e-9
    lines = d.header(f"ripple_add N={n} input capacitance, corner {d.corner}")
    for j, name in enumerate(d.inputs):
        ts = t0 + j * 2 * slot
        lines.append(d.pwl(name, [(ts, 1), (ts + slot, 0)], 0))
        lines.append(f".meas tran qr_{j} INTEG i(V_{d.node(name)}) FROM={ts - 0.1e-9:.6e} TO={ts + slot - 0.1e-9:.6e}")
        lines.append(f".meas tran qf_{j} INTEG i(V_{d.node(name)}) FROM={ts + slot - 0.1e-9:.6e} TO={ts + 2 * slot - 0.1e-9:.6e}")
    lines.append(f".tran 10p {t0 + len(d.inputs) * 2 * slot:.6e}")
    meas, _ = run(lines, out / f"{d.corner}_cin.cir")
    caps = {}
    for j, name in enumerate(d.inputs):
        cr = -meas[f"qr_{j}"] / d.vdd
        cf = meas[f"qf_{j}"] / d.vdd
        caps[name] = {"rise_fF": round(cr * 1e15, 3), "fall_fF": round(cf * 1e15, 3)}
    def stat(prefix):
        v = [max(c["rise_fF"], c["fall_fF"]) for k, c in caps.items() if k.startswith(prefix)]
        return {"min_fF": min(v), "max_fF": max(v), "mean_fF": round(sum(v) / len(v), 3)}
    return {"test": "input_capacitance", "corner": d.corner, "pvt": CORNERS[d.corner], "N": n,
            "method": "charge drawn from the port's ideal source during a 0.375 ns ramp (and settling, "
                      "6 ns window), C = Q / VDD; all other inputs held at 0, so later ports see the "
                      "state left by earlier ones (each port returns to 0 before the next). Includes pin, "
                      "routing and Miller charge; the comparable Liberty value is the cell pin cap plus "
                      "the routed wire C from SPEF",
            "summary": {"a": stat("a["), "b": stat("b["), "cin": caps["cin"]}, "ports": caps}


TESTS = {"func": test_func, "delay": test_delay, "energy": test_energy, "leak": test_leak, "cin": test_cin}


def main():
    n, corner, outd = int(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    args = sys.argv[4:]
    pex = IMPL / f"n{n}" / "pex" / f"ripple_add_n{n}_pex.spice"
    if "--netlist" in args:
        pex = Path(args[args.index("--netlist") + 1]).resolve()
        del args[args.index("--netlist"):args.index("--netlist") + 2]
    tests = args or list(TESTS)
    outd.mkdir(parents=True, exist_ok=True)
    d = Deck(n, corner, pex)
    import os
    d.pex_rel = os.path.relpath(pex, outd)
    for t in tests:
        r = TESTS[t](d, outd)
        r["pex_netlist"] = str(pex.relative_to(IMPL))
        (outd / f"{corner}_{t}.json").write_text(json.dumps(r, indent=1) + "\n")
        brief = {k: v for k, v in r.items() if k not in ("rows", "ports", "arcs", "states")}
        print(t, corner, json.dumps(brief)[:600])
        if t == "delay":
            for k, v in r["arcs"].items():
                print("  ", k, {e: (v[e]["to_s_msb_ns"], v[e]["s_msb_slew_10_90_ns"]) for e in v})
        if t == "func":
            print("   functional", "PASS" if r["pass"] else "FAIL",
                  [(x["k"], x["pass"]) for x in r["rows"] if not x["pass"]])


if __name__ == "__main__":
    main()
