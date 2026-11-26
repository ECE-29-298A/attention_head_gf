"""Break each validator check in turn (in memory, source untouched) and confirm the matching self-test turns BAD,
and that the remaining self-tests are unaffected. Runs only selftests() + check_function on a corrupted netlist."""
import sys,os,types,json,re
LP="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/modules/max_reg/layout_plan"
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"rerun","out")
sys.path.insert(0,LP); sys.path.insert(0,LP+"/tools")
SRC=open(LP+"/validate_placement.py").read()
def load(src):
    m=types.ModuleType("vp_mut"); m.__file__=LP+"/validate_placement.py"
    exec(compile(src,LP+"/validate_placement.py","exec"),m.__dict__); return m
MUT={ # case name -> (old, new) disabling exactly the check that case targets
 "overlap": ('if (rr, k) in occ: E("geometry", f"overlap', 'if False: E("geometry", f"overlap'),
 "off-grid": ('E("geometry", f"{r[\'inst\']} off the site/row grid")', 'None'),
 "orientation vs row parity": ('if r[key] not in (native, G.mirror(native)): E(', 'if False: E('),
 "tap overlap (b_m shifted -4 sites)": ('if as_ < t1 and t0 < as_ + ww: E("tap"', 'if False: E("tap"'),
 "outside rows 1..37 (b_m shifted +16 rows)": ('E("outside_core", f"{r[\'inst\']} outside rows', 'E("geometry", f"{r[\'inst\']} outside rows'),
 "compare chain broken": ('elif drv.get(z, {}).get("rel_row") != i - 1:', 'elif False:'),
 "chain input moved off A1": ('if z != f"c[{i}]": E("intent"', 'if False: E("intent"'),
 "oai21 gt moved off A1": ('if ld["pins"]["A1"] != "gt":', 'if False:'),
 "slow chain cell (aoi222_1) substituted": ('if _SLEW.get(c["master"], 99) >= limit:', 'if False:'),
 "b_m instance names swapped": ('if t != "dffq_1" or not m or int(m.group(1)) != c["bit"]:', 'if False:'),
}
G=__import__("gen_placement")
cen=G.census(); ctx=G.chip_context()
man=json.load(open(os.path.join(OUT,"MANIFEST.json")))
nl_names=G.parse_netlist(os.path.normpath(os.path.join(LP,man["inputs"]["names_netlist"][0])))
base=load(SRC); ref={n:ok for n,ok,f in base.selftests(OUT,cen,ctx,nl_names)}
print("unmutated:",ref)
res={}
for case,(old,new) in MUT.items():
    assert SRC.count(old)==1,(case,SRC.count(old))
    m=load(SRC.replace(old,new))
    st={n:(ok,f) for n,ok,f in m.selftests(OUT,cen,ctx,nl_names)}
    others=[n for n in st if n!=case and st[n][0]!=ref[n]]
    res[case]={"target_now":"BAD" if not st[case][0] else "still ok (self-test does NOT depend on this check)","fired":st[case][1],"others_changed":others}
    print("%-45s -> %s  fired=%s others_changed=%s"%(case,res[case]["target_now"],st[case][1],others))
# function check: corrupt the netlist (swap chain pins on one stage) and confirm check_function reports
src=open(os.path.join(OUT,"max_reg_a_sdff.v")).read()
bad=src.replace(".A1(c[9]), .A2(na[9])",".A1(na[9]), .A2(c[9])",1)          # functionally neutral (AND inputs commute)
bad2=src.replace(".A1(gt), .A2(first), .B(en)",".A1(gt), .A2(en), .B(first)",1)  # functional change
for tag,txt in (("swap A1/A2 on aoi21 (equivalent)",bad),("swap first/en on u_ld (functional bug)",bad2)):
    p=os.path.join(os.path.dirname(OUT),"mut_%s.v"%("eq" if "equiv" in tag else "bug"))
    open(p,"w").write(txt); errs=[]; notes=[]
    base.check_function("a_sdff",p,lambda k,mm: errs.append(f"[{k}] {mm}"),notes,nvec=1<<14)
    print("check_function", tag, "->", (errs[:2] or notes))
    res[tag]=errs[:2] or notes
json.dump(res,open(os.path.join(os.path.dirname(OUT),"selftest_mutation.json"),"w"),indent=1)
