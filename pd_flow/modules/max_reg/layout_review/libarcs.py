"""Own Liberty extract (ss_125C_3v00): cell area, pin cap, delay arcs and setup/hold constraints for chosen cells."""
import re,sys
PDKV="/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee"
LIB=PDKV+"/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__ss_125C_3v00.lib"
cells=sys.argv[1:]
txt=open(LIB).read()
def block(s,start):
    i=s.index('{',start); d=0
    for j in range(i,len(s)):
        if s[j]=='{': d+=1
        elif s[j]=='}':
            d-=1
            if d==0: return s[i+1:j],j
def vals(tb):
    v=re.search(r'values\s*\((.*?)\)\s*;',tb,re.S).group(1)
    rows=[[float(x) for x in r.split(',')] for r in re.findall(r'"([^"]*)"',v)]
    i1=re.search(r'index_1\s*\(\s*"([^"]*)"',tb); i2=re.search(r'index_2\s*\(\s*"([^"]*)"',tb)
    return rows,(i1 and [float(x) for x in i1.group(1).split(',')]),(i2 and [float(x) for x in i2.group(1).split(',')])
def interp(rows,i1,i2,x1,x2):
    import bisect
    def seg(ix,x):
        k=max(0,min(len(ix)-2,bisect.bisect_right(ix,x)-1)); return k,(x-ix[k])/(ix[k+1]-ix[k])
    if i1 is None: return rows[0][0]
    if i2 is None or len(rows[0])==1:
        k,t=seg(i1,x1); r=[row[0] for row in rows] if len(rows)>1 else rows[0]
        return r[k]+(r[k+1]-r[k])*t
    a,ta=seg(i1,x1); b,tb=seg(i2,x2)
    v00,v01,v10,v11=rows[a][b],rows[a][b+1],rows[a+1][b],rows[a+1][b+1]
    return (v00*(1-ta)*(1-tb)+v01*(1-ta)*tb+v10*ta*(1-tb)+v11*ta*tb)
SL=float(__import__('os').environ.get('SLEW','1.0')); LD=float(__import__('os').environ.get('LOAD','0.01'))
print("# point: input transition %.3f ns, load %.4f pF (delay); constraint: data slew %.3f, clk slew 0.75"%(SL,LD,SL))
for c in cells:
    m=re.search(r'cell\s*\(\s*"?gf180mcu_fd_sc_mcu7t5v0__%s"?\s*\)'%c,txt)
    body,_=block(txt,m.end())
    area=re.search(r'area\s*:\s*([\d.]+)',body).group(1)
    print("== %s area %s"%(c,area))
    for pm in re.finditer(r'\n\s*pin\s*\(\s*"?(\w+)"?\s*\)',body):
        pb,_=block(body,pm.end()); pin=pm.group(1)
        cap=re.search(r'\n\s*capacitance\s*:\s*([\d.]+)',pb)
        dirn=re.search(r'direction\s*:\s*"?(\w+)',pb).group(1)
        print("  pin %-4s %-6s cap %s"%(pin,dirn,cap and cap.group(1)))
        for tm in re.finditer(r'\n\s*timing\s*\(\s*\)',pb):
            tb,_=block(pb,tm.end())
            rp=re.search(r'related_pin\s*:\s*"(\w+)"',tb).group(1)
            tt=re.search(r'timing_type\s*:\s*"?(\w+)',tb); tt=tt.group(1) if tt else 'combinational'
            when=re.search(r'when\s*:\s*"([^"]*)"',tb); when=when.group(1) if when else ''
            out=[]
            for kind in ['cell_rise','cell_fall','rise_constraint','fall_constraint']:
                km=re.search(r'\n\s*%s\s*\(\s*"?\w*"?\s*\)'%kind,tb)
                if not km: continue
                kb,_=block(tb,km.end()); rows,i1,i2=vals(kb)
                if 'constraint' in kind: v=interp(rows,i1,i2,SL,0.75)
                else: v=interp(rows,i1,i2,SL,LD)
                out.append("%s %.3f"%(kind,v))
            print("    %-4s->%-4s %-14s %-22s %s"%(rp,pin,tt,when[:22],"  ".join(out)))
