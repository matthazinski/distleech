#!/usr/bin/env python2

from distleech_server import init_db, add_csv_to_db
import os
from os import listdir
from os.path import isfile, join, expanduser

try:
    init_db()
except:
    print 'Will not delete existing DB, using existing one'

mypath = expanduser('~/csv')
csvfiles = [f for f in listdir(mypath) if isfile(join(mypath, f))]
for c in csvfiles:
    print(c)
    fullpath = os.path.join(mypath, c)
    add_csv_to_db(fullpath)

