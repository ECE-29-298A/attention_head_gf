# Shared context for workflow agents

Project root: `/Users/samuelzhang/Desktop/2B ECE/attention_head_gf` (**the path contains a space:
quote every path** in shell, Yosys, SBY and EQY scripts; in `.sby`/`.eqy` `[files]` sections,
copy files in or use relative paths rather than absolute ones).
Read `pd_flow/PHASE0_AUDIT.md` first: the hierarchy, invariants, CDC/reset rules, baseline
metrics and tool notes are there.

## Rules
- Golden (original) RTL: `pd_flow/baseline/original_rtl/`. Never edit it.
- Work only inside your module directory `pd_flow/modules/<module>/<phase>/`, unless your brief
  says otherwise. Do not edit `src/`, `test/`, `info.yaml`, the reference project, the PDK or
  installed tools. Do not commit or push. The orchestrator commits.
- Never weaken a check to make it pass. Report failures, counterexamples and timeouts as they are.
- Label every result as one of: proven (unbounded), bounded-pass (depth k), failed,
  timed-out, unsupported, inconclusive. A cover witness or bounded pass is not a proof.
- Keep logs, counterexamples/witnesses and machine-readable results (JSON) in your directory.
- CPU budget: at most 8 concurrent jobs in total. Do not nest parallelism.

## Tools (native macOS)
```bash
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
PY=/usr/local/bin/python3                 # has cocotb 2.0, pytest, click, numpy
$PY ~/.local/bin/sby -f x.sby             # SymbiYosys: MUST be run with this python
$PY ~/.local/bin/eqy -f x.eqy             # EQY: same
yosys (0.71), yosys-smtbmc, z3, yosys-abc, verilator 5.046, iverilog/vvp, ngspice-47
```
Working smoke references: `/Users/samuelzhang/formal_tools/smoke_test/counter.sby`
(k-induction) and `example.eqy` (SAT equivalence).

Existing regression: `pd_flow/scripts/regress.sh <logdir>` (all suites, about 30 s).
Mapped area: `pd_flow/scripts/synth_area.py [--rtl DIR] [--out JSON] [module ...]`, with module
names as in its TARGETS table.

## Physical (Docker, LibreLane 3.0.14)
```bash
source /Users/samuelzhang/ttsetup/env.sh   # PDK_ROOT, PDK=gf180mcuD, docker on PATH
IMG=ghcr.io/librelane/librelane:3.0.14
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
docker run --rm -v "$PDKV:$PDKV" -v "<work>:<work>" -w "<work>" $IMG bash -lc '...'
```
The container has openroad, opensta, magic, netgen, klayout 0.30.7, yosys 0.62. Docker memory
is 7.65 GiB. Mount space-free host paths only, such as `/Users/samuelzhang/ttharden/...`, and
copy results back into `pd_flow/`. GF180 PDK (gf180mcuD): `$PDKV/gf180mcuD/libs.tech/{klayout,magic,netgen,ngspice}`,
`libs.ref/gf180mcu_fd_sc_mcu7t5v0` (7-track cells used by the chip). Hardware tetrising
method: `/Users/samuelzhang/Desktop/HW_tetrising_ai/*.md`.

## Host KLayout (works natively, preferred for layout scripting and DRC)
```bash
K=/Applications/klayout.app/Contents/MacOS/klayout    # KLayout 0.30.14; batch: $K -b -r script.py|.drc -rd var=value
DRC=$PDKV/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc
$K -b -r $DRC -rd input=x.gds -rd topcell=X -rd report=x.lyrdb -rd feol=true -rd beol=true -rd offgrid=true -rd run_mode=deep
```
LVS deck: `$PDKV/gf180mcuD/libs.tech/klayout/tech/lvs/`. Reference point: the PDK's own
`gf180mcu_fd_sc_mcu7t5v0__addf_1`, checked standalone, reports 4 items (DF.13_MV, DF.14_MV).
These are probably well/tap context rules that clear once the cell sits in a placed row
(unconfirmed). Compare a custom cell standalone against this and in-row context separately.
`python3 -c 'import klayout.db'` is not installed on the host. Use `$K -b -r` for Python
scripts (the `klayout.db`/`pya` API is available inside).

## Layout scope (user decision D4, overrides the workflow's transistor-level wording)
Custom layout means **custom placement of existing GF180 7-track standard cells only**
(tetrising). Do not design transistor-level cells. Do not hand-draw routing.
Connections between cell ports are made by automatic routing (OpenROAD global and detailed
routing) with the placement fixed. Use as little manual routing guidance as possible. Routing
relief that changes placement, such as spacing or filler, is allowed. The Phase 3 deliverable
is a scripted, coordinate-level cell placement (row, site, orientation per instance) plus the
gate-level netlist it places. Phase 4 generates the placement, fixes it, routes it
automatically, then runs DRC, LVS, extraction and characterization.
