@echo off
python generate_webcontent.py -from_day_files
python generate_webcontent.py -fpp -from_day_files
ftp -i -s:uwin.ftp

