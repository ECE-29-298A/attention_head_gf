"""Worst ss setup slack per endpoint class, endpoints identified by Q net (names are unstable)."""
import re,sys,gzip,glob,json
sys.path.insert(0,'.')
from pathcmp import paths
P="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/"
R=P+"modules/ripple_add/layout_plan/chip_runs/"
runs={"base":P+"baseline/harden","n03":R+"n03/harden","n04":R+"n04/harden"}
for t in ["b_m","b_ms","a_sdff"]: runs[t]=P+f"modules/max_reg/layout_plan/chip_runs/{t}/harden"
out={}
for k,d in runs.items():
    txt=open(glob.glob(d+"/pnl/*.pnl.v")[0]).read()
    q={}
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);',txt,re.S):
        if 'dff' in m.group(1):
            mm=re.search(r'\.Q\(([^)]*)\)',m.group(3)); q[m.group(2)]=mm.group(1).strip().lstrip('\\') if mm else None
    f=glob.glob(d+"/sta_postpnr/max_ss_125C_3v00/max.rpt*")[0]
    cls={}
    n=0
    for p in paths(f):
        n+=1
        e=q.get(p['end'],p['end']); s=q.get(p['start'],p['start'])
        c=re.sub(r'\[\d+\]','',e)
        if c not in cls: cls[c]=(p['slack'],s,e)
    out[k]=cls
    print("==",k,"paths in report:",n)
    for c,v in sorted(cls.items(),key=lambda x:x[1][0])[:5]: print("   %-32s %8.3f  from %s to %s"%(c,v[0],v[1],v[2]))
json.dump(out,open("pathclass.json","w"),indent=1)
