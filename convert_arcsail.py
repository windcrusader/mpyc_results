"""convert_arcsail.py.
Converts and arcsail csv results file into a file more friendly for Sailwave.
"""
import csv
import re
import sys
import os
import math
from datetime import timedelta 
from collections import namedtuple

SailResult = namedtuple('SailResult',
                        'HelmName, SailNo, Class, RaceNo, Elapsed, Code')

class Result():
    def __init__(self, helmname, sailno, elapsed, bclass, code, raceno):
        self.props = SailResult(HelmName = helmname, SailNo = sailno,
                                Elapsed = str(timedelta(seconds=int(float(elapsed)))), 
                                Class = re.search(r"([\s\w\d.]+)",
                                        bclass).group(0).strip().upper(),
                                Code = code, 
                                RaceNo = re.search(r"(\d)",raceno).group(0))

        assert self.props.SailNo.isdigit(), "invalid sail number"
        assert self.props.Class is not None, "bclass cannot be empty"
        assert self.props.RaceNo.isdigit(), "raceno cannot be non integer"
        #assert self.props.Elapsed.isdigit(), "elapsed cannot be non integer"
        
    def convert_elapsed(secs):
        """Convert a time in secs to hh:mm:ss format"""
        
        
        
    def __repr__(self):
        return (repr(self.props))           
        
    def __str__(self):
        return (self.props)    
    
    def __iter__(self):
        for aproperty in self.props:
            yield aproperty

def read_file(filename):
    results = []
    with open(filename) as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        start = False
        
        for row in reader:
            if row[0] == "TeamRaceTime":
                print("Found start row")
                start = True
            if start == True and row[0] == "data" and row[1][0] == "p":
                #print("Found race data")
                if row[14] == "LASEM":
                    bclass = "ILCA 6"
                elif row[14] == "LASE":
                    bclass = "ILCA 7"
                elif row[14] == "LAS4.7":
                    bclass = "ILCA 4" 
                results.append(Result(elapsed = row[7],sailno = row[22],
                                      helmname = row[21],bclass = bclass,
                                      raceno = row[23], code = row[16]))
            if row[0] == "TeamRaceTimeScoring":
                start = False

    return(results)
                                                                         
def print_csv(results,filename):
    
    #Get filename without extension
    name = os.path.splitext(filename)[0]
    fileout = name + "_sailwave.csv"
    
    with open(fileout, "w") as csvfile:
        writer = csv.writer(csvfile, delimiter = ",")
        writer.writerow(SailResult._fields)
        for row in results:
            writer.writerow(row)
            
      

if __name__ == '__main__':

    results = read_file(sys.argv[1])
    print(results)
    print_csv(results, sys.argv[1])
