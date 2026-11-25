"""Pipeline settings. Every number here is a starting point to tune on the 1% sample run."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

LANGS = ["en", "hi", "es", "pt", "ja", "fr", "ar"]
MAX_ALIASES_PER_LANG = 8

# ------------------------------------------------------------------ selection targets
TARGET_REAL = int(os.environ.get("MR_TARGET_REAL", "350000"))
TARGET_FICTIONAL = int(os.environ.get("MR_TARGET_FICTIONAL", "150000"))
# Pass 1 keeps every human with at least this many Wikipedia sitelinks; the final
# threshold N is then chosen so that about TARGET_REAL people remain.
HUMAN_PREFILTER_SITELINKS = int(os.environ.get("MR_HUMAN_PREFILTER", "3"))
# Non-human items need at least this many sitelinks to be kept as possible characters,
# works, countries, occupations and other attribute values.
TYPED_PREFILTER_SITELINKS = int(os.environ.get("MR_TYPED_PREFILTER", "1"))

# Sitelink keys that end in "wiki" but are not Wikipedias.
NON_WIKIPEDIA_SITES = {
    "commonswiki", "specieswiki", "metawiki", "wikidatawiki", "mediawikiwiki", "sourceswiki",
    "incubatorwiki", "foundationwiki", "outreachwiki", "wikimaniawiki", "wikifunctionswiki",
}

# ------------------------------------------------------------------ Wikidata ids
Q_HUMAN = 5
# Roots whose subclass trees count as "fictional character". Q95074 fictional character,
# Q178885 deity, Q2239243 mythical creature. Classes whose English label matches
# FICTIONAL_ROOT_LABEL_PATTERNS are added as roots too, because the Q-numbers for
# "mythical character" and "legendary figure" could not be verified; the run report
# lists every class picked up this way.
FICTIONAL_ROOT_QIDS = [95074, 178885, 2239243]
FICTIONAL_ROOT_LABEL_PATTERNS = [
    r"^(mythological|mythical|legendary|folklore) (character|figure|hero|heroine|being|creature)$",
    r"^(hindu|greek|roman|norse|egyptian|japanese|chinese) (deity|god|goddess|mythological figure)$",
]
DEITY_ROOT_QIDS = [178885]

GENDER_MAP = {
    6581097: "male", 6581072: "female", 2449503: "male", 1052281: "female",
    44148: "male", 43445: "female", 48270: "nonbinary", 1097630: "nonbinary",
}

# Continents (P30). Oceania appears under several items.
CONTINENT_REGION = {
    48: "asia", 15: "africa", 46: "europe", 49: "north_america", 18: "latin_america",
    538: "oceania", 55643: "oceania", 3960: "oceania", 51: "antarctica",
}

# ------------------------------------------------------------------ properties
# Pass 1 / typed items: item-valued claims kept as lists of numeric ids.
TYPED_ITEM_PROPS = [
    "P31", "P279", "P21", "P27", "P17", "P30", "P495", "P1366", "P1441", "P1080", "P8345",
    "P179", "P170", "P50", "P641", "P175", "P2563", "P106", "P1884", "P1340", "P361", "P463",
]
HUMAN_ITEM_PROPS = [
    "P31", "P21", "P27", "P106", "P641", "P54", "P166", "P39", "P102", "P136", "P1303",
    "P69", "P463", "P1412", "P103", "P800", "P1884", "P1340", "P19",
]
TIME_PROPS = ["P569", "P570"]

PAGEVIEW_MONTHS = 12
# Wikis whose pageviews count toward popularity. Big wikis plus the game's languages.
PAGEVIEW_WIKIS = [
    "en", "de", "fr", "es", "ja", "ru", "it", "zh", "pt", "ar", "hi", "ko", "pl", "nl", "fa",
    "tr", "id", "vi", "uk", "sv", "he", "bn", "ta", "te", "mr", "ml", "ur", "th", "ms", "fil",
]

# ------------------------------------------------------------------ popularity
# popularity = SITELINK_WEIGHT * ln(1 + sitelinks) + PAGEVIEW_WEIGHT * ln(1 + pageviews_12m)
SITELINK_WEIGHT = 1.0
PAGEVIEW_WEIGHT = 0.6


# ------------------------------------------------------------------ attribute groups
@dataclass(frozen=True)
class Group:
    id: int
    key: str
    scope: str            # all | real | fictional
    p_match: float
    p_other: float
    min_support: int
    max_questions: int
    template: str         # English question template; {label} is the value label
    description: str
    rollup_depth: int = 0  # how many P279 levels of ancestors to add as extra values


GROUPS: list[Group] = [
    Group(1, "kind", "all", 0.97, 0.03, 1, 1, "", "Real person or fictional character"),
    Group(2, "gender", "all", 0.95, 0.04, 50, 3, "", "Gender from P21; trans women count as female, trans men as male"),
    Group(3, "vital", "real", 0.95, 0.05, 1, 1, "", "Alive or dead (P570)"),
    Group(4, "birth_year", "real", 0.95, 0.05, 1, 20, "", "Birth year (P569); questions are thresholds such as born after 1990"),
    Group(5, "region", "all", 0.93, 0.08, 1, 12, "", "World region from citizenship (P27) or country of origin of the work (P495)"),
    Group(6, "country", "all", 0.93, 0.08, 200, 150, "Is your character from {label}?", "Country of citizenship, mapped to the current country when there is one successor"),
    Group(7, "occupation", "all", 0.92, 0.12, 150, 600, "Is your character a {label}?", "Occupation (P106) plus parent occupations", rollup_depth=3),
    Group(8, "sport", "all", 0.92, 0.08, 100, 60, "Is your character known for {label}?", "Sport (P641), also inferred from occupation"),
    Group(9, "team", "real", 0.92, 0.12, 120, 400, "Has your character played for {label}?", "Sports team (P54)"),
    Group(10, "award", "real", 0.9, 0.15, 150, 300, "Has your character won the {label}?", "Awards (P166) plus parent awards", rollup_depth=2),
    Group(11, "position", "real", 0.92, 0.1, 30, 400, "Has your character been {label}?", "Positions held (P39) plus parent positions", rollup_depth=2),
    Group(12, "party", "real", 0.9, 0.1, 200, 80, "Is your character a member of the {label}?", "Political party (P102)"),
    Group(13, "genre", "real", 0.85, 0.15, 200, 120, "Is your character known for {label}?", "Genre (P136) for musicians and writers"),
    Group(14, "instrument", "real", 0.88, 0.15, 150, 60, "Does your character play the {label}?", "Instrument (P1303)"),
    Group(15, "educated_at", "real", 0.88, 0.1, 300, 150, "Did your character study at {label}?", "Educated at (P69)"),
    Group(16, "member_of", "all", 0.93, 0.08, 3, 3000, "Is your character a member of {label}?", "Member of (P463): bands, groups, teams of heroes"),
    Group(17, "language", "real", 0.85, 0.2, 300, 80, "Does your character speak {label}?", "Languages spoken (P1412) and native language (P103)"),
    Group(18, "notable_work", "real", 0.88, 0.1, 3, 4000, "Is your character known for {label}?", "Notable work (P800)"),
    Group(19, "franchise", "fictional", 0.95, 0.06, 3, 6000, "Is your character from {label}?", "Media franchise (P8345), narrative universe (P1080), series (P179), from the character or its works"),
    Group(20, "work", "fictional", 0.93, 0.08, 3, 8000, "Does your character appear in {label}?", "Present in work (P1441)"),
    Group(21, "medium", "fictional", 0.9, 0.15, 1, 12, "", "Film, TV, anime, manga, comics, video game, book, animation; from the works' classes"),
    Group(22, "creator", "fictional", 0.9, 0.08, 5, 1500, "Was your character created by {label}?", "Creator (P170) or author of the work (P50)"),
    Group(23, "char_type", "fictional", 0.92, 0.08, 1, 40, "", "Species or type from the character's classes: human, animal, robot, alien, deity..."),
    Group(24, "power", "fictional", 0.9, 0.25, 20, 200, "Does your character have this power: {label}?", "Superhuman abilities (P2563)"),
    Group(25, "hair_color", "all", 0.88, 0.1, 50, 20, "Does your character have {label}?", "Hair colour (P1884)"),
    Group(26, "eye_color", "all", 0.85, 0.12, 50, 15, "Does your character have {label}?", "Eye colour (P1340)"),
    Group(27, "played_character", "real", 0.93, 0.1, 1, 20000, "Has your character played {label}?", "Actor of a fictional character (reverse of P175 on the character)"),
    Group(28, "played_in_franchise", "real", 0.9, 0.1, 3, 3000, "Has your character acted in {label}?", "Franchises of the characters the actor played"),
]
GROUPS_BY_KEY = {g.key: g for g in GROUPS}

# Fixed questions for groups without a {label} template.
FIXED_QUESTIONS: dict[str, list[tuple[str, str, list[str]]]] = {
    # group: [(question key suffix, English text, value keys that mean "yes")]
    "kind": [("real", "Is your character a real person?", ["real"])],
    "gender": [("male", "Is your character male?", ["male"]),
               ("female", "Is your character female?", ["female"])],
    "vital": [("alive", "Is your character still alive?", ["alive"])],
    "region": [
        ("asia", "Is your character from Asia?", ["south_asia", "east_asia", "southeast_asia", "middle_east", "asia"]),
        ("south_asia", "Is your character from South Asia (India, Pakistan, Bangladesh, Sri Lanka, Nepal)?", ["south_asia"]),
        ("east_asia", "Is your character from East Asia (China, Japan, Korea, Taiwan, Mongolia)?", ["east_asia"]),
        ("southeast_asia", "Is your character from Southeast Asia?", ["southeast_asia"]),
        ("middle_east", "Is your character from the Middle East?", ["middle_east"]),
        ("europe", "Is your character from Europe?", ["europe"]),
        ("africa", "Is your character from Africa?", ["africa"]),
        ("north_america", "Is your character from the United States or Canada?", ["north_america"]),
        ("latin_america", "Is your character from Latin America or the Caribbean?", ["latin_america"]),
        ("oceania", "Is your character from Australia, New Zealand or the Pacific?", ["oceania"]),
    ],
    "medium": [
        ("film", "Is your character known from movies?", ["film"]),
        ("tv", "Is your character from a TV series?", ["tv"]),
        ("anime", "Is your character from an anime?", ["anime"]),
        ("manga", "Is your character from a manga?", ["manga"]),
        ("comics", "Is your character from comic books?", ["comics"]),
        ("video_game", "Is your character from a video game?", ["video_game"]),
        ("book", "Does your character come from a book?", ["book"]),
        ("animated", "Is your character animated (a cartoon)?", ["animated", "anime"]),
        ("mythology", "Is your character from mythology, religion or folklore?", ["mythology"]),
    ],
    "char_type": [
        ("human", "Is your character human?", ["human"]),
        ("animal", "Is your character an animal?", ["animal", "dog", "cat", "bird", "fish", "rodent", "bear", "pokemon"]),
        ("dog", "Is your character a dog?", ["dog"]),
        ("cat", "Is your character a cat?", ["cat"]),
        ("bird", "Is your character a bird?", ["bird"]),
        ("robot", "Is your character a robot, android or AI?", ["robot"]),
        ("alien", "Is your character an alien?", ["alien"]),
        ("deity", "Is your character a god or goddess?", ["deity"]),
        ("demon", "Is your character a demon or devil?", ["demon"]),
        ("vampire", "Is your character a vampire?", ["vampire"]),
        ("ghost", "Is your character a ghost or spirit?", ["ghost"]),
        ("dragon", "Is your character a dragon?", ["dragon"]),
        ("monster", "Is your character a monster or creature?", ["monster", "dragon", "demon", "vampire"]),
        ("superhero", "Is your character a superhero?", ["superhero"]),
        ("villain", "Is your character a villain?", ["villain"]),
        ("mutant", "Is your character a mutant?", ["mutant"]),
        ("magic_user", "Is your character a wizard, witch or sorcerer?", ["magic_user"]),
        ("pokemon", "Is your character a Pokemon?", ["pokemon"]),
    ],
}

# Birth-year thresholds: (key, text, lower bound inclusive, upper bound exclusive)
BIRTH_YEAR_QUESTIONS: list[tuple[str, str, int | None, int | None]] = [
    ("after_2000", "Was your character born in 2000 or later?", 2000, None),
    ("after_1990", "Was your character born in 1990 or later?", 1990, None),
    ("after_1980", "Was your character born in 1980 or later?", 1980, None),
    ("after_1970", "Was your character born in 1970 or later?", 1970, None),
    ("after_1960", "Was your character born in 1960 or later?", 1960, None),
    ("after_1950", "Was your character born in 1950 or later?", 1950, None),
    ("after_1940", "Was your character born in 1940 or later?", 1940, None),
    ("after_1920", "Was your character born in 1920 or later?", 1920, None),
    ("after_1900", "Was your character born in 1900 or later?", 1900, None),
    ("before_1850", "Did your character live before 1850?", None, 1850),
    ("before_1700", "Did your character live before 1700?", None, 1700),
    ("before_1500", "Did your character live before 1500?", None, 1500),
    ("before_1000", "Did your character live more than 1,000 years ago?", None, 1000),
    ("bce", "Did your character live before the year 1 (BCE)?", None, 1),
]

# Region overrides by country (Wikidata numeric id). Anything not listed falls back
# to the country's continent via CONTINENT_REGION. North America minus the US and
# Canada is Latin America.
REGION_BY_COUNTRY: dict[int, str] = {
    # South Asia
    668: "south_asia", 843: "south_asia", 902: "south_asia", 854: "south_asia", 837: "south_asia",
    917: "south_asia", 826: "south_asia", 889: "south_asia", 129286: "south_asia",
    # East Asia
    148: "east_asia", 17: "east_asia", 884: "east_asia", 423: "east_asia", 865: "east_asia",
    711: "east_asia", 8646: "east_asia", 14773: "east_asia", 13426199: "east_asia",
    # Southeast Asia
    252: "southeast_asia", 928: "southeast_asia", 869: "southeast_asia", 881: "southeast_asia",
    833: "southeast_asia", 334: "southeast_asia", 836: "southeast_asia", 424: "southeast_asia",
    819: "southeast_asia", 921: "southeast_asia", 574: "southeast_asia",
    # Middle East
    851: "middle_east", 794: "middle_east", 796: "middle_east", 801: "middle_east", 810: "middle_east",
    822: "middle_east", 858: "middle_east", 43: "middle_east", 79: "middle_east", 878: "middle_east",
    846: "middle_east", 817: "middle_east", 398: "middle_east", 842: "middle_east", 805: "middle_east",
    219060: "middle_east",
    # United States and Canada
    30: "north_america", 16: "north_america",
}

# Labels of very general classes that are never useful as questions.
ROLLUP_STOP_LABELS = {
    "occupation", "profession", "job", "position", "person", "human", "worker", "employee",
    "activity", "role", "award", "prize", "honour", "honor", "order", "decoration",
    "public office", "position held", "title", "status", "entity", "agent", "group of humans",
    "social group", "organization", "work", "creative work", "artist",
}

# Label patterns on a character's classes (and their ancestors) -> char_type values.
CHAR_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"\bhuman\b|\bperson\b|\bwoman\b|\bman\b|\bgirl\b|\bboy\b", "human"),
    (r"\b(dog|canine|puppy)\b", "dog"),
    (r"\b(cat|feline|kitten)\b", "cat"),
    (r"\b(bird|duck|parrot|owl|penguin|chicken)\b", "bird"),
    (r"\b(fish|shark|whale|dolphin|octopus)\b", "fish"),
    (r"\b(mouse|rat|rodent|hamster|squirrel)\b", "rodent"),
    (r"\b(bear|panda)\b", "bear"),
    (r"\b(animal|mammal|reptile|insect|amphibian|creature of nature|horse|fox|wolf|rabbit|lion|tiger|pig|monkey|ape|frog|turtle|snake)\b", "animal"),
    (r"\b(robot|android|cyborg|artificial intelligence|automaton|droid|mecha)\b", "robot"),
    (r"\b(alien|extraterrestrial)\b", "alien"),
    (r"\b(deity|god|goddess|demigod)\b", "deity"),
    (r"\b(demon|devil|oni)\b", "demon"),
    (r"\bvampire\b", "vampire"),
    (r"\b(ghost|spirit|yokai|youkai)\b", "ghost"),
    (r"\bdragon\b", "dragon"),
    (r"\b(monster|kaiju|mythical creature|legendary creature)\b", "monster"),
    (r"\b(superhero|superheroine|super hero)\b", "superhero"),
    (r"\b(supervillain|villain|antagonist)\b", "villain"),
    (r"\bmutant\b", "mutant"),
    (r"\b(wizard|witch|sorcerer|sorceress|mage|magician)\b", "magic_user"),
    (r"\bpok[eé]mon\b", "pokemon"),
]

# Label patterns on a work's classes (and ancestors) -> medium values.
MEDIUM_PATTERNS: list[tuple[str, str]] = [
    (r"\banime\b", "anime"),
    (r"\bmanga\b|\blight novel\b", "manga"),
    (r"\bvideo game\b|\bvideo game series\b|\bcomputer game\b", "video_game"),
    (r"\b(comic|comics|comic book|graphic novel|webcomic|manhwa|manhua)\b", "comics"),
    (r"\b(television series|tv series|television program|television programme|sitcom|soap opera|web series|miniseries)\b", "tv"),
    (r"\b(film|movie|motion picture)\b", "film"),
    (r"\b(novel|book|literary|short story|play|poem|fairy tale|novella|book series)\b", "book"),
    (r"\b(animated|animation|cartoon)\b", "animated"),
    (r"\b(myth|mythology|legend|folklore|religious text|scripture|epic poem)\b", "mythology"),
]

# Multiplies every group's min_support. Set below 1 for small test runs (0 means 1).
SUPPORT_SCALE = float(os.environ.get("MR_SUPPORT_SCALE", "1.0"))


def min_support(group: "Group") -> int:
    return max(1, int(round(group.min_support * SUPPORT_SCALE)))


ENRICH_TOP_N = int(os.environ.get("MR_ENRICH_TOP_N", "50000"))
ENRICH_MODEL = os.environ.get("MR_ENRICH_MODEL", "claude-haiku-5-5")
I18N_MODEL = os.environ.get("MR_I18N_MODEL", "claude-opus-5-5")

USER_AGENT = os.environ.get(
    "MR_USER_AGENT", "MindReaderPipeline/1.0 (data pipeline for a guessing game; set MR_USER_AGENT to add a contact)")


@dataclass
class Paths:
    work: str

    def p(self, *parts: str) -> str:
        return os.path.join(self.work, *parts)

    def ensure(self) -> "Paths":
        for sub in ("pass1", "pass2", "build", "images"):
            os.makedirs(self.p(sub), exist_ok=True)
        return self


@dataclass
class RunReport:
    stats: dict = field(default_factory=dict)

    def add(self, key: str, value) -> None:
        self.stats[key] = value
