import re,sys
f=sys.argv[1]; want=set(sys.argv[2:])
txt=open(f).read()
for m in re.finditer(r'(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\\?\S+)\s*\((.*?)\);',txt,re.S):
    cell,inst,body=m.groups()
    if inst in want:
        q=re.search(r'\.(Q|Z|ZN)\(([^)]*)\)',body); d=re.search(r'\.D\(([^)]*)\)',body)
        print(inst,cell.split('__')[1],'Q=',q and q.group(2).strip(),'D=',d and d.group(1).strip())
