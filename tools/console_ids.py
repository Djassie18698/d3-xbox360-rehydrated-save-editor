"""Adds the console's own item ids to data/items.json.

The console renamed its legendary and set item rows to "<PC name>_1xx", so their gbids (hashes of the name) differ
from the PC ones. The console still has some of the old rows, but those are not the items the game drops: an item
saved with the PC gbid can come out as a different item. Rehydrated's PC proxy maps the console ids back to the PC
ones (src/recomp/network/gbid_mappings.h); this reads that table and stores each item's console id as consoleGbid.

usage: console_ids.py <gbid_mappings.h> [data folder]     (default: ../data)"""
import json, os, re, sys


def main(mappings, out):
    text = open(mappings, encoding='utf-8').read()
    table = text.split('s_ItemGbidMappings[] = {')[1].split('};')[0]
    console = {pc: int(gb, 16) for gb, _, name, pc in re.findall(r'\{ (0x[0-9A-F]+), (0x[0-9A-F]+) \},\s*// (\S+) -> (\S+)', table)
               if name == pc + '_1xx'}
    path = os.path.join(out, 'items.json')
    with open(path, encoding='utf-8') as f:
        items = json.load(f)
    for i in items:
        i.pop('consoleGbid', None)
        if i['name'] in console:
            i['consoleGbid'] = console[i['name']]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=1)
    print('%d items have a console id' % sum('consoleGbid' in i for i in items))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
