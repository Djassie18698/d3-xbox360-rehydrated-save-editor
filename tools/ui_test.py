"""Drives the editor window without showing it, on a copy of a save folder: adds a rare with a gem, follower gear,
sets level, Paragon and hardcore gold, duplicates, saves and reads the result back.

usage: ui_test.py <real user data root> <test root>"""
import os, shutil, sys, tkinter as tk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import editor
import items as it
import savegame as sg

real, root = sys.argv[1:3]
remembered = sg.load_settings().get('saves')
shutil.rmtree(root, ignore_errors=True)
shutil.copytree(real, root)
path = sg.find_save_dirs(root)[0]
tk_root = tk.Tk()
tk_root.withdraw()
try:
    app = editor.App(tk_root)
    app.open(path)
    data = app.data
    hero_row = next(i for i, (k, x) in enumerate(app.owner_rows) if k == 'hero' and x.name == 'Dean')
    app.owners.selection_clear(0, 'end')
    app.owners.selection_set(hero_row)
    app.show_owner()
    hero = app.current

    def add(name, slot, hireling=0, quality=None):
        info = next(i for i in data.items if i['name'] == name)
        c = hero.container
        sq = c.free_square(slot, 10, 6, data.height(info['gbid']), data) if slot == it.BACKPACK else 0
        item = sg.make_item(c, data, info, slot, sq, quality)
        item.hireling = hireling
        c.add(item)
        hero.dirty = True
        app.show_owner()
        return next(iid for iid, i in app.item_rows.items() if i.msg is item.msg)

    # A rare helm: socket affix + gem through the side panel, then Apply.
    iid = add('Helm_002', it.BACKPACK, quality=6)
    app.tree.selection_set(iid)
    app.show_item()
    print('rare name on creation:', app.name_label.cget('text'))
    app.pending_affixes.append(next(a['gbid'] for a in data.affixes if a['name'] == 'Sockets Helm I'))
    app.pending_gems.append(next(i['gbid'] for i in data.items if i['name'] == 'Amethyst_14'))
    app.refresh_pending()
    print('affix labels:', app.affix_list.get(0, 'end'))
    app.apply_item()
    add('Sword_1H_001', 65, hireling=1)
    app.level_var.set(42)
    app.set_level()
    app.unlock_followers()
    # Duplicate the helm: the copy gets gems of its own.
    helm_iid = next(iid for iid, i in app.item_rows.items() if data.item_name(i.gbid) == 'Leather Hood' and i.gems)
    app.tree.selection_set(helm_iid)
    app.duplicate()
    # Hardcore stash: gold and Paragon.
    hc_row = next(i for i, (k, x) in enumerate(app.owner_rows) if k == 'stash' and x == 1)
    app.owners.selection_clear(0, 'end')
    app.owners.selection_set(hc_row)
    app.show_owner()
    app.gold.set('777777')
    app.set_gold()
    app.paragon.set(12)
    app.set_paragon()
    print('stats column sample:', [app.tree.item(i)['values'][4] for i in app.tree.get_children()][:2])
    app.save.save()
finally:
    tk_root.destroy()
    if remembered:
        sg.store_settings(saves=remembered)

check = sg.SaveFolder(path)
h = next(x for x in check.heroes if x.name == 'Dean')
print('level', h.level, 'followers', h.msg.sub(4).sub(3).get(3))
for i in h.container.items:
    extra = []
    if i.gems:
        extra.append('gems %s' % [data.item_name(g.gbid) for g in i.gems])
    if i.slot == it.SOCKET:
        extra.append('in item %x' % i.socket_of)
    if i.rare_name:
        extra.append('name %s' % data.rare_name_text(data.by_gbid[i.gbid], i.rare_name))
    print('  %-22s %-22s %x %s' % (editor.where_label(i), data.item_name(i.gbid), i.id_low, ' '.join(extra)))
print('hardcore gold', check.account.get_gold(1), 'paragon', check.account.get_paragon(1), 'normal paragon', check.account.get_paragon(0))
