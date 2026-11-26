"""Minimal DEF reader (COMPONENTS + NETS) for locating cells by the nets they touch.
Usage as library: comps, nets, dbu = read_def(path)."""
import re, sys

def read_def(path):
    txt = open(path).read()
    dbu = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", txt).group(1))
    comps = {}
    sec = re.search(r"^COMPONENTS \d+ ;(.*?)^END COMPONENTS", txt, re.S | re.M).group(1)
    for st in sec.split(";"):
        m = re.match(r"\s*-\s+(\S+)\s+(\S+)(.*)", st, re.S)
        if not m:
            continue
        name, master, rest = m.groups()
        p = re.search(r"\+\s+(PLACED|FIXED|FIRM)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)", rest)
        comps[name] = dict(master=master, status=p.group(1) if p else None,
                           x=int(p.group(2)) / dbu if p else None,
                           y=int(p.group(3)) / dbu if p else None,
                           orient=p.group(4) if p else None)
    nets = {}
    sec = re.search(r"^NETS \d+ ;(.*?)^END NETS", txt, re.S | re.M).group(1)
    for st in sec.split(";"):
        m = re.match(r"\s*-\s+(\S+)(.*)", st, re.S)
        if not m:
            continue
        name, rest = m.groups()
        head = rest.split("+ ROUTED")[0].split("+ USE")[0]
        nets[name] = re.findall(r"\(\s*(\S+)\s+(\S+)\s*\)", head)
    return comps, nets, dbu

if __name__ == "__main__":
    c, n, d = read_def(sys.argv[1])
    print(len(c), "components", len(n), "nets", "dbu", d)
