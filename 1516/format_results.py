'''
Format results MPYC.

This script takes the results exported from the MPYC YRR access database from and
converts them to a format that can be imported directly into sailwave.

The script requires two tables to be exported from the YRR database.

Table 1 is the 'tbl results'.  This should be exported as a csv file.
Table 2 is the 'qry tbl Race Details'.  This should be exported as a csv file.

Table 1 is used to gather all results.  Because Table one does not include the
race start time this is gathered from table 2 and combined into to a new csv 
file saved to the same directory.

Some additional things the scripts does:
1. MPYC convention has been to append the class name to the helm name if not laser
standard.  For example if Joe Bloggs is sailing a 4.7, then his helm name would
be "Joe Bloggs 4.7".  The script strips these out and converts them to a class.

2.  It looks for incorrect sail numbers. For example if the same helm and class
has sailed with more than one sail number it converts the sail number to the first one found.
'''

#format MPYC export
import csv
import sys 
import os.path
import re
import datetime


newcsv = []
outfile = open(os.path.splitext(sys.argv[1])[0] + '_formatted.csv', 'w', newline='') 
writer = csv.writer(outfile, delimiter=',')
                            
                            
def convertclass(yclass, name):
    if yclass == 'la':
        if '4.7' in name:
            newclass = 'LASER 4.7'
        elif ' ra' in name:
            newclass = 'LASER RADIAL'
        elif ' Ra' in name:
            newclass = 'LASER RADIAL'
        elif ' Radial' in name:
            newclass = 'LASER RADIAL'    
        elif ' Rad' in name:
            newclass = 'LASER RADIAL'  
        elif 'Phase II' in name:
            newclass = 'PHASE 2'
        elif 'Phase 2' in name:
            newclass = 'PHASE 2'        
        else:
            newclass = 'LASER'
    elif yclass == 'op':
        newclass = 'OPTIMIST'
    elif yclass == 'pc':
        newclass = 'P CLASS'
    elif yclass == 'su':
        newclass = 'SUNBURST'
    elif yclass == 'ze':
        newclass = 'ZEPHYR'
    elif yclass == 'pt':
        newclass = 'PAPER TIGER'
    elif yclass == 'p2':
        newclass = 'PHASE 2'
    elif yclass == 'fb':
        newclass = 'FIREBUG'
    elif yclass == 'st':
        newclass = 'STARLING'
    else:
        #print('here')
        newclass = yclass
        
    return newclass
        
        
def format_name(skipper):
    replacestr = ['\s+4.7','\s+Radial','\s+Phase 2','\s+Phase II','\s+Rad', 
                    '\s+ra', '\s+Ra']
    
    for str in replacestr:
        skipper = re.sub(str,'', skipper)
    return skipper


#get race details
with open(sys.argv[2]) as csvfile:  
    races = {}
    reader = csv.reader(csvfile, delimiter=',')
    for i, row in enumerate(reader):
        #convert date and starttime into proper starttime
        if i != 0:
            date = datetime.datetime.strptime(row[0],'%d-%b-%y')
            start = datetime.datetime.strptime(row[4],'%d-%b-%y %H:%M:%S')
            actualstart = datetime.datetime.combine(date,start.time())
            races[row[1]] = actualstart
    #print(races)
                            
with open(sys.argv[1]) as csvfile:
    reader = csv.reader(csvfile, delimiter=',')
    hash_name_class = {}
    for i, row in enumerate(reader):
        nrow = row
        if i == 0:
            #Header row
            writer.writerow(row + ['starttime'])
        else:
            #convertclass
            nrow[2] = convertclass(row[2],row[5])
            #remove class from name
            nrow[5] = format_name(row[5])
            #print(nrow[2])
            #check name
            if nrow[5] + nrow[2] in hash_name_class.keys():
                #adjust sailnumber
                nrow[4] = hash_name_class[nrow[5] + nrow[2]]
            else:
                hash_name_class[nrow[5] + nrow[2]] = nrow[4]
            #convert finish time
            if row[10] == 'dnf':
                nrow[9] = 'dnf'
            else:
                dt = datetime.datetime.strptime(row[9],'%d-%b-%y %H:%M:%S')
                #print(races[row[1]])
                finishtime = datetime.datetime.combine(races[row[1]].date(),
                                                        dt.time())
                nrow[9] = finishtime.strftime('%d-%m-%y@%H.%M.%S')
            writer.writerow(nrow + [races[row[1]].strftime('%d-%m-%y@%H.%M.%S')])
            
        
    
    
