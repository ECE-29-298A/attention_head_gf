#!/usr/bin/env python3
"""Map the configured top using the pinned GF180 library and optionally route it."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = "gf180mcu_fd_sc_mcu7t5v0"
SCL = ROOT / "pdk/gf180mcu-pdk/libraries" / LIBRARY / "latest"
CORNERS = {
    "tt": "tt_025C_3v30",
    "ss": "ss_125C_3v00",
    "ff": "ff_n40C_3v60",
}


def merge_liberty(corner, target):
    header = (SCL / "liberty" / f"{LIBRARY}__{corner}.lib").read_text().rstrip()
    fragments = sorted((SCL / "cells").glob(f"*/*__{corner}.lib"))
    if not header.endswith("}") or len(fragments) != 229:
        raise ValueError(f"Incomplete GF180 7-track library for {corner} at {SCL}")
    with target.open("w") as output:
        output.write(header[:-1] + "\n")
        for fragment in fragments:
            output.write(fragment.read_text() + "\n")
        output.write("}\n")


def run_logged(command, work, log, env=None):
    with log.open("w") as output:
        result = subprocess.run(command, cwd=work, env=env,
                                stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(f"{command[0]} exited {result.returncode}. See {log}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yosys", default="yosys")
    parser.add_argument("--openroad", default="openroad")
    parser.add_argument("--output", type=Path, default=ROOT / "build/gf180_one_tile")
    parser.add_argument("--tile-def", type=Path, help="Tiny Tapeout GF180 1x1 DEF. Enables physical checks.")
    parser.add_argument("--clock-period", type=float, help="Override the configured clock period in ns")
    parser.add_argument("--rcx-rules", type=Path,
                        help="Directory containing rcx-nom.rules, rcx-min.rules, rcx-max.rules")
    args = parser.parse_args()
    if args.clock_period is not None and args.clock_period <= 0:
        parser.error("--clock-period must be positive")
    if args.rcx_rules and not args.tile_def:
        parser.error("--rcx-rules requires --tile-def")
    project = yaml.safe_load((ROOT / "info.yaml").read_text())["project"]
    if project["tiles"] != "1x1":
        raise SystemExit("This flow requires a 1x1 project.")
    top = project["top_module"]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources = " ".join(f'"{ROOT / "src" / name}"' for name in project["source_files"])
    for label, corner in CORNERS.items():
        if label == "tt" or args.tile_def:
            merge_liberty(corner, output / f"{label}.lib")

    (output / "synth.ys").write_text(f"""read_verilog -sv {sources}
hierarchy -check -top {top}
synth -top {top} -flatten -noabc
dfflibmap -liberty tt.lib
abc -liberty tt.lib
setundef -zero
hilomap -singleton -hicell {LIBRARY}__tieh Z -locell {LIBRARY}__tiel ZN
clean
read_liberty -lib -ignore_miss_func tt.lib
delete t:$scopeinfo
check -mapped -assert
stat -liberty tt.lib
write_verilog -noattr -noexpr -nodec mapped.v
""")
    synth_log = output / "synth.log"
    run_logged([args.yosys, "-Q", "-s", "synth.ys"], output, synth_log)
    area = re.search(r"Chip area for module '[^']+':\s*([0-9.]+)", synth_log.read_text())
    if area is None:
        raise SystemExit(f"Yosys did not report mapped cell area. See {synth_log}")
    print(f"Mapped standard-cell area: {float(area[1]):,.4f} µm²", flush=True)

    if args.tile_def:
        tile_def = args.tile_def.resolve(strict=True)
        if not re.search(r"DIEAREA\s*\(\s*0\s+0\s*\)\s*\(\s*693280\s+321440\s*\)",
                         tile_def.read_text()):
            raise SystemExit(f"Unexpected GF180 1x1 die boundary in {tile_def}")
        config = json.loads((ROOT / "src/config.json").read_text())
        env = os.environ | {
            "ATTENTION_TOP": top,
            "ATTENTION_SCL": str(SCL),
            "ATTENTION_TILE_DEF": str(tile_def),
            "ATTENTION_CLOCK_PERIOD": str(args.clock_period or config["CLOCK_PERIOD"]),
            "ATTENTION_PLACEMENT_DENSITY": str(config["PL_TARGET_DENSITY_PCT"] / 100),
        }
        route_log = output / "route.log"
        run_logged([args.openroad, "-no_init", "-exit", str(ROOT / "scripts/gf180_one_tile.tcl")],
                   output, route_log, env)
        print(f"Physical checks passed. See {route_log}", flush=True)

        if args.rcx_rules:
            sta_tcl = str(ROOT / "scripts/gf180_one_tile_sta.tcl")
            for corner in ("nom", "min", "max"):
                rules = (args.rcx_rules / f"rcx-{corner}.rules").resolve(strict=True)
                extract_env = env | {"ATTENTION_RC_CORNER": corner,
                                     "ATTENTION_RC_RULES": str(rules)}
                run_logged([args.openroad, "-no_init", "-exit", sta_tcl],
                           output, output / f"extract-{corner}.log", extract_env)
            sta_log = output / "sta.log"
            run_logged([args.openroad, "-no_init", "-exit", sta_tcl], output, sta_log, env)
            report = sta_log.read_text()
            for line in report.splitlines():
                if line.startswith("worst slack"):
                    print(line)
            if "(VIOLATED)" in report:
                raise SystemExit(f"Extracted timing or electrical checks need repair. See {sta_log}")


if __name__ == "__main__":
    main()
