---
name: signoff-operator
description: Specialized skill for GDSII stream-out, KLayout DRC smoke checks, Netgen LVS comparison, and Magic extraction triage. Guides agents through honest physical-verification verdicts and their limits.
---

# Signoff Operator Skill

This skill guides coding agents through post-P&R physical verification with open-source tools. Its core discipline is **verdict honesty**: report exactly what each tool proved, and never upgrade smoke checks into signoff.

---

## 1. The Handoff Chain

```text
[routed DEF] --gds_stream_out--> [GDSII] --drc_klayout--> [DRC findings]
[layout (.mag/GDS)] --extract_magic--> [layout.spice] --lvs_netgen--> [match/mismatch vs schematic.spice]
```

- `gds_info` first when handed an unknown layout: top cells, layers, bbox, shape counts. No PDK needed.
- `gds_stream_out` produces **abstract-level** GDS (cell footprints from LEF, no transistor geometry): valid DRC input and handoff preview, not tapeout GDS.

## 2. Verdict Discipline

- **DRC**: default is a generated generic width/space smoke deck over the layout's own layers — geometry sanity, NOT foundry signoff. A real verdict needs a PDK rule deck via `deck_file`. Zero findings on the smoke deck means "no gross errors," never "DRC clean."
- **LVS**: Netgen compares SPICE-vs-SPICE structurally (`nosetup` default). **Property errors count as mismatch** even when topology matches. For GF180MCU, use the matching PDK setup file and device models when available; require real routed wires (`detail_route`) and a corresponding schematic SPICE netlist before claiming a full-loop LVS match.
- **Extraction**: Magic runs on generic technology without a PDK tech file — correct flow plumbing, device values not trustworthy. Require `tech_file` before quoting extracted numbers.
- **Failure taxonomy**: `INCONCLUSIVE`/tool-error (missing files, unreadable GDS) is reported as tool failure with the stderr tail, never as a clean bill.

## 3. Checklist

- [ ] Did `gds_info` confirm the expected top cell and layers before checking?
- [ ] Is the DRC deck identified (generated-smoke vs PDK) in the verdict?
- [ ] For LVS mismatch: are property errors distinguished from topology mismatches?
- [ ] Are `*.lyrdb` / `comp.out` artifacts referenced by path, not pasted inline?
- [ ] Does any "clean" claim name the deck and scope that produced it?
