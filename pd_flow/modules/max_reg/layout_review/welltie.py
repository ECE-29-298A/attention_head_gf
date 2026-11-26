"""Own DF.13/14 geometric estimate on the FINAL chip DEFs (taps/endcaps as placed by the tool):
for each FIXED cell, per well, the farthest x in the cell to the nearest tie (same row: dy=0, or the
neighbour row that shares that well: dy=3.92 um). Tie = filltie or endcap outline."""
import re,glob,math,json
exec(open('check_fixed.py').read().split('# LEF widths')[0])
PDKV="/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee"
lef=open(PDKV+"/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef").read()
W={m.group(1).split('__')[-1]:float(m.group(2)) for m in re.finditer(r'MACRO (\S+).*?SIZE ([\d.]+) BY',lef,re.S)}
out={}
for v in ("b_m","b_ms","a_sdff"):
    c=read_def(f"/Users/samuelzhang/ttharden/mr3_{v}/runs/wokwi/final/def/tt_um_attention_head_gf.def")
    row=lambda y: int(round((y-3.92)/3.92))
    ties={}
    for k,x in c.items():
        if x['master'].startswith(('filltie','endcap')): ties.setdefault(row(x['y']),[]).append((x['x'],x['x']+W[x['master']]))
    worst=(0,None)
    for k,x in c.items():
        if x['status']!='FIXED' or x['master'].startswith(('filltie','endcap')): continue
        r=row(x['y']); a,b=x['x'],x['x']+W[x['master']]
        for well,nb in (("N",r+1 if r%2==0 else r-1),("P",r-1 if r%2==0 else r+1)):
            far=0
            for px in [a+i*0.01*(b-a) for i in range(101)]:
                d=1e9
                for rr,dy in ((r,0.0),(nb,3.92)):
                    for t0,t1 in ties.get(rr,[]):
                        dx=0 if t0<=px<=t1 else min(abs(px-t0),abs(px-t1)); d=min(d,math.hypot(dx,dy))
                far=max(far,d)
            if far>worst[0]: worst=(far,(k,r,well))
    # same-row-only worst (no neighbour credit)
    w2=0
    for k,x in c.items():
        if x['status']!='FIXED' or x['master'].startswith(('filltie','endcap')): continue
        r=row(x['y']); a,b=x['x'],x['x']+W[x['master']]
        for px in (a,b):
            d=min((0 if t0<=px<=t1 else min(abs(px-t0),abs(px-t1))) for t0,t1 in ties.get(r,[]))
            w2=max(w2,d)
    out[v]={"worst_um":round(worst[0],2),"at":worst[1],"same_row_only_worst_um":round(w2,2)}
    print(v,out[v])
json.dump(out,open("welltie.json","w"),indent=1)
