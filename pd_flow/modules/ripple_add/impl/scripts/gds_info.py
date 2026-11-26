# KLayout batch script: top-cell bbox (um) and the top cell's own text labels of a GDS, printed as one JSON line.
# klayout -b -r gds_info.py -rd gds=FILE
import json
import pya
ly = pya.Layout(); ly.read(gds)
top = ly.top_cell()
b = top.dbbox()
labels = set()
for li in ly.layer_indexes():
    for s in top.shapes(li).each():          # top-cell labels only (cells carry their own A/Z/... labels)
        if s.is_text():
            labels.add(s.text_string)
print(json.dumps({"top": top.name, "bbox": [b.left, b.bottom, b.right, b.top], "labels": sorted(labels)}))
