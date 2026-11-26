import json,sys,os
P="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow"
runs={
 "base": P+"/baseline/harden/metrics.json",
 "n03": P+"/modules/ripple_add/layout_plan/chip_runs/n03/harden/metrics.json",
 "n04": P+"/modules/ripple_add/layout_plan/chip_runs/n04/harden/metrics.json",
 "ra_n03_raw": "/Users/samuelzhang/ttharden/ra_n03/runs/wokwi/final/metrics.json",
 "ra_n04_raw": "/Users/samuelzhang/ttharden/ra_n04/runs/wokwi/final/metrics.json",
}
for t in ["b_m","b_ms","a_sdff"]:
    runs[t]=P+f"/modules/max_reg/layout_plan/chip_runs/{t}/harden/metrics.json"
    runs[t+"_raw"]=f"/Users/samuelzhang/ttharden/mr3_{t}/runs/wokwi/final/metrics.json"
keys=["design__instance__area__stdcell","timing__setup__ws","timing__setup_vio__count","timing__hold__ws","timing__hold_vio__count",
"design__max_slew_violation__count","design__max_cap_violation__count","design__max_fanout_violation__count",
"power__total","route__wirelength","route__drc_errors","magic__drc_error__count","design__lvs_error__count","route__antenna_violation__count",
"design__instance__area__class:timing_repair_buffer","timing__setup__ws__corner:max_ss_125C_3v00"]
out={}
for k,f in runs.items():
    if not os.path.exists(f): print("MISSING",k,f); continue
    m=json.load(open(f)); out[k]={x:m.get(x) for x in keys}
hdr="%-38s"%"metric"+"".join("%14s"%k[:13] for k in out)
print(hdr)
for x in keys:
    print("%-38s"%x[-38:]+"".join("%14s"%(("%.6g"%out[k][x]) if isinstance(out[k][x],(int,float)) else str(out[k][x])) for k in out))
# raw == copied?
import hashlib
for t in ["b_m","b_ms","a_sdff"]:
    a=open(runs[t],'rb').read(); b=open(runs[t+"_raw"],'rb').read()
    print(t,"copy==raw:",a==b)
json.dump(out,open("metrics_scrape.json","w"),indent=1)
