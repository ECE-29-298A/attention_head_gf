#!/usr/bin/env python3
"""Module-level exploration netlists (fixed width, top 'ripple_add'), for STA/power only.
The chosen implementation's netlists are emitted by ../gen_placement.py, not by this file."""
import os, shutil
P = "gf180mcu_fd_sc_mcu7t5v0__"
HERE = os.path.dirname(os.path.abspath(__file__))
def chain(n, masters, msb_x3):
    L = [f"module ripple_add (input wire [{n-1}:0] a, input wire [{n-1}:0] b, input wire cin, output wire [{n-1}:0] s);",
         f"  wire [{n}:0] c;", "  assign c[0] = cin;"]
    for i in range(n):
        if msb_x3 and i == n - 1:
            L.append(f"  {P}xor3_1 u_msb (.A1(a[{i}]), .A2(b[{i}]), .A3(c[{i}]), .Z(s[{i}]));")
            L.append(f"  assign c[{n}] = 1'b0;")
        else:
            m = masters(i)
            L.append(f"  {P}{m} u_fa{i} (.A(a[{i}]), .B(b[{i}]), .CI(c[{i}]), .S(s[{i}]), .CO(c[{i+1}]));")
    L.append("endmodule")
    return "\n".join(L) + "\n"
V = {
  "addf1":   (lambda i: "addf_1", False),
  "addf1x3": (lambda i: "addf_1", True),
  "addf2x3": (lambda i: "addf_2", True),
  "alt12x3": (lambda i: "addf_1" if i % 2 == 0 else "addf_2", True),
}
for name, (m, x3) in V.items():
    for n in (22, 12):
        open(f"{HERE}/netlists/{name}_n{n}.v", "w").write(chain(n, m, x3))
for n in (22, 12):
    shutil.copy(f"{HERE}/../../verif/gate/netlists/ripple_add_gf180_n{n}.v", f"{HERE}/netlists/abc_n{n}.v")
print("ok")
