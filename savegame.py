"""A Rehydrated save folder (d3save): account (gold, shared stash) and heroes (backpack, equipment)."""
import glob, json, os, random, re, shutil, struct, subprocess, time
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


LEGENDARY_GROUP = 0xA14D315D


DAMAGE_TYPES = ['Physical', 'Fire', 'Lightning', 'Cold', 'Poison', 'Arcane', 'Holy']
RESOURCE_TYPES = ['Mana', 'Arcanum', 'Fury', 'Spirit', 'Power', 'Hatred', 'Discipline']
RESOURCE_NAMES = {'Arcanum': 'Arcane Power'}
# Stats whose description is under another name, and a few the game's string table has no entry for.
STAT_ALIASES = {'Damage_Weapon_Min': 'Damage_Weapon_Bonus_Min', 'Damage_Weapon_Delta': 'Damage_Weapon_Bonus_Delta',
                'Crit_Percent_Bonus_Capped': 'Critical_Chance', 'Crit_Damage_Percent': 'Critical_Damage_Percent'}
STAT_TEMPLATES = {
    'Damage_Weapon_Min': '+[{VALUE}] Minimum {TYPE} Damage',
    'Damage_Weapon_Delta': '+[{VALUE}] Maximum {TYPE} Damage (on top of the minimum)',
    'Resource_Max_Bonus': '[{VALUE}|+|] Maximum {RESOURCE}',
    'Resource_Regen_Per_Second': '[{VALUE}|+|] {RESOURCE} Regeneration per Second',
    'Resource_On_Hit': '[{VALUE}|+|] {RESOURCE} per Hit',
    'Resource_On_Kill': '[{VALUE}|+|] {RESOURCE} per Kill',
    'Resource_On_Crit': '[{VALUE}|+|] {RESOURCE} per Critical Hit',
    'Resource_Set_Point_Bonus': '[{VALUE}|+|] {RESOURCE} when entering a game',
    'Spending_Resource_Heals_Percent': 'Each {RESOURCE} spent heals [{VALUE}] Life',
    'Damage_Dealt_Percent_Bonus': '[{VALUE}*100|+|]% {TYPE} skill damage',
    'Damage_Percent_Bonus_Vs_Monster_Type': '[{VALUE}*100|+|]% damage against {MONSTER}',
    'Weapon_On_Hit_Bleed_Proc_Damage_Base': '[{VALUE}] Bleed damage',
    'Weapon_On_Hit_Bleed_Proc_Damage_Delta': '[{VALUE}|+|] extra Bleed damage',
    'Movement_Scalar': '[{VALUE}*100|+|]% Movement Speed',
    'Item_Indestructible': 'Ignores durability loss',
    'Durability_Max': '[{VALUE}|+|] Maximum Durability',
    'Item_Power_Passive': 'Special power',
}
MONSTER_TYPES = ['Undead', 'Demons', 'Beasts', 'Humans']


def _number(v):
    return ('%d' % round(v)) if abs(v - round(v)) < 0.005 else ('%.2f' % v).rstrip('0').rstrip('.')


def describe_stat(stat, templates):
    """One affix stat [attribute, parameter, low, high] as the game describes it: the template from
    AttributeDescriptions, with [{VALUE}*100|+|]-style parts filled in with the value range."""
    attr, param, lo, hi = stat
    names = [attr, attr.replace('_X1', ''), STAT_ALIASES.get(attr, attr)]
    resource = attr.startswith('Resource') or 'Resource' in attr
    types = RESOURCE_TYPES if resource else DAMAGE_TYPES
    keys = [n + '#' + types[param] for n in names if 0 <= param < len(types)] + names
    template = next((templates[k] for k in keys if k in templates), None) or STAT_TEMPLATES.get(attr)
    if template:
        resource_name = types[param] if resource and 0 <= param < len(types) else 'resource'
        template = (template.replace('{RESOURCE}', RESOURCE_NAMES.get(resource_name, resource_name))
                    .replace('{TYPE}', DAMAGE_TYPES[param] if 0 <= param < len(DAMAGE_TYPES) else '')
                    .replace('{MONSTER}', MONSTER_TYPES[param] if 0 <= param < len(MONSTER_TYPES) else 'monsters'))
    if lo is None:
        lo = hi = 0
    if not template:
        return '%s %s' % (attr.replace('_', ' '), _number(lo) if lo == hi else '%s-%s' % (_number(lo), _number(hi)))

    def fill(m):
        parts = m.group(1).split('|')
        expr, plus = parts[0], len(parts) > 1 and '+' in parts[1]
        while expr.count('}') > expr.count('{'):     # some templates have a stray brace: [{VALUE}*100}]
            expr = expr[:expr.rindex('}')] + expr[expr.rindex('}') + 1:]
        if '{VALUE2}' in expr.upper():      # already a range, e.g. Sockets ([{VALUE}-{VALUE2}])
            return _number(lo) if lo == hi else '%s-%s' % (_number(lo), _number(hi))
        values = []
        for v in (lo, hi):
            e = re.sub(r'\{VALUE\d?\}', repr(v), expr, flags=re.I)
            if not re.fullmatch(r'[0-9.+\-*/() e]+', e):
                return m.group(0)
            values.append(eval(e))
        text = _number(values[0]) if abs(values[0] - values[1]) < 0.005 else '%s-%s' % (_number(values[0]), _number(values[1]))
        return ('+' if plus and values[0] >= 0 else '') + text
    text = re.sub(r'\[([^\]]*\{VALUE\d?\}[^\]]*)\]', fill, template, flags=re.I)
    text = re.sub(r'\{VALUE\d?\}', _number(lo) if lo == hi else '%s-%s' % (_number(lo), _number(hi)), text, flags=re.I)
    return re.sub(r'\{/?c[^}]*\}', '', text).strip()


class GameData:
    def __init__(self):
        with open(os.path.join(DATA, 'items.json'), encoding='utf-8') as f:
            self.items = json.load(f)
        with open(os.path.join(DATA, 'affixes.json'), encoding='utf-8') as f:
            self.affixes = json.load(f)
        self.by_gbid = {i['gbid']: i for i in self.items}
        self.affix_by_gbid = {a['gbid']: a for a in self.affixes}
        try:
            with open(os.path.join(DATA, 'text.json'), encoding='utf-8') as f:
                text = json.load(f)
        except OSError:
            text = {}
        self.stat_text = text.get('attributes', {})
        self.rare_words = {int(k): v for k, v in text.get('rareNames', {}).items()}

    def item_name(self, gbid):
        info = self.by_gbid.get(gbid)
        return info['display'] if info else 'Unknown item (%08X)' % (gbid or 0)

    def affix_name(self, gbid):
        a = self.affix_by_gbid.get(gbid)
        return a['name'] if a else 'Unknown affix (%08X)' % (gbid & 0xFFFFFFFF)

    def affix_effects(self, gbid):
        """What the affix does, in the game's own words, e.g. ['+46-56 Strength']."""
        a = self.affix_by_gbid.get(gbid)
        return [describe_stat(st, self.stat_text) for st in a.get('stats', [])] if a else []

    def affix_label(self, gbid):
        effects = self.affix_effects(gbid)
        return '%s (%s)' % (', '.join(effects), self.affix_name(gbid)) if effects else self.affix_name(gbid)

    def sockets(self, affixes):
        return int(sum(st[2] or 0 for g in affixes for st in self.affix_by_gbid.get(g, {}).get('stats', [])
                       if st[0] == 'Sockets'))

    def rare_name_choices(self, info, affixes):
        """Every name a rare of this item type with these affixes can have: [(text, rare_name value)], each a word
        from an affix's list and one from the item type's (item word first or last)."""
        prefix_list, suffix_list = (info.get('rareNameLists') or [None, None])[:2]
        out, seen = [], set()
        for g in affixes:
            a_prefix, a_suffix = (self.affix_by_gbid.get(g, {}).get('rareNameLists') or [None, None])[:2]
            for first_words, first_sno, last_words, last_sno, item_first in (
                    (self.rare_words.get(a_prefix), a_prefix, self.rare_words.get(suffix_list), suffix_list, False),
                    (self.rare_words.get(prefix_list), prefix_list, self.rare_words.get(a_suffix), a_suffix, True)):
                if not first_words or not last_words:
                    continue
                for i, w1 in enumerate(first_words):
                    for j, w2 in enumerate(last_words):
                        text = '%s %s' % (w1, w2)
                        if text in seen:
                            continue
                        seen.add(text)
                        value = (True, last_sno, j, i) if item_first else (False, first_sno, i, j)
                        out.append((text, value))
        return sorted(out)

    def random_rare_name(self, info, affixes):
        choices = self.rare_name_choices(info, affixes)
        return random.choice(choices)[1] if choices else None

    def rare_name_text(self, info, value):
        if not value:
            return None
        item_first, sno, affix_index, item_index = value
        prefix_list, suffix_list = (info.get('rareNameLists') or [None, None])[:2]
        item_words = self.rare_words.get(prefix_list if item_first else suffix_list) or []
        affix_words = self.rare_words.get(sno & 0xFFFFFFFF) or []
        if not 0 <= item_index < len(item_words) or not 0 <= affix_index < len(affix_words):
            return None
        return ' '.join((item_words[item_index], affix_words[affix_index]) if item_first else
                        (affix_words[affix_index], item_words[item_index]))

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

    def legendary_affixes(self, info):
        """The affixes a legendary rolls when it drops: one per family listed on the item, from the affixes of that
        family a legendary can have up to the listed affix level (the best tier, so created items are good rolls)."""
        # Legendary-only affixes name the group of all legendaries and rule item types out by exclusion.
        groups = set(info.get('typeGroups', [])) | {LEGENDARY_GROUP}
        out = []
        for family, max_level in info.get('affixRolls', []):
            tiers = [a for a in self.affixes if family in (a['family'], a.get('family2')) and a['qualityMask'] & (1 << 9)]
            fits_type = [a for a in tiers if groups & set(a['groups']) and not groups & set(a['excludedGroups'])]
            tiers = fits_type or tiers
            fitting = [a for a in tiers if a['level'] <= max_level] or sorted(tiers, key=lambda a: a['level'])[:1]
            if fitting:
                top = max(a['level'] for a in fitting)
                out.append(random.choice([a for a in fitting if a['level'] == top])['gbid'])
        return out

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

    def socket_items(self, item):
        return [i for i in self.items if i.slot == it.SOCKET and i.socket_of == item.id_low]

    def set_gems(self, item, gbids):
        """Puts these gems in the item's sockets, replacing the ones there, in both places the game keeps them."""
        for old in self.socket_items(item):
            self.remove(old)
        ids = []
        for g in gbids:
            ids.append(self.next_id() + len(ids))
        item.set_gems(gbids, ids)
        for g, gem_id in zip(gbids, ids):
            gem = it.new_item(gem_id, g, it.SOCKET, 0, stack=1)
            gem.msg.fields.insert(1, d3save.Field(3, d3save.BYTES, b'', d3save.Message(
                [d3save.Field(1, d3save.VARINT, 1), d3save.Field(2, d3save.VARINT, item.id_low)])))
            self.add(gem)

    def remove_with_gems(self, item):
        for gem in self.socket_items(item):
            self.remove(gem)
        self.remove(item)

    def next_id(self):
        """A free item id; socketed gems have ids of their own too."""
        ids = [i.id_low or 0 for i in self.items]
        ids += [e.sub(1).get(2, 0) for i in self.items for e in i.gen.subs(13)]
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


# Saved attribute keys (SavedAttributes entry {1: key, 2: zigzag value}), found by comparing heroes of different
# levels and classes and confirmed in game. The base stats are floats (zigzag of the IEEE bits) the game raises at
# every level-up, so a level change has to set them too.
LEVEL_KEY = 0x1F5F
STAT_KEYS = {'Strength': 0x1EFB, 'Dexterity': 0x1EF7, 'Intelligence': 0x1EF3, 'Vitality': 0x1EDF}
MAX_LEVEL = 60
# Level 1 base stats and the gain per level: the main stat of the class +3, Vitality +2, the others +1.
CLASS_MAIN_STAT = {'Barbarian': 'Strength', 'Demon Hunter': 'Dexterity', 'Monk': 'Dexterity',
                   'Witch Doctor': 'Intelligence', 'Wizard': 'Intelligence'}


def base_stats(class_name, level):
    main = CLASS_MAIN_STAT.get(class_name)
    stats = {}
    for stat in STAT_KEYS:
        start, gain = (10, 3) if stat == main else (9, 2) if stat == 'Vitality' else (8, 1)
        stats[stat] = float(start + gain * (level - 1))
    return stats


EXPERIENCE_NEXT_KEY = 0x1F7F
# Experience needed from each level to the next (levels 1-60), from the game's ExperienceTable; the console saves
# a fresh level-1 hero with the same 1200.
LEVEL_XP = [1200, 3900, 8400, 15000, 24000, 35700, 50400, 68025, 88825, 113050, 140950, 172775, 208775, 250250, 288750,
            329000, 371000, 414750, 460250, 507500, 556500, 610875, 674625, 748250, 832250, 927125, 1033375, 1151500,
            1282000, 1416125, 1560125, 1716925, 1886925, 2070525, 2268125, 2480125, 2706925, 2948925, 3206525, 3480125,
            3770125, 4076925, 4400925, 4742525, 5102125, 5480125, 5876925, 6292925, 6728525, 7184125, 8240125, 9367125,
            10567125, 11842125, 13194125, 14625125, 16137125, 17732125, 19412125, 21179125]
DIFFICULTIES = ['Normal', 'Nightmare', 'Hell', 'Inferno']
# The game numbers acts 0, 100, 200, 300 (Act I-IV). Any other act makes it exit with a fatal error when the hero
# enters the game, as it finds no world to put them in.
ACT_STEP = 100
# Hero digest player_flags, as the client reads them (bit 1 is a female hero).
HARDCORE_FLAG, DEAD_FLAG = 0x1, 0x8


def load_quests():
    """Story quests per act (data/quests.json): [{sno, name, steps: [{uid, text}], completed}]."""
    try:
        with open(os.path.join(DATA, 'quests.json'), encoding='utf-8') as f:
            return json.load(f)
    except OSError:
        return [[], [], [], []]


def _insert_field(msg, field, before):
    """Adds a field in front of the first field numbered above `before`, the order the game writes them in."""
    at = next((i for i, f in enumerate(msg.fields) if f.num > before), len(msg.fields))
    msg.fields.insert(at, field)


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
        """The hero list reads the digest; the game reads the saved Level and base stat attributes."""
        self.digest.set(5, d3save.zigzag(value))
        self.set_attribute(LEVEL_KEY, d3save.zigzag(value))
        self.set_attribute(EXPERIENCE_NEXT_KEY, d3save.zigzag(LEVEL_XP[value - 1]))   # an empty bar at the new level
        if self.class_name in CLASS_MAIN_STAT:
            for stat, amount in base_stats(self.class_name, value).items():
                bits, = struct.unpack('<i', struct.pack('<f', amount))
                self.set_attribute(STAT_KEYS[stat], d3save.zigzag(bits))
        self.dirty = True

    def attribute(self, key):
        return next((e.get(2) for e in self.msg.sub(3).subs(2) if e.get(1) == key), None)

    def set_attribute(self, key, raw):
        attrs = self.msg.sub(3)
        entry = next((e for e in attrs.subs(2) if e.get(1) == key), None)
        if entry is None:
            entry = d3save.Message([d3save.Field(1, d3save.VARINT, key), d3save.Field(2, d3save.VARINT, 0)])
            attrs.add_message(2, entry)
        entry.set(2, raw)

    id_low = property(lambda s: s.digest.sub(2).get(2))

    def unlock_followers(self):
        """Makes the Templar, Scoundrel and Enchantress available (normally done by the Act 1/2 quests) and brings
        the Templar along, so follower gear can be used and seen."""
        data = self.msg.sub(4, create=True).sub(3, create=True)
        data.set(3, 0xE)          # available hirelings, a bit per hireling class (1-3)
        if not data.get(2):
            data.set(2, 1)        # active hireling: Templar
        self.dirty = True

    # --- progress
    def _dz(self, num, default=0):
        return d3save.unzigzag(self.digest.get(num, d3save.zigzag(default)))

    flags = property(lambda s: s.digest.get(6, 0))
    hardcore = property(lambda s: bool(s.flags & HARDCORE_FLAG))
    dead = property(lambda s: bool(s.flags & DEAD_FLAG))
    highest_difficulty = property(lambda s: s._dz(12))

    @property
    def last_played(self):
        """(difficulty, act, quest sno, step uid) the game starts the hero at."""
        q = self.digest.get(13, 0xFFFFFFFF)
        return self._dz(11), self._dz(9) // ACT_STEP, q - (1 << 32) if q >= 1 << 31 else q, self._dz(14, -1)

    def unlock_progress(self, difficulty, quests):
        """Unlocks every act and every difficulty up to `difficulty` (0 Normal .. 3 Inferno): all story quests count
        as played to their end on those difficulties, so any quest and checkpoint can be picked when starting a game."""
        d = self.digest
        d.set(10, d3save.zigzag(3 * ACT_STEP))                             # highest unlocked act: Act IV
        d.set(12, d3save.zigzag(max(difficulty, self.highest_difficulty)))
        d.set(16, d3save.zigzag(max(difficulty - 1, self._dz(16, -1))))   # highest completed difficulty
        had = {(e.get(1), d3save.unzigzag(e.get(2, 0))) for e in d.subs(8)}
        for diff in range(difficulty + 1):
            for act in quests:
                for q in act:
                    if (q['sno'], diff) in had:
                        continue
                    entry = d3save.Message([d3save.Field(1, d3save.FIXED32, q['sno'] & 0xFFFFFFFF),
                                            d3save.Field(2, d3save.VARINT, d3save.zigzag(diff)),
                                            d3save.Field(3, d3save.VARINT, d3save.zigzag(q['completed']))])
                    if d.first(8):
                        d.insert_message_after(8, entry)
                    else:
                        _insert_field(d, d3save.Field(8, d3save.BYTES, b'', entry), 8)
        saved = self.msg.sub(4)
        if saved is not None:
            saved.set(2, 0xFFFFFFFF)   # activated waypoints
        self.dirty = True

    def start_at(self, difficulty, act, sno, step):
        """Where the hero starts the next game: the quest and checkpoint shown under "Resume" when starting a game.
        `act` is 0 for Act I .. 3 for Act IV."""
        d = self.digest
        for num, value in ((9, act * ACT_STEP), (11, difficulty)):
            d.set(num, d3save.zigzag(value))
        d.set(13, sno & 0xFFFFFFFF, d3save.FIXED32)
        d.set(14, d3save.zigzag(step))
        # The quest in progress: replace the saved quest state with the chosen quest at the chosen step.
        self.msg.remove(5)
        quest = d3save.Message([d3save.Field(1, d3save.FIXED32, sno & 0xFFFFFFFF),
                                d3save.Field(2, d3save.VARINT, d3save.zigzag(difficulty)),
                                d3save.Field(3, d3save.VARINT, d3save.zigzag(step))])
        _insert_field(self.msg, d3save.Field(5, d3save.BYTES, b'', quest), 5)
        self.dirty = True

    def revive(self):
        """Brings a dead hardcore hero back: clears the dead flag and the name of what killed them."""
        self.digest.set(6, self.flags & ~DEAD_FLAG)
        console = self.msg.sub(10)
        if console is not None:
            console.remove(3)
        self.dirty = True

    @property
    def container(self):
        if self.msg.sub(6) is None:
            # The item list goes after the saved hero data (field 4), like the game writes it.
            fields = self.msg.fields
            at = next((i for i, f in enumerate(fields) if f.num > 6), len(fields))
            fields.insert(at, d3save.Field(6, d3save.BYTES, b'', d3save.Message()))
        return Container(self.msg.sub(6))


# Account partitions: 0 holds normal heroes' shared stash, gold and Paragon level, 1 the same for hardcore heroes.
PARTITION_NAMES = {0: 'Normal', 1: 'Hardcore'}
# Account attribute keys (partition field 2), mapped in game like the hero keys: Paragon level and the experience
# still needed for the next Paragon level, which the game reads from this table (console values, levels 0..99).
ALT_LEVEL_KEY, ALT_XP_NEXT_KEY = 0x1FF9, 0x1FFB
MAX_PARAGON = 100
STASH_SLOTS_KEY, STASH_TAB_SLOTS = 0x1FFF, 70
ARTISANS = ['Blacksmith', 'Jeweler']   # the save keeps a third (Mystic) the console game has no use for
MAX_ARTISAN = 10
PARAGON_XP = [7200000 + 1440000 * n for n in range(59)] + [
    92160000, 95040000, 97920000, 100800000, 103680000, 106560000, 109440000, 112320000, 115200000, 118080000,
    120960000, 126000000, 131040000, 136080000, 141120000, 146160000, 151200000, 156240000, 161280000, 166320000,
    171360000, 177840000, 184320000, 190800000, 197280000, 203760000, 210240000, 216720000, 223200000, 229680000,
    236160000, 244800000, 253440000, 262080000, 270720000, 279360000, 288000000, 296640000, 305280000, 313920000,
    322560000]


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
    def partitions(self):
        """Partitions the editor shows (normal, and hardcore when the save has it)."""
        return [i for i in PARTITION_NAMES if self.partition(i) is not None]

    def stash(self, index=0):
        return Container(self.partition(index).sub(3, create=True))

    @property
    def container(self):
        return self.stash(0)

    def gold_item(self, index=0):
        for i in self.stash(index).items:
            if i.slot == it.GOLD:
                return i
        return None

    def get_gold(self, index=0):
        g = self.gold_item(index)
        return g.stack if g else 0

    def set_gold(self, amount, index=0):
        g = self.gold_item(index)
        if g is None:
            c = self.stash(index)
            g = it.new_item(c.next_id(), GOLD_GBID, it.GOLD, 0, stack=amount)
            c.add(g)
        g.stack = amount
        self.dirty = True

    gold = property(get_gold, set_gold)

    def _attribute(self, index, key):
        attrs = self.partition(index).sub(2, create=True)
        return next((e for e in attrs.subs(2) if e.get(1) == key), None), attrs

    def get_paragon(self, index=0):
        entry, _ = self._attribute(index, ALT_LEVEL_KEY)
        return d3save.unzigzag(entry.get(2, 0)) if entry else 0

    def set_paragon(self, level, index=0):
        """Paragon level for every hero of the partition; their bonus stats follow from it in game."""
        level = max(0, min(level, MAX_PARAGON))
        for key, value in ((ALT_LEVEL_KEY, level), (ALT_XP_NEXT_KEY, PARAGON_XP[level] if level < MAX_PARAGON else 0)):
            entry, attrs = self._attribute(index, key)
            if entry is None:
                entry = d3save.Message([d3save.Field(1, d3save.VARINT, key), d3save.Field(2, d3save.VARINT, 0)])
                attrs.add_message(2, entry)
            entry.set(2, d3save.zigzag(value))
        self.partition(index).set(8, level)          # alt_level copies the game keeps next to the attributes
        if index == 0:
            self.msg.sub(2).set(6, level)
        self.dirty = True

    # Shared_Stash_Slots (attribute 9): 70 per stash tab, at most 210 (the attribute's bounds in the game).
    def get_stash_tabs(self, index=0):
        entry, _ = self._attribute(index, STASH_SLOTS_KEY)
        return max(1, -(-d3save.unzigzag(entry.get(2, 0)) // STASH_TAB_SLOTS)) if entry else 1

    def set_stash_tabs(self, tabs, index=0):
        tabs = max(1, min(tabs, 3))
        entry, attrs = self._attribute(index, STASH_SLOTS_KEY)
        if entry is None:
            entry = d3save.Message([d3save.Field(1, d3save.VARINT, STASH_SLOTS_KEY), d3save.Field(2, d3save.VARINT, 0)])
            attrs.add_message(2, entry)
        entry.set(2, d3save.zigzag(tabs * STASH_TAB_SLOTS))
        self.dirty = True

    # Artisans: partition field 4 holds one CrafterData per artisan {1: learned recipes, 3: level, 4: cooldown}.
    def crafters(self, index=0):
        return self.partition(index).sub(4, create=True).subs(1)

    def get_artisan(self, artisan, index=0):
        c = self.crafters(index)
        return c[artisan].get(3, 0) if artisan < len(c) else 0

    def set_artisan(self, artisan, level, index=0):
        data = self.partition(index).sub(4, create=True)
        while len(data.subs(1)) <= artisan:
            data.add_message(1, d3save.Message([d3save.Field(3, d3save.VARINT, 0), d3save.Field(4, d3save.VARINT, 0)]))
        data.subs(1)[artisan].set(3, max(0, min(level, MAX_ARTISAN)))
        self.dirty = True

    hardcore_unlocked = property(lambda s: bool(s.msg.sub(2).get(4, 0) & 1))

    def unlock_hardcore(self):
        """Lets new hardcore heroes be created (normally after a hero reaches level 10)."""
        self.msg.sub(2).set(4, self.msg.sub(2).get(4, 0) | 1)   # Account.Digest.flags HARDCORE_HERO_UNLOCKED
        self.dirty = True


GOLD_GBID = 0x07869277   # Gold1


class SaveFolder:
    def __init__(self, path):
        self.path = path
        self.account = Account(os.path.join(path, 'account.dat'))
        self.heroes = [Hero(p) for p in sorted(glob.glob(os.path.join(path, 'heroes', '*.dat')))]

    def clone_hero(self, hero, name):
        """A copy of a hero under a new name and id (the file name is the id)."""
        ids = {h.id_low for h in self.heroes}
        low = random.getrandbits(63) | 1
        while low in ids:
            low = random.getrandbits(63) | 1
        copy = Hero.__new__(Hero)
        copy.path = os.path.join(self.path, 'heroes', '%016x.dat' % low)
        copy.msg = d3save.Message.parse(hero.msg.encode())
        copy.digest.sub(2).set(2, low)
        copy.digest.set(3, name.encode('utf-8'), d3save.BYTES)
        copy.dirty = True
        self.heroes.append(copy)
        return copy

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


PRESET_FORMAT = 'd3-x360-rehydrated-item'


def item_preset(item):
    """An item as a preset (JSON-able): the saved item record and the gems in its sockets."""
    import base64
    return {'format': PRESET_FORMAT, 'version': 1, 'item': base64.b64encode(item.msg.encode()).decode(),
            'gems': [g.gbid for g in item.gems]}


def place_item(msg, gems, container, slot, square, hireling=0):
    """Adds a copy of a saved item record to a container with a new id, at the given place, with its own gems."""
    item = it.Item(d3save.Message.parse(msg.encode()))
    item.msg.sub(1).set(2, container.next_id())
    item.gen.remove(13)                  # the gems get new ids below
    item.msg.remove(3)                   # no longer socketed in anything
    if item.msg.first(7) is not None:
        item.msg.set(7, 0)
    item.slot, item.square, item.hireling = slot, square, hireling
    container.add(item)
    if gems:
        container.set_gems(item, gems)
    return item


def preset_record(preset):
    """The item record and gems of a preset; raises ValueError for anything else."""
    import base64
    if not isinstance(preset, dict) or preset.get('format') != PRESET_FORMAT:
        raise ValueError('not an item preset of this editor')
    msg = d3save.Message.parse(base64.b64decode(preset['item']))
    if it.Item(msg).gbid is None:
        raise ValueError('the preset holds no item')
    return msg, [int(g) for g in preset.get('gems', [])]


def grid_of(slot):
    return (BACKPACK_W, BACKPACK_H) if slot == it.BACKPACK else (STASH_W, STASH_H)


def make_item(container, data, info, slot, square, quality=None, affixes=(), stack=None):
    """A new item for `info` (an items.json entry) with sensible durability and stack size."""
    stackable = info['type'] in ('HealthPotion', 'Gem', 'CraftingReagent', 'Dye', 'Gold')
    if stack is None:
        stack = 1 if stackable else 0
    if quality is None:
        quality = 9 if info['legendary'] else None
    if quality == 9 and not affixes:
        affixes = data.legendary_affixes(info)
    if quality in (3, 4, 5, 6, 7, 8) and not affixes:
        # Magic items roll 1-2 affixes and rares 4-6: without any the game shows a blue or yellow item with no stats.
        affixes = data.random_affixes(info, {3: 1, 4: 2, 5: 2, 6: 4, 7: 5, 8: 6}[quality])
    item = it.new_item(container.next_id(), info['gbid'], slot, square, stack=stack,
                       durability=info['maxDurability'] if info['maxDurability'] > 0 and not stackable else 0,
                       quality=quality, seed=random.getrandbits(32), affixes=affixes)
    if quality in (6, 7, 8):
        item.rare_name = data.random_rare_name(info, affixes)   # rares always carry a name
    return item
