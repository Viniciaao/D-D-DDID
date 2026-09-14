import os, struct, sys, re

def load_ini(path, db):
    for line in open(path, encoding='cp1252', errors='replace'):
        line = line.strip()
        if not line or line.startswith(';') or line.startswith('[') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k = k.strip()
        if not re.fullmatch(r'[0-9A-Fa-f]{4}', k): continue
        op = int(k, 16)
        cnt, _, fmt = v.partition(',')
        try: cnt = int(cnt.strip())
        except: continue
        db.setdefault(op, (cnt, fmt.strip()))

db = {}
sa = os.environ.get('SCM_SA_DIR', '/tmp/sbdata/sa')
for f in ['SASCM.INI','SASCM.CLEO.ini','SASCM.CLEO+.ini','SASCM.NewOpcodes.ini','SASCM.Clipboard.ini']:
    p = os.path.join(sa, f)
    if os.path.exists(p): load_ini(p, db)

NUL = b'\x00'

def read_param(data, ip):
    t = data[ip]; ip += 1
    if t == 0x01:
        v = struct.unpack_from('<i', data, ip)[0]; ip += 4
        return '@%x' % (-v), ip
    if t == 0x02:
        v = struct.unpack_from('<H', data, ip)[0]; ip += 2
        return '$%d' % v, ip
    if t == 0x03:
        v = struct.unpack_from('<H', data, ip)[0]; ip += 2
        return '%d@' % v, ip
    if t == 0x04:
        v = struct.unpack_from('<b', data, ip)[0]; ip += 1
        return '%d' % v, ip
    if t == 0x05:
        v = struct.unpack_from('<h', data, ip)[0]; ip += 2
        return '%d' % v, ip
    if t == 0x06:
        v = struct.unpack_from('<f', data, ip)[0]; ip += 4
        return '%gf' % v, ip
    if t == 0x09:
        raw = data[ip:ip+8]; ip += 8
        key = raw.split(NUL)[0].decode('cp1252','replace')
        return "gxt'%s'" % key, ip
    if t == 0x0A:
        raw = data[ip:ip+8]; ip += 8
        key = raw.split(NUL)[0].decode('cp1252','replace')
        return 'str8"%s"' % key, ip
    if t in (0x07, 0x08):
        base = struct.unpack_from('<H', data, ip)[0]; ip += 2
        idx = struct.unpack_from('<H', data, ip)[0]; ip += 2
        size = struct.unpack_from('<H', data, ip)[0]; ip += 2
        tag = 'GARR' if t == 0x07 else 'LARR'
        return '%s%d(%d,%di)' % (tag, base, idx, size), ip
    if t == 0x0E:
        ln = data[ip]; ip += 1
        s = data[ip:ip+ln].decode('cp1252','replace'); ip += ln
        return '"%s"' % s, ip
    if t == 0x11:
        v = struct.unpack_from('<H', data, ip)[0]; ip += 2
        return '%d@v' % v, ip
    if t == 0x10:
        v = struct.unpack_from('<H', data, ip)[0]; ip += 2
        return '$%dv' % v, ip
    if t == 0x15:
        raw = data[ip:ip+8]; ip += 8
        key = raw.split(NUL)[0].decode('cp1252','replace')
        return 'gxt8"%s"' % key, ip
    raise ValueError('unknown type %02x at %x' % (t, ip-1))

def disasm_block(data, ip, limit):
    out = []
    while ip < limit:
        opstart = ip
        opw = struct.unpack_from('<H', data, ip)[0]
        notflag = bool(opw & 0x8000)
        op = opw & 0x7FFF
        ip += 2
        if op == 0x00D6:
            t = data[ip]; ip += 1
            cnt = data[ip]; ip += 1
            out.append((opstart, op, 'IF raw=%#x' % cnt, []))
            continue
        cnt = db.get(op, (None,))[0]
        params = []
        try:
            if cnt == -1:
                while True:
                    if data[ip] == 0x00:
                        ip += 1
                        break
                    r, ip = read_param(data, ip)
                    params.append(r)
            elif cnt is not None:
                for _ in range(cnt):
                    r, ip = read_param(data, ip)
                    params.append(r)
            else:
                out.append((opstart, op, 'UNKNOWN', []))
                return out, ip, False
        except Exception as e:
            out.append((opstart, op, 'PARSE_ERR %s' % e, []))
            return out, ip, False
        fmt = db.get(op, (0,'?'))[1]
        out.append((opstart, op, ('NOT ' if notflag else '') + fmt[:50], params))
        if op == 0x0002:
            return out, ip, True
    return out, ip, True

def full_disasm(data, limit):
    seen = set()
    queue = [0]
    byoff = {}
    while queue:
        start = queue.pop()
        if start in seen or start >= limit: continue
        seen.add(start)
        blk, ip, _ = disasm_block(data, start, limit)
        for item in blk:
            byoff.setdefault(item[0], item)
        for (off, op, txt, params) in blk:
            if op in (0x0002, 0x004D, 0x0050):
                for p in params:
                    if p.startswith('@'):
                        queue.append(int(p[1:], 16))
        queue.append(ip)
    return byoff

if __name__ == '__main__':
    path = sys.argv[1]
    data = open(path,'rb').read()
    i = data.rfind(b'__SBFTR\x00')
    codesz = struct.unpack_from('<I', data, i-4)[0] if i>0 else len(data)
    byoff = full_disasm(data, codesz)
    for o in sorted(byoff):
        off, op, txt, params = byoff[o]
        print('%05x %04X  %s  %s' % (off, op, txt, ' | '.join(params)))
