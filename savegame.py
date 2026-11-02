"""A Rehydrated save folder (d3save): account (gold, shared stash) and heroes (backpack, equipment)."""
import glob, json, os, random, shutil, subprocess, time
import d3save
import items as it

def documents_dir():
    """The user's Documents folder, also when Windows moved it (OneDrive, another drive)."""
    try:
        import ctypes, uuid
        guid = uuid.UUID('FDD39AD0-238F-46AF-ADB4-6C85480369C7')   # FOLDERID_Documents
        buf = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.c_char_p(guid.bytes_le), 0, None, ctypes.byref(buf)) == 0:
            path = buf.value
            ctypes.windll.ole32.CoTaskMemFree(buf)
            return path
    except (AttributeError, OSError):
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


# Rehydrated keeps saves in <user data root>\<profile>\<title>\00000001\d3save; the default root is Documents\rehydrated.
DEFAULT_ROOT = os.path.join(documents_dir(), 'rehydrated')
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
SETTINGS = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'd3-rehydrated-save-editor.json')


def load_settings():
    try:
        with open(SETTINGS, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def store_settings(**values):
    settings = load_settings()
    settings.update(values)
    try:
        with open(SETTINGS, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=1)
    except OSError:
        pass
BACKPACK_W, BACKPACK_H = 10, 6
STASH_W, STASH_H = 7, 30         # three tabs of 7 x 10
SMALL_TYPES = {'Ring', 'Amulet', 'Belt', 'Belt_Barbarian', 'GenericBelt', 'Gem', 'HealthPotion', 'PowerPotion',
               'CraftingReagent', 'Dye', 'Gold', 'Junk', 'Book', 'Scroll', 'ScrollAngelWings', 'StoneOfRecall',
               'StoneOfWealth', 'TalismanUnlock', 'Runestone_A', 'Runestone_B', 'Runestone_C', 'Runestone_D',
               'Runestone_E', 'Runestone_Unattuned', 'CraftingPlan_Smith', 'CraftingPlan_Jeweler',
               'CraftingPlanLegendary_Smith', 'PageOfTraining_Smith', 'PageOfTraining_Jeweler', 'Quest',
               'QuestUsable', 'GeneralUtility', 'Glyph', 'HealthGlyph'}
CLASS_NAMES = {0x1D4681B1: 'Wizard', 0xC88B9649: 'Demon Hunter', 0x003DAC15: 'Monk', 0x4FB91EE2: 'Barbarian',
               0x0343C22A: 'Witch Doctor'}


def find_save_dirs(root=DEFAULT_ROOT):
    """d3save folders under a Rehydrated user data root, most recently played first. Also accepts the d3save folder
    itself or any folder in between."""
    if os.path.exists(os.path.join(root, 'account.dat')):
        return [root]
    found = set()
    for depth in range(4):
        found.update(glob.glob(os.path.join(root, *['*'] * depth, 'd3save')))
    return sorted((d for d in found if os.path.exists(os.path.join(d, 'account.dat'))), key=os.path.getmtime, reverse=True)


def game_running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq rehydrated.exe', '/NH'], capture_output=True, text=True,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    return 'rehydrated.exe' in out.lower()


class GameData:
    def __init__(self):
        with open(os.path.join(DATA, 'items.json'), encoding='utf-8') as f:
            self.items = json.load(f)
        with open(os.path.join(DATA, 'affixes.json'), encoding='utf-8') as f:
            self.affixes = json.load(f)
        self.by_gbid = {i['gbid']: i for i in self.items}
        self.affix_by_gbid = {a['gbid']: a for a in self.affixes}

    def item_name(self, gbid):
        info = self.by_gbid.get(gbid)
        return info['display'] if info else 'Unknown item (%08X)' % (gbid or 0)

    def affix_name(self, gbid):
        a = self.affix_by_gbid.get(gbid)
        return a['name'] if a else 'Unknown affix (%08X)' % (gbid & 0xFFFFFFFF)

    def affixes_for(self, info, everything=False):
        """Affixes the game may roll on this item type (kind 0 are level requirement changes, not stats)."""
        if everything:
            return list(self.affixes)
        groups = set(info.get('typeGroups', []))
        return [a for a in self.affixes if a['kind'] and groups & set(a['groups'])
                and not groups & set(a['excludedGroups'])]

    def random_affixes(self, info, count):
        """`count` regular affixes from different families, the best tier the item's level allows."""
        families = {}
        for a in self.affixes_for(info):
            if a['kind'] == 3:
                families.setdefault(a['family'], []).append(a)
        best = []
        for tiers in families.values():
            fitting = [a for a in tiers if a['level'] <= info['level']]
            best.append(max(fitting, key=lambda a: a['level']) if fitting else min(tiers, key=lambda a: a['level']))
        picks = random.sample(best, min(count, len(best)))
        return [a['gbid'] for a in picks]

    def height(self, gbid):
        info = self.by_gbid.get(gbid)
        return 1 if not info or info['type'] in SMALL_TYPES else 2


class Container:
    """Items in one save message (hero item list or account partition item list)."""

    def __init__(self, list_msg):
        self.list_msg = list_msg

    @property
    def items(self):
        return [it.Item(m) for m in self.list_msg.subs(1)]

    def remove(self, item):
        self.list_msg.fields = [f for f in self.list_msg.fields if f.msg is not item.msg]

    def add(self, item):
        self.list_msg.add_message(1, item.msg)

    def next_id(self):
        ids = [i.id_low or 0 for i in self.items]
        return max(ids + [0x7F000000]) + 1

    def free_square(self, slot, width, height, item_height, data):
        """First free top-left square in the backpack or stash grid for an item of the given height."""
        used = set()
        for i in self.items:
            if i.slot != slot:
                continue
            for dy in range(data.height(i.gbid)):
                used.add(i.square + dy * width)
        for y in range(height - item_height + 1):
            for x in range(width):
                sq = y * width + x
                if all(sq + dy * width not in used for dy in range(item_height)):
                    return sq
        return None


# Saved attribute key of the hero level (SavedAttributes entry {1: key, 2: zigzag value}); found by comparing heroes
# of different levels and confirmed in game.
LEVEL_KEY = 0x1F5F
MAX_LEVEL = 60


class Hero:
    def __init__(self, path):
        self.path = path
        self.msg = d3save.load(path)
        self.dirty = False

    digest = property(lambda s: s.msg.sub(2))
    name = property(lambda s: s.digest.get(3, b'').decode('utf-8', 'replace'))
    class_name = property(lambda s: CLASS_NAMES.get(s.digest.get(4), 'Unknown class'))
    @property
    def level(self):
        return d3save.unzigzag(self.digest.get(5, 0))

    @level.setter
    def level(self, value):
        """The hero list reads the digest; the game itself reads the saved Level attribute."""
        self.digest.set(5, d3save.zigzag(value))
        attrs = self.msg.sub(3)
        entry = next((e for e in attrs.subs(2) if e.get(1) == LEVEL_KEY), None)
        if entry is None:
            entry = d3save.Message([d3save.Field(1, d3save.VARINT, LEVEL_KEY), d3save.Field(2, d3save.VARINT, 0)])
            attrs.add_message(2, entry)
        entry.set(2, d3save.zigzag(value))
        self.dirty = True

    id_low = property(lambda s: s.digest.sub(2).get(2))

    @property
    def container(self):
        if self.msg.sub(6) is None:
            # The item list goes after the saved hero data (field 4), like the game writes it.
            fields = self.msg.fields
            at = next((i for i, f in enumerate(fields) if f.num > 6), len(fields))
            fields.insert(at, d3save.Field(6, d3save.BYTES, b'', d3save.Message()))
        return Container(self.msg.sub(6))


class Account:
    def __init__(self, path):
        self.path = path
        self.msg = d3save.load(path)
        self.dirty = False

    def partition(self, index=0):
        for p in self.msg.subs(20):
            if p.get(1, 0) == index:
                return p
        return None

    @property
    def container(self):
        return Container(self.partition(0).sub(3, create=True))

    def gold_item(self):
        for i in self.container.items:
            if i.slot == it.GOLD:
                return i
        return None

    @property
    def gold(self):
        g = self.gold_item()
        return g.stack if g else 0

    @gold.setter
    def gold(self, amount):
        g = self.gold_item()
        if g is None:
            c = self.container
            g = it.new_item(c.next_id(), GOLD_GBID, it.GOLD, 0, stack=amount)
            c.add(g)
        g.stack = amount
        self.dirty = True


GOLD_GBID = 0x07869277   # Gold1


class SaveFolder:
    def __init__(self, path):
        self.path = path
        self.account = Account(os.path.join(path, 'account.dat'))
        self.heroes = [Hero(p) for p in sorted(glob.glob(os.path.join(path, 'heroes', '*.dat')))]

    def backup(self):
        """Copies the whole save folder next to it before anything is written."""
        base = os.path.join(os.path.dirname(self.path), 'd3save-backup-' + time.strftime('%Y%m%d-%H%M%S'))
        dest, n = base, 1
        while os.path.exists(dest):   # saved twice within a second
            n += 1
            dest = '%s-%d' % (base, n)
        shutil.copytree(self.path, dest)
        return dest

    def save(self):
        if game_running():
            raise RuntimeError('Close the game first: it overwrites the saves while it runs.')
        changed = [x for x in [self.account] + self.heroes if x.dirty]
        if not changed:
            return None
        dest = self.backup()
        for x in changed:
            data = d3save.save_bytes(x.msg)
            tmp = x.path + '.tmp'
            with open(tmp, 'wb') as f:
                f.write(data)
            d3save.Message.parse(d3save.decrypt(open(tmp, 'rb').read()))   # must read back
            os.replace(tmp, x.path)
            x.dirty = False
        return dest


def make_item(container, data, info, slot, square, quality=None, affixes=(), stack=None):
    """A new item for `info` (an items.json entry) with sensible durability and stack size."""
    stackable = info['type'] in ('HealthPotion', 'Gem', 'CraftingReagent', 'Dye', 'Gold')
    if stack is None:
        stack = 1 if stackable else 0
    if quality is None:
        quality = 9 if info['legendary'] else None
    if quality in (3, 4, 5, 6, 7, 8) and not affixes:
        # Magic items roll 1-2 affixes and rares 4-6: without any the game shows a blue or yellow item with no stats.
        affixes = data.random_affixes(info, {3: 1, 4: 2, 5: 2, 6: 4, 7: 5, 8: 6}[quality])
    return it.new_item(container.next_id(), info['gbid'], slot, square, stack=stack,
                       durability=info['maxDurability'] if info['maxDurability'] > 0 and not stackable else 0,
                       quality=quality, seed=random.getrandbits(32), affixes=affixes)
