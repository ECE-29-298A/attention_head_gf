import gzip,sys,re
f=sys.argv[1]
o=gzip.open(f,'rt') if f.endswith('.gz') else open(f)
s=e=None
for ln in o:
    if ln.startswith('Startpoint:'): s=ln.split()[1]
    elif ln.startswith('Endpoint:'): e=ln.split()[1]
    elif 'slack' in ln: print(s,e,ln.split()[0])
