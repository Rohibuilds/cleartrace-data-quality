"""Create a compact, dependency-free one-page ClearTrace submission PDF."""
from pathlib import Path
import re

OUT = Path(__file__).with_name("ClearTrace_Submission_Brief.pdf")
W, H = 595, 842
ops = []
links = []

def esc(s):
    s = s.encode("ascii", "replace").decode("ascii")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def text(x, y, s, size=9, font="F1", color=(.10,.15,.22)):
    r,g,b=color
    ops.append(f"BT /{font} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x} {y} Tm ({esc(s)}) Tj ET")

def rect(x,y,w,h,fill,stroke=None,radius=0):
    r,g,b=fill
    ops.append(f"q {r:.3f} {g:.3f} {b:.3f} rg")
    if stroke:
        sr,sg,sb=stroke
        ops.append(f"{sr:.3f} {sg:.3f} {sb:.3f} RG 0.8 w")
    if radius:
        k=.5523*radius
        p=[f"{x+radius} {y} m",f"{x+w-radius} {y} l",f"{x+w-radius+k} {y} {x+w} {y+radius-k} {x+w} {y+radius} c",f"{x+w} {y+h-radius} l",f"{x+w} {y+h-radius+k} {x+w-radius+k} {y+h} {x+w-radius} {y+h} c",f"{x+radius} {y+h} l",f"{x+radius-k} {y+h} {x} {y+h-radius+k} {x} {y+h-radius} c",f"{x} {y+radius} l",f"{x} {y+radius-k} {x+radius-k} {y} {x+radius} {y} c"]
        ops.append(" ".join(p)+(" B" if stroke else " f"))
    else:
        ops.append(f"{x} {y} {w} {h} re"+(" B" if stroke else " f"))
    ops.append("Q")

def line(x1,y1,x2,y2,color=(.84,.88,.91),width=0.7):
    r,g,b=color
    ops.append(f"q {r} {g} {b} RG {width} w {x1} {y1} m {x2} {y2} l S Q")

# Header
rect(0,0,W,H,(1,1,1))
rect(0,0,W,7,(.09,.62,.56))
text(48,794,"PROBLEM 01  /  DATAFIX",8,"F2",(.09,.55,.49))
text(48,755,"ClearTrace",31,"F2",(.07,.13,.22))
text(49,731,"Every issue explained. Every fix traceable.",12,"F1",(.34,.41,.50))
rect(48,657,499,55,(.07,.14,.24),radius=8)
text(66,692,"REVIEW-FIRST DATA QUALITY",8,"F2",(.52,.88,.83))
text(66,672,"Inspect defects. Review repairs. Keep every decision traceable.",11,"F2",(1,1,1))
text(48,627,"THE WORKFLOW",8,"F2",(.34,.41,.50))
labels=["Import","Inspect","Explain","Propose","Review","Revalidate","Export + audit"]
x=48
for label in labels:
    width=54 if label!="Export + audit" else 91
    rect(x,597,width,21,(.91,.96,.95),radius=5)
    text(x+7,604,label,7,"F2",(.10,.35,.34))
    x+=width+7
text(48,568,"WHAT MAKES CLEARTRACE USEFUL",8,"F2",(.34,.41,.50))
text(48,545,"Deterministic checks surface missing values, duplicates, whitespace, category",9,"F1")
text(48,530,"inconsistencies, invalid dates, non-numeric values, and statistical outliers.",9,"F1")
text(48,515,"Findings explain the evidence. Reviewers can edit, approve, or reject a repair",9,"F1")
text(48,500,"before it changes the dataset. Revisions, comparisons, undo, and audit records",9,"F1")
text(48,485,"make accepted changes easier to verify. A phone-friendly PWA supports mobile use.",9,"F1")
text(48,453,"SUBMISSION DETAILS",8,"F2",(.34,.41,.50))
rows=[
    ("Team name","ClearTrace"),
    ("Selected problem","Problem 01 - DataFix: Autonomous Data Quality and Repair Engine"),
    ("LinkedIn video","[ADD AFTER RECORDING - MAXIMUM 3 MINUTES]"),
    ("Public GitHub","github.com/Rohibuilds/cleartrace-data-quality"),
    ("Google Drive PDF","[ADD SHARE LINK AFTER UPLOAD]"),
]
y=428
for i,(label,value) in enumerate(rows):
    if i%2==0: rect(48,y-7,499,25,(.96,.975,.98))
    text(58,y,label,8,"F2",(.20,.29,.40))
    text(185,y,value,8,"F1",(.10,.15,.22))
    y-=27
text(58,y,"Deployed app",8,"F2",(.20,.29,.40))
text(185,y,"cleartrace-web-production.up.railway.app",8,"F1",(.09,.48,.44))
links.append((185,y-2,390,y+11,"https://cleartrace-web-production.up.railway.app/"))
y-=45
rect(48,y-65,499,75,(.99,.975,.92),(.88,.79,.54),7)
text(61,y-12,"DEMO SCOPE",8,"F2",(.51,.39,.12))
text(61,y-29,"Judges can explore and repair synthetic data without signing in.",8,"F1",(.29,.27,.21))
text(61,y-43,"The temporary judge workspace blocks uploads; personal accounts use email codes.",8,"F1",(.29,.27,.21))
text(61,y-57,"Email-code delivery needs Gmail SMTP setup. Do not upload confidential datasets.",8,"F1",(.29,.27,.21))
line(48,48,547,48)
text(48,31,"CLEARTRACE  /  DATA QUALITY MADE REVIEWABLE",7,"F2",(.45,.52,.60))
text(445,31,"SUBMISSION BRIEF",7,"F2",(.45,.52,.60))

content="\n".join(ops).encode("ascii")
objs=[]
def obj(s): objs.append(s if isinstance(s, bytes) else s.encode("ascii")); return len(objs)
# Font resources
f1=obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
f2=obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
stream=obj(b"<< /Length "+str(len(content)).encode()+b" >>\nstream\n"+content+b"\nendstream")
annots=[]
for x1,y1,x2,y2,url in links:
    annots.append(obj(f"<< /Type /Annot /Subtype /Link /Rect [{x1} {y1} {x2} {y2}] /Border [0 0 0] /A << /S /URI /URI ({esc(url)}) >> >>"))
page=obj("PLACEHOLDER")
pages=obj("PLACEHOLDER")
catalog=obj("PLACEHOLDER")
objs[page-1]=f"<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {stream} 0 R /Annots [{ ' '.join(f'{a} 0 R' for a in annots) }] >>".encode()
objs[pages-1]=f"<< /Type /Pages /Kids [{page} 0 R] /Count 1 >>".encode()
objs[catalog-1]=f"<< /Type /Catalog /Pages {pages} 0 R >>".encode()
pdf=bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
offsets=[0]
for i,data in enumerate(objs,1):
    offsets.append(len(pdf)); pdf+=f"{i} 0 obj\n".encode()+data+b"\nendobj\n"
xref=len(pdf); pdf+=f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
for off in offsets[1:]: pdf+=f"{off:010d} 00000 n \n".encode()
pdf+=f"trailer\n<< /Size {len(objs)+1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
OUT.write_bytes(pdf)
print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
