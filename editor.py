"""Diablo III save editor for the original Xbox 360 release (2013) running in Rehydrated: items, affixes, gold, hero level."""
import os, random, sys, tkinter as tk
from tkinter import ttk, messagebox, filedialog
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import items as it
import savegame as sg

EQUIP_SLOTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
QUALITIES = [(1, 'Normal'), (3, 'Magic'), (6, 'Rare'), (9, 'Legendary')]
AFFIX_KINDS = {0: 'requirement', 1: 'rare only', 2: 'legendary', 3: ''}
MAX_AFFIXES = 32   # the affix message the server sends holds 32; more and the game disconnects


def quality_label(q):
    return it.QUALITY_NAMES.get(q, str(q))


class AddItemDialog(tk.Toplevel):
    """Search the game's item list and choose where the new item goes."""

    def __init__(self, app, hero_mode):
        super().__init__(app.root)
        self.app, self.result = app, None
        self.title('Add item')
        self.geometry('760x560')
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
        if hero_mode:
            places = ['Backpack'] + [it.SLOT_NAMES[s] + ' (equip)' for s in EQUIP_SLOTS]
        else:
            places = ['Stash']
        self.place = tk.StringVar(value=places[0])
        ttk.Combobox(dest, textvariable=self.place, values=places, state='readonly', width=22).pack(side='left', padx=6)
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
                                   tags=('legendary',) if info['legendary'] else ())
            self.shown[iid] = info
        self.tree.tag_configure('legendary', foreground='#b35c00')

    def ok(self):
        sel = self.tree.selection()
        if not sel:
            return
        place = self.place.get()
        slot = it.BACKPACK if place == 'Backpack' else it.STASH if place == 'Stash' else \
            next(s for s in EQUIP_SLOTS if it.SLOT_NAMES[s] + ' (equip)' == place)
        quality = dict((n, q) for q, n in QUALITIES).get(self.quality.get())
        self.result = (self.shown[sel[0]], slot, quality, max(1, self.count.get()))
        self.destroy()


class AffixDialog(tk.Toplevel):
    """Pick an affix the game can roll on this item; "Show all" also offers ones it never would."""

    def __init__(self, app, info, taken):
        super().__init__(app.root)
        self.app, self.info, self.result = app, info, None
        self.taken = {app.data.affix_by_gbid[g]['family'] for g in taken if g in app.data.affix_by_gbid}
        self.title('Add affix')
        self.geometry('620x520')
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
        cols = ('name', 'level', 'req', 'kind')
        self.tree = ttk.Treeview(f, columns=cols, show='headings', selectmode='browse')
        for c, w, t in [('name', 300, 'Affix'), ('level', 70, 'Level'), ('req', 110, 'Required level'), ('kind', 90, '')]:
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
            if q in a['name'].lower() and (everything or a['family'] not in self.taken):
                iid = self.tree.insert('', 'end', values=(a['name'], a['level'], a['requiredLevel'], AFFIX_KINDS.get(a['kind'], '')))
                self.shown[iid] = a

    def ok(self):
        sel = self.tree.selection()
        if sel:
            copies = max(1, self.copies.get()) if self.everything.get() else 1
            self.result = [self.shown[sel[0]]['gbid']] * copies
            self.destroy()


class App:
    def __init__(self, root):
        self.root = root
        root.title('Diablo III Save Editor - Xbox 360 (2013) saves in Rehydrated')
        root.geometry('1180x680')
        self.data = sg.GameData()
        self.save = None
        self.current = None   # Hero or Account
        self.item_rows = {}

        bar = ttk.Frame(root, padding=6)
        bar.pack(fill='x')
        ttk.Button(bar, text='Open folder...', command=self.choose).pack(side='left')
        self.path_label = ttk.Label(bar, text='')
        self.path_label.pack(side='left', padx=8)
        ttk.Button(bar, text='Save', command=self.do_save).pack(side='right')
        ttk.Button(bar, text='Reload', command=self.reload).pack(side='right', padx=6)
        self.gold = tk.StringVar()
        ttk.Button(bar, text='Set gold', command=self.set_gold).pack(side='right', padx=6)
        ttk.Entry(bar, textvariable=self.gold, width=14).pack(side='right')
        ttk.Label(bar, text='Gold').pack(side='right', padx=4)

        body = ttk.PanedWindow(root, orient='horizontal')
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body, padding=6)
        body.add(left, weight=1)
        ttk.Label(left, text='Heroes and stash').pack(anchor='w')
        self.owners = tk.Listbox(left, exportselection=False, width=30)
        self.owners.pack(fill='both', expand=True)
        self.owners.bind('<<ListboxSelect>>', lambda e: self.show_owner())
        lv = ttk.Frame(left)
        lv.pack(fill='x', pady=(6, 0))
        ttk.Label(lv, text='Hero level').pack(side='left')
        self.level_var = tk.IntVar(value=1)
        self.level_spin = ttk.Spinbox(lv, from_=1, to=sg.MAX_LEVEL, textvariable=self.level_var, width=5)
        self.level_spin.pack(side='left', padx=6)
        self.level_btn = ttk.Button(lv, text='Set', command=self.set_level)
        self.level_btn.pack(side='left')

        mid = ttk.Frame(body, padding=6)
        body.add(mid, weight=4)
        cols = ('where', 'name', 'type', 'quality', 'affixes')
        self.tree = ttk.Treeview(mid, columns=cols, show='headings', selectmode='browse')
        for c, w, t in [('where', 150, 'Where'), ('name', 230, 'Item'), ('type', 120, 'Type'), ('quality', 90, 'Quality'), ('affixes', 260, 'Affixes')]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='w')
        self.tree.pack(fill='both', expand=True)
        self.tree.tag_configure('legendary', foreground='#b35c00')
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.show_item())
        btns = ttk.Frame(mid)
        btns.pack(fill='x', pady=6)
        ttk.Button(btns, text='Add item...', command=self.add_item).pack(side='left')
        ttk.Button(btns, text='Duplicate', command=self.duplicate).pack(side='left', padx=6)
        ttk.Button(btns, text='Delete', command=self.delete).pack(side='left')

        right = ttk.LabelFrame(body, text='Selected item', padding=8)
        body.add(right, weight=2)
        self.item_title = ttk.Label(right, text='', font=('Segoe UI', 11, 'bold'), wraplength=280)
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
        ab = ttk.Frame(right)
        ab.pack(fill='x', pady=4)
        ttk.Button(ab, text='Add affix...', command=self.add_affix).pack(side='left')
        ttk.Button(ab, text='Remove', command=self.remove_affix).pack(side='left', padx=6)
        ttk.Button(ab, text='Random', command=self.random_affixes).pack(side='left')
        ttk.Label(right, text='Magic items hold 1-2 affixes, rares 4-6. Legendaries also keep their own fixed stats. '
                  'Press Apply changes to keep affix edits.', wraplength=280, foreground='#777').pack(anchor='w', pady=4)
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
        self.owners.delete(0, 'end')
        self.owners.insert('end', 'Shared stash (account)')
        for h in self.save.heroes:
            self.owners.insert('end', '%s - level %d %s' % (h.name, h.level, h.class_name))
        self.gold.set(str(self.save.account.gold))
        self.owners.selection_set(1 if self.save.heroes else 0)
        self.show_owner()
        self.set_status('Loaded %d heroes.' % len(self.save.heroes))

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

    def set_level(self):
        if not isinstance(self.current, sg.Hero):
            return
        try:
            level = max(1, min(int(self.level_var.get()), sg.MAX_LEVEL))
        except (ValueError, tk.TclError):
            return
        self.current.level = level
        sel = self.owners.curselection()[0]
        self.owners.delete(sel)
        self.owners.insert(sel, '%s - level %d %s' % (self.current.name, level, self.current.class_name))
        self.owners.selection_set(sel)
        self.set_status('%s is now level %d (not saved yet).' % (self.current.name, level))

    def set_gold(self):
        try:
            amount = int(self.gold.get().replace('.', '').replace(',', ''))
        except ValueError:
            return
        self.save.account.gold = max(0, min(amount, 2_000_000_000))
        self.show_owner()
        self.set_status('Gold set to %d (not saved yet).' % self.save.account.gold)

    # --- views
    def show_owner(self):
        sel = self.owners.curselection()
        if not sel or not self.save:
            return
        self.current = self.save.account if sel[0] == 0 else self.save.heroes[sel[0] - 1]
        is_hero = isinstance(self.current, sg.Hero)
        for w in (self.level_spin, self.level_btn):
            w.state(['!disabled'] if is_hero else ['disabled'])
        if is_hero:
            self.level_var.set(self.current.level)
        self.tree.delete(*self.tree.get_children())
        self.item_rows = {}
        hero = isinstance(self.current, sg.Hero)
        for item in sorted(self.current.container.items, key=lambda i: (i.slot != it.BACKPACK if hero else 0, i.slot, i.square)):
            if item.slot == it.GOLD:
                continue
            info = self.data.by_gbid.get(item.gbid, {})
            if item.slot in (it.BACKPACK, it.STASH):
                w = sg.BACKPACK_W if item.slot == it.BACKPACK else sg.STASH_W
                where = '%s %d,%d' % (it.SLOT_NAMES[item.slot], item.square % w + 1, item.square // w + 1)
            else:
                where = it.SLOT_NAMES.get(item.slot, 'Slot %d' % item.slot)
            stack = ' x%d' % item.stack if item.stack > 1 else ''
            iid = self.tree.insert('', 'end', values=(where, self.data.item_name(item.gbid) + stack, info.get('typeDisplay', '?'),
                                   quality_label(item.quality), ', '.join(self.data.affix_name(a) for a in item.affixes)),
                                   tags=('legendary',) if item.quality == 9 or info.get('legendary') else ())
            self.item_rows[iid] = item
        self.show_item()

    def selected(self):
        sel = self.tree.selection()
        return self.item_rows.get(sel[0]) if sel else None

    def show_item(self):
        item = self.selected()
        self.affix_list.delete(0, 'end')
        if not item:
            self.item_title.config(text='')
            return
        info = self.data.by_gbid.get(item.gbid, {})
        self.item_title.config(text='%s\n%s, item level %s' % (self.data.item_name(item.gbid), info.get('typeDisplay', '?'), info.get('level', '?')))
        self.q_var.set(quality_label(item.quality))
        self.stack_var.set(item.stack)
        self.dur_var.set(item.durability)
        self.pending_affixes = list(item.affixes)
        for a in self.pending_affixes:
            self.affix_list.insert('end', self.data.affix_name(a))

    # --- edits
    def mark(self):
        self.current.dirty = True

    def apply_item(self):
        item = self.selected()
        if not item:
            return
        q = dict((n, q) for q, n in QUALITIES).get(self.q_var.get())
        if q is not None:
            item.quality = q
        if self.pending_affixes and item.quality < 3:
            item.quality = 6 if len(self.pending_affixes) > 2 else 3   # affixes only show on magic and better
        item.affixes = self.pending_affixes[:MAX_AFFIXES]
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
            for g in d.result[:max(room, 0)]:
                self.pending_affixes.append(g)
                self.affix_list.insert('end', self.data.affix_name(g))

    def remove_affix(self):
        sel = self.affix_list.curselection()
        if sel:
            del self.pending_affixes[sel[0]]
            self.affix_list.delete(sel[0])

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
        self.affix_list.delete(0, 'end')
        for a in self.pending_affixes:
            self.affix_list.insert('end', self.data.affix_name(a))

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
        info, slot, quality, count = d.result
        c = self.current.container
        stackable = info['type'] in ('HealthPotion', 'Gem', 'CraftingReagent', 'Dye')
        for n in range(1 if stackable else count):
            if slot in (it.BACKPACK, it.STASH):
                w, h = (sg.BACKPACK_W, sg.BACKPACK_H) if slot == it.BACKPACK else (sg.STASH_W, sg.STASH_H)
                square = c.free_square(slot, w, h, self.data.height(info['gbid']), self.data)
                if square is None:
                    messagebox.showwarning('No room', 'The %s is full.' % it.SLOT_NAMES[slot].lower())
                    break
            else:
                for old in [i for i in c.items if i.slot == slot]:
                    old.slot, old.square = it.BACKPACK, c.free_square(it.BACKPACK, sg.BACKPACK_W, sg.BACKPACK_H, self.data.height(old.gbid), self.data) or 0
                square = 0
            c.add(sg.make_item(c, self.data, info, slot, square, quality, stack=count if stackable else None))
        self.mark()
        self.show_owner()
        extra = ' with random affixes; select it to change them' if quality in (3, 6) else ''
        self.set_status('Added %s%s (not saved yet).' % (info['display'], extra))

    def duplicate(self):
        item = self.selected()
        if not item or item.slot not in (it.BACKPACK, it.STASH):
            messagebox.showinfo('Duplicate', 'Pick an item in the backpack or stash.')
            return
        c = self.current.container
        w, h = (sg.BACKPACK_W, sg.BACKPACK_H) if item.slot == it.BACKPACK else (sg.STASH_W, sg.STASH_H)
        square = c.free_square(item.slot, w, h, self.data.height(item.gbid), self.data)
        if square is None:
            messagebox.showwarning('No room', 'No free space for a copy.')
            return
        import d3save
        copy = it.Item(d3save.Message.parse(item.msg.encode()))
        copy.msg.sub(1).set(2, c.next_id())
        copy.square = square
        c.add(copy)
        self.mark()
        self.show_owner()

    def delete(self):
        item = self.selected()
        if item and messagebox.askyesno('Delete', 'Delete %s?' % self.data.item_name(item.gbid)):
            self.current.container.remove(item)
            self.mark()
            self.show_owner()

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
