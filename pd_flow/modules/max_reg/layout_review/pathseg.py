"""Segment arrival times on the config_chain[7]->S[21] ss path at common pins."""
import sys,gzip,re
sys.path.insert(0,'.')
from pathcmp import paths
P="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/"
R=P+"modules/ripple_add/layout_plan/chip_runs/"
runs={"base":(P+"baseline/harden/sta_postpnr/max_ss_125C_3v00/max.rpt","_2306_","_2276_"),
"n03":(R+"n03/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz","_2300_","_2270_"),
"b_m":(P+"modules/max_reg/layout_plan/chip_runs/b_m/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz","_2306_","_2276_"),
"b_ms":(P+"modules/max_reg/layout_plan/chip_runs/b_ms/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz","_2306_","_2276_")}
marks=["/CLK","_2306_/Q|_2300_/Q","_1417_/ZN","_1647_/ZN","_2048_/ZN","_2050_/Z","_2052_/ZN"]
print("%-6s %8s %8s %8s %8s %8s %8s %8s %8s %8s"%("run","launchCK","Q","addEntry","1647","2048","xor3","D","slack","nstg"))
for k,(f,s,e) in runs.items():
    for p in paths(f):
        if p['start']==s and p['end']==e: break
    st=p['stages']; res=[]
    ck=[x for x in st if x['pin'].endswith('/CLK')][0]['t']; res.append(ck)
    for m in marks[1:]:
        hit=[x['t'] for x in st if re.fullmatch(m,x['pin'])]
        res.append(hit[0] if hit else float('nan'))
    print("%-6s "%k+" ".join("%8.3f"%v for v in res)+" %8.3f %8d"%(p['slack'],len(st)))
