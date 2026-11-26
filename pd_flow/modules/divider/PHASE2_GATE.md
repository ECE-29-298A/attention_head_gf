# divider: Phase 2 gate (area optimization)

Date: 2026-11-26. Verdict: **c06 ACCEPTED.**
- RTL: `opt/best/divider.v`, sha256 `9e6530df73bc40f0…`.
- Lemmas: `opt/best/divider_lemmas.sv`, sha256 `20908a91b590ff0c…`.

**What c06 changes:**
- The dividend/quotient register is 19 bits instead of 23; the 4 constant-zero bits are not stored.
- Quotient bits are stored pre-complemented, which removes about 12 XORs.
- The state register is merged into the 5-bit step counter: 0–22 divide, 23 round, 24 idle/reset.
- Flops go from 57 to 50.
- Ports, parameters, defaults and cycle behaviour are identical. It relies on **no** caller
  guarantee (A1–A4).

**Frozen contract `549f089fd92465c1`, with c06 and its lemma file** (orchestrator runs):
- RTL: all_ok, 23/23. `seq_eq_00` and `seq_eq_11` are proven, as are `equiv_00/11`.
  - `eqy_rtl` fails, which is expected because the state is re-encoded; it is non-gating.
  - `fv_result` is unsupported, which is non-gating; correctness follows by transitivity.
- Gate, contract recipe `verif/gate/synth_gf180.sh`:
  - 00: 14/14, 7,810.5 µm² (golden 8,853);
  - 11: 13/13, 10,012.3 µm².
  - Agent 3's renamed LibreLane netlist was **not** used, because a candidate-authored transform
    does not belong in the gate path. The shipped LibreLane netlist is covered at assembly by
    full-chip equivalence and LVS.
- `test/divider` and `test/controller` pass unmodified (Agent 3).

**Area, shipped-flow x0 config, flat synthesis** (`opt/OPTIMIZATION.md`):
- **Chip:** 40,725.4 → 40,358.8 µm², **−367**. All 7 cosmetic texts of c06 come in at −329 to −498.
- **In-context divider cone:** 8,423.0 → 7,746.9 µm², **−676 (−8.0%)**.
- Every c06 text is below the golden noise band.

**For the next steps:**
- **Assembly:** c06 is applied to `src/divider.v` at chip assembly, together with F1+F2. Until
  then `src/` is untouched.
- **Datapath placement:** the netlist changes, so the datapath placement (`xpk20_s1`, keyed by
  instance name) must be re-mapped and re-screened on the new netlist.
- **Controller testbench:** it probes `divider_unit.step`; c06 keeps the golden `step` values while
  busy, and reads 24 instead of 0 when idle.
