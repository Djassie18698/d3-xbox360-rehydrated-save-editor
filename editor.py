"""Diablo III save editor for the original Xbox 360 release (2013) running in Rehydrated: items, affixes, gems, rare
names, follower gear, item presets, gold, hero level, quest progress, Paragon level, artisans and stash tabs."""
import json, os, random, sys, tkinter as tk
from tkinter import ttk, messagebox, filedialog
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import d3save
import items as it
import savegame as sg

EQUIP_SLOTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
QUALITIES = [(1, 'Normal'), (3, 'Magic'), (6, 'Rare'), (9, 'Legendary')]
AFFIX_KINDS = {0: 'requirement', 1: 'rare only', 2: 'legendary', 3: ''}
MAX_AFFIXES = 32   # the affix message the server sends holds 32; more and the game disconnects
MAX_SOCKETS = 3    # the client's socket attributes hold 0-3; with more gems than that it disconnects
STACKABLE = ('HealthPotion', 'Gem', 'CraftingReagent', 'Dye')


def quality_label(q):
    return it.QUALITY_NAMES.get(q, str(q))


def where_label(item):
    if item.slot in (it.BACKPACK, it.STASH):
        w = sg.BACKPACK_W if item.slot == it.BACKPACK else sg.STASH_W
        return '%s %d,%d' % (it.SLOT_NAMES[item.slot], item.square % w + 1, item.square // w + 1)
    if item.hireling:
        return '%s: %s' % (it.HIRELING_NAMES.get(item.hireling, 'Follower'), it.FOLLOWER_SLOTS.get(item.slot, item.slot))
    return it.SLOT_NAMES.get(item.slot, 'Slot %d' % item.slot)


class SearchList(tk.Toplevel):
    """A searchable list to pick one entry from: rows are (columns..., value)."""

    def __init__(self, app, title, headings, rows, extra=None):
        super().__init__(app.root)
        self.result, self.rows = None, rows
        self.title(title)
        self.geometry('640x520')
        self.transient(app.root)
        f = ttk.Frame(self, padding=8)
        f.pack(fill='both', expand=True)
        top = ttk.Frame(f)
        top.pack(fill='x')
        ttk.Label(top, text='Search').pack(side='left')
        self.query = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.query, width=30)
        e.pack(side='left', padx=6)
        e.focus_set()
        self.tree = ttk.Treeview(f, columns=[h for h, _ in headings], show='headings', selectmode='browse')
        for h, w in headings:
            self.tree.heading(h, text=h)
            self.tree.column(h, width=w, anchor='w')
        self.tree.pack(fill='both', expand=True, pady=8)
        self.tree.bind('<Double-1>', lambda e: self.ok())
        if extra:
            ttk.Label(f, text=extra, foreground='#777').pack(side='left')
        ttk.Button(f, text='OK', command=self.ok).pack(side='right')
        self.query.trace_add('write', lambda *_: self.refresh())
        self.refresh()
        self.grab_set()

    def refresh(self):
        q = self.query.get().lower()
        self.tree.delete(*self.tree.get_children())
        self.shown = {}
        for row in self.rows:
            if not q or any(q in str(c).lower() for c in row[:-1]):
                self.shown[self.tree.insert('', 'end', values=row[:-1])] = row[-1]
                if len(self.shown) >= 3000:
                    break

    def ok(self):
        sel = self.tree.selection()
        if sel:
            self.result = self.shown[sel[0]]
            self.destroy()


class AddItemDialog(tk.Toplevel):
    """Search the game's item list and choose where the new item goes."""

    def __init__(self, app, hero_mode):
        super().__init__(app.root)
        self.app, self.result = app, None
        self.title('Add item')
        self.geometry('780x560')
        self.transient(app.root)
        top = ttk.Frame(self, padding=8)
        top.pack(fill='both', expand=True)

        row = ttk.Frame(top)
        row.pack(fill='x')
        ttk.Label(row, text='Search').pack(side='left')
        self.query = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.query, width=30)
        e.pack(side='left', padx=6)
        e.focus_set()
        self.legendary_only = tk.BooleanVar()
        ttk.Checkbutton(row, text='Legendaries only', variable=self.legendary_only, command=self.refresh).pack(side='left', padx=6)
        ttk.Label(row, text='Type').pack(side='left', padx=(12, 0))
        self.type_filter = tk.StringVar(value='(all)')
        types = sorted({i['typeDisplay'] for i in app.data.items if i.get('console', True)})
        ttk.Combobox(row, textvariable=self.type_filter, values=['(all)'] + types, width=22, state='readonly').pack(side='left', padx=6)
        self.type_filter.trace_add('write', lambda *_: self.refresh())
        self.query.trace_add('write', lambda *_: self.refresh())

        cols = ('name', 'type', 'level', 'internal')
        self.tree = ttk.Treeview(top, columns=cols, show='headings', selectmode='browse')
        for c, w, t in [('name', 260, 'Name'), ('type', 140, 'Type'), ('level', 60, 'Level'), ('internal', 220, 'Internal name')]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='w')
        self.tree.pack(fill='both', expand=True, pady=8)
        self.tree.bind('<Double-1>', lambda e: self.ok())

        dest = ttk.Frame(top)
        dest.pack(fill='x')
        ttk.Label(dest, text='Put it in').pack(side='left')
        self.places = {}
        if hero_mode:
            self.places['Backpack'] = (it.BACKPACK, 0)
            for s in EQUIP_SLOTS:
                self.places[it.SLOT_NAMES[s] + ' (equip)'] = (s, 0)
            for h in (1, 2, 3):
                for s, name in it.FOLLOWER_SLOTS.items():
                    self.places['%s: %s' % (it.HIRELING_NAMES[h], name)] = (s, h)
        else:
            self.places['Stash'] = (it.STASH, 0)
        self.place = tk.StringVar(value=next(iter(self.places)))
        ttk.Combobox(dest, textvariable=self.place, values=list(self.places), state='readonly', width=24).pack(side='left', padx=6)
        ttk.Label(dest, text='Quality').pack(side='left', padx=(12, 0))
        self.quality = tk.StringVar(value='(default)')
        ttk.Combobox(dest, textvariable=self.quality, values=['(default)'] + [n for _, n in QUALITIES], state='readonly', width=12).pack(side='left', padx=6)
        ttk.Label(dest, text='Amount').pack(side='left', padx=(12, 0))
        self.count = tk.IntVar(value=1)
        ttk.Spinbox(dest, from_=1, to=100, textvariable=self.count, width=5).pack(side='left', padx=6)
        ttk.Button(dest, text='Add', command=self.ok).pack(side='right')
        self.refresh()
        self.grab_set()

    def refresh(self):
        q = self.query.get().lower()
        t = self.type_filter.get()
        self.tree.delete(*self.tree.get_children())
        self.shown = {}
        for info in sorted(self.app.data.items, key=lambda i: (i['display'].lower(), i['level'])):
            if not info.get('console', True):
                continue   # PC-only item: the console game drops it
            if self.legendary_only.get() and not info['legendary']:
                continue
            if t != '(all)' and info['typeDisplay'] != t:
                continue
            if q and q not in info['display'].lower() and q not in info['name'].lower():
                continue
            iid = self.tree.insert('', 'end', values=(info['display'], info['typeDisplay'], info['level'], info['name']),
                                   tags=('set',) if info.get('set') else ('legendary',) if info['legendary'] else ())
            self.shown[iid] = info
        self.tree.tag_configure('legendary', foreground='#b35c00')
        self.tree.tag_configure('set', foreground='#1f8a1f')

    def ok(self):
        sel = self.tree.selection()
        if not sel:
            return
        slot, hireling = self.places[self.place.get()]
        quality = dict((n, q) for q, n in QUALITIES).get(self.quality.get())
        self.result = (self.shown[sel[0]], slot, hireling, quality, max(1, self.count.get()))
        self.destroy()


class AffixDialog(tk.Toplevel):
    """Pick an affix the game can roll on this item; "Show all" also offers ones it never would."""

    def __init__(self, app, info, taken):
        super().__init__(app.root)
        self.app, self.info, self.result = app, info, None
        self.taken = {app.data.affix_by_gbid[g]['family'] for g in taken if g in app.data.affix_by_gbid}
        self.title('Add affix')
        self.geometry('760x540')
        self.transient(app.root)
        f = ttk.Frame(self, padding=8)
        f.pack(fill='both', expand=True)
        row = ttk.Frame(f)
        row.pack(fill='x')
        ttk.Label(row, text='Search').pack(side='left')
        self.query = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.query, width=30)
        e.pack(side='left', padx=6)
        e.focus_set()
        self.everything = tk.BooleanVar()
        ttk.Checkbutton(row, text='Show all affixes (modded)', variable=self.everything, command=self.refresh).pack(side='left', padx=6)
        cols = ('effect', 'name', 'level', 'kind')
        self.tree = ttk.Treeview(f, columns=cols, show='headings', selectmode='browse')
        for c, w, t in [('effect', 360, 'Effect'), ('name', 190, 'Affix'), ('level', 60, 'Level'), ('kind', 80, '')]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='w')
        self.tree.pack(fill='both', expand=True, pady=8)
        self.tree.bind('<Double-1>', lambda e: self.ok())
        ttk.Label(f, text='Normally an item holds one affix per family. With "Show all" checked, any affix can be\n'
                  'added, also several times: copies stack (up to %d affixes per item).' % MAX_AFFIXES,
                  foreground='#777').pack(side='left')
        ttk.Button(f, text='Add', command=self.ok).pack(side='right')
        self.copies = tk.IntVar(value=1)
        ttk.Spinbox(f, from_=1, to=MAX_AFFIXES, textvariable=self.copies, width=4).pack(side='right', padx=6)
        ttk.Label(f, text='Copies').pack(side='right')
        self.query.trace_add('write', lambda *_: self.refresh())
        self.refresh()
        self.grab_set()

    def refresh(self):
        q = self.query.get().lower()
        everything = self.everything.get()
        self.tree.delete(*self.tree.get_children())
        self.shown = {}
        for a in sorted(self.app.data.affixes_for(self.info, everything), key=lambda a: (a['name'].lower(), a['level'])):
            effect = '; '.join(self.app.data.affix_effects(a['gbid']))
            if (q in a['name'].lower() or q in effect.lower()) and (everything or a['family'] not in self.taken):
                iid = self.tree.insert('', 'end', values=(effect, a['name'], a['level'], AFFIX_KINDS.get(a['kind'], '')))
                self.shown[iid] = a

    def ok(self):
        sel = self.tree.selection()
        if sel:
            copies = max(1, self.copies.get()) if self.everything.get() else 1
            self.result = [self.shown[sel[0]]['gbid']] * copies
            self.destroy()


class StatDialog(tk.Toplevel):
    """Type the total a stat should have; the editor stacks affixes to get there."""

    def __init__(self, app, affixes, stats):
        super().__init__(app.root)
        self.app, self.affixes, self.result = app, affixes, None
        self.stats = {sg.describe_stat(st, app.data.stat_text): st for st in stats}
        self.title('Set stat')
        self.transient(app.root)
        f = ttk.Frame(self, padding=10)
        f.pack(fill='both', expand=True)
        self.stat = tk.StringVar(value=next(iter(self.stats)))
        ttk.Label(f, text='Stat').grid(row=0, column=0, sticky='w')
        ttk.Combobox(f, textvariable=self.stat, values=list(self.stats), state='readonly', width=50).grid(row=0, column=1, sticky='w', padx=6)
        self.now = ttk.Label(f, text='')
        self.now.grid(row=1, column=1, sticky='w', padx=6, pady=4)
        ttk.Label(f, text='Total').grid(row=2, column=0, sticky='w')
        self.value = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.value, width=12)
        e.grid(row=2, column=1, sticky='w', padx=6)
        e.focus_set()
        e.bind('<Return>', lambda _: self.ok())
        ttk.Label(f, text='The game rolls every number from its own affix tables, so the editor stacks copies of the\n'
                  'affix for this stat until the total is at least this much (the copies\' rolls can add a bit more).\n'
                  '0 takes the stat off. At most %d affixes per item.' % MAX_AFFIXES,
                  foreground='#777').grid(row=3, column=0, columnspan=2, sticky='w', pady=6)
        ttk.Button(f, text='Set', command=self.ok).grid(row=4, column=1, sticky='e')
        self.stat.trace_add('write', lambda *_: self.show())
        self.show()
        self.grab_set()

    def show(self):
        st = self.stats[self.stat.get()]
        scale = self.app.data.stat_scale(st)
        low, high = self.app.data.stat_total(self.affixes, st)
        self.now.config(text='Now %s' % (sg._number(low * scale) if low == high else
                                         '%s-%s' % (sg._number(low * scale), sg._number(high * scale))), foreground='#777')
        if not self.value.get():
            self.value.set(sg._number(low * scale))

    def ok(self):
        try:
            value = float(self.value.get().replace(',', '.').rstrip('%'))
        except ValueError:
            return
        st = self.stats[self.stat.get()]
        self.result = (st, value / self.app.data.stat_scale(st))
        self.destroy()


class ProgressDialog(tk.Toplevel):
    """Unlocks difficulties, acts and quests for a hero and picks where the next game starts."""

    def __init__(self, app, hero):
        super().__init__(app.root)
        self.app, self.hero, self.result = app, hero, None
        self.quests = app.quests
        self.title('Quest progress - %s' % hero.name)
        self.transient(app.root)
        f = ttk.Frame(self, padding=10)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text='Unlock', font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(f, text='All acts and quests up to').grid(row=1, column=0, sticky='w')
        self.unlock = tk.StringVar(value=sg.DIFFICULTIES[max(hero.highest_difficulty, 0)])
        ttk.Combobox(f, textvariable=self.unlock, values=sg.DIFFICULTIES, state='readonly', width=12).grid(row=1, column=1, sticky='w', padx=6)
        self.do_unlock = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text='Unlock', variable=self.do_unlock).grid(row=1, column=2, sticky='w')
        ttk.Label(f, text='Every story quest counts as played on that difficulty and the ones below, and all\n'
                  'waypoints are active.', foreground='#777').grid(row=2, column=0, columnspan=3, sticky='w', pady=(0, 8))

        ttk.Label(f, text='Next game starts at', font=('Segoe UI', 10, 'bold')).grid(row=3, column=0, columnspan=3, sticky='w')
        diff, act, sno, step = hero.last_played
        self.diff = tk.StringVar(value=sg.DIFFICULTIES[diff] if 0 <= diff < 4 else sg.DIFFICULTIES[0])
        self.act = tk.StringVar()
        self.quest = tk.StringVar()
        self.step = tk.StringVar()
        rows = [('Difficulty', self.diff, sg.DIFFICULTIES, 14), ('Act', self.act, ['Act %s' % r for r in ('I', 'II', 'III', 'IV')], 14),
                ('Quest', self.quest, [], 40), ('Checkpoint', self.step, [], 60)]
        self.boxes = {}
        for n, (label, var, values, width) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=4 + n, column=0, sticky='w')
            box = ttk.Combobox(f, textvariable=var, values=values, state='readonly', width=width)
            box.grid(row=4 + n, column=1, columnspan=2, sticky='w', padx=6, pady=2)
            self.boxes[label] = box
        self.act.trace_add('write', lambda *_: self.fill_quests())
        self.quest.trace_add('write', lambda *_: self.fill_steps())
        found = next(((a, q) for a, quests in enumerate(self.quests) for q in quests if q['sno'] == sno), None)
        self.act.set(self.boxes['Act']['values'][found[0] if found else max(0, min(act, 3))])
        if found:
            self.quest.set(found[1]['name'])
            self.step.set(next((st['text'] for st in found[1]['steps'] if st['uid'] == step), found[1]['steps'][0]['text']))
        ttk.Label(f, text='In PC proxy mode the game starts here ("Continue"); on the console side it is the\n'
                  '"Resume" quest, in the town of its act. A difficulty above the unlocked ones is unlocked too.',
                  foreground='#777'
                  ).grid(row=8, column=0, columnspan=3, sticky='w', pady=6)
        ttk.Button(f, text='OK', command=self.ok).grid(row=9, column=2, sticky='e')
        self.grab_set()

    def act_index(self):
        values = list(self.boxes['Act']['values'])
        return values.index(self.act.get()) if self.act.get() in values else 0

    def fill_quests(self):
        names = [q['name'] for q in self.quests[self.act_index()]]
        self.boxes['Quest']['values'] = names
        if self.quest.get() not in names:
            self.quest.set(names[0] if names else '')

    def chosen_quest(self):
        return next((q for q in self.quests[self.act_index()] if q['name'] == self.quest.get()), None)

    def fill_steps(self):
        q = self.chosen_quest()
        texts = [st['text'] for st in q['steps']] if q else []
        self.boxes['Checkpoint']['values'] = texts
        if self.step.get() not in texts:
            self.step.set(texts[0] if texts else '')

    def ok(self):
        q = self.chosen_quest()
        if not q:
            return
        step = next(st['uid'] for st in q['steps'] if st['text'] == self.step.get())
        unlock = sg.DIFFICULTIES.index(self.unlock.get()) if self.do_unlock.get() else None
        self.result = (unlock, sg.DIFFICULTIES.index(self.diff.get()), self.act_index(), q['sno'], step, q['name'])
        self.destroy()


BULK_KINDS = {
    'Every legendary': lambda i: i['legendary'],
    'Legendary weapons': lambda i: i['legendary'] and i['table'] == 'Items_Legendary_Weapons',
    'Legendary armor': lambda i: i['legendary'] and i['table'] == 'Items_Legendary' and i['type'] not in ('Ring', 'Amulet'),
    'Legendary rings and amulets': lambda i: i['legendary'] and i['type'] in ('Ring', 'Amulet'),
    'Best gem of each kind (stacks)': None,
    'Crafting materials (stacks)': lambda i: i['type'] == 'CraftingReagent',
    'Dyes (stacks)': lambda i: i['type'] == 'Dye',
}


def bulk_items(data, kind, type_display='(all)', level=70):
    """The items a bulk add puts in, highest level first."""
    pool = [i for i in data.items if i.get('console', True) and i['level'] <= level]
    test = BULK_KINDS[kind]
    if test is None:   # gems: the best of each kind (Ruby, Emerald, ...) up to the level
        best = {}
        for i in pool:
            if i['type'] == 'Gem':
                gem = i['name'].split('_')[0]
                if gem not in best or i['level'] > best[gem]['level']:
                    best[gem] = i
        chosen = list(best.values())
    else:
        chosen = [i for i in pool if test(i)]
    if type_display != '(all)':
        chosen = [i for i in chosen if i['typeDisplay'] == type_display]
    return sorted(chosen, key=lambda i: (-i['level'], i['display']))


class BulkDialog(tk.Toplevel):
    """Adds many items at once until the stash or backpack is full."""

    def __init__(self, app, hero_mode):
        super().__init__(app.root)
        self.app, self.result = app, None
        self.title('Bulk add')
        self.transient(app.root)
        f = ttk.Frame(self, padding=10)
        f.pack(fill='both', expand=True)
        self.kind = tk.StringVar(value=next(iter(BULK_KINDS)))
        self.type = tk.StringVar(value='(all)')
        self.level = tk.IntVar(value=70)
        self.stack = tk.IntVar(value=100)
        ttk.Label(f, text='Add').grid(row=0, column=0, sticky='w')
        ttk.Combobox(f, textvariable=self.kind, values=list(BULK_KINDS), state='readonly', width=30).grid(row=0, column=1, sticky='w', padx=6)
        types = sorted({i['typeDisplay'] for i in app.data.items if i['legendary'] and i.get('console', True)})
        ttk.Label(f, text='Only type').grid(row=1, column=0, sticky='w')
        ttk.Combobox(f, textvariable=self.type, values=['(all)'] + types, state='readonly', width=30).grid(row=1, column=1, sticky='w', padx=6)
        ttk.Label(f, text='Up to item level').grid(row=2, column=0, sticky='w')
        ttk.Spinbox(f, from_=1, to=70, textvariable=self.level, width=6).grid(row=2, column=1, sticky='w', padx=6)
        ttk.Label(f, text='Stack size').grid(row=3, column=0, sticky='w')
        ttk.Spinbox(f, from_=1, to=1000, textvariable=self.stack, width=6).grid(row=3, column=1, sticky='w', padx=6)
        where = 'backpack' if hero_mode else 'stash'
        ttk.Label(f, text='Into the %s, highest level first, until it is full.\nLegendaries get their own affix rolls.' % where,
                  foreground='#777').grid(row=4, column=0, columnspan=2, sticky='w', pady=6)
        ttk.Button(f, text='Add', command=self.ok).grid(row=5, column=1, sticky='e')
        self.grab_set()

    def ok(self):
        try:
            level, stack = int(self.level.get()), max(1, int(self.stack.get()))
        except (ValueError, tk.TclError):
            return
        self.result = (bulk_items(self.app.data, self.kind.get(), self.type.get(), level), stack)
        self.destroy()


class App:
    def __init__(self, root):
        self.root = root
        root.title('Diablo III Save Editor - Xbox 360 (2013) saves in Rehydrated')
        root.geometry('1280x720')
        self.data = sg.GameData()
        self.quests = sg.load_quests()
        self.save = None
        self.current = None      # Hero, or the Account for a stash
        self.partition = 0       # the stash partition shown when the account is selected
        self.owner_rows = []
        self.item_rows = {}

        bar = ttk.Frame(root, padding=6)
        bar.pack(fill='x')
        ttk.Button(bar, text='Open folder...', command=self.choose).pack(side='left')
        self.path_label = ttk.Label(bar, text='')
        self.path_label.pack(side='left', padx=8)
        ttk.Button(bar, text='Save', command=self.do_save).pack(side='right')
        ttk.Button(bar, text='Reload', command=self.reload).pack(side='right', padx=6)

        body = ttk.PanedWindow(root, orient='horizontal')
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body, padding=6)
        body.add(left, weight=1)
        ttk.Label(left, text='Heroes and stash').pack(anchor='w')
        self.owners = tk.Listbox(left, exportselection=False, width=32)
        self.owners.pack(fill='both', expand=True)
        self.owners.bind('<<ListboxSelect>>', lambda e: self.show_owner())

        acct = ttk.LabelFrame(left, text='Account', padding=6)
        acct.pack(fill='x', pady=(6, 0))
        self.acct_label = ttk.Label(acct, text='')
        self.acct_label.grid(row=0, column=0, columnspan=3, sticky='w')
        self.gold = tk.StringVar()
        ttk.Label(acct, text='Gold').grid(row=1, column=0, sticky='w')
        ttk.Entry(acct, textvariable=self.gold, width=14).grid(row=1, column=1, sticky='w', padx=4)
        ttk.Button(acct, text='Set', command=self.set_gold).grid(row=1, column=2)
        self.paragon = tk.IntVar()
        ttk.Label(acct, text='Paragon').grid(row=2, column=0, sticky='w')
        ttk.Spinbox(acct, from_=0, to=sg.MAX_PARAGON, textvariable=self.paragon, width=6).grid(row=2, column=1, sticky='w', padx=4)
        ttk.Button(acct, text='Set', command=self.set_paragon).grid(row=2, column=2)
        self.tabs = tk.IntVar()
        ttk.Label(acct, text='Stash tabs').grid(row=3, column=0, sticky='w')
        ttk.Spinbox(acct, from_=1, to=3, textvariable=self.tabs, width=6).grid(row=3, column=1, sticky='w', padx=4)
        ttk.Button(acct, text='Set', command=self.set_tabs).grid(row=3, column=2)
        self.artisan_vars = []
        for n, name in enumerate(sg.ARTISANS):
            var = tk.IntVar()
            self.artisan_vars.append(var)
            ttk.Label(acct, text=name).grid(row=4 + n, column=0, sticky='w')
            ttk.Spinbox(acct, from_=0, to=sg.MAX_ARTISAN, textvariable=var, width=6).grid(row=4 + n, column=1, sticky='w', padx=4)
            ttk.Button(acct, text='Set', command=lambda n=n: self.set_artisan(n)).grid(row=4 + n, column=2)
        self.hardcore_btn = ttk.Button(acct, text='Unlock hardcore heroes', command=self.unlock_hardcore)
        self.hardcore_btn.grid(row=4 + len(sg.ARTISANS), column=0, columnspan=3, sticky='w', pady=(4, 0))

        herof = ttk.LabelFrame(left, text='Hero', padding=6)
        herof.pack(fill='x', pady=(6, 0))
        ttk.Label(herof, text='Level').grid(row=0, column=0, sticky='w')
        self.level_var = tk.IntVar(value=1)
        self.level_spin = ttk.Spinbox(herof, from_=1, to=sg.MAX_LEVEL, textvariable=self.level_var, width=6)
        self.level_spin.grid(row=0, column=1, sticky='w', padx=4)
        self.level_btn = ttk.Button(herof, text='Set', command=self.set_level)
        self.level_btn.grid(row=0, column=2)
        self.followers_btn = ttk.Button(herof, text='Unlock followers', command=self.unlock_followers)
        self.followers_btn.grid(row=1, column=0, columnspan=3, sticky='w', pady=(4, 0))
        self.progress_btn = ttk.Button(herof, text='Quests and difficulty...', command=self.edit_progress)
        self.progress_btn.grid(row=2, column=0, columnspan=3, sticky='w', pady=(4, 0))
        self.revive_btn = ttk.Button(herof, text='Revive (hardcore)', command=self.revive)
        self.revive_btn.grid(row=3, column=0, columnspan=3, sticky='w', pady=(4, 0))
        self.hero_label = ttk.Label(herof, text='', foreground='#777', wraplength=240)
        self.hero_label.grid(row=4, column=0, columnspan=3, sticky='w')

        mid = ttk.Frame(body, padding=6)
        body.add(mid, weight=4)
        cols = ('where', 'name', 'type', 'quality', 'affixes')
        self.tree = ttk.Treeview(mid, columns=cols, show='headings', selectmode='browse')
        for c, w, t in [('where', 150, 'Where'), ('name', 220, 'Item'), ('type', 110, 'Type'), ('quality', 80, 'Quality'), ('affixes', 330, 'Stats')]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='w')
        self.tree.pack(fill='both', expand=True)
        self.tree.tag_configure('legendary', foreground='#b35c00')
        self.tree.tag_configure('set', foreground='#1f8a1f')
        self.tree.tag_configure('rare', foreground='#9a7d00')
        self.tree.tag_configure('magic', foreground='#2a5bd7')
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.show_item())
        btns = ttk.Frame(mid)
        btns.pack(fill='x', pady=6)
        ttk.Button(btns, text='Add item...', command=self.add_item).pack(side='left')
        ttk.Button(btns, text='Duplicate', command=self.duplicate).pack(side='left', padx=6)
        ttk.Button(btns, text='Delete', command=self.delete).pack(side='left')
        ttk.Button(btns, text='Bulk add...', command=self.bulk_add).pack(side='left', padx=(18, 0))
        ttk.Button(btns, text='Copy to...', command=self.copy_to).pack(side='left', padx=6)
        ttk.Button(btns, text='Save preset...', command=self.save_preset).pack(side='left')
        ttk.Button(btns, text='Load preset...', command=self.load_preset).pack(side='left', padx=6)

        right = ttk.LabelFrame(body, text='Selected item', padding=8)
        body.add(right, weight=2)
        self.item_title = ttk.Label(right, text='', font=('Segoe UI', 11, 'bold'), wraplength=320)
        self.item_title.pack(anchor='w')
        grid = ttk.Frame(right)
        grid.pack(fill='x', pady=6)
        self.q_var, self.stack_var, self.dur_var = tk.StringVar(), tk.IntVar(), tk.IntVar()
        ttk.Label(grid, text='Quality').grid(row=0, column=0, sticky='w')
        ttk.Combobox(grid, textvariable=self.q_var, values=[n for _, n in QUALITIES], state='readonly', width=14).grid(row=0, column=1, sticky='w')
        ttk.Label(grid, text='Stack').grid(row=1, column=0, sticky='w')
        ttk.Spinbox(grid, from_=0, to=1000000000, textvariable=self.stack_var, width=14).grid(row=1, column=1, sticky='w')
        ttk.Label(grid, text='Durability').grid(row=2, column=0, sticky='w')
        ttk.Spinbox(grid, from_=0, to=100000, textvariable=self.dur_var, width=14).grid(row=2, column=1, sticky='w')

        ttk.Label(right, text='Affixes').pack(anchor='w')
        self.affix_list = tk.Listbox(right, height=8)
        self.affix_list.pack(fill='both', expand=True)
        self.affix_list.bind('<Double-1>', lambda e: self.edit_stat())
        ab = ttk.Frame(right)
        ab.pack(fill='x', pady=4)
        ttk.Button(ab, text='Add affix...', command=self.add_affix).pack(side='left')
        ttk.Button(ab, text='Remove', command=self.remove_affix).pack(side='left', padx=6)
        ttk.Button(ab, text='Random', command=self.random_affixes).pack(side='left')

        nf = ttk.Frame(right)
        nf.pack(fill='x', pady=(6, 0))
        ttk.Label(nf, text='Rare name').pack(side='left')
        self.name_label = ttk.Label(nf, text='', foreground='#9a7d00')
        self.name_label.pack(side='left', padx=6)
        nb = ttk.Frame(right)
        nb.pack(fill='x', pady=2)
        ttk.Button(nb, text='Choose name...', command=self.choose_name).pack(side='left')
        ttk.Button(nb, text='Random name', command=self.random_name).pack(side='left', padx=6)

        sf = ttk.Frame(right)
        sf.pack(fill='x', pady=(6, 0))
        self.gem_label = ttk.Label(sf, text='Gems')
        self.gem_label.pack(side='left')
        ttk.Button(sf, text='Set', command=self.set_sockets, width=5).pack(side='right')
        self.sockets_var = tk.IntVar()
        ttk.Spinbox(sf, from_=0, to=MAX_SOCKETS, textvariable=self.sockets_var, width=4).pack(side='right', padx=4)
        ttk.Label(sf, text='Sockets').pack(side='right')
        self.gem_list = tk.Listbox(right, height=3)
        self.gem_list.pack(fill='x')
        gb = ttk.Frame(right)
        gb.pack(fill='x', pady=4)
        ttk.Button(gb, text='Add gem...', command=self.add_gem).pack(side='left')
        ttk.Button(gb, text='Remove gem', command=self.remove_gem).pack(side='left', padx=6)

        rf = ttk.Frame(right)
        rf.pack(fill='x', pady=(6, 0))
        self.req_label = ttk.Label(rf, text='Level requirement')
        self.req_label.pack(side='left')
        ttk.Button(rf, text='Set', command=self.set_requirement, width=5).pack(side='right')
        self.req_var = tk.IntVar(value=1)
        ttk.Spinbox(rf, from_=1, to=sg.MAX_LEVEL, textvariable=self.req_var, width=4).pack(side='right', padx=4)
        ttk.Label(rf, text='Wear from level').pack(side='right')

        ttk.Label(right, text='Magic items hold 1-2 affixes, rares 4-6. Any item can have up to 3 sockets. '
                  'Press Apply changes to keep your edits.', wraplength=320, foreground='#777').pack(anchor='w', pady=4)
        ttk.Button(right, text='Apply changes', command=self.apply_item).pack(anchor='e', pady=6)
        self.status = ttk.Label(root, text='', padding=6)
        self.status.pack(fill='x')

        last = sg.load_settings().get('saves')
        dirs = (sg.find_save_dirs(last) if last and os.path.isdir(last) else []) or sg.find_save_dirs()
        if dirs:
            self.open(dirs[0])
        else:
            self.set_status('No saves found in %s. Use "Open folder..." to pick your Rehydrated user data folder '
                            'or a d3save folder.' % sg.DEFAULT_ROOT)

    # --- loading and saving
    def choose(self):
        d = filedialog.askdirectory(title='Pick a d3save folder or your Rehydrated user data folder',
                                    initialdir=sg.DEFAULT_ROOT if os.path.isdir(sg.DEFAULT_ROOT) else sg.documents_dir())
        if not d:
            return
        dirs = sg.find_save_dirs(d)
        if not dirs:
            messagebox.showerror('No saves', 'No Diablo III saves (d3save with account.dat) in\n' + d)
            return
        self.open(dirs[0])

    def open(self, path):
        if not os.path.exists(os.path.join(path, 'account.dat')):
            messagebox.showerror('Not a save folder', 'No account.dat in\n' + path)
            return
        sg.store_settings(saves=path)
        self.save = sg.SaveFolder(path)
        self.path_label.config(text=path)
        old = self.save.pc_id_items(self.data)
        if old and messagebox.askyesno('Legendary items', '%d legendary or set items in these saves use the PC version\'s '
                                       'item id (written by an older version of this editor). The console has its own '
                                       'version of them, and with the PC id the game can show another item.\n\n'
                                       'Switch them to the console version? (Save afterwards to keep it.)' % len(old)):
            self.save.use_console_ids(self.data)
        self.fill_owners(select=len(self.save.account.partitions) if self.save.heroes else 0)
        self.set_status('Loaded %d heroes.' % len(self.save.heroes) +
                        (' %d legendaries switched to the console version (not saved yet).' % len(old) if old and self.unsaved() else ''))

    def fill_owners(self, select):
        self.owners.delete(0, 'end')
        self.owner_rows = [('stash', p) for p in self.save.account.partitions] + [('hero', h) for h in self.save.heroes]
        for kind, x in self.owner_rows:
            self.owners.insert('end', self.owner_label(kind, x))
        self.owners.selection_set(select)
        self.show_owner()

    @staticmethod
    def owner_label(kind, x):
        if kind == 'stash':
            return 'Shared stash (%s)' % sg.PARTITION_NAMES[x]
        state = ' (hardcore, dead)' if x.dead else ' (hardcore)' if x.hardcore else ''
        return '%s - level %d %s%s' % (x.name, x.level, x.class_name, state)

    def reload(self):
        if self.save:
            if self.unsaved() and not messagebox.askyesno('Reload', 'Discard unsaved changes?'):
                return
            self.open(self.save.path)

    def unsaved(self):
        return self.save and any(x.dirty for x in [self.save.account] + self.save.heroes)

    def do_save(self):
        if not self.save:
            return
        try:
            backup = self.save.save()
        except Exception as e:
            messagebox.showerror('Not saved', str(e))
            return
        if backup:
            self.set_status('Saved. Backup of the previous saves: ' + backup)
            messagebox.showinfo('Saved', 'Saved.\n\nA backup of the previous saves is in:\n' + backup)
        else:
            self.set_status('Nothing changed.')

    # --- account and hero
    def set_level(self):
        if not isinstance(self.current, sg.Hero):
            return
        try:
            level = max(1, min(int(self.level_var.get()), sg.MAX_LEVEL))
        except (ValueError, tk.TclError):
            return
        self.current.level = level
        self.fill_owners(self.owners.curselection()[0])
        self.set_status('%s is now level %d (not saved yet).' % (self.current.name, level))

    def unlock_followers(self):
        if isinstance(self.current, sg.Hero):
            self.current.unlock_followers()
            self.set_status('Templar, Scoundrel and Enchantress unlocked for %s; the Templar comes along (not saved yet).' % self.current.name)

    def progress_text(self, hero):
        diff, act, sno, step = hero.last_played
        quest = next((q for quests in self.quests for q in quests if q['sno'] == sno), None)
        unlocked = sg.DIFFICULTIES[hero.highest_difficulty] if 0 <= hero.highest_difficulty < 4 else '?'
        where = '%s, %s' % (sg.DIFFICULTIES[diff] if 0 <= diff < 4 else '?', quest['name']) if quest else 'the start'
        return 'Unlocked up to %s. Next game: %s' % (unlocked, where)

    def edit_progress(self):
        hero = self.current
        if not isinstance(hero, sg.Hero):
            return
        d = ProgressDialog(self, hero)
        self.root.wait_window(d)
        if not d.result:
            return
        unlock, diff, act, sno, step, name = d.result
        if unlock is not None or diff > hero.highest_difficulty:
            hero.unlock_progress(max(unlock or 0, diff), self.quests)
        hero.start_at(diff, act, sno, step)
        self.show_owner()
        self.set_status('%s: next game starts at %s on %s (not saved yet).' % (hero.name, name, sg.DIFFICULTIES[diff]))

    def revive(self):
        hero = self.current
        if isinstance(hero, sg.Hero) and hero.dead:
            hero.revive()
            self.fill_owners(self.owners.curselection()[0])
            self.set_status('%s is alive again (not saved yet).' % hero.name)

    def set_tabs(self):
        try:
            tabs = int(self.tabs.get())
        except (ValueError, tk.TclError):
            return
        self.save.account.set_stash_tabs(tabs, self.partition)
        self.show_owner()
        self.set_status('%s stash: %d tabs (not saved yet).' % (sg.PARTITION_NAMES[self.partition], self.save.account.get_stash_tabs(self.partition)))

    def set_artisan(self, n):
        try:
            level = int(self.artisan_vars[n].get())
        except (ValueError, tk.TclError):
            return
        self.save.account.set_artisan(n, level, self.partition)
        self.show_owner()
        self.set_status('%s %s is now level %d (not saved yet).' % (sg.PARTITION_NAMES[self.partition], sg.ARTISANS[n],
                                                                   self.save.account.get_artisan(n, self.partition)))

    def unlock_hardcore(self):
        self.save.account.unlock_hardcore()
        self.show_owner()
        self.set_status('Hardcore heroes can now be created (not saved yet).')

    def set_gold(self):
        try:
            amount = int(self.gold.get().replace('.', '').replace(',', ''))
        except ValueError:
            return
        self.save.account.set_gold(max(0, min(amount, 2_000_000_000)), self.partition)
        self.show_owner()
        self.set_status('%s gold set to %d (not saved yet).' % (sg.PARTITION_NAMES[self.partition], self.save.account.get_gold(self.partition)))

    def set_paragon(self):
        try:
            level = int(self.paragon.get())
        except (ValueError, tk.TclError):
            return
        self.save.account.set_paragon(level, self.partition)
        self.show_owner()
        self.set_status('%s Paragon level set to %d for all those heroes (not saved yet).' % (
            sg.PARTITION_NAMES[self.partition], self.save.account.get_paragon(self.partition)))

    # --- views
    def owner_container(self):
        return self.save.account.stash(self.partition) if self.current is self.save.account else self.current.container

    def show_owner(self):
        sel = self.owners.curselection()
        if not sel or not self.save:
            return
        kind, x = self.owner_rows[sel[0]]
        if kind == 'stash':
            self.current, self.partition = self.save.account, x
        else:
            self.current, self.partition = x, 0
        is_hero = kind == 'hero'
        for w in (self.level_spin, self.level_btn, self.followers_btn, self.progress_btn):
            w.state(['!disabled'] if is_hero else ['disabled'])
        self.revive_btn.state(['!disabled'] if is_hero and self.current.dead else ['disabled'])
        if is_hero:
            self.level_var.set(self.current.level)
            self.hero_label.config(text=self.progress_text(self.current))
            if self.current.hardcore:
                self.partition = 1   # a hardcore hero's gold, Paragon, artisans and stash
        else:
            self.hero_label.config(text='')
        acct = self.save.account
        self.tabs.set(acct.get_stash_tabs(self.partition))
        for n, var in enumerate(self.artisan_vars):
            var.set(acct.get_artisan(n, self.partition))
        self.hardcore_btn.state(['disabled'] if acct.hardcore_unlocked else ['!disabled'])
        self.acct_label.config(text='%s heroes (shared stash, gold, Paragon)' % sg.PARTITION_NAMES[self.partition])
        self.gold.set(str(acct.get_gold(self.partition)))
        self.paragon.set(acct.get_paragon(self.partition))

        self.tree.delete(*self.tree.get_children())
        self.item_rows = {}
        order = lambda i: (i.hireling, i.slot != it.BACKPACK if is_hero else 0, i.slot, i.square)
        for item in sorted(self.owner_container().items, key=order):
            if item.slot in (it.GOLD, it.SOCKET):
                continue   # gold is set above; gems show with the item they sit in
            info = self.data.by_gbid.get(item.gbid, {})
            stack = ' x%d' % item.stack if item.stack > 1 else ''
            name = self.data.item_name(item.gbid) + stack
            rare = self.data.rare_name_text(info, item.rare_name) if item.rare_name else None
            if rare:
                name = '%s (%s)' % (rare, name)
            stats = [e for a in item.affixes for e in self.data.affix_effects(a)] or [self.data.affix_name(a) for a in item.affixes]
            gems = item.gems
            if gems:
                stats.append('gems: ' + ', '.join(self.data.item_name(g.gbid) for g in gems))
            tag = 'set' if item.quality == 9 and info.get('set') else \
                'legendary' if item.quality == 9 or info.get('legendary') else 'rare' if 6 <= item.quality <= 8 else \
                'magic' if 3 <= item.quality <= 5 else ''
            iid = self.tree.insert('', 'end', values=(where_label(item), name, info.get('typeDisplay', '?'),
                                                      quality_label(item.quality), '; '.join(stats)), tags=(tag,) if tag else ())
            self.item_rows[iid] = item
        self.show_item()

    def selected(self):
        sel = self.tree.selection()
        return self.item_rows.get(sel[0]) if sel else None

    def show_item(self):
        item = self.selected()
        self.affix_list.delete(0, 'end')
        self.gem_list.delete(0, 'end')
        self.name_label.config(text='')
        if not item:
            self.item_title.config(text='')
            return
        info = self.data.by_gbid.get(item.gbid, {})
        self.item_title.config(text='%s\n%s, item level %s%s' % (
            self.data.item_name(item.gbid), info.get('typeDisplay', '?'), info.get('level', '?'),
            '\nSet: %s (when Legendary)' % info['set'] if info.get('set') else ''))
        self.q_var.set(quality_label(item.quality))
        self.stack_var.set(item.stack)
        self.dur_var.set(item.durability)
        self.pending_affixes = list(item.affixes)
        self.pending_name = item.rare_name
        self.pending_gems = [g.gbid for g in item.gems]
        self.pending_seed = None
        self.refresh_pending()

    def refresh_pending(self):
        item = self.selected()
        info = self.data.by_gbid.get(item.gbid, {}) if item else {}
        self.affix_list.delete(0, 'end')
        for a in self.pending_affixes:
            self.affix_list.insert('end', self.data.affix_label(a))
        self.name_label.config(text=self.data.rare_name_text(info, self.pending_name) or '(none)')
        self.gem_list.delete(0, 'end')
        for g in self.pending_gems:
            self.gem_list.insert('end', self.data.item_name(g))
        sockets = self.data.sockets(self.pending_affixes)
        self.sockets_var.set(sockets)
        self.gem_label.config(text='Gems (%d of %d sockets)' % (len(self.pending_gems), sockets))
        base, low, high = self.data.requirement(info, self.pending_affixes)
        if item and high:
            seed = item.seed if self.pending_seed is None else self.pending_seed
            worst = sg.eased_level(self.data, info, self.pending_affixes, seed)
            best = max(base - high, 1)
            self.req_label.config(text='Level %d (normally %d)' % (worst, base) if worst == best else
                                  'Level %d-%d (normally %d)' % (best, worst, base))
        else:
            self.req_label.config(text='Level requirement %d' % base)

    # --- edits
    def mark(self):
        self.current.dirty = True

    def apply_item(self):
        item = self.selected()
        if not item:
            return
        info = self.data.by_gbid.get(item.gbid, {})
        q = dict((n, q) for q, n in QUALITIES).get(self.q_var.get())
        if q is not None:
            item.quality = q
        if self.pending_affixes and item.quality < 3:
            item.quality = 6 if len(self.pending_affixes) > 2 else 3   # affixes only show on magic and better
        if self.data.sockets(self.pending_affixes) > MAX_SOCKETS:
            messagebox.showinfo('Sockets', 'The game shows at most %d sockets per item and disconnects with more '
                                'gems; use the Sockets setting instead of more Sockets affixes.' % MAX_SOCKETS)
            return
        item.affixes = self.pending_affixes[:MAX_AFFIXES]
        if self.pending_seed is not None:
            item.seed = self.pending_seed
            self.pending_seed = None
        if 6 <= item.quality <= 8 and not self.pending_name:
            self.pending_name = self.data.random_rare_name(info, item.affixes)
        item.rare_name = self.pending_name if 6 <= item.quality <= 8 else None
        if self.pending_gems != [g.gbid for g in item.gems]:
            self.owner_container().set_gems(item, self.pending_gems)
        item.stack = max(0, self.stack_var.get())
        if item.durability or self.dur_var.get():
            item.durability = self.dur_var.get()
            item.max_durability = max(item.max_durability, self.dur_var.get())
        self.mark()
        self.show_owner()
        self.set_status('Item changed (not saved yet).')

    def add_affix(self):
        item = self.selected()
        if not item:
            return
        d = AffixDialog(self, self.data.by_gbid.get(item.gbid, {}), self.pending_affixes)
        self.root.wait_window(d)
        if d.result:
            room = MAX_AFFIXES - len(self.pending_affixes)
            if len(d.result) > room:
                messagebox.showinfo('Affixes', 'An item can hold %d affixes; %d added.' % (MAX_AFFIXES, max(room, 0)))
            self.pending_affixes += d.result[:max(room, 0)]
            self.refresh_pending()

    def edit_stat(self):
        sel = self.affix_list.curselection()
        if not sel or not self.selected():
            return
        stats = [st for st in self.data.affix_by_gbid.get(self.pending_affixes[sel[0]], {}).get('stats', [])
                 if st[2] is not None and st[0] not in ('Sockets', 'Item_Level_Requirement_Reduction')]
        if not stats:
            messagebox.showinfo('Set stat', 'This affix has no number to change (sockets and the level requirement '
                                'have their own settings).')
            return
        d = StatDialog(self, self.pending_affixes, stats)
        self.root.wait_window(d)
        if not d.result:
            return
        st, target = d.result
        try:
            self.pending_affixes, copies = self.data.set_stat_total(self.pending_affixes, st, target, MAX_AFFIXES)
        except ValueError as e:
            messagebox.showinfo('Set stat', str(e).capitalize() + '.')
            return
        self.refresh_pending()
        scale = self.data.stat_scale(st)
        low, high = self.data.stat_total(self.pending_affixes, st)
        self.set_status('Stat total now %s-%s from %d affix%s. Press Apply changes to keep it.' % (
            sg._number(low * scale), sg._number(high * scale), copies, 'es' if copies > 1 else '')
            if copies else 'Stat taken off. Press Apply changes to keep it.')

    def remove_affix(self):
        sel = self.affix_list.curselection()
        if sel:
            del self.pending_affixes[sel[0]]
            self.refresh_pending()

    def random_affixes(self):
        item = self.selected()
        info = self.data.by_gbid.get(item.gbid) if item else None
        if not info:
            return
        q = dict((n, q) for q, n in QUALITIES).get(self.q_var.get(), item.quality)
        if q == 9:
            self.pending_affixes = self.data.legendary_affixes(info)   # what this legendary rolls when it drops
        else:
            self.pending_affixes = self.data.random_affixes(info, 6 if q == 6 else 2)
        self.refresh_pending()

    def choose_name(self):
        item = self.selected()
        if not item:
            return
        info = self.data.by_gbid.get(item.gbid, {})
        choices = self.data.rare_name_choices(info, self.pending_affixes)
        if not choices:
            messagebox.showinfo('Rare name', 'Rare names come from the item type and its affixes: add affixes first.')
            return
        d = SearchList(self, 'Rare name', [('Name', 560)], [(text, value) for text, value in choices],
                       'The names a rare of this type with these affixes can get. The item becomes Rare.')
        self.root.wait_window(d)
        if d.result:
            self.pending_name = d.result
            self.q_var.set('Rare')
            self.refresh_pending()

    def random_name(self):
        item = self.selected()
        if item:
            self.pending_name = self.data.random_rare_name(self.data.by_gbid.get(item.gbid, {}), self.pending_affixes)
            if self.pending_name:
                self.q_var.set('Rare')
            self.refresh_pending()

    def add_gem(self):
        item = self.selected()
        if not item:
            return
        sockets = min(self.data.sockets(self.pending_affixes), MAX_SOCKETS)
        if len(self.pending_gems) >= sockets:
            messagebox.showinfo('Gems', 'No free socket. Set Sockets (up to %d) and try again.' % MAX_SOCKETS)
            return
        gems = sorted((i for i in self.data.items if i['type'] == 'Gem' and i.get('console', True)),
                      key=lambda i: (i['name'].split('_')[0], i['level']))
        d = SearchList(self, 'Add gem', [('Gem', 300), ('Level', 80)], [(g['display'], g['level'], g['gbid']) for g in gems])
        self.root.wait_window(d)
        if d.result:
            self.pending_gems.append(d.result)
            self.refresh_pending()

    def socket_affix(self, info):
        """A Sockets affix for this item: one the game rolls on its type, else the plain one."""
        def is_socket(a):
            return any(st[0] == 'Sockets' for st in a.get('stats', []))
        fitting = [a for a in self.data.affixes_for(info) if is_socket(a)]
        pool = fitting or [a for a in self.data.affixes if is_socket(a)]
        return min(pool, key=lambda a: a['level'])['gbid']

    def set_sockets(self):
        """Any item can get up to 3 sockets, also ones the game gives fewer (a dagger normally has at most 1)."""
        item = self.selected()
        if not item:
            return
        try:
            n = max(0, min(int(self.sockets_var.get()), MAX_SOCKETS))
        except (ValueError, tk.TclError):
            return
        socket_gbids = {a['gbid'] for a in self.data.affixes if any(st[0] == 'Sockets' for st in a.get('stats', []))}
        self.pending_affixes = [a for a in self.pending_affixes if a not in socket_gbids]
        self.pending_affixes += [self.socket_affix(self.data.by_gbid.get(item.gbid, {}))] * n
        self.pending_gems = self.pending_gems[:n]
        self.refresh_pending()

    def set_requirement(self):
        """Lower the level requirement with stacked "level requirement reduced" affixes and a seed that rolls them
        high enough; this also rerolls the item's other stats."""
        item = self.selected()
        if not item:
            return
        try:
            target = max(1, min(int(self.req_var.get()), sg.MAX_LEVEL))
        except (ValueError, tk.TclError):
            return
        info = self.data.by_gbid.get(item.gbid, {})
        try:
            self.pending_affixes, seed, copies = sg.ease_requirement(self.data, info, self.pending_affixes, target, MAX_AFFIXES)
        except ValueError as e:
            messagebox.showinfo('Level requirement', str(e).capitalize() + '. Remove some affixes and try again.')
            return
        if seed is not None:
            self.pending_seed = seed
        self.refresh_pending()
        self.set_status('Level requirement: %d "level requirement reduced" affixes. Press Apply changes to keep it.' % copies
                        if copies else 'Level requirement back to normal. Press Apply changes to keep it.')

    def remove_gem(self):
        sel = self.gem_list.curselection()
        if sel:
            del self.pending_gems[sel[0]]
            self.refresh_pending()

    def reroll(self):
        item = self.selected()
        if item:
            item.seed = random.getrandbits(32)
            self.mark()
            self.set_status('New random rolls for this item (not saved yet).')

    def add_item(self):
        if not self.current:
            return
        hero = isinstance(self.current, sg.Hero)
        d = AddItemDialog(self, hero)
        self.root.wait_window(d)
        if not d.result:
            return
        info, slot, hireling, quality, count = d.result
        c = self.owner_container()
        stackable = info['type'] in STACKABLE
        for n in range(1 if stackable else count):
            if slot in (it.BACKPACK, it.STASH):
                w, h = (sg.BACKPACK_W, sg.BACKPACK_H) if slot == it.BACKPACK else (sg.STASH_W, sg.STASH_H)
                square = c.free_square(slot, w, h, self.data.height(info['gbid']), self.data)
                if square is None:
                    messagebox.showwarning('No room', 'The %s is full.' % it.SLOT_NAMES[slot].lower())
                    break
            else:
                for old in [i for i in c.items if i.slot == slot and i.hireling == hireling]:
                    old.slot, old.hireling = it.BACKPACK, 0
                    old.square = c.free_square(it.BACKPACK, sg.BACKPACK_W, sg.BACKPACK_H, self.data.height(old.gbid), self.data) or 0
                square = 0
            item = sg.make_item(c, self.data, info, slot, square, quality, stack=count if stackable else None)
            item.hireling = hireling
            c.add(item)
        self.mark()
        self.show_owner()
        extra = ' with random affixes; select it to change them' if quality in (3, 6) else ''
        self.set_status('Added %s%s (not saved yet).' % (info['display'], extra))

    def duplicate(self):
        item = self.selected()
        if not item or item.slot not in (it.BACKPACK, it.STASH):
            messagebox.showinfo('Duplicate', 'Pick an item in the backpack or stash.')
            return
        c = self.owner_container()
        w, h = (sg.BACKPACK_W, sg.BACKPACK_H) if item.slot == it.BACKPACK else (sg.STASH_W, sg.STASH_H)
        square = c.free_square(item.slot, w, h, self.data.height(item.gbid), self.data)
        if square is None:
            messagebox.showwarning('No room', 'No free space for a copy.')
            return
        copy = it.Item(d3save.Message.parse(item.msg.encode()))
        copy.msg.sub(1).set(2, c.next_id())
        copy.square = square
        c.add(copy)
        gems = [g.gbid for g in item.gems]
        if gems:
            c.set_gems(copy, gems)   # the copy gets gems of its own
        self.mark()
        self.show_owner()

    def delete(self):
        item = self.selected()
        if item and messagebox.askyesno('Delete', 'Delete %s?' % self.data.item_name(item.gbid)):
            self.owner_container().remove_with_gems(item)
            self.mark()
            self.show_owner()

    # --- many items, copies and presets
    def place_in(self, container, slot, item_height):
        w, h = sg.grid_of(slot)
        return container.free_square(slot, w, h, item_height, self.data)

    def bulk_add(self):
        if not self.current:
            return
        hero = isinstance(self.current, sg.Hero)
        d = BulkDialog(self, hero)
        self.root.wait_window(d)
        if not d.result:
            return
        chosen, stack = d.result
        added = self.add_many(chosen, stack)
        self.set_status('Added %d of %d items%s (not saved yet).' % (added, len(chosen), '; the rest did not fit' if added < len(chosen) else ''))

    def add_many(self, infos, stack):
        hero = isinstance(self.current, sg.Hero)
        c, slot = self.owner_container(), it.BACKPACK if hero else it.STASH
        added = 0
        for info in infos:
            square = self.place_in(c, slot, self.data.height(info['gbid']))
            if square is None:
                break
            stackable = info['type'] in STACKABLE
            c.add(sg.make_item(c, self.data, info, slot, square, stack=stack if stackable else None))
            added += 1
        if added:
            self.mark()
            self.show_owner()
        return added

    def copy_to(self):
        item = self.selected()
        if not item:
            messagebox.showinfo('Copy to', 'Pick an item first.')
            return
        rows = [(self.owner_label(k, x), (k, x)) for k, x in self.owner_rows]
        d = SearchList(self, 'Copy to', [('Where', 560)], rows, 'Into the backpack of a hero or a shared stash.')
        self.root.wait_window(d)
        if d.result:
            self.copy_item(item, *d.result)

    def copy_item(self, item, kind, x):
        acct = self.save.account
        owner, c, slot = (acct, acct.stash(x), it.STASH) if kind == 'stash' else (x, x.container, it.BACKPACK)
        square = self.place_in(c, slot, self.data.height(item.gbid))
        if square is None:
            messagebox.showwarning('No room', 'No free space there.')
            return None
        copy = sg.place_item(item.msg, [g.gbid for g in item.gems], c, slot, square)
        owner.dirty = True
        self.show_owner()
        self.set_status('Copied %s (not saved yet).' % self.data.item_name(item.gbid))
        return copy

    def save_preset(self, path=None):
        item = self.selected()
        if not item:
            messagebox.showinfo('Save preset', 'Pick an item first.')
            return
        name = self.data.rare_name_text(self.data.by_gbid.get(item.gbid, {}), item.rare_name) or self.data.item_name(item.gbid)
        path = path or filedialog.asksaveasfilename(
            title='Save item preset', defaultextension='.d3item', filetypes=[('Item presets', '*.d3item'), ('All files', '*.*')],
            initialfile=''.join(ch for ch in name if ch.isalnum() or ch in ' -_') + '.d3item')
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(dict(sg.item_preset(item), name=name), f, indent=1)
        self.set_status('Saved %s to %s.' % (name, path))

    def load_preset(self, paths=None):
        if not self.current:
            return
        paths = paths or filedialog.askopenfilenames(title='Load item presets', filetypes=[('Item presets', '*.d3item'), ('All files', '*.*')])
        hero = isinstance(self.current, sg.Hero)
        c, slot = self.owner_container(), it.BACKPACK if hero else it.STASH
        added = []
        for path in paths:
            try:
                with open(path, encoding='utf-8') as f:
                    msg, gems = sg.preset_record(json.load(f))
            except (OSError, ValueError, KeyError) as e:
                messagebox.showerror('Load preset', '%s:\n%s' % (os.path.basename(path), e))
                continue
            square = self.place_in(c, slot, self.data.height(it.Item(msg).gbid))
            if square is None:
                messagebox.showwarning('No room', 'The %s is full.' % it.SLOT_NAMES[slot].lower())
                break
            added.append(self.data.item_name(sg.place_item(msg, gems, c, slot, square).gbid))
        if added:
            self.mark()
            self.show_owner()
            self.set_status('Added %s (not saved yet).' % ', '.join(added))

    def set_status(self, text):
        self.status.config(text=text)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use('vista')
    except tk.TclError:
        pass
    app = App(root)

    def on_close():
        if app.unsaved() and not messagebox.askyesno('Quit', 'You have unsaved changes. Quit anyway?'):
            return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', on_close)
    root.mainloop()


if __name__ == '__main__':
    main()
