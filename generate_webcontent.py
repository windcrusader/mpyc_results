'''generate_webcontent.py

This script processes an exported set of results of the MPYC database from
sailwave and creates two html pages for upload to the MPYC website.

The first page is the league table that shows each skipper's relative
performance against all other skippers they have raced against in the club.

The second page is a overall points table based on the results so far in the
season.

Note to sailware admins, all mark foy or non-handicap races (e.g Buxton cup)
must have a special race handicap entered for all sailors to ensure that the
race result is not adjusted by the handicap system in the usual way.

Usage:
generate_webcontent.py "raceresults.dat"

Output:
two files in the 'htmloutput' directory: "league_table_laser.html" and
"points_table.html".

'''
import csv
import sys
import os.path
import datetime
import operator
import json
import copy
import argparse
from jinja2 import Environment, PackageLoader
from collections import namedtuple
from collections import defaultdict
from datetime import timedelta

env = Environment(loader=PackageLoader('generate_webcontent', 'templates'))

RaceEntry = namedtuple("RaceEntry",
                       "name, yclass, sailno, club, division, forkey,\
                            comprating,\
                           comptotal")

parser = argparse.ArgumentParser(description='generate_webcontent_\
                                                from_sailwave')
parser.add_argument('-calc_corrections',
                    action="store_true",
                    help="""Calculate PY corrections based on race data""")

parser.add_argument('-fpp',
                    action="store_true",
                    help="input file is first past the post scoring")


class Globals():
    """Convenience wrapper for Globals"""

    today = datetime.datetime.today()
    todayformat = '%s' % (today.strftime('%d %b %y %H:%M'))
    rank_method = 'PCT'
    season = "2526"
    table_position_file = "historical_positions.json"
    # Minimum number of yachts of a class in a race for consideration in
    # handicap adjustment calculation.
    min_number_per_class = 3


class MatchRes:
    '''This class is used to store the result of matchups between two helms
        and to keep track of the totals'''

    def __init__(self, helmi, helmj):
        self.wins = 0.0
        self.losses = 0.0
        self.draws = 0.0
        self.races = 0.0
        self.score = 0.0
        self.pct = 50.0
        self.helmi = helmi  # name of primary helm
        self.helmj = helmj  # name of matchup helm

    def eval_tot(self):
        self.races = self.wins + self.losses + self.draws
        self.score = self.wins - self.losses
        self.pct = round(self.wins / self.races * 100, 1)

    def print_out(self):
        return ['%d/%d/%d' % (self.score, self.wins, self.races)]

    def __repr__(self):
        rstr = (f" wins:{self.wins}" +
                f" losses:{self.losses}" +
                f" draws:{self.draws}" +
                f" score:{self.score}" +
                f" pct:{self.pct}" +
                f" helmi:{self.helmi}" +
                f" helmj:{self.helmj}")
        return rstr


class HelmRes:
    '''This class stores a RaceEntry and all the results associated with that
    RaceEntry. In addition there are some statistical metrics stored such
    as number of races and points total.'''

    def __init__(self, name="", yclass="", sailno="", club="", division="",
                 forkey="", comprating="", comptotal=0.0):
        self.props = RaceEntry(name=name, yclass=yclass, sailno=sailno,
                               club=club, division=division,
                               forkey=forkey, comprating=comprating,
                               comptotal=comptotal)
        # series results a list of tuples of the results for the race entry
        # with properties equal to "props"
        # list is of the form [(#sailwaveraceid, pos/code),...]
        self.results = []
        # a list of the points in each race. Not sure where it is used
        self.points = []
        # stores the total number of races competed in
        self.races = 0
        # a dictionary to hold the number of firsts, seconds, and thirds.
        self.placetally = {1: 0, 2: 0, 3: 0}
        self.mpycscore = 0.0

    def __repr__(self):
        # Override base method to return a list of all properties
        res_str = ""
        res_str += repr(self.props)
        res_str += " results: " + repr(self.results)
        res_str += " points: " + repr(self.points)
        res_str += " races: " + repr(self.races)
        res_str += " placetally: " + repr(self.placetally)
        return res_str

    def __hash__(self):
        return hash(self.props)

    def __eq__(self, other):
        return self.props == other.props

    def __ne__(self, other):
        # Not strictly necessary, but to avoid having both x==y and x!=y
        # True at the same time
        return not self.props == other.props


def sort_matrix(matin, key, key2=False):
    f = operator.attrgetter(key)
    if key:
        f2 = operator.attrgetter(key2)
    for row in matin:
        if not key2:
            row.sort(key=lambda b: f(b))
        else:
            row.sort(key=lambda b: (f(b), f2(b)))

def convert_time_to_secs(timestring):
    # Standardize separator
    timestring = timestring.replace(".", ":")
    parts = list(map(int, timestring.split(":")))
    
    if len(parts) == 1:
        # Input was just minutes (e.g., "75")
        delta = timedelta(minutes=parts[0])
    elif len(parts) == 2:
        # Input was hours:minutes (e.g., "1:75")
        delta = timedelta(hours=parts[0], minutes=parts[1])
    elif len(parts) == 3:
        # Input was hours:minutes:seconds
        delta = timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
    else:
        return 0

    # .total_seconds() returns a float, so we convert to int
    return int(delta.total_seconds())


def read_sailwave_series_summary(division, args):
    '''Reads the sailwave data file and generates a series summary dict.

    Grabs a particular division e.g SENIOR

    Also builds a race results dict with elapsed and corrected times
    structure as follows:
    {RaceKey:{helmkey:{class:Laser, rating:1100, elapsed:00:24:12,
             corrected:00:21:12},...}...}

    This is used for calculating handicap corrections.
    '''
    if args.fpp:

        filename = (Globals.season + "/" + "MPYC_Master_Template_" +
                Globals.season + "_FPP.blw")
    else:
        filename = (Globals.season + "/" + "MPYC_Master_Template_" +
                Globals.season + ".blw")

    with open(filename) as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        helms = []
        races = []
        races_detail = defaultdict(dict)
        rcod = ""
        for i, row in enumerate(reader):
            if row[0] == "comptotal":
                helm = {'forkey': row[2]}
                # append highpointscore
                helm['comptotal'] = row[1]
            elif row[0] == "compsailno":
                try:
                    if row[2] == helm['forkey']:
                        helm['sailno'] = row[1]
                except UnboundLocalError:
                    continue
            elif row[0] == "compclass":
                try:
                    if row[2] == helm['forkey']:
                        helm['yclass'] = row[1]
                except UnboundLocalError:
                    continue
            elif row[0] == "compdivision":
                try:
                    if row[2] == helm['forkey']:
                        helm['division'] = row[1]
                except UnboundLocalError:
                    continue
            elif row[0] == "compclub":
                try:
                    if row[2] == helm['forkey']:
                        helm['club'] = row[1]
                except UnboundLocalError:
                    continue
            elif row[0] == "comprating":
                try:
                    if row[2] == helm['forkey']:
                        helm['comprating'] = row[1]
                except UnboundLocalError:
                    continue
            elif row[0] == "comphelmname":
                try:
                    if row[2] == helm['forkey']:
                        helm['name'] = row[1]
                        if helm['division'] == division:
                            helms.append(HelmRes(**helm))
                except UnboundLocalError:
                    continue

            elif row[0] == "rcod":
                # look for a race code like DNC
                rcod = row[1]
            elif row[0] == "rrset":
                rcod = ""
            elif row[0] == "rpos":
                # found a race position
                # search through list of helms for a match and append it to
                # the results dictionary
                for helm in helms:
                    if helm.props.forkey == row[2] and rcod != "DNC":
                        # add the result but only if a DNC was not found
                        # earlier
                        # check if DSQ or DNF
                        if rcod in ["DSQ", "DNF"]:
                            helm.results.append((row[3], rcod))
                        else:
                            helm.results.append((row[3], row[1]))
                            # check if 1st, 2nd or 3rd
                        if row[1] == '1':
                            helm.placetally[1] += 1
                        elif row[1] == '2':
                            helm.placetally[2] += 1
                        elif row[1] == '3':
                            helm.placetally[3] += 1
                        # increment total results
                        helm.races += 1

            elif row[0] == "rpts":
                # found the race points
                # search through the helms and find and append
                for helm in helms:
                    if helm.props.forkey == row[2]:
                        helm.points.append(row[1])
            elif row[0] == "racerank":
                # found a race
                races.append(row[3])
            elif row[0] == "rcor":
                # add corrected time to the race list
                for helm in helms:
                    if helm.props.forkey == row[2]:
                        detail = {"class": helm.props.yclass,
                                  "rating": helm.props.comprating,
                                  "corrected": convert_time_to_secs(row[1])}

                races_detail[row[3]][row[2]] = detail
            elif row[0] == "rele":
                # Check if DNC is flagged along with an elapsed time
                # this means there is an error in the sailwave data
                # which needs to be manually corrected.
                rele = row[1]
                if rcod == "DNC" and rele != "0:00:00":
                    print(f"Error found elapsed time = {rele} \
                        at row {i} but DNC is set")
                if rele != "0:00:00" and rcod.lower() != "dnf":
                    races_detail[row[3]][row[2]]["elapsed"] = \
                        convert_time_to_secs(row[1])
    return helms, races, races_detail


def generate_html(matin, args):
    '''Generates the laser league table using jinja2 and the template in the
    directory templates'''

    print('Generating league table...')
    if args.fpp:
        outfilename = "htmloutput/leaguetable" + Globals.season + "_fpp.htm"
    else:    
        outfilename = "htmloutput/leaguetable" + Globals.season + ".htm"
    file = open(outfilename, 'w')
    # sort rows based on sort method
    if Globals.rank_method == 'PCT':
        sort_matrix(matin, 'pct', 'score')
    else:
        sort_matrix(matin, 'score')
    template = env.get_template('league_table_template.html')
    print(template.render(updatetime=Globals.todayformat,
                          table=matin), file=file)


def process_race(racedat, matrix, raceno):
    '''This method updates the matrix match results for a race.

    racedat is a dictionary with a helm as keys and results as values
    matrix is a output matrix containing matchup objects which represent a
    matchup for two skippers.
    '''
    helms = sorted(racedat, key=lambda b: b.props.name)
    # print(helms)
    no_helms = len(helms)
    for i in range(no_helms):
        # create list of races competed by helmi
        for raceidi, resulthelmi in helms[i].results:
            if raceno == raceidi:
                for j in range(no_helms):
                    if j == i:
                        # helms are equal so go to next helm.
                        continue
                    for raceidj, resulthelmj in helms[j].results:
                        if raceno == raceidj:
                            if resulthelmj == 'DNF' or resulthelmj == 'DSQ':
                                if (resulthelmi == 'DNF' or
                                        resulthelmi == 'DSQ'):
                                    # both dnf or DSQ so draw
                                    matrix[i][j].draws += 1
                                else:
                                    matrix[i][j].wins += 1
                            elif resulthelmj == 'OCS':
                                matrix[i][j].wins += 1
                            else:
                                # get float using re and determine who won
                                # the matchrace
                                # check if the first result is a DNF
                                if (resulthelmi == 'DNF' or
                                        resulthelmi == 'DSQ'):
                                    matrix[i][j].losses += 1
                                else:
                                    # do the evaluation
                                    diff = float(resulthelmi) - \
                                        float(resulthelmj)
                                    if diff > 0.0:
                                        # it's a loss
                                        matrix[i][j].losses += 1
                                    elif diff < 0.0:
                                        # it's a win
                                        matrix[i][j].wins += 1
                                    elif diff == 0.0:
                                        # tie
                                        matrix[i][j].draws += 1
                                    # update total
                                    matrix[i][j].eval_tot()


# get race results
def format_results(race_dat, matrix):
    '''Produces a csv file with matchup results, useful for debugging'''
    outfile = open(os.path.splitext(sys.argv[1])[
        0] + '_matchupmatrix.csv', 'w', newline='')
    writer = csv.writer(outfile, delimiter=',')
    helms = sorted(list(race_dat.keys()), key=lambda b: b.name)
    writer.writerow([""] + [helm.name for helm in helms])
    for i in range(len(helms)):
        row = [helms[i].name]
        for j in range(len(helms)):
            if j == i:
                row.extend(["-"])
            else:
                row.extend(matrix[i][j].print_out())
            # print(row)
        writer.writerow(row)


def save_table_position(formatted_res, no_races):
    """Saves the current state of the points table to file"""
    # first try to open the file and if it cannot be found, create it.
    try:
        file = open(Globals.table_position_file, 'r')
        file.close()
        newfile = False
    except FileNotFoundError:
        file = open(Globals.table_position_file, 'w')
        file.close()
        newfile = True

    with open(Globals.table_position_file, "r+") as tfile:
        # got the file so first check if table needs updating
        if newfile is not True:
            jdecode = json.load(tfile)
            jencode = copy.deepcopy(jdecode)
        else:
            jdecode= {}
            jencode = {}
        # get number of races
        if no_races not in jdecode.keys():
            # write an update
            jencode[no_races] = formatted_res
            # reset file to start point for updating
            tfile.seek(0)
            tfile.truncate(
            json.dump(jencode, tfile))

    # return the last table state
    laststatekey = sorted(jdecode.keys())[0]
    return jdecode[laststatekey]


def generate_points_table(sailresults, highpoint, num_races, args):
    '''This method generates the HTML points table
    If nom_sail is True then the table is processed with the sailor's results based on 
    using that sail in every race, even if on the day they did not use that sail.
    '''

    print('Generating points table...')
    if args.fpp:
        outfilename = "htmloutput/pointstable" + Globals.season + "_fpp.htm"
    else:
        outfilename = "htmloutput/pointstable" + Globals.season + ".htm"
    file = open(outfilename, 'w')

    sortedsailresults = sorted(sailresults, key=lambda b: b.props.name)
    # Season score is a dict containing the helm name the total points, and
    # the array of
    # results e.g DNF-DNC-1-4-5-OCS

    for helmres in sortedsailresults:
        if helmres.props.club == 'mpyc':
            # print(helm.name)
            # print(series_sum[helm])
            # todo need to interleave results from different classes in the
            # correct order.
            for racekey, racepos in sorted(helmres.results):
                if racepos.isdigit():
                    # print(racepos)
                    # print(helmres.points)
                    rank = float(racepos)
                    racescore = 300 / (rank + 2)
                    helmres.mpycscore += racescore

    # print(season_score.items())
    if not highpoint:
        # lowpoint scoring
        table = sorted(sortedsailresults,
                       key=lambda x: x.points, reverse=True)
    else:
        table = sorted(sortedsailresults, key=lambda x: x.props.comptotal,
                       reverse=True)
    # round score
    # print(table)
    # create the formatted results
    if not highpoint:
        formattedresults = []
        for helmres in table:
            # get last ten ranked results
            results10 = helmres.results[-10:]
            formattedresults.append(
                [helmres.props.name, round(helmres.points),
                 "-".join(results10)])
    else:
        formattedresults = []
        resultshighpoint = {}
        for helmres in table:
            if helmres.props.club == "mpyc":
                results10 = helmres.results[-10:]
                # print(results10)
                # print(helm.results.items())
                if helmres.props.name not in resultshighpoint.keys():
                    resultshighpoint[helmres.props.name] = [
                        helmres.props.yclass,
                        round(float(helmres.props.comptotal)), results10,
                        helmres.races,
                        helmres.placetally[1],
                        helmres.placetally[2], helmres.placetally[3],
                        f"{helmres.placetally[1] / helmres.races * 100:4.1f}",
                        f"{float(helmres.props.comptotal) / helmres.races:4.1f}"]
                else:
                    resultshighpoint[helmres.props.name][1] += round(
                        float(helmres.props.comptotal))

                    resultshighpoint[helmres.props.name][2].extend(results10)
                    resultshighpoint[helmres.props.name][3] += helmres.races
                    resultshighpoint[helmres.props.name][4] += helmres.placetally[1]
                    resultshighpoint[helmres.props.name][5] += helmres.placetally[2]
                    resultshighpoint[helmres.props.name][6] += helmres.placetally[3]
                    resultshighpoint[helmres.props.name][7] = f"{resultshighpoint[helmres.props.name][4] / resultshighpoint[helmres.props.name][3] * 100:4.1f}"
                    resultshighpoint[helmres.props.name][8] = f"{resultshighpoint[helmres.props.name][1] / resultshighpoint[helmres.props.name][3]:4.1f}"                

        # go through each helm and reorder results from last race to first
        # and trim any races greater than 10 entries
        for helmname in resultshighpoint.keys():
            # print(resultshighpoint[key][1])
            # resort in reverse race order
            sortemp = sorted(resultshighpoint[helmname][2], reverse=True)
            # print(sortemp)
            # Now process into a comma seperated list of positions while
            # removing the race foreign key.
            temp = [item[1] for item in sortemp][0:10]
            # print(temp)
            resultshighpoint[helmname][2] = ",".join(temp)
            # Add to formatted list to pass to the template.
            formattedresults.append(
                [helmname])
            formattedresults[-1].extend(resultshighpoint[helmname][:])

    # save current table position to file
    #last_table_state = save_table_position(formattedresults, num_races)
    # Add position delta to table
    # print(last_table_state)
    # print(formattedresults)

    if not highpoint:
        template = env.get_template('points_table_template.html')
    else:
        if args.fpp:
            template = env.get_template('points_table_template_highpoint_fpp.html')
        else:
            template = env.get_template('points_table_template_highpoint.html')
    print(template.render(updatetime=Globals.todayformat,
                          table=formattedresults,
                          races=num_races), file=file)


def initialise_matrix(sailresults):  # initialise matrix
    matrix = []
    sailresultssorted = sorted(sailresults, key=lambda b: b.props.name)
    for i in range(len(sailresultssorted)):
        matrix.append([])
        for j in range(len(sailresultssorted)):
            matrix[i].append(MatchRes(sailresultssorted[i].props,
                             sailresultssorted[j].props))

    return matrix


def handicap_adjust(races_detail):
    """Calculates adjustments to PY handicaps.

    Uses the method described in:
    https://www.rya.org.uk/SiteCollectionDocuments/technical/Web%20Documents/PY%20Documentation/Specimen%20Races%202016.pdf
    Specimen Race One is the example.

    """

    # List candidate races.
    # A candidate race is one in which there is at least three of different
    # classes in the race
    # create default dict to store a tally of the number of boats in each
    # class in the race
    class_tally = defaultdict(dict)
    # iterate over races to create a tally of boats in each class in each race
    for racekey, raceresults in races_detail.items():
        for helmkey, props in raceresults.items():

            try:
                class_tally[racekey][props['class']] += 1
            except KeyError:
                class_tally[racekey][props['class']] = 1

    candidate_races = []
    for race, tally in class_tally.items():
        num_classes_with_minimum_boats = 0
        if len(tally) > 1:
            # Only consider races that have more than one class
            for yclass, num in tally.items():
                if num >= Globals.min_number_per_class:
                    num_classes_with_minimum_boats += 1
        if num_classes_with_minimum_boats > 1:
            candidate_races.append(race)

    print(f"{len(candidate_races)} races meet the criteria of having more" +
          f" than one class and at least {Globals.min_number_per_class} in" +
          " each class")

    # Get average corrected time for top 2/3 of fleet to exclude poor
    # performers
    correction = {"ILCA 7": {"sum": 0.0, "r": 0},
                  "ILCA 6": {"sum": 0.0, "r": 0},
                  "ILCA 4": {"sum": 0.0, "r": 0}}
    for racekey in candidate_races:
        # print(f"Processing handicap adjustment for race id {racekey}")
        results = races_detail[racekey]
        # Created corrected times list and sort
        cor_times = []
        for helmkey, props in results.items():
            cor_times.append(props['corrected'])
        cor_times.sort()
        # average top 2/3
        act = sum(cor_times[:round(len(cor_times)*2/3)]) \
            / round(len(cor_times)*2/3)
        # print(f"average corrected time is {act}")
        act_105 = act * 1.05
        # now calculate S
        sum_s = []
        for cs in cor_times:
            if cs < act_105:
                sum_s.append(cs)
        std = sum(sum_s) / len(sum_s)
        # print(f"standard corrected time is {std}")
        # now calculate performance indexes
        for helmkey, props in results.items():
            if props["corrected"] < act_105 and props["class"] \
             in correction.keys():
                # time is less than mean * 1.05 of top 2/3 so include
                performance = props["elapsed"] * 1000 / std
                p_index = performance - float(props["rating"])
                # add to correction matrix
                correction[props["class"]]["sum"] += p_index
                correction[props["class"]]["r"] += 1

    print("Suggested handicap adjustments are:")
    for yclass, vals in correction.items():
        cor = vals["sum"] / vals["r"]
        print(f"{yclass}: {cor} (r={vals['r']})")
    return correction


if __name__ == '__main__':
    args = parser.parse_args()
    sailresults, races, racesdetail = read_sailwave_series_summary("SENIOR", args)
    # print(sailresults)
    # print(races)
    matrix = initialise_matrix(sailresults)
    # print(matrix)
    raceno = len(races)
    print('processing matchups for %d races' % raceno)

    for race in races:
        process_race(sailresults, matrix, race)

    # for helm in helms:
    #    print(f"{helm.name} {helm.placetally}")

    # Output some season summary statistics
    # Create a list of the number of races each helm participated in
    races_list = [helm.races for helm in sailresults]
    print(f"Total person races: {sum(races_list)}")
    print(f"Average sailors per race: {sum(races_list) / len(races)}")

    generate_html(matrix, args)
    # print(matrix)
    generate_points_table(sailresults, True, raceno, args)

    if args.calc_corrections is True:
        handicap_adjust(racesdetail)
