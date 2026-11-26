import re,sys,collections
def netlens(path):
    t=open(path).read()
    sec=re.search(r'^NETS \d+ ;(.*?)^END NETS',t,re.S|re.M).group(1)
    out={}
    for blk in re.split(r'\n\s*- ',sec):
        m=re.match(r'(\S+)',blk.strip())
        if not m: continue
        name=m[1].replace('\\','')
        pins=re.findall(r'\( (\S+) (\S+) \)',blk.split('+')[0])
        L=0;layers=collections.Counter()
        for seg in re.finditer(r'(?:ROUTED|NEW) (Metal\d)\s+(?:\d+\s+)?(?:\+ \S+ )*\( (\d+) (\d+)(?: \d+)? \) \( (\*|\d+) (\*|\d+)(?: \d+)? \)',blk):
            x1,y1=int(seg[2]),int(seg[3]); x2=x1 if seg[4]=='*' else int(seg[4]); y2=y1 if seg[5]=='*' else int(seg[5])
            d=(abs(x2-x1)+abs(y2-y1))/2000; L+=d; layers[seg[1]]+=d
        out[name]=(L,dict(layers),[p[0].replace('\\','') for p in pins])
    return out
