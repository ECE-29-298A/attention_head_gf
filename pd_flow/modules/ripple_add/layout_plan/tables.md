
**Module level, N=22** (OpenSTA 0.30 ns input slew, 0.02 pF output load, no wire; power: input activity 0.5/cycle at 10 MHz, TT; switched pin C: 4000 random vectors)

| Implementation | Cells | Area µm² | Worst a/b/cin→s TT ns | SS ns | Power TT µW (total) | Switched pin C fF/vector zero-delay | unit-delay |
|---|---:|---:|---:|---:|---:|---:|---:|
| ABC-mapped (module, default ABC) | 95 | 2146.91 | 10.594 | 21.319 | 138.7 | 498.4 | 543.3 |
| pure addf_1 chain | 22 | 1593.72 | 19.908 | 41.429 | 115.8 | 356.0 | 400.5 |
| hybrid: addf_1 + xor3_1 MSB | 22 | 1571.76 | 19.280 | 40.127 | 115.0 | 348.6 | 392.7 |
| addf_2 chain + xor3_1 MSB | 22 | 1710.06 | 18.762 | 38.754 | 147.9 | 352.4 | 396.6 |
| addf_1/addf_2 alternating + xor3_1 MSB | 22 | 1637.62 | 19.037 | 39.483 | 130.8 | 350.4 | 394.6 |

**Module level, N=12** (OpenSTA 0.30 ns input slew, 0.02 pF output load, no wire; power: input activity 0.5/cycle at 10 MHz, TT; switched pin C: 4000 random vectors)

| Implementation | Cells | Area µm² | Worst a/b/cin→s TT ns | SS ns | Power TT µW (total) | Switched pin C fF/vector zero-delay | unit-delay |
|---|---:|---:|---:|---:|---:|---:|---:|
| ABC-mapped (module, default ABC) | 50 | 1148.09 | 6.100 | 12.231 | 73.1 | 264.6 | 286.0 |
| pure addf_1 chain | 12 | 869.30 | 11.172 | 23.195 | 61.7 | 194.1 | 215.3 |
| hybrid: addf_1 + xor3_1 MSB | 12 | 847.35 | 10.545 | 21.893 | 61.0 | 186.7 | 207.5 |
| addf_2 chain + xor3_1 MSB | 12 | 919.79 | 10.268 | 21.160 | 77.8 | 188.8 | 209.5 |
| addf_1/addf_2 alternating + xor3_1 MSB | 12 | 880.28 | 10.423 | 21.571 | 68.7 | 187.7 | 208.4 |

**Chip level** (shipped flow: `ll_synth.sh` synthesis; full `tt_tool.py --harden`; power = LibreLane vectorless STA, nom TT)

| Variant | Synth µm² | Cells | Std-cell µm² | Util % | Repair buf µm² | Setup WNS ss/tt/ff ns | Hold WNS ss/tt/ff ns | Slew/Cap/Fanout | Power mW (int/sw) | Wire µm | DRC/LVS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base: golden RTL, ABC in context (re-run) | 41116.1 | 1434 | 46819.2 | 90.09 | 1154.7 | 41.79 / 70.72 / 76.06 | 1.136 / 0.415 / 0.109 | 381/1/11 | 3.050 (1.934/1.116) | 53890 | 0+0/0 |
| n03: golden, XOR operands swapped (noise) | 41100.7 | 1431 | 46990.5 | 90.42 | 1431.3 | 38.21 / 68.89 / 75.39 | 1.160 / 0.428 / 0.119 | 316/2/13 | 2.971 (1.914/1.057) | 53676 | 0+0/0 |
| n04: golden, OR operands swapped (noise) | 41201.7 | 1414 | 47220.9 | 90.87 | 1396.2 | 42.90 / 71.72 / 75.29 | 1.241 / 0.469 / 0.142 | 260/1/11 | 3.220 (2.044/1.175) | 51958 | 0+0/0 |
| abcfrozen: module ABC netlists frozen as cells | 41972.2 | 1435 | 48037.6 | 92.44 | 1470.8 | 41.37 / 70.92 / 75.36 | 1.232 / 0.465 / 0.140 | 311/1/14 | 3.758 (2.337/1.421) | 57224 | 0+0/0 |
| addf1: pure addf_1 chains (22 + 12) | 41056.8 | 1313 | 47010.2 | 90.46 | 1404.9 | 25.08 / 63.46 / 75.55 | 1.189 / 0.442 / 0.125 | 287/3/11 | 3.435 (2.195/1.240) | 51313 | 0+0/0 |
| hyb: hybrid addf_1 + xor3_1, both widths, carry on xor3 A3 | 41012.9 | 1313 | 46926.8 | 90.30 | 1396.2 | 26.12 / 63.95 / 75.59 | 1.194 / 0.446 / 0.129 | 287/3/10 | 3.421 (2.194/1.227) | 50789 | 0+0/0 |
| hybcos: determinism check: bit-identical to hyb | 41012.9 | 1313 | 46926.8 | 90.30 | 1396.2 | 26.12 / 63.95 / 75.59 | 1.194 / 0.446 / 0.129 | 287/3/10 | 3.421 (2.194/1.227) | 50789 | 0+0/0 |
| hyb22: hybrid on N=22 only, N=12 ABC, carry on A3 | 40922.9 | 1360 | 47471.2 | 91.35 | 1545.4 | 19.20 / 60.28 / 75.97 | 1.113 / 0.404 / 0.104 | 269/3/12 | 3.559 (2.207/1.352) | 54398 | 0+0/0 |
| final: superseded generator RTL, carry on xor3 A1 (slow arc), free placement | 41012.9 | 1313 | 47001.4 | 90.44 | 1426.9 | 23.69 / 62.75 / 75.35 | 1.201 / 0.450 / 0.132 | 308/2/11 | 3.443 (2.199/1.244) | 50460 | 0+0/0 |
| final_mgp: final (A1) + MANUAL_GLOBAL_PLACEMENTS: REJECTED, drift | 41012.9 | 1313 | 46979.5 | 90.40 | 1426.9 | 23.46 / 62.68 / 75.51 | 1.188 / 0.443 / 0.128 | 418/3/13 | 3.821 (2.214/1.607) | 70885 | 0+0/0 |
| final_fixed: final (A1) + MACRO_PLACEMENT_CFG (FIRM) | 41012.9 | 1313 | 46997.0 | 90.44 | 1374.2 | 23.16 / 62.58 / 75.53 | 1.155 / 0.425 / 0.116 | 414/0/12 | 3.611 (2.204/1.407) | 60557 | 0+0/0 |
| fixed_a3: CURRENT generator RTL (carry on A3, RIPPLE_ADD_CELLS) + MACRO_PLACEMENT_CFG (FIRM) | 41012.9 | 1313 | 47040.9 | 90.52 | 1413.7 | 25.26 / 63.58 / 75.56 | 1.188 / 0.441 / 0.126 | 399/0/11 | 3.599 (2.205/1.394) | 59779 | 0+0/0 |
