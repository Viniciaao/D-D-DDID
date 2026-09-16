#!/usr/bin/env python3
"""
sbcompile.py - faithful reimplementation of the Sanny Builder 3 compiler for
the SCM subset used by the D-D-DDID mod. Validated by byte-exact recompiles.
"""
import struct, re, sys, os

# Sanny Builder data dir (sa/SASCM*.ini, sa/keywords.txt, sa/CustomVariables.ini)
# override with the SCM_SA_DIR environment variable
SA = os.environ.get('SCM_SA_DIR', '/tmp/sbdata/sa')
INI_FILES = ['SASCM.INI', 'SASCM.CLEO.ini', 'SASCM.CLEO+.ini',
             'SASCM.NewOpcodes.ini', 'SASCM.Clipboard.ini']

BY_NUM = {}
VARIANTS = {}
MNEMONIC = {}
ALIAS = {}
# SB3-era fmt spellings differing from the SB4 data files
FMT_OVERRIDES = {
    0x0453: 'set_object %1d% XY_rotation %2d% %3d% angle %4d%',
    0x0829: 'actor %1d% perform_animation %2h% IFP_file %3h% rate %4d% time %5h% and_dies',
    0x016F: 'particle %1d% rot %5d% size %6d% intensity %7d% flags %8d% %9d% %10d% at %2d% %3d% %4d%',
    # 0D59 is commented out in SASCM.CLEO+.ini; NewOpcodes spells it differently
    0x0D59: 'get_current_weather_to %1d%',
}

# Opcodes accepting more than one surface form. The .ini can only hold one
# spelling per opcode, but the SB3 compiler accepts these variants too.
EXTRA_FORMS = {
    # CLEO+ 0F02: the trailing "scale x y z" triple is optional, and when it is
    # omitted the handle goes to the last argument. Param count differs (13/10).
    # older SB spelling accepted alongside read_*_from_ini_file
    0x0AF0: [(4, '%4d% = read_int_from_ini_file %1s% section %2s% key %3s%'),
             (4, '%4d% = get_int_from_ini_file %1s% section %2s% key %3s%')],
    0x0AF2: [(4, '%4d% = read_float_from_ini_file %1s% section %2s% key %3s%'),
             (4, '%4d% = get_float_from_ini_file %1s% section %2s% key %3s%')],
    # 0AC0 is often written without the leading "set_"
    0x0AC0: [(2, 'set_audio_stream %1d% looped %2d%'),
             (2, 'audio_stream %1d% looped %2d%')],
    # "car" is accepted as a synonym of "vehicle"
    # 0AA7 is frequently written as plain "call_function" (the return var is
    # then the last vararg). Keep the canonical spelling first.
    # "read_struct/write_struct" spellings used across this mod
    0x0D4E: [(4, '%4d% = struct %1d% offset %2d% size %3d%'),
             (4, '%4d% = read_struct %1d% offset %2d% size %3d%')],
    0x0D4F: [(4, 'struct %1d% offset %2d% size %3d% = %4d%'),
             (4, 'write_struct %1d% offset %2d% size %3d% value %4d%')],
    0x0AA7: [(-1, 'call_function_return %1d% num_params %2h% pop %3h%'),
             (-1, 'call_function %1d% num_params %2h% pop %3h%')],
    0x0A97: [(2, '%2d% = vehicle %1d% struct'),
             (2, '%2d% = car %1d% struct')],
    0x0F02: [
        (13, 'create_render_object_to_char_bone_from_special %1d% special_model %2d% bone %3d% offset %4d% %5d% %6d% rotation %7d% %8d% %9d% scale %10d% %11d% %12d% store_to %13d%'),
        (10, 'create_render_object_to_char_bone_from_special %1d% special_model %2d% bone %3d% offset %4d% %5d% %6d% rotation %7d% %8d% %9d% store_to %10d%'),
    ],
}

def norm_fmt(fmt):
    s = re.sub(r'%\d+[a-zA-Z][a-zA-Z/]*%', '\x00', fmt.lower())
    s = re.sub(r'[ \t]*\x00[ \t]*', '\x00', s)
    return s.strip()

def skeleton_keys(skel):
    """all prefix keys ending at placeholder boundaries (or full)"""
    keys = {skel}
    idx = 0
    while True:
        p = skel.find('\x00', idx)
        if p < 0:
            break
        keys.add(skel[:p+1])
        idx = p + 1
    return keys

def load_opcodes():
    for fn in INI_FILES:
        p = os.path.join(SA, fn)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='cp1252', errors='replace'):
            line = line.strip()
            if not line or line.startswith(';') or line.startswith('[') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            k = k.strip()
            if not re.fullmatch(r'[0-9A-Fa-f]{4}', k):
                continue
            op = int(k, 16)
            cnt, _, fmt = v.partition(',')
            try:
                cnt = int(cnt.strip())
            except ValueError:
                continue
            fmt = fmt.split(';')[0].strip()
            if op in FMT_OVERRIDES:
                fmt = FMT_OVERRIDES[op]
            BY_NUM.setdefault(op, (cnt, fmt))
            skel = norm_fmt(fmt)
            for k in skeleton_keys(skel):
                MNEMONIC.setdefault(k, []).append(op)
    for op, forms in EXTRA_FORMS.items():
        VARIANTS[op] = forms
        for cnt, fmt in forms:
            for k in skeleton_keys(norm_fmt(fmt)):
                if op not in MNEMONIC.get(k, []):
                    MNEMONIC.setdefault(k, []).append(op)
    for line in open(os.path.join(SA, 'keywords.txt'), encoding='cp1251'):
        line = line.strip()
        if not line or line.startswith(';') or '=' not in line:
            continue
        a, b = line.split('=', 1)
        try:
            op = int(a.strip(), 16)
        except ValueError:
            continue
        if op in BY_NUM:
            ALIAS.setdefault(b.strip().lower(), []).append(op)
load_opcodes()

GLOBALS = {}
def load_globals():
    for line in open(os.path.join(SA, 'CustomVariables.ini'), encoding='cp1252', errors='replace'):
        line = line.split(';')[0].strip()
        if '=' not in line:
            continue
        k, _, v = line.partition('=')
        k = k.strip(); v = v.strip()
        if k.isdigit() and v:
            GLOBALS[v.upper()] = int(k)
load_globals()

class Tok:
    __slots__ = ('kind', 'val', 'line')
    def __init__(self, kind, val, line):
        self.kind, self.val, self.line = kind, val, line
    def __repr__(self):
        return '<%s:%r>' % (self.kind, self.val)

TOKEN_RE = re.compile(r"""
    (?P<directive>\{\$[^}]*\})
  | (?P<ws>[ \t\x0c]+)
  | (?P<comment>//.*)
  | (?P<dq>"(?:[^"\\]|\\.)*")
  | (?P<sq>'(?:[^'\\]|\\.)*')
  | (?P<opcode>[0-9A-Fa-f]{4}(?=:))
  | (?P<var>\d+@[vs]?)
  | (?P<fpnum>-?\d+\.\d*(?:[eE][+-]?\d+)?)
  | (?P<hex>-?0[xX][0-9A-Fa-f]+)
  | (?P<int>-?\d+)
  | (?P<labelref>@[A-Za-z_][A-Za-z0-9_]*)
  | (?P<labeldef>:[A-Za-z_][A-Za-z0-9_]*)
  | (?P<gvar>\$[A-Za-z_0-9][A-Za-z0-9_]*)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_.]*)
  | (?P<op>==|!=|>=|<=|>|<|\+=|-=|\*=|/=|\+|-|\*|/|=|\(|\)|,|:)
""", re.X)

def tokenize(text):
    lines = []
    for ln, raw in enumerate(text.split('\n'), 1):
        raw = raw.rstrip('\r')
        toks = []
        i = 0
        while i < len(raw):
            m = TOKEN_RE.match(raw, i)
            if not m:
                raise SyntaxError('line %d: bad char %r in %r' % (ln, raw[i], raw))
            i = m.end()
            if m.lastgroup in ('ws', 'comment', 'directive'):
                continue
            toks.append(Tok(m.lastgroup, m.group(), ln))
        if toks:
            lines.append(toks)
    return lines

KW_STRUCT = {'if', 'then', 'else', 'end', 'while', 'repeat', 'until', 'for',
             'const', 'jump', 'gosub', 'return', 'break', 'continue'}

class Compiler:
    def __init__(self, src):
        self.src = src
        self.lines = tokenize(src.decode('cp1252'))
        self.consts = {}
        self.code = bytearray()
        self.labels = {}
        self.fixups = []
        self.loops = []
        self.uid = 0

    # --- emit helpers
    def here(self): return len(self.code)
    def emit(self, b): self.code.extend(b)
    def emit_op(self, op, notflag=False):
        self.emit(struct.pack('<H', op | (0x8000 if notflag else 0)))
    def emit_int(self, v):
        if -128 <= v <= 127: self.emit(b'\x04'); self.emit(struct.pack('<b', v))
        elif -32768 <= v <= 32767: self.emit(b'\x05'); self.emit(struct.pack('<h', v))
        else: self.emit(b'\x01'); self.emit(struct.pack('<i', v))
    def emit_float(self, v):
        self.emit(b'\x06'); self.emit(struct.pack('<f', v))
    def emit_string(self, s):
        b = s.encode('cp1252')
        assert len(b) <= 255, s
        self.emit(b'\x0e'); self.emit(struct.pack('<B', len(b))); self.emit(b)
    def emit_gxt(self, s):
        b = s.encode('cp1252')[:8]
        self.emit(b'\x09'); self.emit(b + b'\x00' * (8 - len(b)))
    def emit_label(self, name):
        self.emit(b'\x01')
        self.fixups.append((len(self.code), name.lower()))
        self.emit(struct.pack('<i', 0))
    def emit_var(self, vd):
        kind, idx, s = vd
        t = {( 'local', False): 0x03, ('local', True): 0x11,
             ('global', False): 0x02, ('global', True): 0x10}[(kind, s)]
        self.emit(struct.pack('<BH', t, idx))
    def emit_arr(self, base, idxvar, size):
        self.emit(struct.pack('<BHHH', 0x08, base, idxvar, size))
    def newlab(self, prefix):
        self.uid += 1
        return '%s$%d' % (prefix, self.uid)

    # --- values
    def global_index(self, name):
        u = name.upper()
        if u in GLOBALS: return GLOBALS[u] * 4
        if u.isdigit(): return int(u) * 4
        raise SyntaxError('unknown global $' + name)

    def resolve_var(self, tok):
        """lvalue/rvalue variable -> (kind, index, isstr)"""
        if tok.kind == 'var':
            num, _, sfx = tok.val.partition('@')
            return ('local', int(num), sfx in ('v', 's'))
        if tok.kind == 'gvar':
            return ('global', self.global_index(tok.val[1:]), False)
        if tok.kind == 'ident':
            n = tok.val.lower()
            if n == 'timerb': return ('local', 33, False)
            if n == 'timera': return ('local', 32, False)
            c = self.consts.get(n)
            if c and c[0] == 'var': return ('local', c[1], False)
            raise SyntaxError('not a variable: ' + tok.val)
        raise SyntaxError('not a variable: ' + repr(tok))

    def resolve_value(self, toks):
        """token list -> value spec for parameters/operands"""
        if len(toks) == 1:
            t = toks[0]
            if t.kind == 'int': return ('num', int(t.val))
            if t.kind == 'hex': return ('num', int(t.val, 16))
            if t.kind == 'fpnum': return ('float', float(t.val))
            if t.kind == 'ident':
                n = t.val.lower()
                if n == 'true': return ('num', 1)
                if n == 'false': return ('num', 0)
                if n == 'timera': return ('var', ('local', 32, False))
                if n == 'timerb': return ('var', ('local', 33, False))
                c = self.consts.get(n)
                if c:
                    if c[0] == 'var': return ('var', ('local', c[1], False))
                    if c[0] == 'num': return ('num', c[1])
                    if c[0] == 'float': return ('float', c[1])
                raise SyntaxError('unknown ident ' + t.val)
            if t.kind in ('var', 'gvar'):
                return ('var', self.resolve_var(t))
            if t.kind == 'dq': return ('str', self.unquote(t.val))
            if t.kind == 'sq': return ('gxt', self.unquote(t.val))
            if t.kind == 'labelref': return ('label', t.val[1:])
        # array access Name(idx, Ni)  - tokenizer splits '1i' into int + ident
        if (len(toks) >= 6 and toks[0].kind in ('ident', 'var', 'gvar')
                and toks[1].val == '(' and toks[-1].val == ')'):
            # base may be a const name or a variable written directly (0@(...))
            if toks[0].kind == 'ident':
                c = self.consts.get(toks[0].val.lower())
                assert c and c[0] == 'var', toks[0].val
                base = c[1]
            else:
                base = self.resolve_var(toks[0])[1]
            iv = self.resolve_var(toks[2])
            if toks[4].kind == 'int' and len(toks) >= 7 and toks[5].val == 'i':
                size = int(toks[4].val)
            else:
                size = int(toks[4].val[:-1])
            return ('arr', (base, iv[1], size))
        raise SyntaxError('bad value: ' + repr([t.val for t in toks]))

    def unquote(self, s):
        return s[1:-1]

    def emit_value(self, v, fmtletter):
        """emit a value according to fmt letter"""
        k = v[0]
        if k == 'str':
            self.emit_string(v[1]); return
        if k == 'gxt':
            self.emit_gxt(v[1]); return
        if fmtletter == 'p':
            assert k == 'label'
            self.emit_label(v[1]); return
        if k == 'label':
            self.emit_label(v[1]); return
        if fmtletter in ('s', 'k'):
            if k == 'str': self.emit_string(v[1]); return
            if k == 'num':
                self.emit_int(v[1]); return
            if k == 'float':
                self.emit_float(v[1]); return
            if k == 'var':
                self.emit_var(v[1]); return
            raise SyntaxError('bad %s param' % fmtletter)
        if fmtletter == 'g':
            if k == 'gxt': self.emit_gxt(v[1]); return
            if k == 'str': self.emit_string(v[1]); return
            raise SyntaxError('bad gxt param')
        if k == 'num':
            self.emit_int(v[1]); return
        if k == 'float':
            self.emit_float(v[1]); return
        if k == 'var':
            self.emit_var(v[1]); return
        if k == 'arr':
            self.emit_arr(*v[1]); return
        raise SyntaxError('bad value ' + repr(v))

    # --- main entry
    def compile(self):
        self.parse_body(0, ())
        for off, name in self.fixups:
            if name is None:
                continue
            struct.pack_into('<i', self.code, off, -self.labels[name])
        return bytes(self.code)

    def parse_body(self, idx, stop):
        while idx < len(self.lines):
            toks = self.lines[idx]
            f = toks[0]
            if f.kind == 'ident' and f.val.lower() in stop:
                return idx
            idx = self.parse_one(idx)
        return idx

    def parse_one(self, idx):
        toks = self.lines[idx]
        f = toks[0]
        if f.kind == 'labeldef':
            self.labels[f.val[1:].lower()] = self.here()
            if len(toks) > 1:
                return self.parse_statement_line(idx, toks[1:])
            return idx + 1
        if f.kind == 'ident' and f.val.startswith('{$'):
            return idx + 1
        return self.parse_statement_line(idx, toks)

    def parse_statement_line(self, idx, toks):
        f = toks[0]
        low = f.val.lower() if f.kind == 'ident' else None
        if low == 'const':
            return self.parse_const(idx)
        if low == 'script_name':
            self.emit_op(0x03A4)
            self.emit_string(self.unquote(toks[1].val))
            return idx + 1
        if low == 'if':
            return self.parse_if(idx)
        if low == 'while':
            return self.parse_while(idx)
        if low == 'repeat':
            return self.parse_repeat(idx)
        if low == 'for':
            return self.parse_for(idx)
        if low == 'jump':
            self.emit_op(0x0002); self.emit_label(toks[1].val[1:])
            return idx + 1
        if low == 'gosub':
            self.emit_op(0x0050); self.emit_label(toks[1].val[1:])
            return idx + 1
        if low == 'return':
            self.emit_op(0x0051); return idx + 1
        if low == 'break':
            self.emit_op(0x0002); self.emit_label(self.loops[-1][1])
            return idx + 1
        if low == 'continue':
            self.emit_op(0x0002); self.emit_label(self.loops[-1][0])
            return idx + 1
        self.compile_statement(toks)
        return idx + 1

    def parse_const(self, idx):
        idx += 1
        while True:
            toks = self.lines[idx]
            if toks[0].val.lower() == 'end':
                return idx + 1
            name = toks[0].val.lower()
            vt = toks[2]
            if vt.kind == 'var':
                self.consts[name] = ('var', int(vt.val[:-1]))
            elif vt.kind == 'int':
                self.consts[name] = ('num', int(vt.val))
            elif vt.kind == 'fpnum':
                self.consts[name] = ('float', float(vt.val))
            elif vt.kind == 'hex':
                self.consts[name] = ('num', int(vt.val, 16))
            elif vt.kind == 'var' or (vt.kind == 'ident' and vt.val.lower() in self.consts):
                self.consts[name] = self.consts[vt.val.lower()]
            elif vt.kind == 'gvar':
                self.consts[name] = ('gvar', vt.val)
            else:
                raise SyntaxError('const ' + vt.val)
            idx += 1

    # --- control structures
    def parse_if(self, idx):
        toks = self.lines[idx]
        i = 1
        mode = None
        if i < len(toks) and toks[i].val.lower() in ('and', 'or'):
            mode = toks[i].val.lower(); i += 1
        conds = []
        if i < len(toks):
            conds.append(toks[i:])
        idx += 1
        then_inline = None
        while True:
            t2 = self.lines[idx]
            if t2[0].val.lower() == 'then':
                then_inline = t2[1:]
                idx += 1
                break
            conds.append(t2)
            idx += 1
        n = len(conds)
        raw = 0 if n == 1 else ((n - 1) + 0x14 if mode == 'or' else n - 1)
        self.emit_op(0x00D6); self.emit(b'\x04'); self.emit(struct.pack('<B', raw))
        for c in conds:
            self.compile_condition(c)
        else_lab = self.newlab('ifelse')
        end_lab = self.newlab('ifend')
        self.emit_op(0x004D); self.emit_label(else_lab)
        if then_inline:
            self.compile_statement(then_inline)
        idx = self.parse_body(idx, ('else', 'end'))
        t2 = self.lines[idx]
        if t2[0].val.lower() == 'else':
            self.emit_op(0x0002); self.emit_label(end_lab)
            self.labels[else_lab] = self.here()
            if len(t2) > 1:
                self.compile_statement(t2[1:])
            idx = self.parse_body(idx + 1, ('end',))
            self.labels[end_lab] = self.here()
            return idx + 1
        self.labels[else_lab] = self.here()
        self.labels[end_lab] = self.here()
        return idx + 1

    def parse_while(self, idx):
        """while true ... end  and  while <condition> ... end

        For a real condition SB emits the condition test at the top of the loop
        followed by a jump-if-false past the tail jump. Multi-line conditions
        (while and / while or) use the same 00D6 encoding as parse_if."""
        toks = self.lines[idx]
        is_true = (len(toks) > 1 and toks[1].kind == 'ident'
                   and toks[1].val.lower() == 'true')
        top = self.here()
        toplab = self.newlab('wtop')
        cont = self.newlab('wcont')
        brk = self.newlab('wend')
        self.labels[toplab] = top
        self.loops.append((cont, brk))
        if not is_true:
            i = 1
            mode = None
            if i < len(toks) and toks[i].val.lower() in ('and', 'or'):
                mode = toks[i].val.lower(); i += 1
            conds = []
            if i < len(toks):
                conds.append(toks[i:])
            # extra condition lines until the body starts
            while not conds:
                idx += 1
                conds.append(self.lines[idx])
            n = len(conds)
            raw = 0 if n == 1 else ((n - 1) + 0x14 if mode == 'or' else n - 1)
            self.emit_op(0x00D6); self.emit(b'\x04'); self.emit(struct.pack('<B', raw))
            for c in conds:
                self.compile_condition(c)
            self.emit_op(0x004D); self.emit_label(brk)
        idx = self.parse_body(idx + 1, ('end',))
        # SB: 'continue' lands on the backward jump at the loop tail
        self.labels[cont] = self.here()
        self.emit_op(0x0002); self.emit_label(toplab)
        self.labels[brk] = self.here()
        self.loops.pop()
        return idx + 1

    def parse_repeat(self, idx):
        top = self.here()
        cont = self.newlab('rcond')
        brk = self.newlab('rend')
        self.loops.append((cont, brk))
        idx = self.parse_body(idx + 1, ('until',))
        self.labels[cont] = self.here()
        condtoks = self.lines[idx][1:]
        self.compile_condition(condtoks)
        self.emit_op(0x004D)
        self.emit(b'\x01'); self.emit(struct.pack('<i', -top))
        self.labels[brk] = self.here()
        self.loops.pop()
        return idx + 1

    def parse_for(self, idx):
        toks = self.lines[idx]
        var = self.resolve_var(toks[1])
        a = self.const_int(toks[3])
        b = self.const_int(toks[5])
        step = 1
        if len(toks) > 6 and toks[6].val.lower() == 'step':
            step = self.const_int(toks[7])
        self.emit_op(0x0006); self.emit_var(var); self.emit_int(a)
        top = self.here()
        cont = self.newlab('fstep')
        brk = self.newlab('fend')
        self.loops.append((cont, brk))
        idx = self.parse_body(idx + 1, ('end',))
        self.labels[cont] = self.here()
        self.emit_op(0x000A); self.emit_var(var); self.emit_int(step)
        self.emit_op(0x0019); self.emit_var(var); self.emit_int(b)
        self.emit_op(0x004D)
        self.emit(b'\x01'); self.fixups.append((len(self.code), None)); self.emit(struct.pack('<i', -top))
        self.labels[brk] = self.here()
        self.loops.pop()
        return idx + 1

    def const_int(self, tok):
        if tok.kind == 'int': return int(tok.val)
        if tok.kind == 'hex': return int(tok.val, 16)
        if tok.kind == 'ident':
            c = self.consts.get(tok.val.lower())
            if c and c[0] == 'num': return c[1]
        raise SyntaxError('expected int ' + tok.val)

    # --- conditions
    def compile_condition(self, toks):
        notflag = False
        if toks[0].kind == 'ident' and toks[0].val.lower() == 'not':
            notflag = True; toks = toks[1:]
        pre = self.opcode_prefix(toks)
        if pre:
            op, rest, nf = pre
            self.compile_opcode_stmt(op, rest, nf or notflag)
            return
        if toks[0].kind == 'ident' and '.' in toks[0].val:
            if self.try_class_syntax(toks, notflag):
                return
        if self.candidate_ops(toks):
            self.compile_mnemonic(toks, notflag)
            return
        self.compile_plain_condition(toks, notflag)

    def opcode_prefix(self, toks):
        if toks and toks[0].kind == 'opcode' and len(toks) > 1 and toks[1].val == ':':
            op = int(toks[0].val, 16)
            nf = bool(op & 0x8000)
            return (op & 0x7FFF), toks[2:], nf
        return None

    def compile_plain_condition(self, toks, notflag):
        ops = {'==', '!=', '>=', '<=', '>', '<'}
        opi = next((i for i, t in enumerate(toks) if t.kind == 'op' and t.val in ops), None)
        if opi is None:
            raise SyntaxError('condition ' + repr([t.val for t in toks]))
        lv = self.resolve_value(toks[:opi])
        rv = self.resolve_value(toks[opi+1:])
        opnd = toks[opi].val
        if opnd == '<':
            opnd, notflag = '>=', not notflag
        elif opnd == '<=':
            opnd, notflag = '>', not notflag
        self.emit_op(self.pick_cmp(opnd, lv, rv), notflag)
        self.emit_value(lv, 'd')
        self.emit_value(rv, 'd')

    def pick_cmp(self, opnd, lv, rv):
        fl = lv[0] == 'float' or rv[0] == 'float'
        lv_ = lv[1] if lv[0] == 'var' else None
        rv_ = rv[1] if rv[0] == 'var' else None
        lg = lv_ and lv_[0] == 'global'
        rg = rv_ and rv_[0] == 'global'
        lc = lv[0] in ('num',)
        rc = rv[0] in ('num', 'float')
        key = (opnd, fl, bool(lv_), bool(rv_), bool(lg), bool(rg), lc, rc)
        # table derived from shipped binaries
        if not fl:
            if opnd == '==':
                if lv_ and not rv_ and lg: return 0x0038
                if lv_ and not rv_ and not lg: return 0x0039
                if lv_ and rv_: return 0x003A
            if opnd == '>=':
                if lv_ and not rv_ and lg: return 0x0028
                if lv_ and not rv_: return 0x0029
            if opnd == '>':
                if lv_ and not rv_ and lg: return 0x0018
                if lv_ and not rv_: return 0x0019
                if lv_ and rv_: return 0x001D
            if opnd == '<=':
                if lv_ and not rv_: return 0x002B
                if lv_ and rv_: return 0x002F
            if opnd == '<':
                if lv_ and not rv_: return 0x001B
                if lv_ and rv_: return 0x001F
        else:
            if opnd == '==':
                if lv_ and not rv_ and lg: return 0x0043
                if lv_ and not rv_: return 0x0044
                if lv_ and rv_: return 0x0045
            if opnd == '>':
                if lv_ and not rv_: return 0x0021
                if lv_ and rv_: return 0x0025
            if opnd == '>=':
                if lv_ and not rv_: return 0x0031
                if lv_ and rv_: return 0x0035
            if opnd == '<=':
                if lv_ and not rv_: return 0x0033
                if lv_ and rv_: return 0x0037
            if opnd == '<':
                if lv_ and not rv_: return 0x0023
                if lv_ and rv_: return 0x0027
        raise SyntaxError('no cmp for ' + repr(key))

    # --- statements
    def compile_statement(self, toks):
        pre = self.opcode_prefix(toks)
        if pre:
            op, rest, nf = pre
            self.compile_opcode_stmt(op, rest, nf)
            return
        # wait
        if toks[0].kind == 'ident' and toks[0].val.lower() == 'wait':
            v = self.resolve_value(toks[1:2])
            self.emit_op(0x0001)
            self.emit_value(v, 'd')
            return
        # class syntax
        if toks[0].kind == 'ident' and '.' in toks[0].val:
            if self.try_class_syntax(toks):
                return
        # plain assignment / compare-as-statement
        for i, t in enumerate(toks):
            if t.kind == 'op' and t.val in ('=', '+=', '-=', '*=', '/='):
                try:
                    self.compile_assign(toks[:i], t.val, toks[i+1:])
                    return
                except (SyntaxError, AssertionError):
                    break
        low = toks[0].val.lower() if toks[0].kind == 'ident' else None
        if low == 'break':
            self.emit_op(0x0002); self.emit_label(self.loops[-1][1]); return
        if low == 'continue':
            self.emit_op(0x0002); self.emit_label(self.loops[-1][0]); return
        if low == 'jump':
            self.emit_op(0x0002); self.emit_label(toks[1].val[1:]); return
        if low == 'gosub':
            self.emit_op(0x0050); self.emit_label(toks[1].val[1:]); return
        if low == 'return':
            self.emit_op(0x0051); return
        # bare mnemonic
        self.compile_mnemonic(toks, False)

    def try_class_syntax(self, toks, notflag=False):
        head = toks[0].val.lower()
        if head == 'model.load' and len(toks) >= 4:
            v = self.resolve_value(toks[2:3])
            self.emit_op(0x0247, notflag); self.emit_value(v, 'o'); return True
        if head == 'model.available' and len(toks) >= 4:
            v = self.resolve_value(toks[2:3])
            self.emit_op(0x0248, notflag); self.emit_value(v, 'o'); return True
        if head == 'model.destroy' and len(toks) >= 4:
            v = self.resolve_value(toks[2:3])
            self.emit_op(0x0249, notflag); self.emit_value(v, 'o'); return True
        if head == 'player.defined' and len(toks) >= 4:
            v = self.resolve_value(toks[2:3])
            self.emit_op(0x0256, notflag); self.emit_value(v, 'd'); return True
        # --- one-argument condition members: Class.Member(x)
        SIMPLE = {
            'actor.dead':     (0x0118, 'd'),
            'actor.driving':  (0x00DF, 'd'),
            'object.destroy': (0x0108, 'd'),
            'actor.destroy':  (0x009B, 'd'),
        }
        if head in SIMPLE and len(toks) >= 4:
            op, lt = SIMPLE[head]
            v = self.resolve_value(toks[2:3])
            self.emit_op(op, notflag); self.emit_value(v, lt); return True
        # Actor.Animation(a) == "name"  ->  0611 actor a performing_animation "name"
        if head == 'actor.animation' and len(toks) >= 4 and toks[1].val == '(':
            close = next(i for i, t in enumerate(toks) if t.val == ')')
            rest = toks[close+1:]
            if rest and rest[0].kind == 'op' and rest[0].val in ('==', '!='):
                nf = notflag ^ (rest[0].val == '!=')
                a = self.resolve_value(toks[2:close])
                self.emit_op(0x0611, nf)
                self.emit_value(a, 'd'); self.emit_value(self.resolve_value(rest[1:]), 'h')
                return True
        # Actor.Angle(a) = v  ->  0173 set_actor a Z_angle_to v
        if head == 'actor.angle' and toks[1].val == '(':
            close = next(i for i, t in enumerate(toks) if t.val == ')')
            rest = toks[close+1:]
            if rest and rest[0].kind == 'op' and rest[0].val == '=':
                a = self.resolve_value(toks[2:close])
                self.emit_op(0x0173, notflag)
                self.emit_value(a, 'd'); self.emit_value(self.resolve_value(rest[1:]), 'd')
                return True
        # v = Actor.CurrentCar(a)  is handled by the assignment path below
        # Actor.Create(var, pedtype, model, x, y, z) -> 009A
        if head == 'actor.create' and toks[1].val == '(':
            close = next(i for i, t in enumerate(toks) if t.val == ')')
            args = self.split_args(toks[2:close])
            if len(args) == 6:
                self.emit_op(0x009A, notflag)
                self.emit_value(self.resolve_value(args[1]), 'd')
                self.emit_value(self.resolve_value(args[2]), 'm')
                for k in (3, 4, 5):
                    self.emit_value(self.resolve_value(args[k]), 'd')
                self.emit_target(('var', self.resolve_var(args[0][0])))
                return True
        return False

    def split_args(self, toks):
        """split a token list on commas; SB also tolerates space-separated args"""
        out, cur = [], []
        for t in toks:
            if t.kind == 'op' and t.val == ',':
                if cur:
                    out.append(cur); cur = []
            else:
                cur.append(t)
        if cur:
            out.append(cur)
        # space-separated tail (e.g. "2@ 3@ 4@" as three args)
        if len(out) < 6:
            flat = []
            for grp in out:
                if len(grp) > 1 and all(x.kind in ('var', 'int', 'fpnum') for x in grp):
                    flat.extend([[x] for x in grp])
                else:
                    flat.append(grp)
            out = flat
        return out

    def compile_assign(self, lhs, opnd, rhs):
        if len(lhs) == 1:
            vd = self.resolve_var(lhs[0])
            target = ('var', vd)
        else:
            target = ('arrv', self.resolve_value(lhs))
        rv = self.resolve_value(rhs)
        if opnd == '=':
            if rv[0] == 'var':
                self.emit_op(0x0085)
                self.emit_target(target)
                self.emit_var(rv[1])
            elif rv[0] == 'float':
                self.emit_op(0x0007 if target[1][0] == 'local' else 0x0005)
                self.emit_target(target)
                self.emit_float(rv[1])
            else:
                self.emit_op(0x0006 if target[0] == 'var' and target[1][0] == 'local'
                             else (0x0004 if target[0] == 'var' else 0x0006))
                self.emit_target(target)
                if rv[0] == 'num':
                    self.emit_int(rv[1])
                else:
                    raise SyntaxError('assign rhs ' + repr(rv))
        else:
            fl = rv[0] == 'float'
            if opnd == '+=':
                if target[0] == 'var' and target[1][0] == 'global':
                    op = 0x0009 if fl else 0x0008
                else:
                    op = 0x000B if fl else 0x000A
            elif opnd == '-=':
                if target[0] == 'var' and target[1][0] == 'global':
                    op = 0x000D if fl else 0x000C
                else:
                    op = 0x000F if fl else 0x000E
            elif opnd == '*=':
                if target[0] == 'var' and target[1][0] == 'global':
                    op = 0x0011 if fl else 0x0010
                else:
                    op = 0x0013 if fl else 0x0012
            else:
                if target[0] == 'var' and target[1][0] == 'global':
                    op = 0x0015 if fl else 0x0014
                else:
                    op = 0x0017 if fl else 0x0016
            self.emit_op(op)
            self.emit_target(target)
            if rv[0] == 'float': self.emit_float(rv[1])
            elif rv[0] == 'num': self.emit_int(rv[1])
            else: self.emit_var(rv[1])

    def emit_target(self, target):
        if target[0] == 'var':
            self.emit_var(target[1])
        else:
            _, arr = target
            self.emit_arr(*arr[1])

    # --- mnemonic (no opcode number) statements/conditions
    def candidate_ops(self, toks):
        """ordered candidate opcodes for a mnemonic statement"""
        cands = []
        skel = self.src_skel(toks)
        cands.extend(MNEMONIC.get(skel, []))
        for i in range(len(toks), 1, -1):
            for op in MNEMONIC.get(self.src_skel(toks[:i]), []):
                if op not in cands:
                    cands.append(op)
        if toks and toks[0].kind == 'ident':
            for op in ALIAS.get(toks[0].val.lower(), []):
                if op not in cands:
                    cands.append(op)
        return cands

    def compile_mnemonic(self, toks, notflag):
        cands = self.candidate_ops(toks)
        for op in cands:
            r = None
            if toks[0].kind == 'ident' and op in ALIAS.get(toks[0].val.lower(), ()):
                r = self.match_opcode(op, toks, alias=True)
            if r is None:
                r = self.match_opcode(op, toks)
            if r is not None:
                params, extra, fmt, vararg = r
                self.emit_op(op, notflag)
                self.emit_params(op, params, extra, fmt, vararg)
                return
        raise SyntaxError('no match: ' + repr([t.val for t in toks]))

    def src_skel(self, toks):
        parts = []
        prev_ph = False
        for t in toks:
            is_lit = ((t.kind == 'ident'
                       and t.val.lower() not in ('true', 'false', 'timera', 'timerb')
                       and t.val.lower() not in self.consts)
                      or (t.kind == 'op' and t.val in ('=', '+=', '-=', '*=', '/=')))
            if is_lit:
                if parts and not prev_ph:
                    parts.append(' ')
                parts.append(t.val.lower())
                prev_ph = False
            else:
                parts.append('\x00')
                prev_ph = True
        return ''.join(parts)

    # --- opcode-prefixed statements via fmt matching
    def compile_opcode_stmt(self, op, toks, notflag):
        toks = list(toks)
        if toks and toks[0].kind == 'ident' and toks[0].val.lower() == 'not':
            # SB: 'not' combined with an 8xxx prefix stays negated (no XOR)
            notflag = True
            toks = toks[1:]
        r = None
        if toks and toks[0].kind == 'ident' and op in ALIAS.get(toks[0].val.lower(), ()):
            r = self.match_opcode(op, toks, alias=True)
        if r is None:
            r = self.match_opcode(op, toks)
        if r is None:
            raise SyntaxError('fmt mismatch op %04X: %r' % (op, [t.val for t in toks]))
        params, extra, fmt, vararg = r
        self.emit_op(op, notflag)
        self.emit_params(op, params, extra, fmt, vararg)

    def fmt_seq(self, fmt):
        parts = re.split(r'(%\d+[a-zA-Z][a-zA-Z/]*%)', fmt)
        seq = []
        for part in parts:
            m = re.fullmatch(r'%(\d+)([a-zA-Z])[a-zA-Z/]*%', part)
            if m:
                seq.append(('p', int(m.group(1)), m.group(2)))
            else:
                words = [w.lower() for w in part.split()]
                if words:
                    seq.append(('l', words))
        return seq

    def match_opcode(self, op, toks, alias=False):
        """strict fmt match; returns (params, extra, fmt, vararg) or None.
        Opcodes listed in EXTRA_FORMS have several accepted spellings; try each
        in order and keep the first that consumes the whole token list."""
        if op in VARIANTS:
            for cnt, fmt in VARIANTS[op]:
                r = self._match_one(op, toks, alias, cnt, fmt)
                if r is not None:
                    return r
            return None
        cnt, fmt = BY_NUM[op]
        return self._match_one(op, toks, alias, cnt, fmt)

    def _match_one(self, op, toks, alias, cnt, fmt):
        vararg = (cnt == -1)
        seq = self.fmt_seq(fmt)
        toks = list(toks)
        if alias and toks:
            # the alias word stands in for the fmt's leading literal (if any)
            if seq and seq[0][0] == 'l':
                seq = seq[1:]
            toks = toks[1:]
        def next_ph_pos(pos):
            for k in range(pos, len(seq)):
                if seq[k][0] == 'p':
                    return k
            return None

        ti = 0
        params = {}
        for si, item in enumerate(seq):
            if item[0] == 'l':
                # literal keywords may be omitted (partially or fully) in SB3 sources
                for w in item[1]:
                    if ti < len(toks) and toks[ti].val.lower() == w:
                        ti += 1
                    else:
                        break
                continue
            _, pidx, lt = item
            if ti >= len(toks):
                return None
            nph = next_ph_pos(si + 1)
            is_vararg_tail = vararg and nph is None
            if nph is not None or is_vararg_tail:
                # another placeholder follows (possibly past omitted literals):
                # exactly one argument
                grp = self.take_arg(toks, ti)
                ti += len(grp)
            else:
                nxt_words = seq[si + 1][1] if si + 1 < len(seq) and seq[si + 1][0] == 'l' else None
                grp = []
                while ti < len(toks):
                    if nxt_words and toks[ti].kind in ('ident', 'op') and toks[ti].val.lower() in nxt_words:
                        break
                    a = self.take_arg(toks, ti)
                    grp.extend(a)
                    ti += len(a)
                if not grp:
                    return None
            params[pidx] = (lt, grp)
        extra = []
        if ti < len(toks):
            if not vararg:
                return None
            while ti < len(toks):
                a = self.take_arg(toks, ti)
                extra.append(a)
                ti += len(a)
        # validate that every captured group actually resolves to a value
        try:
            for pidx, (lt, grp) in params.items():
                self.resolve_value(grp)
            for g in extra:
                self.resolve_value(g)
        except SyntaxError:
            return None
        return params, extra, fmt, vararg

    def emit_params(self, op, params, extra, fmt, vararg):
        order = sorted((int(m.group(1)), m.group(2)) for m in re.finditer(r'%(\d+)([a-zA-Z])[a-zA-Z/]*%', fmt))
        last_idx = order[-1][0] if order else 0
        for pidx, lt in order:
            if pidx not in params:
                continue
            lt2, grp = params[pidx]
            vals = [self.resolve_value(grp)]
            if vararg and pidx == last_idx:
                for v in vals:
                    self.emit_value(v, lt)
                for g in extra:
                    v = self.resolve_value(g)
                    self.emit_value(v, 'd')
                self.emit(b'\x00')
            else:
                self.emit_value(vals[0], lt)

    def take_arg(self, toks, ti):
        """one argument: either a single token or parenthesized array access"""
        t = toks[ti]
        if t.kind == 'ident' and ti + 1 < len(toks) and toks[ti+1].val == '(':
            depth = 0
            j = ti
            while j < len(toks):
                if toks[j].val == '(': depth += 1
                elif toks[j].val == ')':
                    depth -= 1
                    if depth == 0:
                        return toks[ti:j+1]
                j += 1
            raise SyntaxError('unbalanced parens')
        return [t]

    def group_values(self, grp):
        """a param group may contain several space-separated args only if
        the fmt placeholder repeats? No - one group = one arg normally."""
        return [self.resolve_value(grp)]

def repr_float(f):
    s = repr(f)
    return s

def compile_source(src):
    return Compiler(src).compile()

def build_file(src):
    code = compile_source(src)
    out = bytearray(code)
    out += b'FLAG\x00\x04\x14\x00\x00'
    out += b'SRC\x00' + struct.pack('<I', len(src)) + src
    out += struct.pack('<I', len(code))
    out += b'__SBFTR\x00'
    return bytes(out)

if __name__ == '__main__':
    src = open(sys.argv[1], 'rb').read()
    out = build_file(src)
    if len(sys.argv) > 2:
        open(sys.argv[2], 'wb').write(out)
        print('wrote %s (%d bytes)' % (sys.argv[2], len(out)))
    else:
        sys.stdout.buffer.write(out)
