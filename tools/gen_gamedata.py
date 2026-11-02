"""Builds the editor's item list from the PC client's own game data (1.0.8). Item names and gbids match the console
release; affixes do not (the console has its own list, see console_affixes.py).

usage: gen_gamedata.py <PC client folder> <output folder>
writes items.json"""
import json, re, struct, sys
from pathlib import Path
from mpq import MPQ

ITEM_TABLES = ['Items_Weapons', 'Items_Armor', 'Items_Other', 'Items_Legendary', 'Items_Legendary_Weapons',
               'Items_Legendary_Other', 'Items_Quests']
# Items that only exist in the console version, so they are not in the PC data.
CONSOLE_ITEMS = [
    {'name': 'HealthPotionConsole', 'display': 'Health Potion (console)', 'type': 'HealthPotion',
     'typeDisplay': 'Potion', 'level': 1, 'requiredLevel': 0, 'maxDurability': 0, 'actor': -1, 'typeGroups': [],
     'table': 'Console', 'legendary': False},
]
ITEM_RECORD = 1488
ITEMTYPE_RECORD = 320


def gbid(name):
    """Game balance ids are a hash of the record name."""
    h = 0
    for c in name.lower():
        h = (h * 33 + ord(c)) & 0xFFFFFFFF
    return h


def records(data, size):
    """Yields (name, record bytes) for a GameBalance table: fixed-size records that start with a 256-byte name."""
    first = re.search(rb'(?<=\x00)[A-Za-z][A-Za-z0-9_ ]{2,60}\x00', data[0x100:])
    pos = 0x100 + first.start()
    while pos + size <= len(data):
        name = data[pos:pos + 256].split(b'\0')[0]
        if not name or not re.fullmatch(rb'[A-Za-z0-9_ \-\'()]+', name):
            break
        yield name.decode(), data[pos:pos + size]
        pos += size


def string_list(mpq, path):
    """StringList (.stl): a table of 80-byte entries holding (offset, size) of key, text and two more strings."""
    # Offsets in the file are relative to the end of the 16-byte SNO header.
    data = mpq.read(path)[0x10:]
    table, table_size = struct.unpack_from('<II', data, 0x18)
    out = {}
    for e in range(table, table + table_size, 80):
        k_off, k_len = struct.unpack_from('<II', data, e + 8)
        v_off, v_len = struct.unpack_from('<II', data, e + 24)
        if k_len:
            out[data[k_off:k_off + k_len - 1].decode('utf-8', 'replace')] = data[v_off:v_off + v_len - 1].decode('utf-8', 'replace')
    return out


def main(client, out):
    mpqs = Path(client) / 'Data_D3' / 'PC' / 'MPQs'
    core, text = MPQ(mpqs / 'CoreData.mpq'), MPQ(mpqs / 'enGB_Text.mpq')
    item_names = string_list(text, 'StringList/Items.stl')
    type_names = string_list(text, 'StringList/ItemTypeNames.stl')

    types = {}
    for name, rec in records(core.read('GameBalance/ItemTypes.gam'), ITEMTYPE_RECORD):
        parent, = struct.unpack_from('<I', rec, 256)
        types[gbid(name)] = {'name': name, 'display': type_names.get(name, name), 'parent': parent}

    def ancestry(type_gbid):
        """The item type and all its parents (e.g. Ring, Jewelry): affixes are allowed per type group."""
        out = []
        while type_gbid in types and type_gbid not in out:
            out.append(type_gbid)
            type_gbid = types[type_gbid]['parent']
        return out

    items = []
    for table in ITEM_TABLES:
        data = core.read('GameBalance/%s.gam' % table)
        if not data:
            continue
        for name, rec in records(data, ITEM_RECORD):
            sno_actor, type_gbid = struct.unpack_from('<iI', rec, 256)
            level, = struct.unpack_from('<i', rec, 272)
            req_level, max_dur = struct.unpack_from('<ii', rec, 304)
            itype = types.get(type_gbid, {'name': '?', 'display': '?'})
            items.append({
                'gbid': gbid(name), 'name': name, 'display': item_names.get(name, name), 'table': table,
                'type': itype['name'], 'typeDisplay': itype['display'], 'level': level, 'requiredLevel': req_level,
                'maxDurability': max_dur, 'actor': sno_actor, 'typeGroups': ancestry(type_gbid),
                'legendary': table.startswith('Items_Legendary') or name.startswith(('Unique_', 'Set_')),
            })

    for extra in CONSOLE_ITEMS:
        items.append(dict(extra, gbid=gbid(extra['name'])))

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'items.json').write_text(json.dumps(items, indent=1), encoding='utf-8')
    print('%d items (%d legendary), %d item types' % (len(items), sum(i['legendary'] for i in items), len(types)))


if __name__ == '__main__':
    main(*sys.argv[1:3])
