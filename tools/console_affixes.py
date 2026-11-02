"""Builds data/affixes.json from the console game's own affix table, read from a running Rehydrated.

The console (Xbox 360) affix list differs from the PC one: every record is named "1xx_<name>" and its gbid is the
hash of that full name, and about a third of the affixes only exist on console. The table is not in the PC client,
so it is read from guest memory once the game shows its main menu. Windows only.

Record layout (512 bytes, big endian): 0 name pointer, 8 gbid, 12 kind, 40 affix level, 56 required level,
88 family (one affix per family on an item), 128 up to 16 item type groups it may roll on, 224 up to 16 groups it
may not roll on, 320 mask of item qualities it may roll on.

usage: console_affixes.py [output folder]     (default: ../data)"""
import ctypes, ctypes.wintypes as w, json, os, re, struct, subprocess, sys

GUEST_BASE = 0x100000000     # rexglue maps guest memory here (see "Guest memory arena mapped" in its log)
RECORD = 0x200


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
    out = []
    while (rec := record(at)):
        name, r = rec
        v = struct.unpack('>128I', r)
        groups = lambda off: [x for x in v[off // 4:off // 4 + 16] if x != 0xFFFFFFFF]
        out.append({'gbid': v[2], 'name': name[4:], 'kind': v[3], 'level': v[10], 'requiredLevel': v[14],
                    'family': v[22], 'groups': groups(128), 'excludedGroups': groups(224), 'qualityMask': v[80]})
        at += RECORD
    return out


def main(out):
    tasks = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq rehydrated.exe', '/FO', 'CSV', '/NH'],
                           capture_output=True, text=True).stdout
    m = re.search(r'"rehydrated\.exe","(\d+)"', tasks, re.I)
    if not m:
        sys.exit('Start Rehydrated and wait for the main menu first.')
    g = Guest(int(m.group(1)))
    affixes = read_table(g, find_table(g))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'affixes.json'), 'w', encoding='utf-8') as f:
        json.dump(affixes, f, indent=1)
    print('%d console affixes' % len(affixes))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
