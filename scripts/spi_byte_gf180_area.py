#!/usr/bin/env python3
"""Map QSPI/OSPI RTL to GF180MCU 7-track cells and report cell area.

Supply either a merged Liberty file or a checkout of the official cell repo.
The default `sequential` mode reports mapped flop area only. Use `--full`
with a native Yosys/ABC installation for complete mapped logic area.
"""

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORNER = "tt_025C_5v00"
LIB_NAME = "gf180mcu_fd_sc_mcu7t5v0"


def merge_liberty(checkout: Path, destination: Path) -> Path:
    header_file = checkout / "liberty" / f"{LIB_NAME}__{CORNER}.lib"
    header = header_file.read_text().rstrip()
    if not header.endswith("}"):
        raise ValueError(f"Invalid Liberty header: {header_file}")
    cells = sorted((checkout / "cells").glob(f"*/*__{CORNER}.lib"))
    if len(cells) != 229:
        raise ValueError(f"Expected 229 GF180 7-track cells; found {len(cells)}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w") as out:
        out.write(header[:-1] + "\n")
        for cell in cells:
            out.write(cell.read_text() + "\n")
        out.write("}\n")
    return destination


def measure(yosys: str, lib: Path, top: str, core: Path,
            full: bool, log_dir: Path, label: str) -> tuple[float, int]:
    sources = [core, ROOT / "src/qspi_byte.v", ROOT / "src/ospi_byte.v"]
    commands = [
        "read_verilog " + " ".join('"' + str(p).replace('\\', '\\\\').replace('"', '\\"') + '"' for p in sources),
        f"synth -noabc -flatten -top {top}",
        f"dfflibmap -liberty {lib}",
    ]
    if full:
        commands += [f"abc -liberty {lib}", "clean"]
    commands += [f"stat -liberty {lib}"]
    result = subprocess.run([yosys, "-Q", "-p", "; ".join(commands)],
                            capture_output=True, text=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{label}_{top}.log"
    log.write_text(result.stdout + result.stderr)
    if result.returncode or "End of script." not in result.stdout:
        raise RuntimeError(f"Yosys did not finish; inspect {log}")
    section = result.stdout.rsplit(f"=== {top} ===", 1)[-1]
    match = re.search(r"Chip area for module '[^']+':\s*([0-9.]+)", section)
    if match is None:
        raise RuntimeError(f"No mapped area in {log}")
    unknown = re.findall(r"Area for cell type (\S+) is unknown!", section)
    if full and unknown:
        raise RuntimeError(f"Full mapping left unknown cells {unknown}; see {log}")
    generic = sum(int(n) for n in re.findall(
        r"^\s*(\d+)\s+-\s+\$_\w+_\s*$", section, re.M))
    return float(match.group(1)), generic


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--lib", type=Path, help="merged GF180 7-track TT/5V Liberty")
    source.add_argument("--pdk-checkout", type=Path,
                        help="checkout of the official GF180 7-track cell repo")
    parser.add_argument("--yosys", default="yosys", help="Yosys executable")
    parser.add_argument("--baseline-core", type=Path,
                        help="older spi_multi_io_byte.v for comparison")
    parser.add_argument("--full", action="store_true",
                        help="run ABC and report complete mapped logic area")
    args = parser.parse_args()
    log_dir = ROOT / "build/spi_byte_gf180_area"
    lib = (args.lib.resolve() if args.lib else
           merge_liberty(args.pdk_checkout.resolve(), log_dir / f"{LIB_NAME}__{CORNER}.lib"))
    versions = [("optimized", ROOT / "src/spi_multi_io_byte.v")]
    if args.baseline_core:
        versions.insert(0, ("baseline", args.baseline_core.resolve()))
    print("variant,top,area_um2,generic_unmapped_cells,scope")
    for label, core in versions:
        for top in ("qspi_byte", "ospi_byte"):
            area, generic = measure(args.yosys, lib, top, core,
                                    args.full, log_dir, label)
            scope = "all_mapped_cells" if args.full else "sequential_cells_only"
            print(f"{label},{top},{area:.4f},{generic},{scope}")


if __name__ == "__main__":
    main()
