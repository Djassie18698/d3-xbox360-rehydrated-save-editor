"""Drives the editor's progress, account, bulk, copy and preset actions without showing the window, on a copy of a
save folder, saves and reads the result back.

usage: ui_test2.py <real user data root> <test root>"""
import os, shutil, sys, tempfile, tkinter as tk
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
    data, save = app.data, app.save

    def select(kind, test):
        row = next(i for i, (k, x) in enumerate(app.owner_rows) if k == kind and test(x))
        app.owners.selection_clear(0, 'end')
        app.owners.selection_set(row)
        app.show_owner()

    hero = save.heroes[0]
    select('hero', lambda x: x is hero)
    app.level_var.set(20)
    app.set_level()
    # Quests and difficulty, as the dialog returns them: unlock Inferno, start at Siegebreaker on Hell.
    siege = next(q for q in app.quests[2] if q['internal'] == 'TraverseBridge')
    hero.unlock_progress(3, app.quests)
    hero.start_at(2, 2, siege['sno'], siege['steps'][-1]['uid'])
    app.show_owner()
    print('hero label:', app.hero_label.cget('text'))
    # Account: stash tabs, artisans, hardcore.
    select('stash', lambda x: x == 0)
    app.tabs.set(3); app.set_tabs()
    for n, var in enumerate(app.artisan_vars):
        var.set(10); app.set_artisan(n)
    app.unlock_hardcore()
    # Bulk add every legendary ring into the stash, best gems into the backpack.
    print(app.add_many(editor.bulk_items(data, 'Legendary rings and amulets'), 1), 'jewelry added to the stash')
    select('hero', lambda x: x is hero)
    print(app.add_many(editor.bulk_items(data, 'Best gem of each kind (stacks)'), 50), 'gem stacks added')
    # A socketed rare dagger, saved as a preset, loaded back, and copied to the stash.
    c = hero.container
    dagger = sg.make_item(c, data, next(i for i in data.items if i['name'] == 'Dagger_001'), it.BACKPACK,
                          app.place_in(c, it.BACKPACK, 2), 6)
    c.add(dagger)
    c.set_gems(dagger, [next(i['gbid'] for i in data.items if i['name'] == 'Ruby_14')])
    app.show_owner()
    iid = next(k for k, v in app.item_rows.items() if v.msg is dagger.msg)
    app.tree.selection_set(iid)
    app.show_item()
    preset = os.path.join(tempfile.gettempdir(), 'ui_test2.d3item')
    app.save_preset(preset)
    app.load_preset([preset])
    app.copy_item(dagger, 'stash', 0)
    # A dead hardcore copy of the hero, revived through the button.
    dead = save.clone_hero(hero, 'Ghost')
    dead.digest.set(6, hero.flags | sg.HARDCORE_FLAG | sg.DEAD_FLAG)
    app.fill_owners(0)
    select('hero', lambda x: x is dead)
    print('owner row:', app.owners.get(app.owners.curselection()[0]), 'revive enabled:', 'disabled' not in app.revive_btn.state())
    app.revive()
    app.save.save()
finally:
    tk_root.destroy()
    if remembered:
        sg.store_settings(saves=remembered)

check = sg.SaveFolder(path)
h = next(x for x in check.heroes if x.id_low == hero.id_low)
print('hero', h.name, 'level', h.level, 'xp next', h.attribute(sg.EXPERIENCE_NEXT_KEY), 'unlocked', h.highest_difficulty,
      'start', h.last_played, 'history', len(h.digest.subs(8)), 'saved quests', len(h.msg.subs(5)))
items = h.container.items
for i in items:
    if i.slot == it.BACKPACK:
        print('  backpack %-24s x%d gems %s' % (data.item_name(i.gbid), i.stack, [data.item_name(g.gbid) for g in i.gems]))
print('  socket items', [(hex(i.socket_of), data.item_name(i.gbid)) for i in items if i.slot == it.SOCKET])
ids = [i.id_low for i in items] + [e.sub(1).get(2) for i in items for e in i.gen.subs(13)]
print('  ids unique:', len(ids) == len(set(i for i in ids if i)), 'gem ids match socket items:',
      sorted(e.sub(1).get(2) for i in items for e in i.gen.subs(13)) == sorted(i.id_low for i in items if i.slot == it.SOCKET))
a = check.account
stash = [i for i in a.stash(0).items if i.slot == it.STASH]
print('stash items', len(stash), 'max square', max(i.square for i in stash), 'tabs', a.get_stash_tabs(), 'artisans',
      [a.get_artisan(n) for n in range(2)], 'hardcore unlocked', a.hardcore_unlocked)
g = next(x for x in check.heroes if x.name == 'Ghost')
print('Ghost flags %x dead %s hardcore %s' % (g.flags, g.dead, g.hardcore))
