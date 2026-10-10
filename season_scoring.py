'''season_scoring.py

Scores a whole season directly from the individual Sailwave day files, so
that the merged "master" files are no longer needed.

How each day was scored on the day (low point, high point, handicap or not)
does not matter here. Only the raw facts are read from each day file: who
sailed each race, their elapsed time or recorded place, and any scoring
code. Every race is then re-scored the same way for the season table:

* ranked by corrected time (handicap) or elapsed time (first past the post)
  across the whole fleet (divisions are not scored separately),
* awarded Rinderle B high points (see rinderle_b_points), and
* summed into a season total.

These rules were derived from, and are tested against, the Sailwave master
files of every season since 2016-17 (see tests/).

Usage:
    python3 season_scoring.py 2627                 # print season tables
    python3 season_scoring.py 2627 --compare       # diff against master files
'''
import argparse
import math
import os
import re
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field

from sailwave_file import read_blw

HANDICAP = 'handicap'
FPP = 'fpp'

# Rinderle B points for first place, by number of boats in the race (n).
# Sailwave uses a lookup table for this. Most values were fitted to the race
# points Sailwave stored in the master files since 2016-17, and reproduce
# them to the stored precision (see tests/test_against_masters.py).
#
# Fleets of 1, 22 and 25 boats have never occurred in a master file, so those
# values come from the published Rinderle B table
# (https://bcycracing.org/rinderle-b-high-point-scoring/) and reproduce its
# columns exactly. That table is not used for the other fleet sizes because
# 28 of its cells differ by 0.1 from what Sailwave actually awards (e.g. 2nd
# of 5 is 65.0 in the table but 65.1 in Sailwave), and every one of the 1,193
# results in the master files affected by those cells agrees with Sailwave.
#
# Fleets of 26-28 boats are unknown. Above 24 boats Sailwave's table no
# longer follows the 1.25 step rule exactly, so results for those fleets may
# differ by 0.1 (APPROXIMATE_FLEETS).
RINDERLE_B_FIRST = {
    1: 79.1, 2: 81.3, 3: 83.6, 4: 85.7997, 5: 87.79995, 6: 89.6001,
    7: 91.2, 8: 92.60005, 9: 93.94277, 10: 95.02218, 11: 96.03089,
    12: 96.9, 13: 97.58637, 14: 98.17093, 15: 98.74036, 16: 99.20015,
    17: 99.5, 18: 99.79997, 19: 100.0, 20: 100.1, 21: 100.3, 22: 100.357,
    23: 100.4, 24: 100.5, 25: 100.476, 29: 115.31, 30: 119.088,
    31: 122.785,
}
APPROXIMATE_FLEETS = {29, 30, 31}
# Points for last place, whatever the fleet size.
RINDERLE_B_LAST = 10.5

# How codes are scored (from the scrcode settings in the master files).
ZERO_POINT_CODES = {'DNC', 'DSQ', 'DGM', 'DNE'}
LAST_PLACE_CODES = {'DNF', 'DNS', 'OCS', 'BFD', 'NSC', 'RET', 'UFD'}
# Codes that do not count as a boat in the race when sizing the fleet. DNS
# and OCS score like a DNF but are not counted as starters; BFD and UFD are
# assumed to behave like OCS (not yet seen in any master file).
NOT_IN_FLEET_CODES = {'DNC', 'DNS', 'OCS', 'BFD', 'UFD'}


class ScoringError(Exception):
    pass


def rinderle_b_points(place, n):
    '''Rinderle B high points for finishing in `place` of `n` boats.

    1st scores F(n) from the lookup table and last scores 10.5. Places from
    2nd to last are spaced evenly, and 1st is a further 1.25 steps above 2nd.
    '''
    try:
        first = RINDERLE_B_FIRST[n]
    except KeyError:
        raise ScoringError(f"No Rinderle B value known for {n} boats") \
            from None
    if place == 1:
        return first
    return RINDERLE_B_LAST + \
        (first - RINDERLE_B_LAST) * (n - place) / (n - 0.75)


def tied_points(place, count, n, decimals):
    '''Points for `count` boats tied at `place`: the average of the places
    they share. Like Sailwave, each place's points are rounded before
    averaging.'''
    return sum(round_half_up(rinderle_b_points(p, n), decimals)
               for p in range(place, place + count)) / count


def code_points(code, n):
    if code in ZERO_POINT_CODES:
        return 0.0
    if code in LAST_PLACE_CODES:
        return RINDERLE_B_LAST
    raise ScoringError(
        f"Scoring code {code} is not supported; add a points override")


def round_half_up(value, places):
    scale = 10 ** places
    return math.floor(value * scale + 0.5 + 1e-9) / scale


def parse_time(text):
    '''Convert a Sailwave time to seconds, or None if there is no time.

    Same conventions as generate_webcontent.convert_time_to_secs:
    H:MM:SS, MM:SS, MM.SS or whole minutes.
    '''
    text = text.strip().replace('.', ':')
    if not text:
        return None
    try:
        parts = [int(p) for p in text.split(':')]
    except ValueError:
        return None
    if len(parts) == 1:
        seconds = parts[0] * 60
    elif len(parts) == 2:
        seconds = parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
    else:
        return None
    return seconds or None


def score_race(entries, decimals=1):
    '''Assign positions and points to one race.

    `entries` is a list of dicts with keys 'code' and 'order'. 'order' is the
    value finishers are ranked by (lower is better); equal values tie. Adds
    'pos' and 'points' (rounded to `decimals` places) to each entry. Every
    boat in the race is scored as one fleet.
    '''
    n = sum(1 for e in entries if e['code'] not in NOT_IN_FLEET_CODES)
    finishers = sorted((e for e in entries if not e['code']),
                       key=lambda e: e['order'])
    place = 1
    i = 0
    while i < len(finishers):
        tied = [e for e in finishers[i:]
                if e['order'] == finishers[i]['order']]
        points = round_half_up(
            tied_points(place, len(tied), n, decimals), decimals)
        for e in tied:
            e['pos'] = place
            e['points'] = points
        place += len(tied)
        i += len(tied)
    for e in entries:
        if e['code']:
            e['pos'] = n if e['code'] in LAST_PLACE_CODES else n + 1
            e['points'] = code_points(e['code'], n)
    return entries


# ---------------------------------------------------------------------------
# Season loading
# ---------------------------------------------------------------------------

@dataclass
class HelmSeason:
    '''A helm's season in one class.'''
    name: str
    yclass: str
    sailno: str = ""
    club: str = ""
    rating: float = 0.0
    total: float = 0.0
    # [(race key, position or code)] for every race they sailed
    results: list = field(default_factory=list)
    points: list = field(default_factory=list)
    races: int = 0
    placetally: dict = field(default_factory=lambda: {1: 0, 2: 0, 3: 0})


@dataclass
class SeasonConfig:
    season: str
    directory: str
    ratings: dict = field(default_factory=dict)
    aliases: dict = field(default_factory=dict)
    class_aliases: dict = field(default_factory=dict)
    exclude: list = field(default_factory=list)
    days: dict = field(default_factory=dict)
    points_decimals: int = 1


@dataclass
class SeasonResult:
    helms: list      # HelmSeason
    races: list      # race keys in sailing order, e.g. "20261003-02"
    # {race key: {helm key: {class, rating, elapsed, corrected}}} for timed
    # races, as used by generate_webcontent.handicap_adjust
    details: dict
    warnings: list


def load_config(season, base_dir='.'):
    directory = os.path.join(base_dir, season)
    config = SeasonConfig(season=season, directory=directory)
    path = os.path.join(directory, 'season.toml')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            data = tomllib.load(f)
        config.ratings = {k.upper(): float(v)
                          for k, v in data.get('ratings', {}).items()}
        config.aliases = data.get('aliases', {})
        config.class_aliases = {k.upper(): v for k, v in
                                data.get('class_aliases', {}).items()}
        config.exclude = data.get('exclude', [])
        config.days = data.get('days', {})
        config.points_decimals = data.get('points_decimals',
                                          config.points_decimals)
    return config


def day_date(filename):
    '''Date (YYYYMMDD) from a file name such as "251018 ClubSailing.blw" or
    "20260919 ClubSailing.blw".'''
    match = re.match(r'(\d{8}|\d{6})', filename)
    if not match:
        return None
    digits = match.group(1)
    return digits if len(digits) == 8 else '20' + digits


def day_files(config):
    '''The season's day files in date order.'''
    files = []
    for filename in os.listdir(config.directory):
        if not filename.lower().endswith('.blw'):
            continue
        if filename.startswith('MPYC_Master') or filename in config.exclude:
            continue
        if config.days.get(filename, {}).get('exclude'):
            continue
        date = config.days.get(filename, {}).get('date') or day_date(filename)
        if date is None:
            print(f"Skipping {filename}: no date in file name",
                  file=sys.stderr)
            continue
        files.append((date, filename))
    return sorted(files)


def canonical_name(name, config):
    name = ' '.join(name.split())
    return config.aliases.get(name, name)


def canonical_class(yclass, config):
    yclass = ' '.join(yclass.split())
    return config.class_aliases.get(yclass.upper(), yclass)


def score_season(config, mode=HANDICAP):
    '''Score every race of the season from the day files.

    Problems in the data are collected in SeasonResult.warnings rather than
    stopping the run.
    '''
    warnings = []
    helms = {}
    race_keys = []
    details = defaultdict(dict)

    for date, filename in day_files(config):
        day = config.days.get(filename, {})
        series = read_blw(os.path.join(config.directory, filename))
        handicapped = mode == HANDICAP and day.get('handicap', True)
        use_places = day.get('order') == 'positions'
        unrated = set()

        for number, race in enumerate(series.races, start=1):
            race_key = f"{date}-{number:02d}"
            where = f"{filename} race {number}"
            entries = []
            for result in series.race_results(race.key):
                comp = series.competitors[result.comp]
                if not comp.name:
                    continue
                entries.append({
                    'comp': comp,
                    'name': canonical_name(comp.name, config),
                    'yclass': canonical_class(comp.yclass, config),
                    'code': result.code,
                    'recorded_pos': result.pos,
                    'elapsed': parse_time(result.elapsed),
                    'elapsed_text': result.elapsed,
                    'race_rating': result.race_rating,
                })
            if not any(e['code'] != 'DNC' for e in entries):
                continue

            finishers = [e for e in entries if not e['code']]
            timed = not use_places and all(e['elapsed'] for e in finishers)
            if not use_places and not timed:
                missing = [f"{e['name']} {e['elapsed_text']!r}"
                           for e in finishers if not e['elapsed']]
                warnings.append(
                    f"{where}: no usable elapsed time for "
                    f"{', '.join(missing)}; ranked by recorded places")
            too_long = [e for e in finishers
                        if timed and e['elapsed'] > 3 * 3600]
            if too_long:
                warnings.append(
                    f"{where}: elapsed time over 3 hours for "
                    f"{len(too_long)} boat(s), e.g. {too_long[0]['name']} "
                    f"{too_long[0]['elapsed_text']!r}; check the units")
            for e in finishers:
                if not timed:
                    e['order'] = float(e['recorded_pos'] or 0)
                    continue
                e['order'] = e['elapsed']
                if handicapped:
                    rating = rating_for(e, config)
                    if rating is None:
                        unrated.add(f"{e['name']} ({e['yclass']})")
                        rating = 1000.0
                    e['rating'] = rating
                    e['order'] = round(e['elapsed'] * 1000 / rating)
                details[race_key][(e['name'], e['yclass'].upper())] = {
                    'class': e['yclass'],
                    'rating': e.get('rating', rating_for(e, config) or 0),
                    'elapsed': e['elapsed'],
                    'corrected': e['order'] if handicapped else e['elapsed'],
                }

            fleet = sum(1 for e in entries
                        if e['code'] not in NOT_IN_FLEET_CODES)
            if fleet in APPROXIMATE_FLEETS:
                warnings.append(
                    f"{where}: {fleet} boats, Rinderle B points may differ "
                    "from Sailwave by 0.1")
            try:
                score_race(entries, config.points_decimals)
            except ScoringError as err:
                warnings.append(f"{where}: {err}; race left out")
                details.pop(race_key, None)
                continue

            race_keys.append(race_key)
            for e in entries:
                if e['code'] == 'DNC':
                    continue
                comp = e['comp']
                key = (e['name'], e['yclass'].upper())
                helm = helms.setdefault(
                    key, HelmSeason(name=e['name'], yclass=e['yclass']))
                helm.sailno = comp.sailno
                helm.club = comp.club
                helm.rating = e.get('rating', rating_for(e, config) or 0)
                helm.points.append(e['points'])
                helm.total += e['points']
                helm.races += 1
                helm.results.append(
                    (race_key, e['code'] if e['code'] in ('DNF', 'DSQ')
                     else str(e['pos'])))
                if not e['code'] and e['pos'] in helm.placetally:
                    helm.placetally[e['pos']] += 1

        if unrated:
            warnings.append(f"{filename}: no rating for "
                            f"{', '.join(sorted(unrated))}, used 1000")

    for helm in helms.values():
        helm.total = round_half_up(helm.total, config.points_decimals)
    return SeasonResult(helms=list(helms.values()), races=race_keys,
                        details=dict(details), warnings=warnings)


def rating_for(entry, config):
    '''The rating to use: the race's own rating if Sailwave has one (e.g.
    1000 for a non-handicap race), else the season's rating for the class,
    else the rating in the day file.'''
    comp = entry['comp']
    if entry['race_rating'] and float(entry['race_rating']):
        return float(entry['race_rating'])
    rating = config.ratings.get(entry['yclass'].upper())
    if rating is None and comp.rating:
        try:
            rating = float(comp.rating)
        except ValueError:
            return None
    return rating


# ---------------------------------------------------------------------------
# Comparison with a Sailwave master file
# ---------------------------------------------------------------------------

def master_totals(path, config):
    '''{(name, CLASS): total} from a Sailwave master file, combining any
    duplicate competitor entries.'''
    series = read_blw(path)
    totals = defaultdict(float)
    for comp in series.competitors.values():
        if comp.total and comp.name:
            key = (canonical_name(comp.name, config),
                   canonical_class(comp.yclass, config).upper())
            totals[key] += float(comp.total)
    return dict(totals)


def compare_with_master(config, mode, master_path, tolerance=0.15):
    '''Returns (rows, warnings): rows are (name, class, ours, master) for
    every helm whose totals differ by more than `tolerance`.'''
    result = score_season(config, mode)
    ours = {(h.name, h.yclass.upper()): h.total for h in result.helms}
    theirs = master_totals(master_path, config)
    rows = []
    for key in sorted(set(ours) | set(theirs)):
        a, b = ours.get(key), theirs.get(key)
        if a is None or b is None or abs(a - b) > tolerance:
            rows.append((key[0], key[1], a, b))
    return rows, result.warnings


def compare_races(config, mode, master_path, tolerance=0.05):
    '''Race by race differences between the day files and a master file.

    Races are matched by who sailed them rather than by order, as races are
    not always merged into the master in date order. Returns a list of
    (race key, master race id, [(helm, ours, master)]) for races that differ,
    where ours/master are (position, points) or None if the helm is missing.
    '''
    result = score_season(config, mode)
    ours = defaultdict(dict)
    for helm in result.helms:
        for (race_key, pos), points in zip(helm.results, helm.points):
            ours[race_key][(helm.name, helm.yclass.upper())] = (pos, points)

    series = read_blw(master_path)
    theirs = {}
    for race in series.races:
        rows = {}
        for res in series.race_results(race.key):
            comp = series.competitors[res.comp]
            if res.pts and res.code != 'DNC' and comp.name:
                key = (canonical_name(comp.name, config),
                       canonical_class(comp.yclass, config).upper())
                rows[key] = (res.code if res.code in ('DNF', 'DSQ')
                             else res.pos, float(res.pts))
        theirs[race.key] = rows

    def similarity(a, b):
        a, b = set(a), set(b)
        return len(a & b) / len(a | b) if a | b else 0

    differences = []
    unmatched = list(theirs)
    for race_key in result.races:
        best = max(unmatched, default=None,
                   key=lambda k: similarity(ours[race_key], theirs[k]))
        if best is None or similarity(ours[race_key], theirs[best]) < 0.5:
            differences.append((race_key, None, []))
            continue
        unmatched.remove(best)
        rows = []
        for helm in sorted(set(ours[race_key]) | set(theirs[best])):
            a, b = ours[race_key].get(helm), theirs[best].get(helm)
            if a is None or b is None or abs(a[1] - b[1]) > tolerance:
                rows.append((helm, a, b))
        if rows:
            differences.append((race_key, best, rows))
    for race_id in unmatched:
        differences.append((None, race_id, []))
    return differences


def print_race_differences(differences):
    for race_key, race_id, rows in differences:
        if race_id is None:
            print(f"  {race_key}: not in the master file")
            continue
        if race_key is None:
            print(f"  master race {race_id}: not in any day file")
            continue
        print(f"  {race_key} (master race {race_id}):")
        for (name, yclass), ours, theirs in rows:
            fmt = lambda v: 'missing' if v is None else f"{v[0]:>3} {v[1]:6.1f}"
            print(f"      {name:22} {yclass:12} day files {fmt(ours):>12}"
                  f"   master {fmt(theirs):>12}")


def master_path(config, mode):
    suffix = '_FPP' if mode == FPP else ''
    return os.path.join(config.directory,
                        f"MPYC_Master_Template_{config.season}{suffix}.blw")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('season', help='season directory, e.g. 2627')
    parser.add_argument('--mode', choices=[HANDICAP, FPP, 'both'],
                        default='both')
    parser.add_argument('--compare', action='store_true',
                        help='compare totals with the master files')
    parser.add_argument('--races', action='store_true',
                        help='with --compare, also show race by race '
                             'differences')
    args = parser.parse_args(argv)
    config = load_config(args.season)
    modes = [HANDICAP, FPP] if args.mode == 'both' else [args.mode]

    for mode in modes:
        print(f"\n=== {args.season} {mode} ===")
        if args.compare:
            rows, warnings = compare_with_master(
                config, mode, master_path(config, mode))
            if rows:
                print(f"{'Helm':24} {'Class':14} {'Day files':>10} "
                      f"{'Master':>10}")
                for name, yclass, ours, theirs in rows:
                    fmt = lambda v: '-' if v is None else f"{v:.1f}"
                    print(f"{name:24} {yclass:14} {fmt(ours):>10} "
                          f"{fmt(theirs):>10}")
            else:
                print("All totals match the master file.")
            if args.races:
                print("Race by race:")
                print_race_differences(compare_races(
                    config, mode, master_path(config, mode)))
        else:
            result = score_season(config, mode)
            warnings = result.warnings
            print(f"{len(result.races)} races")
            for helm in sorted(result.helms, key=lambda h: -h.total):
                print(f"{helm.name:24} {helm.yclass:14} {helm.total:8.1f} "
                      f"{helm.races:3d} races")
        for warning in warnings:
            print("warning:", warning)


if __name__ == '__main__':
    main()
