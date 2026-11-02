"""Item records in hero and account saves.

A saved item is {1: id {1: 1, 2: low}, 4: hireling class, 5: slot, 6: square, 7: used sockets, 8: generator}, with
generator {1: seed, 2: {1: gb type, 2: item gbid}, 3: affix gbids, 6: flags, 7: durability, 8: stack size,
10: quality, 12: max durability} (D3.Items.SavedItem / Generator). Slot, square, hireling class, quality and the gb
type are sint32 (zigzag); gbids are sfixed32. The slot is (inventory slot + 17) * 16 in the game's slot numbering."""
import random
from d3save import Message, Field, VARINT, BYTES, FIXED32, zigzag, unzigzag

SLOT_NAMES = {0: 'Backpack', 1: 'Head', 2: 'Torso', 3: 'Off-Hand', 4: 'Main Hand', 5: 'Hands', 6: 'Waist', 7: 'Feet',
              8: 'Shoulders', 9: 'Legs', 10: 'Wrists', 11: 'Right Finger', 12: 'Left Finger', 13: 'Neck',
              17: 'Stash', 18: 'Gold'}
BACKPACK, STASH, GOLD = 0, 17, 18
GB_ITEMS = 2   # game balance table type of item gbids

QUALITY_NAMES = {0: 'Inferior', 1: 'Normal', 2: 'Superior', 3: 'Magic 1', 4: 'Magic 2', 5: 'Magic 3', 6: 'Rare 4',
                 7: 'Rare 5', 8: 'Rare 6', 9: 'Legendary'}


def encode_slot(inventory_slot):
    return zigzag((inventory_slot + 17) * 16)


def decode_slot(value):
    return unzigzag(value) // 16 - 17


class Item:
    """Wraps one saved item message; everything not exposed here is kept untouched."""

    def __init__(self, msg: Message):
        self.msg = msg

    @property
    def gen(self):
        return self.msg.sub(8, create=True)

    @property
    def gbid(self):
        h = self.gen.sub(2)
        return h.get(2) if h else None

    @gbid.setter
    def gbid(self, value):
        h = self.gen.sub(2, create=True)
        h.set(1, zigzag(GB_ITEMS))
        h.set(2, value, FIXED32)

    slot = property(lambda s: decode_slot(s.msg.get(5, 0)), lambda s, v: s.msg.set(5, encode_slot(v)))
    square = property(lambda s: unzigzag(s.msg.get(6, 0)), lambda s, v: s.msg.set(6, zigzag(v)))
    seed = property(lambda s: s.gen.get(1, 0), lambda s, v: s.gen.set(1, v & 0xFFFFFFFF))
    stack = property(lambda s: s.gen.get(8, 0), lambda s, v: s.gen.set(8, v))
    quality = property(lambda s: unzigzag(s.gen.get(10, 2)), lambda s, v: s.gen.set(10, zigzag(v)))
    durability = property(lambda s: s.gen.get(7, 0), lambda s, v: s.gen.set(7, v))
    max_durability = property(lambda s: s.gen.get(12, 0), lambda s, v: s.gen.set(12, v))

    @property
    def affixes(self):
        return [f.value for f in self.gen.all(3)]

    @affixes.setter
    def affixes(self, gbids):
        fields = self.gen.fields
        at = next((i for i, f in enumerate(fields) if f.num > 3), len(fields))
        fields[:] = [f for f in fields if f.num != 3]
        at = next((i for i, f in enumerate(fields) if f.num > 3), len(fields))
        fields[at:at] = [Field(3, FIXED32, g) for g in gbids]

    @property
    def id_low(self):
        return self.msg.sub(1).get(2)


def new_item(id_low, gbid, slot, square=0, stack=0, durability=0, quality=None, seed=None, affixes=()):
    """A new item record laid out the way the game writes them."""
    gen = Message([Field(1, VARINT, random.getrandbits(32) if seed is None else seed),
                   Field(2, BYTES, b'', Message([Field(1, VARINT, zigzag(GB_ITEMS)), Field(2, FIXED32, gbid)]))])
    gen.fields += [Field(3, FIXED32, a) for a in affixes]
    gen.fields += [Field(6, VARINT, 9), Field(7, VARINT, durability), Field(8, VARINT, stack)]
    if quality is not None:
        gen.fields.append(Field(10, VARINT, zigzag(quality)))
    if durability:
        gen.fields.append(Field(12, VARINT, durability))
    msg = Message([Field(1, BYTES, b'', Message([Field(1, VARINT, 1), Field(2, VARINT, id_low)])),
                   Field(4, VARINT, 0), Field(5, VARINT, encode_slot(slot)), Field(6, VARINT, zigzag(square)),
                   Field(7, VARINT, 0), Field(8, BYTES, b'', gen)])
    return Item(msg)
