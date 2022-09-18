'''
Add starts MPYC.

This script opens a sailwave file and adds start times to the races in it based
on a starttimes file.

'''

#format MPYC export
import csv
import sys 
import os.path
import re
import datetime


newcsv = []
outfile = open(os.path.splitext(sys.argv[1])[0] + '_starts.csv', 'w', newline='') 
writer = csv.writer(outfile, delimiter=',')
                            
sailwavefile = open(sys.argv[1])
text = csv.reader(sailwavefile,delimiter= ",")
    #print(text)
    
    
                            
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
            races[str(row[1])] = actualstart
    #print(races)

for row in text:
    newrows = []
    #print(row[0])
    if row[0] == "racerank":
        print("found a start")
        currank = row[1]
        #check to see if rank in races
        print(currank)
        try:
            races[row[1]]
            updatetime = True 
        except KeyError:
            newrows.append(row)
            updatetime = False
            continue
    elif row[0] == "racestart":
        if updatetime:
            temprow = row
            temprow = "'racestart','|'" + races[currank].strftime('%d-%m-%y@%H.%M.%S')+"|Place|Start 1|||0||0|0||||1','','1449'"
            newrows.append(temprow)
            continue
    newrows.append(row)

for row in newrows:    
    writer.writerow(row)
#print(text)            
        
    
    
