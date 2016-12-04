#!/usr/bin/env python2
"""
Usage: distleech.py metadata SITE NUMBER
       distleech.py torrent SITE NUMBER SEEDBOX
       distleech.py (-h|--help)

Arguments:
    SITE         name of Gazelle instance to use
    NUMBER       number of torrents/metadata to download
    SEEDBOX      name of seedbox from config.py

Options:
    -h --help    show this
    m, metadata  download metadata (rather than torrents)
    t, torrent   download torrents (rather than metadata)
""" 
from docopt import docopt
import whatapi
import cPickle as pickle
from pprint import pprint
import json
import os
import csv
import time
import sys
from config import SITES, COUCHURI
from os.path import expanduser
import sqlite3
import os.path
import couchdb
from datetime import datetime, timedelta
from urlparse import urlparse



def _first_run(username, password, baseurl, filename):
    if not os.path.exists(expanduser('~/.distleech')):
        os.makedirs(expanduser('~/.distleech'))
    apihandle = whatapi.WhatAPI(username=username,
                                password=password,
                                baseurl=baseurl)
    pickle.dump(apihandle.session.cookies, open(filename, 'wb'))
  

def get_api_handle(username, password, baseurl, cookies=None):
    apihandle = whatapi.WhatAPI(username=username,
                                password=password,
                                baseurl=baseurl,
                                cookies=cookies)
    return apihandle


def get_api_handle_for_site(sitename):
    fname = expanduser('~/.distleech/{}.dat'.format(sitename))

    for site in SITES:
        if site['name'] == sitename:
            try:
                cookies = pickle.load(open(fname, 'rb'))
            except:
                _first_run(site['username'], 
                           site['password'],
                           site['baseurl'],
                           fname)
                cookies = pickle.load(open(fname, 'rb'))
            return get_api_handle(site['username'],
                                  site['password'],
                                  site['baseurl'],
                                  cookies)

    return None


def close_api_handle_for_site(apihandle, sitename):
    fname = expanduser('~/.distleech/{}.dat'.format(sitename))
    pickle.dump(apihandle.session.cookies, open(fname, 'wb'))


def normalize_url(url):
    u = urlparse(url)
    return u.netloc


def get_torrent_ids_for_dl(preferredTorrents):
    """
    Takes a list of preferredTorrents as returned from the method
    get_best_torrents_from_group(). Provides a list of torrent IDs that should
    be downloaded. This DLs anything with a score of at least 100 and the best
    item regardless of the score.
    """
    list = []
    bestScore = 0
    bestItem = 0
    for format, value in preferredTorrents.iteritems():
        if 'id' in value:
            if value['score'] > bestScore:
                bestItem = value['id']
                bestScore = value['score']
            if value['score'] >= 100:
                list.append(value['id'])

    if bestItem not in list:
        list.append(bestItem)

    return list


def get_best_torrents_from_group(tg):
    """Takes JSON dict like so:

    >>> j['response']['torrentgroup'][0]['torrent'][0]
    {u'remastered': False, u'remasterRecordLabel': u'', u'seeders': 0, u'encoding': u'Lossless', u'hasLog': True, u'media': u'CD', u'format': u'FLAC', u'scene': False, u'groupId': 5469, u'remasterTitle': u'', u'leechers': 0, u'remasterYear': 0, u'size': 271825613, u'snatched': 0, u'time': u'2016-11-26 06:07:51', u'logScore': 100, u'freeTorrent': True, u'hasFile': 9970, u'id': 9970, u'fileCount': 15, u'hasCue': True}A

    We'd be passing in j['response']['torrentgroup'][0] where j comes from
    get_artist_json()
    """

    relGrpName = tg['groupName']    # Album name

    preferredTorrents = {'WEB': {}, 'Vinyl': {}, 'CD': {}}

    flacList = []
    
    for t in tg['torrent']:
        tScore = 0
        
        # Lossless only, don't want any bitrot
        if t['format'] != 'FLAC':
            continue
        else:
            flacList.append(t['id'])

        # fuck it, we'll sort out what we dl'd later. Get all the flac.

        # TODO

        if t['media'] == 'WEB':
            if t['encoding'] == 'Lossless':
                tScore = 50
            elif t['encoding'] == '24bit Lossless':
                tScore = 100
            if 'score' in preferredTorrents['WEB']:
                if tScore < preferredTorrents['WEB']['score']:
                    preferredTorrents['WEB']['id'] = t['id']
                    preferredTorrents['WEB']['score'] = tScore
            else:
                preferredTorrents['WEB']['id'] = t['id']
                preferredTorrents['WEB']['score'] = tScore
                

        elif t['media'] == 'CD':
            if t['hasLog']:
                tScore = t['logScore']
            if t['hasCue']:
                tScore = tScore + 1
            if 'score' in preferredTorrents['CD']:
                if tScore < preferredTorrents['CD']['score']:
                    preferredTorrents['CD']['id'] = t['id']
                    preferredTorrents['CD']['score'] = tScore
            else:
                preferredTorrents['CD']['id'] = t['id']
                preferredTorrents['CD']['score'] = tScore

        elif t['media'] == 'Vinyl':
            tScore = 0
            if t['encoding'] == 'Lossless':
                tScore = 50
            elif t['encoding'] == '24bit Lossless':
                tScore = 100

            if 'score' in preferredTorrents['Vinyl']:
                if tScore < preferredTorrents['Vinyl']['score']:
                    preferredTorrents['Vinyl']['id'] = t['id']
                    preferredTorrents['Vinyl']['score'] = tScore
            else:
                preferredTorrents['Vinyl']['id'] = t['id']
                preferredTorrents['Vinyl']['score'] = tScore

        else:
            # Cassettes?
            continue


    return preferredTorrents

    
        # TODO if 'remasterTitle' is non-null then this is a reissue
       
def read_artist_json(artistId):
    if os.path.exists('cache/{0}.json'.format(artistId)):
        with open('cache/{0}.json'.format(artistId)) as f:
            json_data = f.read()

        data = json.loads(json_data)
        return data

    else:
        return {}


def write_artist_json(result):
    if 'response' not in result:
        return

    artistId = result['response']['id']
    with open('cache/{0}.json'.format(artistId), 'wb') as f:
        json.dump(result, f)


def get_artist_json(apihandle, artistname):
    try:
        result = apihandle.request('artist', artistname=artistname)
    except:
        result = {}

    return result


def get_torrent_json(apihandle, torrentid):
    try:
        result = apihandle.request('torrent', id=torrentid)
    except:
        result = {}

    return result


def csv_to_album_list(csvpath):
    unparseableArtists = []

    albumsByArtist = {}

    with open(csvpath) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            bareArtist = ''
            sortArtist = row['Artist Name']
            album = row['Album Title']

            bareArtist = sortartist_to_artist(sortArtist)

            if bareArtist == '':
                unparseableArtists.append(sortArtist)
            else:
                if bareArtist in albumsByArtist:
                    albumsByArtist[bareArtist].append(album)
                else:
                    albumsByArtist[bareArtist] = [album]
    
    return albumsByArtist, unparseableArtists


def sortartist_to_artist(sortArtist):
    """
    Attempts to convert an artist string from Len's sort formatting to an
    actual artist name. This still won't work well for multi-artist lists.
    """
    if ',' in sortArtist:
        cs = sortArtist.split(',')
        if len(cs) == 2:
            if '/' in cs[1]:
                bareArtist = sortArtist.split('/')[1].strip()
            else:
                bareArtist = '{0} {1}'.format(cs[1].strip(), cs[0].strip())
    else:
        bareArtist = sortArtist.strip()


def write_download_torrents_list(handle, artist, albumList, outputDir):
    j = get_artist_json(handle, artist)
    if 'response' not in j:
        return

    write_artist_json(j)

    print('Finding torrents for {0}'.format(artist))
        
    ids = []

    for group in j['response']['torrentgroup']:
        if group['groupName'] in albumList:
            print('...found {0}'.format(group['groupName']))
            best = get_best_torrents_from_group(group)
            ids = ids + get_torrent_ids_for_dl(best)

    path = os.path.join(outputDir, '{0}.txt'.format(j['response']['id']))
    
    with open(path, 'a') as f:
        for i in ids:
            f.write(str(i) + '\n')


def get_cached_artist_page(sitename, artistname, apihandle=None, expirytime=0):
    """
    Gets the artist page from CouchDB, if it exists. If the requested document
    does not exist in the cache, or the cache is stale (based on expirytime),
    the Gazelle API is used to fetch the latest artist information and add it
    to the cache prior to returning.

    An API handle is optional. If not specified, reads will return the most
    recent cached data regardless of the expirytime parameter. If no data is
    present, an empty dict will be returned.
    """
    # TODO
    return


def add_torrent_info_to_couchdb(apihandle, dbname, torrentid, username=None):
    """
    Grabs torrentid from Gazelle using the API handle and stores it in dbname
    in CouchDB. The UUID will be the torrent ID. We'll be storing:
    - data['response']
    - datetime of utcnow() - this lets us know if data is stale. There is no
      immediate use for this, but we may wish to scrub torrent metadata at a
      later date and remove things that are either removed from the site or
      have bad metadata.
    - username of submitter - an optional field to indicate who last modified
      this document

    DB name should match the format: torrents_$sitename

    This method must be called whenever a torrent is downloaded which you
    expect Alexandria to be able to handle. A mapreduce can be performed from
    the data in couch to figure out what torrent an unknown directory
    corresponds to, so that it can be appropriately filed away. The file sizes
    can also be used to ensure files downloaded completely.

    We aren't using python bindings for libtorrent to handle torrents directly
    because it's a bitch to compile, particularly on Arch.

    Returns True if there was anything worth storing obtained from Gazelle's
    API and False otherwise
    """
    j = get_torrent_json(apihandle, torrentid)

    doc = {'_id': str(torrentid)}

    # If we get an invalid response, don't want to risk corrupting potentially
    # valid (yet old) data for the same torrent ID.
    if 'status' in j:
        if j['status'] != 'success':
            return False

    if username:
        doc['username'] = username

    doc['datetime'] = datetime.utcnow().isoformat()

    if 'response' in j:
        doc['torrent'] = j['response']

    # Create the db if it doesn't exist
    couch = couchdb.Server(COUCHURI)
    if dbname not in couch:
        couch.create(dbname)

    db = couch[dbname]
    db.save(doc)

    return True

    
if __name__ == "__main__":
    args = docopt(__doc__)

    if not args['NUMBER'].isdigit():
        print('NUMBER must be a number')
        sys.exit(1)

    # Validate siteName
    siteName = args['SITE']
    site = {}
    for s in SITES:
        if s['name'] == siteName:
            site = s
    if not site:
        print('SITE not found in config.py. Exiting.')
        sys.exit(1)

    handle = get_api_handle_for_site(siteName)

    if args['torrent']:
        # Validate seedbox name
        from config import SEEDBOXES, SERVER_URI
        seedboxName = args['SEEDBOX']
        seedbox = {}
        for s in SEEDBOXES:
            if s['name'] == seedboxName:
                seedbox = s
        if not seedbox:
            print('SEEDBOX not found in config.py. Exiting.')
            sys.exit(1)

        raise NotImplementedError('Torrent adding not yet implemented')

        # TODO get N items from server
        # TODO iterate, parse sortArtist, store items in cache, download torrent file, sleep 2 seconds
        # TODO add files to seedbox

    elif args['metadata']:
        from config import SERVER_URI
        raise NotImplementedError('Metadata downloading not yet implemented')

        # TODO get N items from server
        # TODO iterate, grab items using couchdb cache, sleep 2 seconds
        # TODO return to server

    close_api_handle_for_site(handle, siteName)
