"""Prepares a copy of a Rehydrated user data folder for an in-game test of what the editor writes. Load the copy
with Rehydrated (--user_data_root=<test root>), check the hero in game, leave the game so it saves, then run
`ingame_test.py check <test root>` to see what the game kept.

usage: ingame_test.py <case> <real user data root> <test root> [hero name]
       ingame_test.py check <test root> [hero name]
cases: basic   normal items in the backpack and equipment slots, a legendary in the stash, 123456 gold
       affix   a magic ring, a rare helm and a magic dagger with chosen affixes
       crazy   level 60 hero with a dagger of 29 stacked top-tier affixes in the main hand
       legend  level 60 hero with The Barber (legendary dagger) in the main hand, and two PC-only items
       sockets level 60 hero with a dagger of 3 sockets (the most the game allows), each holding a Radiant Star Ruby, in the main hand
       progress level 35, everything unlocked up to Inferno, start at Siegebreaker on Hell, 3 stash tabs, artisans 10,
               hardcore unlocked, rings on stash tabs 2 and 3, and two hardcore copies of another hero (dead, revived)
       extras  Paragon 50, a socketed dagger with a Radiant Star Ruby, a named rare helm, the Templar in full gear
               (follower slots 64-69) and a ring in the hardcore stash
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


def add(hero, name, slot, quality=None, affixes=(), hireling=0):
    c = hero.container
    info = ITEM[name]
    if slot == it.BACKPACK:
        square = c.free_square(slot, sg.BACKPACK_W, sg.BACKPACK_H, data.height(info['gbid']), data)
    else:
        square = 0
        for old in [i for i in c.items if i.slot == slot and i.hireling == hireling]:
            old.slot, old.square = it.BACKPACK, c.free_square(it.BACKPACK, sg.BACKPACK_W, sg.BACKPACK_H, data.height(old.gbid), data)
    item = sg.make_item(c, data, info, slot, square, quality, [AFFIX[a] for a in affixes])
    item.hireling = hireling
    c.add(item)
    hero.dirty = True
    return item


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
    elif case == 'legend':
        hero.level = 60
        add(hero, 'Unique_Dagger_003', 4)
        add(hero, 'Unique_Sword_1H_008', it.BACKPACK)   # not in the console data
        add(hero, 'Offhand_001', it.BACKPACK)          # not in the console data
    elif case == 'sockets':
        hero.level = 60
        dagger = add(hero, 'Dagger_001', 4, 3, ['Sockets I'] * 3)
        hero.container.set_gems(dagger, [ITEM['Ruby_14']['gbid']] * 3)
    elif case == 'extras':
        hero.level = 60
        save.account.set_paragon(50)
        dagger = add(hero, 'Dagger_001', 4, 3, ['Sockets I'])
        hero.container.set_gems(dagger, [ITEM['Ruby_14']['gbid']])
        helm = add(hero, 'Helm_002', it.BACKPACK, 6, ['Str 6', 'Vit 6', 'ArcaneResist I', 'Experience I'])
        helm.rare_name = data.rare_name_choices(ITEM['Helm_002'], helm.affixes)[0][1]
        hero.unlock_followers()
        for slot, name in ((65, 'Sword_1H_001'), (64, 'Shield_001'), (66, 'Templar_Special_001'), (67, 'Amulet01'),
                           (68, 'Ring_01'), (69, 'Ring_02')):
            add(hero, name, slot, hireling=1)
        hc = save.account.stash(1)
        hc.add(sg.make_item(hc, data, ITEM['Ring_02'], it.STASH, 0))
        save.account.dirty = True
    elif case == 'progress':
        hero.level = 35
        quests = sg.load_quests()
        hero.unlock_progress(3, quests)
        siege = next(q for q in quests[2] if q['internal'] == 'TraverseBridge')
        hero.start_at(2, 2, siege['sno'], -1)          # Hell, Act III, Siegebreaker
        acct = save.account
        acct.set_stash_tabs(3)
        for a in range(len(sg.ARTISANS)):
            acct.set_artisan(a, sg.MAX_ARTISAN)
        acct.unlock_hardcore()
        sc = acct.container
        for square in (70, 140):                     # first square of the second and third tab
            sc.add(sg.make_item(sc, data, ITEM['Ring_02'], it.STASH, square))
        # Hardcore copies of another hero: one dead, one revived.
        other = next(h for h in save.heroes if h is not hero and h.msg.sub(3).subs(2))
        for name, flags, revive in (('HcDead', sg.HARDCORE_FLAG | sg.DEAD_FLAG, False), ('HcAlive', sg.HARDCORE_FLAG | sg.DEAD_FLAG, True)):
            copy = save.clone_hero(other, name)
            copy.digest.set(6, other.flags | flags)
            if revive:
                copy.revive()
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
        who = it.HIRELING_NAMES.get(i.hireling, i.hireling) + ' ' if i.hireling else ''
        extra = ''
        if i.gems:
            extra += ' gems: %s' % [data.item_name(g.gbid) for g in i.gems]
        if i.rare_name:
            extra += ' name: %s' % data.rare_name_text(data.by_gbid.get(i.gbid, {}), i.rare_name)
        print('  %-24s %-26s %-10s %s%s' % (who + str(it.SLOT_NAMES.get(i.slot, i.slot)), data.item_name(i.gbid),
                                            it.QUALITY_NAMES.get(i.quality, i.quality),
                                            ', '.join('%s x%d' % kv if kv[1] > 1 else kv[0] for kv in affixes.items()), extra))
    for p in save.account.partitions:
        print('  %s stash: %s; gold %d; paragon %d' % (sg.PARTITION_NAMES[p], [data.item_name(i.gbid) for i in save.account.stash(p).items if i.slot == it.STASH],
                                                      save.account.get_gold(p), save.account.get_paragon(p)))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if sys.argv[1] == 'check':
        check(*sys.argv[2:])
    else:
        make(*sys.argv[1:])
