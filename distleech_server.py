#!/usr/bin/env python2

from flask import Flask, g, request, jsonify
from config import DB, SITES, COUCHURI
import sqlite3
import os
from os.path import expanduser
from datetime import datetime, timedelta
from urlparse import urlparse
import csv
import sys
import time
import json
import couchdb
from distleech import normalize_url
import MySQLdb

app = Flask(__name__)


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = MySQLdb.connect(host=DB['host'],
                                           user=DB['username'],
                                           passwd=DB['password'],
                                           db=DB['db'])
    return db


def init_db():
    """
    Sets up the SQL schema for the sqlite DB.
    """
    with app.app_context():
        db = get_db()
        db.text_factory = lambda x: unicode(x, 'utf-8', 'ignore')
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.commit()
        db.close()


def get_all_requests():
    cur = get_db().cursor()
    cur.execute('SELECT * FROM DownloadTasks')
    data = cur.fetchall()
    print(data)


def add_csv_to_db(csvpath):
    """
    Adds the rows in the given CSV to the sqlite database if they are not
    already present. Rows are never deleted.
    """
    with app.app_context():
        cur = get_db().cursor()
        with open(csvpath) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                sortArtist = unicode(row['Artist Name'], 'utf-8').strip()
                album = unicode(row['Album Title'], 'utf-8').strip()

                # If it already exists in the DB, ignore it.
                cur.execute('SELECT * FROM AlbumInventory WHERE Album=:album AND SortArtist=:sortArtist', {'album': album, 'sortArtist': sortArtist})
                result = cur.fetchone()
                if result:
                    continue

                cur.execute('INSERT INTO AlbumInventory(Album, SortArtist, LastDispatched, LastNacked) VALUES (%s, %s, 0, 0)', (album, sortArtist))

        get_db().commit()


@app.route('/metadata/<int:numrows>')
def get_metadata_to_download(numrows):
    """
    Selects albums from our inventory that have not been allocated to other
    users in the past 2 hours. When dispatch is set, the metadata for the
    returned albums will be marked as dispatched so that other users don't
    try to fetch metadata the same albums.
    """
    cur = get_db().cursor()
    if numrows > 100:   # ratelimit
        numrows = 100

    now_date = datetime.now()
    min_date = datetime.now() + timedelta(hours=-2)
    q = 'SELECT Id, Album, SortArtist FROM AlbumInventory WHERE Id NOT IN (SELECT AlbumRequest FROM DownloadTasks) AND LastDispatched < %s ORDER BY LastNacked ASC LIMIT %s'
    
    cur.execute(q, (min_date, str(numrows)))
    
    rows = cur.fetchall()
    resp = {'albums':[]}

    for row in rows: 
        resp['albums'].append({'id':row[0],
                               'album':row[1],
                               'sortArtist':row[2]})
        q = 'UPDATE AlbumInventory SET LastDispatched = %s WHERE Id = %s'
        cur.execute(q, (now_date, row[0]))

    get_db().commit()

    return jsonify(**resp)


@app.route('/torrents', methods=['GET', 'POST'])
def get_torrent_to_download():
    """
    Selects torrents from a specified site from DownloadTasks and gives
    them to the user to download. If dispatch it set, the user will be
    marked as responsible for downloading. Users have 14 days to complete
    the download by default.
    """
    if request.method == 'GET':
        ret = '403: Method not supported.<br><br>Try:<br>'
        ret += "curl -X POST http://distleech.example.com/torrents -d 'site=https://tracker.example.com&rows=5'"
        return ret, 405
    try:
        site = normalize_url(request.form['site'])
    except:
        resp = {'torrents':[]}
        return jsonify(**resp)
    
    cur = get_db().cursor()

    if 'rows' in request.form:
        numrows = request.form['rows']
    else:
        numrows = 0
    if numrows > 100:   # ratelimit
        numrows = 100

    now_date = datetime.now()
    min_date = datetime.now() + timedelta(days=-14)
    q = 'SELECT Id, SiteTorrentId FROM DownloadTasks WHERE LastDispatched < %s AND Filled = 0 AND SiteUrl = %s ORDER BY LastDispatched ASC LIMIT %s'
    
    cur.execute(q, (min_date, site, str(numrows)))
   
    resp = {'torrents':[]}
    rows = cur.fetchall()

    for row in rows: 
        resp['torrents'].append({'id': row[0],
                                 'siteTorrentId': row[1]})
        q = 'UPDATE DownloadTasks SET LastDispatched = %s WHERE Id = %s'
        cur.execute(q, (now_date, row[0]))

    get_db().commit()
    resp['site'] = site
    return jsonify(**resp)


@app.route('/metadata/submit', methods=['PUT', 'POST'])
def submit_metadata_results():
    """
    This function is run whenever a client returns the results from the
    metadata lookups dispatched during get_metadata_to_download(). 

    This should be a single dict. Key is the AlbumInventory Id and value
    is a list of (site, value) tuples.
    """
    results = request.get_json()
   
    import pprint
    pprint.pprint(results)

    cur = get_db().cursor()
    now = datetime.now()

    if not results:
        return "Invalid request - is it JSON?", 400

    for albumId,v in results.iteritems():
        # JSON has no such thing as int keys
        albumId = int(albumId)

    
        # Item wasn't found. Even if this already exists in DownloadTasks,
        # we don't care because we take that table into account when
        # issuing new metadata dispatches.
        if not v:
            q = 'UPDATE AlbumInventory SET LastNacked = %s WHERE Id = %s'
            cur.execute(q, (now, albumId))
        else:
            for row in v:
                site = normalize_url(row['site'])
                tid = row['torrentId']
                # If there's already a corresponding DownloadTask for the
                # site, tid pair, we can safely ignore it
                q = 'SELECT Id FROM DownloadTasks WHERE SiteUrl = %s AND SiteTorrentId = %s'
                cur.execute(q, (site, tid))
                existingTasks = cur.fetchall() 
                print(existingTasks)
                if existingTasks:
                    continue

                q = 'INSERT INTO DownloadTasks(SiteUrl, SiteTorrentId, AlbumRequest, LastDispatched, Filled) VALUES (%s, %s, %s, 0, 0)'
                cur.execute(q, (site, tid, albumId))

    get_db().commit()
    return "Ok", 200


@app.route('/stats')
def get_stats():
    cur = get_db().cursor()
    cur.execute('SELECT Id FROM AlbumInventory')
    numAlbums = len(cur.fetchall())

    resp = ''

    resp += 'Albums: {0}\n<br>'.format(numAlbums)

    min_date = datetime.now() + timedelta(hours=-2)
    cur.execute('SELECT Id FROM AlbumInventory WHERE LastDispatched < %s', (min_date,))
    numStaleMetadataDispatches = len(cur.fetchall())
    cur.execute('SELECT Id FROM AlbumInventory WHERE LastDispatched > %s', (min_date,))
    numActiveMetadataDispatches = len(cur.fetchall())

    resp += 'Metadata dispatches: {} stale, {} active\n<br>'.format(numStaleMetadataDispatches, numActiveMetadataDispatches)

    cur.execute('SELECT Id FROM DownloadTasks WHERE Filled=1')
    numFilled = len(cur.fetchall())
    cur.execute('SELECT Id FROM DownloadTasks WHERE Filled=0')
    numUnfilled = len(cur.fetchall())

    resp += 'Requests: {0}/{1} filled\n<br>'.format(numFilled, numFilled+numUnfilled)
    return resp


@app.route('/')
def index():
    return 'Nothing to see here. Move along, now.'
