'''Checks season_scoring against every Sailwave master file in the repo.

The master files contain race points, positions and series totals worked out
by Sailwave, so they act as the reference ("oracle") for the Python scoring:

1. Points:   from Sailwave's positions and codes, recompute every race's
             points and compare with the points Sailwave stored.
2. Ranking:  from the elapsed times and ratings in the master, re-rank every
             timed race and compare with Sailwave's positions.
3. Totals:   every series total equals the sum of its race points.

Run with:
    python3 -m unittest tests.test_against_masters -v
or for a detailed report of every mismatch:
    python3 tests/test_against_masters.py
'''
import glob
import os
import sys
import unittest
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sailwave_file import read_blw  # noqa: E402
import season_scoring as ss  # noqa: E402

MASTERS = sorted(glob.glob(os.path.join(ROOT, '*', 'MPYC_Master*.blw')))

# Races whose stored points cannot be reproduced from the master file itself
# because the file was edited after Sailwave last scored it (competitors
# removed or results changed to DNC). Most are found by stale_reason(); this
# one is not, because the remaining positions still run 1..9.
# (season directory, race id) -> reason
KNOWN_STALE_RACES = {
    ('1819', '2173'): "scored as 11 boats, only 9 in file",
}


def decimals(text):
    return len(text.split('.')[1]) if '.' in text else 0


def series_decimals(series):
    '''Decimal places Sailwave used for race points in this file.'''
    return max((decimals(r.pts) for r in series.results.values() if r.pts),
               default=0)


def stale_reason(series, race_key):
    '''Why Sailwave's stored results for a race contradict themselves, or
    None if they are consistent.'''
    season = os.path.basename(os.path.dirname(series.path))
    if (season, race_key) in KNOWN_STALE_RACES:
        return KNOWN_STALE_RACES[(season, race_key)]
    for fleet in race_fleets(series, race_key).values():
        if any(r.code == 'DNC' and float(r.pts) != 0 for r in fleet):
            return "DNC with points"
        positions = sorted(int(float(r.pos)) for r in fleet if not r.code)
        for i, pos in enumerate(positions):
            if pos != i + 1 and not (i and pos == positions[i - 1]):
                return f"gap in positions {positions}"
    return None


def stale_races(series):
    return {race.key: stale_reason(series, race.key)
            for race in series.races if stale_reason(series, race.key)}


def is_stale(series, race_key):
    return stale_reason(series, race_key) is not None


def race_fleets(series, race_key):
    '''Results of a race split by division.

    The master files were scored by Sailwave with each division (JUNIOR,
    SENIOR) ranked separately, so to reproduce them each division is scored
    as its own fleet here. season_scoring itself scores the whole race as one
    fleet.'''
    fleets = defaultdict(list)
    for res in series.race_results(race_key):
        if not res.pts:
            continue
        comp = series.competitors[res.comp]
        fleets[comp.division.upper() or 'SENIOR'].append(res)
    return fleets


def points_mismatches(series):
    '''Recompute points from Sailwave's positions and codes.'''
    mismatches = []
    checked = 0
    dp = series_decimals(series)
    for race in series.races:
        if is_stale(series, race.key):
            continue
        for division, fleet in race_fleets(series, race.key).items():
            entries = [{'code': r.code, 'order': float(r.pos), 'res': r}
                       for r in fleet]
            try:
                ss.score_race(entries, dp)
            except ss.ScoringError as err:
                mismatches.append((race.key, division, None, str(err)))
                continue
            n = sum(1 for e in entries
                    if e['code'] not in ss.NOT_IN_FLEET_CODES)
            tolerance = 0.1 if n in ss.APPROXIMATE_FLEETS else 0
            for e in entries:
                res = e['res']
                expected = float(res.pts)
                ours = e['points']
                checked += 1
                if abs(ours - expected) > tolerance + 1e-6:
                    mismatches.append(
                        (race.key, division,
                         series.competitors[res.comp].name,
                         f"pos {res.pos} {res.code or ''} sailwave "
                         f"{res.pts} ours {ours}"))
    return checked, mismatches


def ranking_mismatches(series, handicapped):
    '''Re-rank timed races from elapsed times (and ratings) and compare
    positions with Sailwave's.'''
    mismatches = []
    checked = 0
    for race in series.races:
        if is_stale(series, race.key):
            continue
        for division, fleet in race_fleets(series, race.key).items():
            entries = []
            for r in fleet:
                comp = series.competitors[r.comp]
                entry = {'code': r.code, 'res': r, 'name': comp.name}
                if not r.code:
                    elapsed = ss.parse_time(r.elapsed)
                    if elapsed is None:
                        entries = None
                        break
                    rating = float(r.race_rating or comp.rating or 1000)
                    entry['order'] = round(elapsed * 1000 / rating) \
                        if handicapped else elapsed
                entries.append(entry)
            if not entries:
                continue  # race scored from places, not times
            ss.score_race(entries)
            for e in entries:
                if e['code']:
                    continue
                checked += 1
                if float(e['res'].pos) != e['pos']:
                    mismatches.append(
                        (race.key, division, e['name'],
                         f"elapsed {e['res'].elapsed} sailwave pos "
                         f"{e['res'].pos} ours {e['pos']}"))
    return checked, mismatches


def total_mismatches(series):
    mismatches = []
    for comp in series.competitors.values():
        if not comp.total:
            continue
        points = [series.results.get((comp.key, race.key))
                  for race in series.races]
        total = sum(float(r.pts) for r in points if r and r.pts)
        if abs(total - float(comp.total)) > 0.05 * len(series.races) / 10 + 0.01:
            mismatches.append((comp.name, comp.total, round(total, 3)))
    return mismatches


class TestRinderleB(unittest.TestCase):

    def test_known_values(self):
        # Middle boat of 3, 5 and 7 starters (quoted on the Sailwave forum)
        self.assertAlmostEqual(ss.rinderle_b_points(2, 3), 42.989, places=3)
        self.assertAlmostEqual(ss.rinderle_b_points(3, 5), 46.876, places=3)
        self.assertAlmostEqual(ss.rinderle_b_points(4, 7), 49.236, places=3)
        # Last place always scores 10.5
        for n in (2, 5, 12, 24):
            self.assertAlmostEqual(ss.rinderle_b_points(n, n), 10.5)

    def test_published_table_where_sailwave_has_no_data(self):
        # Single starter, and full columns for 22 and 25 boats, from
        # https://bcycracing.org/rinderle-b-high-point-scoring/
        self.assertEqual(ss.rinderle_b_points(1, 1), 79.1)
        columns = {
            22: [100.4, 95.1, 90.8, 86.6, 82.4, 78.2, 73.9, 69.7, 65.5,
                 61.2, 57.0, 52.8, 48.6, 44.3, 40.1, 35.9, 31.6, 27.4, 23.2,
                 19.0, 14.7, 10.5],
            25: [100.5, 95.8, 92.1, 88.4, 84.7, 81.0, 77.3, 73.6, 69.9,
                 66.2, 62.4, 58.7, 55.0, 51.3, 47.6, 43.9, 40.2, 36.5, 32.8,
                 29.1, 25.3, 21.6, 17.9, 14.2, 10.5],
        }
        for n, points in columns.items():
            ours = [ss.round_half_up(ss.rinderle_b_points(p, n), 1)
                    for p in range(1, n + 1)]
            self.assertEqual(ours, points, f"{n} starters")

    def test_ties_share_average(self):
        # 1617 race 1007: two boats tied 5th of 11 both scored 56.395
        self.assertAlmostEqual(
            ss.round_half_up(ss.tied_points(5, 2, 11, 3), 3), 56.395)
        # 2526 race 4415: tied 3rd of 4 scored 22.1
        self.assertAlmostEqual(
            ss.round_half_up(ss.tied_points(3, 2, 4, 1), 1), 22.1)

    def test_ocs_and_dns_are_not_starters(self):
        # 2526 race 4415: 4 finishers and 2 OCS, scored as a fleet of 4
        entries = [{'code': '', 'order': t} for t in (1, 2, 3, 3)]
        entries += [{'code': 'OCS'} for _ in range(2)]
        ss.score_race(entries, 1)
        self.assertEqual([e['points'] for e in entries],
                         [85.8, 56.8, 22.1, 22.1, 10.5, 10.5])


class TestAgainstMasters(unittest.TestCase):

    def test_masters_found(self):
        self.assertGreater(len(MASTERS), 10)

    def test_points(self):
        for path in MASTERS:
            with self.subTest(master=os.path.relpath(path, ROOT)):
                checked, bad = points_mismatches(read_blw(path))
                self.assertEqual(bad, [], f"{len(bad)} of {checked}")

    def test_ranking(self):
        for path in MASTERS:
            series = read_blw(path)
            handicapped = series.scoring.get('ratingsystem') != 'None'
            with self.subTest(master=os.path.relpath(path, ROOT)):
                checked, bad = ranking_mismatches(series, handicapped)
                self.assertEqual(bad, [], f"{len(bad)} of {checked}")

    def test_totals_are_sum_of_race_points(self):
        for path in MASTERS:
            with self.subTest(master=os.path.relpath(path, ROOT)):
                self.assertEqual(total_mismatches(read_blw(path)), [])


def report():
    for path in MASTERS:
        series = read_blw(path)
        handicapped = series.scoring.get('ratingsystem') != 'None'
        p_checked, p_bad = points_mismatches(series)
        r_checked, r_bad = ranking_mismatches(series, handicapped)
        t_bad = total_mismatches(series)
        stale = stale_races(series)
        print(f"{os.path.relpath(path, ROOT):42} points {p_checked - len(p_bad)}"
              f"/{p_checked}  ranking {r_checked - len(r_bad)}/{r_checked}"
              f"  totals bad {len(t_bad)}  stale races skipped {len(stale)}")
        for race_key, reason in stale.items():
            print(f"      skipped race {race_key}: {reason}")
        for m in (p_bad + r_bad)[:8]:
            print('     ', m)
        for m in t_bad[:3]:
            print('      total', m)


if __name__ == '__main__':
    report()
