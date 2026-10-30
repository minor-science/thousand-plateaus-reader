# python3 audit_fr_epub.py N [N...] : compare a row's French column with Jo's Minuit 2013 epub of Mille plateaux
# (~/Downloads, chap012.html = plateau 12) and print only the words that differ. Reads the epub in place;
# never copy its text into the project.
import re,sys,unicodedata,difflib,zipfile,html,glob,os
EPUB=glob.glob(os.path.expanduser('~/Downloads/Mille plateaux_*.epub'))[0]
def epub_text():
    s=zipfile.ZipFile(EPUB).read('OEBPS/chap012.html').decode('utf-8')
    s=re.sub(r'(?s)<head>.*?</head>','',s); s=re.sub(r'<br\s*/?>|</p>|</div>|</h\d>','\n',s)
    return html.unescape(re.sub(r'<[^>]+>','',s))
def norm_words(s):
    s=s.replace('’',"'").replace('État','Etat').replace('états','etats')
    s=re.sub(r'\[[^\]]*\]',' ',s)          # drop my bracketed insertions/markers
    s=unicodedata.normalize('NFD',s.lower())
    s=''.join(c for c in s if unicodedata.category(c)!='Mn')
    return re.findall(r"[a-z0-9]+",s)
E=norm_words(epub_text())
Ej=' '.join(E)
rows={int(re.match(r'\| 12¶(\d+)',l).group(1)):l for l in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'variorum_nomadology.md')).read().splitlines() if l.startswith('| 12¶')}
for n in map(int,sys.argv[1:]):
    fr=re.split(r'(?<!\\)\|',rows[n][2:-2])[1]
    W=norm_words(fr)
    # anchor: best 8-gram match
    out=[]; i=0
    while i < len(W)-8:
        seg=W[i:i+40]
        key=' '.join(seg[:8]); pos=Ej.find(key)
        if pos<0:
            i+=1; continue
        start=len(Ej[:pos].split())
        ref=E[start:start+len(seg)+10]
        sm=difflib.SequenceMatcher(None,seg,ref,autojunk=False)
        for tag,a1,a2,b1,b2 in sm.get_opcodes():
            if tag!='equal' and a2<=len(seg)-1:
                out.append(f"{tag}: ours «{' '.join(seg[a1:a2])}» / epub «{' '.join(ref[b1:b2])}»")
        i+=30
    print(f"12¶{n}:", 'no differences' if not out else '');
    for o in dict.fromkeys(out): print('   ',o)
