# GF180MCU area assessment

The area target is the official GF180MCU **7-track, 5 V standard-cell library**
at the typical 25 °C, 5.00 V corner. The 7-track cells are 3.92 µm high; the
official 9-track alternative is 5.04 µm high. This comparison is for the byte
engines alone, without IO pads, caller logic, clock tree, or placement overhead.

Source: [GF180MCU 7-track cell repository](https://github.com/google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0)
at commit `43beb45e4d323a76239de436db2df6732e9a689b`. The repository ships a
Liberty header and 229 individual cell Liberty fragments. The script merges
these into a single library for Yosys.

To reproduce the sequential-cell comparison with Yosys:

```sh
git clone https://github.com/google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0.git /tmp/gf180mcu_7t
git -C /tmp/gf180mcu_7t checkout 43beb45e4d323a76239de436db2df6732e9a689b
python3 scripts/spi_byte_gf180_area.py --pdk-checkout /tmp/gf180mcu_7t --yosys yosys \
    --baseline-core benchmarks/spi_byte_baseline.v
```

The baseline is the byte engine before this GF180-specific optimization.
Add `--full` when Yosys and ABC can complete technology mapping. The
script writes complete logs under `build/spi_byte_gf180_area/`.

The local YoWASP Yosys 0.70 build completed `synth -noabc` and `dfflibmap`,
but its ABC process stopped before mapping combinational cells. The measured
Liberty areas below are therefore **sequential-cell area only**, not total
block area:

| Block | Prior RTL | Optimized RTL | Reduction |
| --- | ---: | ---: | ---: |
| QSPI | 1874.7008 µm² | 1677.1328 µm² | 197.5680 µm² (10.54%) |
| OSPI | 2173.2480 µm² | 1931.7760 µm² | 241.4720 µm² (11.11%) |

The optimized QSPI uses 18 `dffq_1`, 5 `dffrnq_1`, and 2 `dffsnq_1` cells;
the optimized OSPI uses 22, 5, and 2 respectively. Generic combinational
cell counts before ABC changed from 80 to 79 for QSPI and 93 to 87 for OSPI.
These gate counts do not establish a combinational area reduction. Full mapped
area and timing require a native Yosys/ABC run with the selected GF180 cell
library and target clock constraint.
