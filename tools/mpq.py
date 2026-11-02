"""Minimal MPQ (v1-v4) reader: hash/block tables, encrypted tables, zlib/bzip2 sectors. Enough to list and read
files from Diablo III's PC MPQs."""
import bz2, struct, sys, zlib

def _crypt_table():
    t, seed = [0] * 0x500, 0x00100001
    for i in range(0x100):
        for j in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB; hi = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB; t[i + j * 0x100] = hi | (seed & 0xFFFF)
    return t
CT = _crypt_table()

def hash_str(s, kind):
    s1, s2 = 0x7FED7FED, 0xEEEEEEEE
    for ch in s.upper().replace('/', '\\').encode():
        s1 = (CT[kind * 0x100 + ch] ^ (s1 + s2)) & 0xFFFFFFFF
        s2 = (ch + s1 + s2 + (s2 << 5) + 3) & 0xFFFFFFFF
    return s1

def decrypt(data, key):
    out, s2 = bytearray(), 0xEEEEEEEE
    n = len(data) // 4
    words = struct.unpack('<%dI' % n, data[:n * 4])
    for w in words:
        s2 = (s2 + CT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        v = (w ^ (key + s2)) & 0xFFFFFFFF
        key = (((~key << 0x15) + 0x11111111) | (key >> 0x0B)) & 0xFFFFFFFF
        s2 = (v + s2 + (s2 << 5) + 3) & 0xFFFFFFFF
        out += struct.pack('<I', v)
    return bytes(out) + data[n * 4:]

class MPQ:
    def __init__(self, path):
        self.f = open(path, 'rb')
        h = self.f.read(208)
        assert h[:4] == b'MPQ\x1a', 'not an MPQ'
        hsize, arcsize, ver, sshift, hpos, bpos, hcount, bcount = struct.unpack('<IIHHIIII', h[4:32])
        self.sector = 512 << sshift
        hi_bt = hpos_hi = bpos_hi = 0
        if ver >= 1:
            hi_bt, hpos_hi, bpos_hi = struct.unpack('<QHH', h[32:44])
        hpos |= hpos_hi << 32; bpos |= bpos_hi << 32
        self.f.seek(hpos); ht = decrypt(self.f.read(hcount * 16), hash_str('(hash table)', 3))
        self.f.seek(bpos); bt = decrypt(self.f.read(bcount * 16), hash_str('(block table)', 3))
        self.hashes = [struct.unpack_from('<IIHHI', ht, i * 16) for i in range(hcount)]
        self.blocks = [list(struct.unpack_from('<IIII', bt, i * 16)) for i in range(bcount)]
        if hi_bt:
            self.f.seek(hi_bt)
            his = struct.unpack('<%dH' % bcount, self.f.read(bcount * 2))
            for b, hi in zip(self.blocks, his): b[0] |= hi << 32

    def find(self, name):
        a, b = hash_str(name, 1), hash_str(name, 2)
        start = hash_str(name, 0) % len(self.hashes)
        for i in range(len(self.hashes)):
            ha, hb, loc, plat, bi = self.hashes[(start + i) % len(self.hashes)]
            if bi == 0xFFFFFFFF: return None
            if ha == a and hb == b and bi < len(self.blocks): return self.blocks[bi]
        return None

    def read(self, name):
        blk = self.find(name)
        if not blk: return None
        pos, csize, size, flags = blk
        if flags & 0x00010000: raise NotImplementedError('encrypted file: ' + name)
        self.f.seek(pos)
        if flags & 0x01000000:   # single unit
            data = self.f.read(csize)
            return self._decomp(data, size) if (flags & 0x200) and csize < size else data
        n = (size + self.sector - 1) // self.sector
        offs = struct.unpack('<%dI' % (n + 1), self.f.read((n + 1) * 4))
        out = bytearray()
        for i in range(n):
            self.f.seek(pos + offs[i]); chunk = self.f.read(offs[i + 1] - offs[i])
            want = min(self.sector, size - i * self.sector)
            out += self._decomp(chunk, want) if (flags & 0x200) and len(chunk) < want else chunk
        return bytes(out)

    @staticmethod
    def _decomp(data, size):
        m = data[0]
        if m == 2: return zlib.decompress(data[1:])
        if m == 0x10: return bz2.decompress(data[1:])
        raise NotImplementedError('compression %#x' % m)

    def listfile(self):
        d = self.read('(listfile)')
        return d.decode('utf-8', 'replace').split('\r\n') if d else []

if __name__ == '__main__':
    m = MPQ(sys.argv[1])
    names = m.listfile()
    print(len(names), 'files')
    for n in names:
        if len(sys.argv) < 3 or sys.argv[2].lower() in n.lower(): print(n)
