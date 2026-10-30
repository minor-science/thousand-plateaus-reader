# usage: python3 glosscheck.py row_tmp.json -> exit 1 if a bold-italic term (or its singular / a near form) is already glossed
import json,re,sys
d=json.load(open(sys.argv[1]))
g=open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),'glossary_p12.md')).read().lower()
glossed=set(t.strip() for t in re.findall(r"\*([^*\n]+)\*",g))
def stem(w): return re.sub(r"e$","",re.sub(r"[sx]$","",w.strip().lower()))
gstems={stem(t) for t in glossed}
hits=[]
for t in re.findall(r"\*\*\*([^*]+)\*\*\*",d['annot']):
    if t.lower() in glossed or stem(t) in gstems: hits.append(t)
for h in hits: print("ALREADY GLOSSED:",h)
sys.exit(1 if hits else 0)
