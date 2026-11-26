import re,sys,json
lef=open(sys.argv[1]).read()
toks=re.findall(r'"[^"]*"|;|[^\s;]+',lef)
cells={}
i=0
cur=None;pin=None;layer=None;inobs=False
while i<len(toks):
    t=toks[i]
    if t=='MACRO':
        cur=toks[i+1];cells[cur]={'pins':{},'obs':[]};i+=2;continue
    if cur:
        if t=='SIZE' and pin is None and not inobs:
            cells[cur]['w']=float(toks[i+1]);cells[cur]['h']=float(toks[i+3]);i+=4;continue
        if t=='SYMMETRY' and pin is None:
            j=i+1;s=[]
            while toks[j]!=';': s.append(toks[j]);j+=1
            cells[cur]['sym']=s;i=j;continue
        if t=='PIN':
            pin=toks[i+1];cells[cur]['pins'][pin]={'shapes':[]};i+=2;continue
        if t=='OBS': inobs=True;i+=1;continue
        if t=='DIRECTION' and pin: cells[cur]['pins'][pin]['dir']=toks[i+1]
        if t=='USE' and pin: cells[cur]['pins'][pin]['use']=toks[i+1]
        if t=='LAYER': layer=toks[i+1]
        if t=='RECT':
            r=[float(x) for x in toks[i+1:i+5]]
            if pin: cells[cur]['pins'][pin]['shapes'].append((layer,r))
            elif inobs: cells[cur]['obs'].append((layer,r))
            i+=5;continue
        if t=='POLYGON':
            j=i+1;pts=[]
            while toks[j]!=';': pts.append(float(toks[j]));j+=1
            xs=pts[0::2];ys=pts[1::2]
            r=[min(xs),min(ys),max(xs),max(ys)]
            if pin: cells[cur]['pins'][pin]['shapes'].append((layer+'_poly',r))
            elif inobs: cells[cur]['obs'].append((layer+'_poly',r))
            i=j;continue
        if t=='END':
            nm=toks[i+1]
            if pin and nm==pin: pin=None;i+=2;continue
            if inobs and nm not in (cur,): inobs=False;i+=1;continue
            if nm==cur: cur=None;inobs=False;i+=2;continue
    i+=1
json.dump(cells,open(sys.argv[2],'w'))
print(len(cells))
