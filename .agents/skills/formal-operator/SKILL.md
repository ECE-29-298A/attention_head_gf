---
name: formal-operator
description: Specialized skill for formal property verification with SymbiYosys (smtbmc+z3). Guides agents through authoring SVA properties, choosing BMC bounds, interpreting PROVEN/FAILED/UNKNOWN verdicts, and triaging counterexamples.
---

# Formal Operator Skill

This skill guides coding agents through proving SystemVerilog assertions with SymbiYosys instead of only simulating them. Use it after `rtl-reviewer` passes and before relying on any property for signoff.

---

## 1. The Assert Authoring Contract

- **Guard solver-only constructs**: iverilog cannot parse `assert`. Wrap every property block in `` `ifdef FORMAL `` / `` `endif `` and prove with `-DFORMAL` (the `formal_prove` `defines` parameter defaults to it).
- **One property, one intent**: `no_x_after_reset`, `reset_value`, `req_ack_handshake`, `onehot` — the `rtl_generate_assertion` templates. Never hand-write temporal logic when a template fits.
- **Bound the unbounded**: `##[1:$]` liveness must carry a concrete delay bound for BMC tractability.
- **Name clocks and resets explicitly**: every property binds to one `clock` and one `reset` with declared polarity. No implicit clocks.

## 2. Engine Reality (Verified)

- **Available**: `smtbmc z3` (z3 5.1.0) in BMC (`-ditis bounded to depth`) and prove (induction) modes.
- **Excluded**: the ABC/PDR engine crashes parsing witness output against this Yosys build — never select it.
- **Config gotchas baked into `formal_prove`**: engine lines are bare (`smtbmc z3`, no colon); `--noprogress` is never forwarded (z3 rejects it and breaks the pipe); SBY scripts reference basenames (it runs from `src/`).
- **Depth budget**: start at depth 10. Each increment multiplies solver time; past 30, justify the bound from the design's sequential depth.

## 3. Verdict Triage

| Verdict | Meaning | Agent action |
| :--- | :--- | :--- |
| **PROVEN** | Holds to the bound (bmc) or inductively (prove) | Record depth/engine; property may gate signoff. |
| **FAILED** | Counterexample with assert name, file:line, step | Read the trace: fix RTL or the property, never the bound first. |
| **UNKNOWN** | Solver gave up (deep sequential logic, multi-clock) | Raise depth once; if still unknown, fall back to bounded assurance + simulation. Never report as pass. |
| **ERROR** | Flow broke (bad depth, missing files, no asserts) | Fix inputs, not the design. |
| **TIMEOUT** | Bound too deep or design too large | Halve depth, split properties, or abstract the datapath. |

## 4. Checklist

- [ ] Are SVA blocks behind `` `ifdef FORMAL ``?
- [ ] Is each property bound to an explicit clock/reset with correct polarity?
- [ ] Did `formal_lint_sva` pass before spending solver time?
- [ ] For FAILED: is there a counterexample location (file:line, step)?
- [ ] Is UNKNOWN/TIMEOUT reported as inconclusive, never as proven?
