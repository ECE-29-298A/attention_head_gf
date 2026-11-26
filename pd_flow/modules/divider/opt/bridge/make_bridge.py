#!/usr/bin/env python3
"""make_bridge.py: proof bridges for candidates with re-encoded state (c04 family).
B  = golden + observer output ports (bridge/B_gold.v); C' = candidate + observer ports (bridge/C_<name>.v).
Observers are pure extra outputs (original logic untouched; EQY proves golden == B and cand == C' on the
original ports). In the harness eqtop_obs.v all ports, observers included, are compared, so the k-induction
hypothesis contains the invariants and depth 1 suffices:
  obs_lg : golden state is legal (IDLE; DIVIDE with step <= 22 and the 4 zero dividend bits still zero;
           ROUND with step 23). Gate side drives constant 1, so EQY proves it is an invariant.
  obs_lc : candidate state is legal (phase <= 24). Golden side drives constant 1.
  obs_ph : golden (state, step) in the candidate's phase encoding / candidate phase.
  obs_dq : golden quotient mapped to the candidate's 19-bit pre-complemented dq / candidate dq (when busy).
  obs_rm, obs_ng, obs_dv, obs_iv, obs_sn : remainder, negative, divisor, invalid_r, high-quotient flag (busy).
"""
import sys, os
H = os.path.dirname(os.path.abspath(__file__))
def sub(s, a, b):
    assert s.count(a) == 1, (a, s.count(a)); return s.replace(a, b)
PORTS = ("    output wire              obs_lg, obs_lc,\n    output wire        [4:0] obs_ph,\n"
         "    output wire       [18:0] obs_dq,\n    output wire       [11:0] obs_rm, obs_dv,\n"
         "    output wire              obs_ng, obs_iv, obs_sn,\n")
G = open(os.path.join(H, "..", "..", "snapshot", "divider.v")).read()
b = sub(G, "    input  wire              shift,\n", "    input  wire              shift,\n" + PORTS)
b = sub(b, "endmodule", """    // ---- observers (proof bridge only)
    wire [22:0] lowmask = (23'd1 << step) - 23'd1;
    wire [22:0] q_hi = (quotient >> ({1'b0, step} + 6'd4)) << step;
    wire [22:0] q_lo = (quotient & lowmask) ^ ({23{negative}} & lowmask);
    wire [18:0] gold_dq = step <= 5'd19 ? q_hi[18:0] | q_lo[18:0] : quotient[18:0] ^ {19{negative}};
    wire zero_ok = (quotient & (23'hF << step)) == 23'd0;
    assign obs_lg = state == IDLE || (state == DIVIDE && step <= 5'd22 && zero_ok) || (state == ROUND && step == 5'd23);
    assign obs_lc = 1'b1;
    assign obs_ph = state == ROUND ? 5'd24 : state == DIVIDE ? step + 5'd1 : 5'd0;
    assign obs_dq = busy ? gold_dq : 19'd0;
    assign obs_rm = busy ? remainder_value : 12'd0;
    assign obs_dv = busy ? divisor : 12'd0;
    assign obs_ng = busy & negative;
    assign obs_iv = busy & invalid_r;
    wire [22:0] q_bits = quotient & lowmask;
    assign obs_sn = CHECK_INVALID && busy && (|(q_bits >> (step > 5'd11 ? step - 5'd11 : 5'd0)));
endmodule""")
open(os.path.join(H, "B_gold.v"), "w").write(b)
for c in sys.argv[1:]:
    s = open(c).read()
    s = sub(s, "    input  wire              shift,\n", "    input  wire              shift,\n" + PORTS)
    s = sub(s, "endmodule", """    // ---- observers (proof bridge only)
    assign obs_lg = 1'b1;
    assign obs_lc = %s;
    assign obs_ph = %s;
    assign obs_dq = busy ? dq : 19'd0;
    assign obs_rm = busy ? remainder_value : 12'd0;
    assign obs_dv = busy ? divisor : 12'd0;
    assign obs_ng = busy & negative;
    assign obs_iv = busy & invalid_r;
    assign obs_sn = busy & high_quotient;
endmodule""" % (("phase <= 5'd24", "phase") if "reg [4:0] phase;" in s
                      else ("step <= 5'd24", "idle ? 5'd0 : step + 5'd1")))
    open(os.path.join(H, "C_" + os.path.basename(c)), "w").write(s)
