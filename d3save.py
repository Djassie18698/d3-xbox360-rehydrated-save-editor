"""Diablo III (original 2013 Xbox 360 release) save files, as Rehydrated writes them in its d3save folder.

A save is a protobuf message XOR'd with a running key. Messages are kept as ordered field lists so that everything
the editor doesn't understand is written back exactly as it was read."""
import struct

SAVE_KEY = 0x305F92D82EC9A01B
VARINT, FIXED64, BYTES, FIXED32 = 0, 1, 2, 5


def decrypt(data: bytes) -> bytes:
    key, out = SAVE_KEY, bytearray()
    for c in data:
        out.append(c ^ (key & 0xFF))
        key = (c << 56) | (key >> 8)
    return bytes(out)


def encrypt(data: bytes) -> bytes:
    key, out = SAVE_KEY, bytearray()
    for p in data:
        c = p ^ (key & 0xFF)
        out.append(c)
        key = (c << 56) | (key >> 8)
    return bytes(out)


def _varint(buf, i):
    shift = value = 0
    while True:
        b = buf[i]
        i += 1
        value |= (b & 0x7F) << shift
        if b < 0x80:
            return value, i
        shift += 7


def _put_varint(out, value):
    value &= 0xFFFFFFFFFFFFFFFF
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)


def zigzag(n):
    return (n << 1) ^ (n >> 63)


def unzigzag(n):
    return (n >> 1) ^ -(n & 1)


class Field:
    """One protobuf field. `value` is an int (varint/fixed) or bytes; `msg` caches the parsed sub-message."""
    __slots__ = ('num', 'wt', 'value', 'msg')

    def __init__(self, num, wt, value, msg=None):
        self.num, self.wt, self.value, self.msg = num, wt, value, msg

    def __repr__(self):
        return 'Field(%d, %d, %r)' % (self.num, self.wt, self.msg if self.msg is not None else self.value)


class Message:
    def __init__(self, fields=None):
        self.fields = fields or []

    @staticmethod
    def parse(buf):
        fields, i = [], 0
        while i < len(buf):
            tag, i = _varint(buf, i)
            num, wt = tag >> 3, tag & 7
            if wt == VARINT:
                v, i = _varint(buf, i)
            elif wt == FIXED64:
                v = struct.unpack_from('<Q', buf, i)[0]; i += 8
            elif wt == FIXED32:
                v = struct.unpack_from('<I', buf, i)[0]; i += 4
            elif wt == BYTES:
                n, i = _varint(buf, i)
                v = bytes(buf[i:i + n]); i += n
            else:
                raise ValueError('unsupported wire type %d at %d' % (wt, i))
            if num == 0:
                raise ValueError('field 0')
            fields.append(Field(num, wt, v))
        return Message(fields)

    def encode(self):
        out = bytearray()
        for f in self.fields:
            _put_varint(out, (f.num << 3) | f.wt)
            if f.wt == VARINT:
                _put_varint(out, f.value)
            elif f.wt == FIXED64:
                out += struct.pack('<Q', f.value & 0xFFFFFFFFFFFFFFFF)
            elif f.wt == FIXED32:
                out += struct.pack('<I', f.value & 0xFFFFFFFF)
            else:
                data = f.msg.encode() if f.msg is not None else f.value
                _put_varint(out, len(data))
                out += data
        return bytes(out)

    # Access helpers
    def all(self, num):
        return [f for f in self.fields if f.num == num]

    def first(self, num):
        for f in self.fields:
            if f.num == num:
                return f
        return None

    def get(self, num, default=None):
        f = self.first(num)
        return default if f is None else f.value

    def sub(self, num, create=False):
        """The sub-message in field `num` (parsed once, then edited in place)."""
        f = self.first(num)
        if f is None:
            if not create:
                return None
            f = Field(num, BYTES, b'', Message())
            self.fields.append(f)
        if f.msg is None:
            f.msg = Message.parse(f.value)
        return f.msg

    def subs(self, num):
        out = []
        for f in self.all(num):
            if f.msg is None:
                f.msg = Message.parse(f.value)
            out.append(f.msg)
        return out

    def set(self, num, value, wt=VARINT):
        f = self.first(num)
        if f is None:
            self.fields.append(Field(num, wt, value))
        else:
            f.value, f.wt, f.msg = value, wt, None

    def remove(self, num):
        self.fields = [f for f in self.fields if f.num != num]

    def add_message(self, num, msg):
        self.fields.append(Field(num, BYTES, b'', msg))

    def insert_message_after(self, num, msg):
        """Adds a repeated sub-message next to the existing ones, keeping the field order the game writes."""
        last = max((i for i, f in enumerate(self.fields) if f.num == num), default=None)
        f = Field(num, BYTES, b'', msg)
        if last is None:
            self.fields.append(f)
        else:
            self.fields.insert(last + 1, f)

    def dump(self, indent=0):
        pad = '  ' * indent
        lines = []
        for f in self.fields:
            if f.wt == BYTES:
                try:
                    m = f.msg if f.msg is not None else Message.parse(f.value)
                    if f.value and m.encode() != f.value:
                        raise ValueError
                    lines.append('%s%d: {' % (pad, f.num))
                    lines.append(m.dump(indent + 1))
                    lines.append(pad + '}')
                    continue
                except Exception:
                    lines.append('%s%d: %r' % (pad, f.num, f.value))
            else:
                lines.append('%s%d: %d (0x%X)' % (pad, f.num, f.value, f.value))
        return '\n'.join(l for l in lines if l)


def load(path):
    with open(path, 'rb') as fh:
        return Message.parse(decrypt(fh.read()))


def save_bytes(msg):
    return encrypt(msg.encode())
