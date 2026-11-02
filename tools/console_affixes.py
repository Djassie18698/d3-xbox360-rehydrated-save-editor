"""Builds data/affixes.json from the console game's own affix table, and the legendary affix rolls in
data/items.json from its item tables, read from a running Rehydrated.

The console (Xbox 360) affix list differs from the PC one: every record is named "1xx_<name>" and its gbid is the
hash of that full name, and about a third of the affixes only exist on console. The table is not in the PC client,
so it is read from guest memory once the game shows its main menu. Windows only.

Record layout (512 bytes, big endian): 0 name pointer, 8 gbid, 12 kind, 40 affix level, 56 required level,
80/84 the rare name lists (prefix, suffix) the affix lends words from, 88 family (one affix per family on an item),
92 a second family legendary rolls may name, 128 up to 16 item type groups it may roll on, 224 up to 16 groups it
may not roll on, 320 mask of item qualities it may roll on, 336 four stat slots of 24 bytes: attribute, parameter,
0, formula pointer, formula offset, formula size.

Item record (1320 bytes, big endian): 0 name pointer, 8 gbid, 100/104 the rare name lists (prefix, suffix) of the
item type, 1224 up to 6 affix families a legendary rolls one affix from when it drops, 1248 the highest affix level
for each. The console reworked legendaries, so these differ from the PC client's.

Formulas are small stack programs of big endian words, the operation in the top byte: 6 <float> pushes a number, 1 makes a random range of the
two numbers on top, 4 rounds it, 11-14 add/subtract/multiply/divide, 0 ends.

usage: console_affixes.py [data folder]     (default: ../data; items.json must exist there)"""
import ctypes, ctypes.wintypes as w, json, os, re, struct, subprocess, sys

GUEST_BASE = 0x100000000     # rexglue maps guest memory here (see "Guest memory arena mapped" in its log)
RECORD = 0x200
ITEM_RECORD = 0x528
ATTRIB_DEFS = 0x82F9DA88     # the game's attribute definition table (40-byte entries; name pointer at 28)


def gbid(name):
    h = 0
    for c in name.lower().encode():
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_uint64), ('AllocationBase', ctypes.c_uint64), ('AllocationProtect', w.DWORD),
                ('PartitionId', w.WORD), ('RegionSize', ctypes.c_uint64), ('State', w.DWORD), ('Protect', w.DWORD),
                ('Type', w.DWORD)]


class Guest:
    """Read access to a running rehydrated.exe's guest memory, by guest address."""

    def __init__(self, pid):
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.OpenProcess.restype = w.HANDLE
        self.k.VirtualQueryEx.argtypes = [w.HANDLE, ctypes.c_uint64, ctypes.POINTER(MBI), ctypes.c_size_t]
        self.k.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t,
                                             ctypes.POINTER(ctypes.c_size_t)]
        self.h = self.k.OpenProcess(0x0410, False, pid)
        if not self.h:
            raise OSError('cannot open rehydrated.exe (pid %d)' % pid)

    def regions(self):
        addr = GUEST_BASE
        while addr < GUEST_BASE + 0x100000000:
            m = MBI()
            if not self.k.VirtualQueryEx(self.h, addr, ctypes.byref(m), ctypes.sizeof(m)):
                break
            if m.State == 0x1000 and not m.Protect & 0x101:
                yield m.BaseAddress - GUEST_BASE, m.RegionSize
            addr = m.BaseAddress + m.RegionSize

    def read(self, guest, size):
        buf = ctypes.create_string_buffer(size)
        n = ctypes.c_size_t()
        self.k.ReadProcessMemory(self.h, GUEST_BASE + guest, buf, size, ctypes.byref(n))
        return buf.raw[:n.value]


def find_table(g):
    """Finds one affix record: a "1xx_" name, then a word pointing at it followed by 0 and the name's hash."""
    names = {}
    for base, size in g.regions():
        data = g.read(base, size)
        for m in re.finditer(rb'(?<=\x00)1xx_[ -~]{2,120}?\x00', data):
            names[base + m.start()] = m.group()[:-1].decode()
            if len(names) >= 50:
                break
        if names:
            break
    if not names:
        raise RuntimeError('no affix names in memory yet: wait for the main menu and try again')
    for base, size in g.regions():
        data = g.read(base, size)
        for addr, name in names.items():
            pat = struct.pack('>III', addr, 0, gbid(name))
            i = data.find(pat)
            if i >= 0 and i % 4 == 0:
                return base + i
    raise RuntimeError('affix records not found')


def attribute_names(g):
    names = []
    while True:
        raw = g.read(ATTRIB_DEFS + len(names) * 40, 40)
        index, = struct.unpack_from('>i', raw)
        if index != len(names):
            return names
        name = g.read(struct.unpack_from('>I', raw, 28)[0], 64).split(b'\0')[0].decode('latin1')
        if not name:
            return names
        names.append(name)


def formula_range(words):
    """(low, high) a formula can produce, or None for formulas this does not understand."""
    stack, i = [], 0
    while i < len(words):
        op = words[i] >> 24
        if op == 0:
            break
        if op == 6:
            v, = struct.unpack('>f', struct.pack('>I', words[i + 1]))
            stack.append((v, v))
            i += 2
            continue
        if op == 1 and len(stack) >= 2:
            (a, _), (b, _) = stack.pop(), stack.pop()
            stack.append((min(a, b), max(a, b)))
        elif op == 4 and stack:
            pass
        elif op in (11, 12, 13, 14) and len(stack) >= 2:
            (b1, b2), (a1, a2) = stack.pop(), stack.pop()
            if op == 11:
                stack.append((a1 + b1, a2 + b2))
            elif op == 12:
                stack.append((a1 - b2, a2 - b1))
            elif op == 13:
                stack.append((a1 * b1, a2 * b2))
            elif b1:
                stack.append((a1 / b1, a2 / b1))
        else:
            return None
        i += 1
    return stack[-1] if len(stack) == 1 else None


def read_table(g, at):
    def record(a):
        r = g.read(a, RECORD)
        if len(r) < RECORD:
            return None
        ptr, zero, gb = struct.unpack_from('>3I', r)
        name = g.read(ptr, 128).split(b'\0')[0].decode('latin1') if zero == 0 else ''
        return (name, r) if name.startswith('1xx_') and gbid(name) == gb else None

    while record(at - RECORD):
        at -= RECORD
    attrs = attribute_names(g)
    out = []
    while (rec := record(at)):
        name, r = rec
        v = struct.unpack('>128I', r)
        groups = lambda off: [x for x in v[off // 4:off // 4 + 16] if x != 0xFFFFFFFF]
        stats = []
        for slot in range(4):
            attr, param, _, ptr, _, size = v[84 + slot * 6:90 + slot * 6]
            if attr == 0xFFFFFFFF or attr >= len(attrs):
                continue
            words = struct.unpack('>%dI' % (size // 4), g.read(ptr, size)) if ptr and size else ()
            rng = formula_range(words)
            stats.append([attrs[attr], -1 if param == 0xFFFFFFFF else param] + ([round(rng[0], 4), round(rng[1], 4)] if rng else [None, None]))
        out.append({'gbid': v[2], 'name': name[4:], 'kind': v[3], 'level': v[10], 'requiredLevel': v[14],
                    'family': v[22], 'family2': v[23], 'groups': groups(128), 'excludedGroups': groups(224),
                    'qualityMask': v[80], 'stats': stats, 'rareNameLists': [v[20], v[21]]})
        at += RECORD
    return out


def region_of(g, addr):
    return next((b, n) for b, n in g.regions() if b <= addr < b + n)


def read_item_rolls(g, base, size, items):
    """Finds the item tables in the game data region. Returns {gbid: [[family, max affix level], ...]} and the
    gbids that exist in the console data at all (PC items missing there are dropped by the game)."""
    data = g.read(base, size)
    want = {gbid(i['name']): i['name'] for i in items}
    found = {}
    present = {g for g in want if data.find(struct.pack('>I', g)) >= 0}

    def record(o):
        if not 0 <= o <= len(data) - ITEM_RECORD:
            return None
        ptr, zero, gb = struct.unpack_from('>3I', data, o)
        if zero or gb not in want or not base <= ptr < base + len(data):
            return None
        name = data[ptr - base:ptr - base + 128].split(b'\0')[0].decode('latin1')
        return gb if gbid(name) == gb else None

    for gb, name in want.items():
        if gb in found:
            continue
        # Other tables point at the same name; the item table is the one whose neighbours are items too.
        at = -1
        for m in re.finditer(rb'\0' + re.escape(name.encode()) + rb'\0', data):
            pat = struct.pack('>III', base + m.start() + 1, 0, gb)
            i = data.find(pat)
            while i >= 0 and not (i % 4 == 0 and (record(i - ITEM_RECORD) or record(i + ITEM_RECORD))):
                i = data.find(pat, i + 1)
            if i >= 0:
                at = i
                break
        if at < 0:
            continue
        while record(at - ITEM_RECORD):
            at -= ITEM_RECORD
        while (g_ := record(at)) is not None:
            v = struct.unpack_from('>%dI' % (ITEM_RECORD // 4), data, at)
            families, levels = v[1224 // 4:1224 // 4 + 6], v[1248 // 4:1248 // 4 + 6]
            found[g_] = ([[f, l] for f, l in zip(families, levels) if f not in (0, 0xFFFFFFFF)], [v[25], v[26]])
            at += ITEM_RECORD
    return found, present


def main(out):
    tasks = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq rehydrated.exe', '/FO', 'CSV', '/NH'],
                           capture_output=True, text=True).stdout
    m = re.search(r'"rehydrated\.exe","(\d+)"', tasks, re.I)
    if not m:
        sys.exit('Start Rehydrated and wait for the main menu first.')
    g = Guest(int(m.group(1)))
    table = find_table(g)
    affixes = read_table(g, table)
    with open(os.path.join(out, 'affixes.json'), 'w', encoding='utf-8') as f:
        json.dump(affixes, f, indent=1)
    print('%d console affixes' % len(affixes))

    path = os.path.join(out, 'items.json')
    with open(path, encoding='utf-8') as f:
        items = json.load(f)
    rolls, present = read_item_rolls(g, *region_of(g, table), items)
    for i in items:
        i['affixRolls'], i['rareNameLists'] = rolls.get(gbid(i['name']), ([], []))
        i['console'] = gbid(i['name']) in present or i['table'] == 'Console'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=1)
    print('%d of %d items exist on console, %d roll legendary affixes' % (
        sum(i['console'] for i in items), len(items), sum(1 for r, _ in rolls.values() if r)))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
