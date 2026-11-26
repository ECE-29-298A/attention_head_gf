"""Compare one named ss setup path (start->end) stage by stage between hardens (own parser)."""
import gzip,re,sys,json
P="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/"
def opn(f): return gzip.open(f,'rt') if f.endswith('.gz') else open(f)
def paths(f):
    cur=None
    for ln in opn(f):
        if ln.startswith('Startpoint:'):
            cur={'start':ln.split()[1],'end':None,'stages':[],'slack':None}
        elif ln.startswith('Endpoint:'): cur['end']=ln.split()[1]
        elif cur is not None:
            m=re.match(r'\s+(?:(\d+)\s+([\d.]+)\s+)?([\d.]+)\s+([\d.-]+)\s+([\d.]+)\s+([v^])\s+(\S+)\s+\((\S+)\)',ln)
            if m and not cur.get('done_arr'):
                cur['stages'].append(dict(fo=m.group(1),cap=m.group(2),slew=float(m.group(3)),dly=float(m.group(4)),t=float(m.group(5)),pin=m.group(7),cell=m.group(8).replace('gf180mcu_fd_sc_mcu7t5v0__','')))
            if 'data arrival time' in ln: cur['done_arr']=True; cur['arr']=float(ln.split()[0])
            if 'slack' in ln:
                cur['slack']=float(ln.split()[0]); yield cur; cur=None
def find(f,s,e):
    for p in paths(f):
        if p['start']==s and p['end']==e: return p
def main():
    runs={"base":P+"baseline/harden/sta_postpnr/max_ss_125C_3v00/max.rpt"}
    for t in ["b_m","b_ms","a_sdff"]: runs[t]=P+f"modules/max_reg/layout_plan/chip_runs/{t}/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz"
    s,e=sys.argv[1],sys.argv[2]; which=sys.argv[3].split(',')
    ps={k:find(runs[k],s,e) for k in which}
    for k,p in ps.items():
        print(k, 'slack',p and p['slack'], 'arrival',p and p.get('arr'), 'nstages', p and len(p['stages']))
    a,b=[ps[k] for k in which[:2]]
    sa={x['pin']:x for x in a['stages']}; 
    print("%-22s %-10s %8s %8s %8s %8s"%("pin","cell",which[0]+"_dly",which[1]+"_dly","d","cum"))
    cum=0
    for x in b['stages']:
        y=sa.get(x['pin'])
        d=x['dly']-(y['dly'] if y else 0); cum+=d
        if abs(d)>0.05 or y is None or (y and y['cell']!=x['cell']):
            print("%-22s %-10s %8s %8.3f %+8.3f %+8.3f %s"%(x['pin'],x['cell'],("%.3f"%y['dly']) if y else '-',x['dly'],d,cum,'' if y and y['cell']==x['cell'] else ('cell '+(y['cell'] if y else 'NEW'))))
    print("missing in",which[1],[p for p in sa if p not in {x['pin'] for x in b['stages']}])
    print("total arrival delta", b['arr']-a['arr'], "slack delta", b['slack']-a['slack'])
if __name__=="__main__": main()
