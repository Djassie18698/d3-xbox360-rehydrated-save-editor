"""Prepares a copy of a Rehydrated user data folder for an in-game test of what the editor writes. Load the copy
with Rehydrated (--user_data_root=<test root>), check the hero in game, leave the game so it saves, then run
`ingame_test.py check <test root>` to see what the game kept.

usage: ingame_test.py <case> <real user data root> <test root> [hero name]
       ingame_test.py check <test root> [hero name]
cases: basic   normal items in the backpack and equipment slots, a legendary in the stash, 123456 gold
       affix   a magic ring, a rare helm and a magic dagger with chosen affixes
       crazy   level 60 hero with a dagger of 29 stacked top-tier affixes in the main hand
The hero is the last played one unless a name is given."""
import collections, os, shutil, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import items as it
import savegame as sg

data = sg.GameData()
ITEM = {i['name']: i for i in data.items}
AFFIX = {a['name']: a['gbid'] for a in data.affixes}


def top(prefix):
    return max((a for a in data.affixes if a['name'].startswith(prefix) and a['kind'] == 3), key=lambda a: a['level'])['name']


def pick_hero(save, name=None):
    last = save.account.msg.sub(2).sub(2)
    if name:
        hero = next(h for h in save.heroes if h.name == name)
        last.set(2, hero.id_low)   # play this hero when the game starts
        save.account.dirty = True
        return hero
    return next((h for h in save.heroes if h.id_low == last.get(2)), save.heroes[0])


def add(hero, name, slot, quality=None, affixes=()):
    c = hero.container
    info = ITEM[name]
    if slot == it.BACKPACK:
        square = c.free_square(slot, sg.BACKPACK_W, sg.BACKPACK_H, data.height(info['gbid']), data)
    else:
        square = 0
        for old in [i for i in c.items if i.slot == slot]:
            old.slot, old.square = it.BACKPACK, c.free_square(it.BACKPACK, sg.BACKPACK_W, sg.BACKPACK_H, data.height(old.gbid), data)
    c.add(sg.make_item(c, data, info, slot, square, quality, [AFFIX[a] for a in affixes]))
    hero.dirty = True


def make(case, real, root, name=None):
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(real, root)
    save = sg.SaveFolder(sg.find_save_dirs(root)[0])
    hero = pick_hero(save, name)
    if case == 'basic':
        for item, slot in [('Helm_002', it.BACKPACK), ('ChestArmor_001', 2), ('Boots_001', 7), ('Amulet01', 13),
                           ('Ring_02', 11), ('Unique_Dagger_003', 4)]:
            add(hero, item, slot)
        sc = save.account.container
        sc.add(sg.make_item(sc, data, ITEM['Unique_Sword_1H_008'], it.STASH, sc.free_square(it.STASH, sg.STASH_W, sg.STASH_H, 2, data)))
        save.account.gold = 123456
    elif case == 'affix':
        add(hero, 'Ring_01', it.BACKPACK, 3, ['Experience I'])
        add(hero, 'Helm_002', it.BACKPACK, 6, ['Str 1 Secondary', 'Vit 1 Secondary', 'Experience I', 'GoldPickUpRadius 1'])
        add(hero, 'Dagger_001', it.BACKPACK, 3, ['Dex 1', 'MinMaxDam 1 Fast'])
    elif case == 'crazy':
        hero.level = 60
        add(hero, 'Dagger_001', 4, 6, ['Damage VIII'] * 4 + 4 * ['PrimaryAttribute_Int 17 Legendary', 'AllStats 17 Legendary',
            top('CriticalD '), top('CriticalChance '), 'Haste 11', 'DamageBonusArcane 4 Legendary'] + ['Indestructible 10'])
    else:
        sys.exit(__doc__)
    save.save()
    print('test copy ready for %s: %s' % (hero.name, save.path))


def check(root, name=None):
    save = sg.SaveFolder(sg.find_save_dirs(root)[0])
    hero = pick_hero(save, name)
    print('%s, level %d' % (hero.name, hero.level))
    for i in hero.container.items:
        affixes = collections.Counter(data.affix_name(a) for a in i.affixes)
        print('  %-14s %-26s %-10s %s' % (it.SLOT_NAMES.get(i.slot, i.slot), data.item_name(i.gbid), it.QUALITY_NAMES.get(i.quality, i.quality),
                                          ', '.join('%s x%d' % kv if kv[1] > 1 else kv[0] for kv in affixes.items())))
    print('  stash: %s; gold %d' % ([data.item_name(i.gbid) for i in save.account.container.items if i.slot == it.STASH], save.account.gold))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if sys.argv[1] == 'check':
        check(*sys.argv[2:])
    else:
        make(*sys.argv[1:])
