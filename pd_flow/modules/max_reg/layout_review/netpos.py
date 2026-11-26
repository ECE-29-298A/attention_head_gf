"""Positions of chosen components and HPWL of chosen nets in final DEFs (own minimal DEF parser)."""
import re,sys,glob
P="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/"
runs={"base":P+"baseline/harden/def/","b_m":P+"modules/max_reg/layout_plan/chip_runs/b_m/harden/def/","b_ms":P+"modules/max_reg/layout_plan/chip_runs/b_ms/harden/def/"}
comps=sys.argv[1].split(','); nets=sys.argv[2].split(',')
for k,d in runs.items():
    f=glob.glob(d+"*.def")[0]; t=open(f).read()
    units=int(re.search(r'UNITS DISTANCE MICRONS (\d+)',t).group(1))
    cs=t[t.index('\nCOMPONENTS'):t.index('END COMPONENTS')]
    pos={}
    for m in re.finditer(r'-\s+(\S+)\s+(\S+).*?\+\s+(PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*(\S+)',cs):
        pos[m.group(1)]=(m.group(2).split('__')[-1],m.group(3),int(m.group(4))/units,int(m.group(5))/units)
    ns=t[t.index('\nNETS'):t.index('END NETS')]
    print("==",k)
    for c in comps: print("  ",c,pos.get(c))
    for n in nets:
        m=re.search(r'-\s+%s\s+(.*?);'%re.escape(n),ns,re.S)
        if not m: print("  net",n,"missing"); continue
        pins=re.findall(r'\(\s*(\S+)\s+(\S+)\s*\)',m.group(1).split('+')[0])
        xs=[pos[c][2] for c,p in pins if c in pos]; ys=[pos[c][3] for c,p in pins if c in pos]
        print("   net %s pins %d HPWL(origins) %.1f um : %s"%(n,len(pins),(max(xs)-min(xs))+(max(ys)-min(ys)),[(c,p) for c,p in pins]))
