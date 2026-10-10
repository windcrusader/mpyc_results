'''Scores whole seasons from the day files and compares them with the
Sailwave master files.

Where the day files and a master disagree, the reason has been checked by
hand and is listed below. All of them are errors in the master files, so a
new difference means something has changed and should be investigated.

Run with:
    python3 -m unittest tests.test_day_files -v
To see the differences themselves:
    python3 season_scoring.py 2526 --compare --races
'''
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import season_scoring as ss  # noqa: E402

# 2526: boats differ between the master and the day files in these races.
# 14 Nov: Brian Dixon sailed all three races in the day file but is missing
#         from the master (which has Richard Mansell in race 1 instead).
# 14 Mar race 3: Phil Galloway is in the master but not in the day file.
CREW_DIFFERENCES_2526 = {
    '20251114-01', '20251114-02', '20251114-03', '20260314-03'}

# 2526 handicap: the master rates Laser II (Tim Friedel, Amber Judkins) at
# 1100 where the day files have 1085 or 1104, and Joshua Judkins (ILCA 4) at
# 1208 rather than 1216, which swaps places in these races.
RATING_DIFFERENCES_2526 = {
    '20250920-04', '20251101-01', '20251130-03', '20260208-04',
    '20260427-01', '20260427-03', '20260427-05', '20260509-01',
    '20260509-02', '20260509-03', '20260509-04'}

# 2627 handicap: the master has no rating for George Ward or Leon Mantz, so
# Sailwave scored them as 1000.
UNRATED_IN_MASTER_2627 = {('George Ward', 'ILCA 7'), ('Leon Mantz', 'ILCA 6')}


def differing_races(season, mode):
    config = ss.load_config(season, ROOT)
    path = ss.master_path(config, mode)
    return {race_key for race_key, _, _ in
            ss.compare_races(config, mode, path)}


def differing_totals(season, mode):
    config = ss.load_config(season, ROOT)
    rows, _ = ss.compare_with_master(config, mode,
                                     ss.master_path(config, mode))
    return {(name, yclass) for name, yclass, _, _ in rows}


class TestSeason2627(unittest.TestCase):

    def test_fpp_matches_master(self):
        self.assertEqual(differing_totals('2627', ss.FPP), set())

    def test_handicap_matches_master_except_unrated(self):
        self.assertEqual(differing_totals('2627', ss.HANDICAP),
                         UNRATED_IN_MASTER_2627)


class TestSeason2526(unittest.TestCase):

    def test_fpp_differences_are_known(self):
        self.assertEqual(differing_races('2526', ss.FPP),
                         CREW_DIFFERENCES_2526)

    def test_handicap_differences_are_known(self):
        self.assertEqual(differing_races('2526', ss.HANDICAP),
                         CREW_DIFFERENCES_2526 | RATING_DIFFERENCES_2526)


if __name__ == '__main__':
    unittest.main()
