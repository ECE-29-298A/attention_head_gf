---
name: fpga-operator
description: "Specialized skill for open-source FPGA flows (iCE40/ECP5): Yosys synthesis, nextpnr place-and-route, bitstream packing, board presets, and safe hardware programming practices."
---

# FPGA Operator Skill

This skill guides coding agents through Lattice FPGA implementation with Yosys + nextpnr + icepack/ecppack. Use it for board-targeted builds; ASIC flows belong to `asic-flow-operator`.

---

## 1. The Flow ( synth → P&R → bitstream → program )

```text
[RTL (.v)] --fpga_synth--> [JSON netlist] --fpga_place_route--> [.asc/.config + util/Fmax]
  --fpga_bitstream--> [.bin/.bit] --fpga_program--> [board flash]
```

- **Family first**: `ice40` (synth_ice40 → nextpnr-ice40 → icepack) vs `ecp5` (synth_ecp5 → nextpnr-ecp5 → ecppack). Never mix families in one chain.
- **Boards over raw pairs**: prefer presets (`icebreaker` → up5k/sg48, `hx8k` → hx8k/ct256, `ulx3s_45f`, `ecp5_25k`). Explicit device/package overrides presets; unknown boards fail fast with a pointer to `fpga_boards`.
- **Read the report, not the log**: `--report` JSON gives utilization per resource (`ICESTORM_LC.used/avail`) and `fmax.achieved` vs `constraint`. A successful exit with 95%+ LC utilization is a congestion warning, not a victory.

## 2. Programming Safety (Non-Negotiable)

- **Dry-run default**: `fpga_program` plans (`iceprog <file>`) without touching hardware. Only set `dry_run: false` on a host with the board on USB, and report `flashed` plus tool output — never assume the blink.
- **ECP5 gap**: openFPGALoader is absent from the image. ECP5 bitstreams are built (`ecppack --compress` supported) but flashed externally; say so explicitly.
- **No-HW honesty**: "bitstream built, flashing unverified" is a complete, honest result. Do not simulate programming success.

## 3. Triage Playbook

| Symptom | Diagnosis | Action |
| :--- | :--- | :--- |
| nextpnr "premature end" / JSON parse fail | synth JSON stale or wrong top | Re-run `fpga_synth`, confirm top name matches. |
| Utilization > 90% LC | Device too small or unconstrained replication | Move up a device/preset or constrain with a `.pcf`. |
| Fmax achieved < constraint | Long carry chains / placement spread | Add pipeline registers; try a bigger speed grade. |
| `SIM=verilator` cocotb path | Needs Verilator ≥ 5.036 (image ships 5.020) | Simulate with icarus; note the version gate. |

## 4. Checklist

- [ ] Does the family stay consistent across synth → P&R → pack?
- [ ] Is device/package from a preset (or explicitly justified)?
- [ ] Are utilization and Fmax quoted from the report (not guessed)?
- [ ] Is programming reported as dry-run unless hardware output proves otherwise?
