@echo off
python generate_webcontent.py
ftp -i -s:uwin.ftp

