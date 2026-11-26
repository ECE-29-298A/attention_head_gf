"""Own check (not tools/check_placed.py): for every run, every DEF from step 17 to final in the run tree,
each cfg instance must be FIXED at the exact cfg x/y/orientation with the master of the source netlist;
taps/endcaps identical to the baseline; no component overlaps a fixed cell; Q net in final pnl."""
import re,glob,os,json,sys
P="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/"
LP=P+"modules/max_reg/layout_plan/"
def read_def(f):
    t=open(f).read(); u=int(re.search(r'UNITS DISTANCE MICRONS (\d+)',t).group(1))
    cs=t[t.index('\nCOMPONENTS'):t.index('END COMPONENTS')]
    comps={}
    for m in re.finditer(r'-\s+(\S+)\s+(\S+)((?:(?!;).)*?)\+\s+(PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*(\S+)',cs,re.S):
        comps[m.group(1).replace('\\','')]=dict(master=m.group(2).split('__')[-1],status=m.group(4),x=int(m.group(5))/u,y=int(m.group(6))/u,o=m.group(7))
    return comps
# LEF widths
PDKV="/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee"
lef=open(PDKV+"/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef").read()
W={m.group(1).split('__')[-1]:float(m.group(2)) for m in re.finditer(r'MACRO (\S+).*?SIZE ([\d.]+) BY',lef,re.S)}
base=read_def(P+"baseline/harden/def/tt_um_attention_head_gf.def")
btaps={k:(v['x'],v['y'],v['o']) for k,v in base.items() if v['master'].startswith(('filltie','endcap'))}
src_master={"a_sdff":{},"b_m":{},"b_ms":{}}
for v in src_master:
    for c in json.load(open(LP+f"out/{v}/placement.json"))["cells"]:
        nm=("core.max_unit."+c["inst"]) if v=="a_sdff" else c["inst"]; src_master[v][nm]=c["master"]
report={}
for v,cfgname in (("b_m","mr_bm.cfg"),("b_ms","mr_bms.cfg"),("a_sdff","mr_asdff.cfg")):
    cfg={l.split()[0]:(float(l.split()[1]),float(l.split()[2]),l.split()[3]) for l in open(LP+f"chip_runs/{v}/{cfgname}") if l.strip()}
    run=f"/Users/samuelzhang/ttharden/mr3_{v}/runs/wokwi/"
    defs=sorted(glob.glob(run+"*/*.def"),key=lambda p:int(os.path.basename(os.path.dirname(p)).split('-')[0]))
    defs=[d for d in defs if int(os.path.basename(os.path.dirname(d)).split('-')[0])>=17]+[run+"final/def/tt_um_attention_head_gf.def"]
    rv={"cfg_lines":len(cfg),"defs":{}}
    for d in defs:
        c=read_def(d); bad=[]
        for n,(x,y,o) in cfg.items():
            k=c.get(n)
            if not k: bad.append((n,"missing")); continue
            if k['status']!='FIXED' or abs(k['x']-x)>1e-6 or abs(k['y']-y)>1e-6 or k['o']!=o or k['master']!=src_master[v][n]:
                bad.append((n,k))
        # taps vs baseline (only after tap insertion step 19)
        taps={kk:(vv['x'],vv['y'],vv['o']) for kk,vv in c.items() if vv['master'].startswith(('filltie','endcap'))}
        tapdiff = None if not taps else (taps!=btaps)
        # overlap of any other component with fixed cells (same row y, x-interval intersection)
        ov=[]
        fx=[(n,cfg[n][0],cfg[n][0]+W[src_master[v][n]],cfg[n][1]) for n in cfg]
        rows={}
        for kk,vv in c.items():
            if vv['master'] not in W: continue
            rows.setdefault(round(vv['y'],2),[]).append((kk,vv['x'],vv['x']+W[vv['master']]))
        for n,x0,x1,y in fx:
            for kk,a,b in rows.get(round(y,2),[]):
                if kk!=n and a<x1-1e-6 and x0<b-1e-6: ov.append((n,kk))
        # orientation legality: N/FN on even rows (y=3.92+2k*3.92), FS/S on odd
        orient_bad=[n for n,(x,y,o) in cfg.items() if (o in ('N','FN'))!=(round((y-3.92)/3.92)%2==0)]
        rv["defs"][os.path.relpath(d,run)]={"bad":bad[:3],"n_bad":len(bad),"taps_differ_from_baseline":tapdiff,"overlaps":ov[:3],"orient_bad":orient_bad}
    # Q nets in final pnl
    pnl=open(glob.glob(run+"final/pnl/*.pnl.v")[0]).read()
    q={}
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);',pnl,re.S):
        n=m.group(2).replace('\\','')
        if n in cfg:
            mm=re.search(r'\.Q\(([^)]*)\)',m.group(3)); q[n]=(m.group(1),mm.group(1).strip().lstrip('\\') if mm else None)
    if v!="a_sdff":
        names=json.load(open(LP+f"out/{v}/names.json"))
        want={}
        for role in ("M","S"):
            if names.get(role): want.update({inst:net for net,inst in names[role].items()})
        rv["q_net_ok"]=sum(1 for n in cfg if q.get(n,(None,None))[1]==want.get(n) and q[n][0]=="dffq_1")
    else:
        rv["q_net_ok"]=sum(1 for n in cfg if q.get(n) and (q[n][1] is None or q[n][1].startswith("core.max_unit") or "M[" in q[n][1]))
    report[v]=rv
    print("==",v,"cfg",len(cfg),"q_net_ok",rv["q_net_ok"])
    for d,r in rv["defs"].items(): print("  %-62s bad %d taps_differ %s overlaps %d orient_bad %d"%(d,r["n_bad"],r["taps_differ_from_baseline"],len(r["overlaps"]),len(r["orient_bad"])), r["bad"][:1], r["overlaps"][:2])
json.dump(report,open("check_fixed.json","w"),indent=1)
