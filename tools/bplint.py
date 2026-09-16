#!/usr/bin/env python3
"""Linter estrutural para os fontes CLEO do Busy Pedestrians.
Nao compila: verifica balanceamento de blocos, labels/gosub, e integridade
dos pares load/release que nos interessam para memoria."""
import sys, re, glob, os

OPEN = ('if','while','for','repeat','const','hex')
def toks(line):
    s = line.split('//')[0].strip()
    return s

def check(path):
    errs=[]
    raw=open(path,encoding='latin-1').read().split('\n')
    depth=0; stack=[]
    labels=set(); gosubs=[]
    for i,l in enumerate(raw,1):
        s=toks(l)
        if not s: continue
        w=s.split()
        head=w[0].lower().rstrip(':')
        if s.startswith(':'):
            labels.add(s[1:].split()[0].lower()); continue
        # blocos
        if head in ('if','while','for','const','hex'):
            # 'if'/'while' de linha unica nao abrem bloco:
            #   "if 056D: actor X defined" -> abre (condicao sozinha)
            #   "if X then Y end"          -> inline, nao abre
            #   "if X" + "then Y" (2 linhas, sem end) -> inline, nao abre
            low=s.lower()
            inline=False
            if head in ('if','while'):
                if re.search(r'\bthen\b.*\bend\b',low) or low.endswith(' end'):
                    inline=True
                elif head=='if' and re.search(r'\bthen\b\s*\S',low):
                    inline=True
            if not inline:
                stack.append((head,i)); depth+=1
        elif head=='repeat':
            stack.append(('repeat',i)); depth+=1
        elif head in ('jf','jump_if_false','else_jump') or re.match(r'004d:',head):
            # estilo antigo: "if <cond>" fechado por "jf @label", sem 'end'
            if stack and stack[-1][0]=='if':
                stack.pop(); depth-=1
        elif head=='then' and re.search(r'^then\s+\S',s,re.I) and stack and stack[-1][0]=='if':
            # "then <cmd>" numa linha propria fecha o if de 2 linhas sem 'end'
            # "then <cmd>" so fecha o if se a proxima linha significativa
            # nao for continuacao do bloco (return/else/end/outro cmd indentado)
            nxt=''
            for k in range(i,len(raw)):
                c=toks(raw[k])
                if c: nxt=c.split()[0].lower().rstrip(':'); break
            if nxt in ('else','end','return'):
                pass  # bloco multi-linha, sera fechado pelo 'end'
            else:
                stack.pop(); depth-=1
        elif head in ('end',):
            if not stack: errs.append(f'{i}: "end" sem bloco aberto')
            else: stack.pop(); depth-=1
        elif head=='until':
            if not stack or stack[-1][0]!='repeat':
                errs.append(f'{i}: "until" sem "repeat"')
            else: stack.pop(); depth-=1
        m=re.match(r'gosub\s+@(\S+)',s,re.I)
        if m: gosubs.append((m.group(1).lower(),i))
    for kind,i in stack:
        errs.append(f'{i}: bloco "{kind}" nao fechado')
    for g,i in gosubs:
        if g not in labels: errs.append(f'{i}: gosub @{g} sem label')
    return errs

def stats(path):
    t=open(path,encoding='latin-1').read()
    return dict(
        load=len(re.findall(r'0F00:',t)),
        unload=len(re.findall(r'0F01:',t)),
        mkrender=len(re.findall(r'0F0[234]:',t)),
        delrender=len(re.findall(r'0E2F:',t)),
        anim_load=len(re.findall(r'04ED:',t)),
        anim_rel=len(re.findall(r'04EF:',t)),
        aud_load=len(re.findall(r'0AC1:',t)),
        aud_rem=len(re.findall(r'0AAE:',t)),
    )

if __name__=='__main__':
    args=sys.argv[1:]
    files=[]
    for a in args:
        files.extend(glob.glob(a))
    bad=0; agg={}
    for f in sorted(files):
        e=check(f)
        s=stats(f)
        for k,v in s.items(): agg[k]=agg.get(k,0)+v
        if e:
            bad+=1
            print(f'== {os.path.basename(f)}')
            for x in e[:10]: print('   ',x)
    print(f'\narquivos com erro estrutural: {bad}/{len(files)}')
    print('totais:', agg)
