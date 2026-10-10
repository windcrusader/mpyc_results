'''sailwave_file.py

Reads a Sailwave .blw file into plain Python objects.

A .blw file is a CSV file where every row has the form
    "key","value","competitor id","race id"
e.g. "rpos","3","4858","4349" is competitor 4858's position in race 4349.

Only the data needed for season scoring is extracted: competitors, the races
that were sailed, each competitor's result in each race and the scoring
system settings.
'''
import csv
from dataclasses import dataclass, field


@dataclass
class Competitor:
    key: str
    name: str = ""
    yclass: str = ""
    sailno: str = ""
    club: str = ""
    division: str = ""
    rating: str = ""
    # Series total as calculated by Sailwave (only present when scored).
    total: str = ""


@dataclass
class Result:
    '''One competitor's result in one race, exactly as stored by Sailwave.'''
    comp: str
    race: str
    pos: str = ""        # rpos: position (or position given by code)
    pts: str = ""        # rpts: points awarded by Sailwave
    code: str = ""       # rcod: DNC, DNF, DSQ, ... (upper cased)
    elapsed: str = ""    # rele
    corrected: str = ""  # rcor
    # rrat: rating for this race only, overriding the competitor's rating
    # (e.g. 1000 for everyone in a non-handicap race)
    race_rating: str = ""


@dataclass
class Race:
    key: str
    rank: int
    start: str = ""


@dataclass
class SailwaveSeries:
    path: str
    competitors: dict = field(default_factory=dict)  # key -> Competitor
    races: list = field(default_factory=list)        # sailed races, in order
    results: dict = field(default_factory=dict)      # (comp, race) -> Result
    scoring: dict = field(default_factory=dict)      # scr* settings
    codes: dict = field(default_factory=dict)        # code -> scrcode fields

    def race_results(self, race_key):
        '''All results recorded for a race, excluding empty placeholders.'''
        return [res for (comp, race), res in self.results.items()
                if race == race_key and (res.pos or res.code)]


COMP_FIELDS = {
    'comphelmname': 'name',
    'compclass': 'yclass',
    'compsailno': 'sailno',
    'compclub': 'club',
    'compdivision': 'division',
    'comprating': 'rating',
    'comptotal': 'total',
}

RESULT_FIELDS = {
    'rpos': 'pos',
    'rpts': 'pts',
    'rcod': 'code',
    'rele': 'elapsed',
    'rcor': 'corrected',
    'rrat': 'race_rating',
}


def read_blw(path):
    '''Parse a Sailwave .blw file.'''
    series = SailwaveSeries(path=path)
    race_info = {}
    with open(path, encoding='latin-1', newline='') as f:
        for row in csv.reader(f):
            row = (row + [''] * 4)[:4]
            key, value, comp, race = row
            if key in COMP_FIELDS:
                competitor = series.competitors.setdefault(
                    comp, Competitor(key=comp))
                setattr(competitor, COMP_FIELDS[key], value.strip())
            elif key in RESULT_FIELDS and comp and race:
                result = series.results.setdefault(
                    (comp, race), Result(comp=comp, race=race))
                if key == 'rcod':
                    value = value.strip().upper()
                setattr(result, RESULT_FIELDS[key], value.strip())
            elif key in ('racerank', 'racesailed', 'racestart'):
                race_info.setdefault(race, {})[key] = value
            elif key == 'scrcode':
                parts = value.split('|')
                series.codes[parts[0].upper()] = parts
            elif key.startswith('scr'):
                series.scoring[key[3:]] = value

    sailed = [(int(info['racerank']), race)
              for race, info in race_info.items()
              if info.get('racesailed') == '1' and 'racerank' in info]
    series.races = [Race(key=race, rank=rank,
                         start=race_info[race].get('racestart', ''))
                    for rank, race in sorted(sailed)]
    return series
