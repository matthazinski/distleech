#!/usr/bin/env python2
import couchdb
import requests
from urlparse import urljoin
from config import COUCHURI, SITES, SEARCH_DIRS, SERVER
from pprint import pprint
import json
import os
from HTMLParser import HTMLParser

# The ID in the DB corresponds to the ID on the torrent site. _id is available
# in the output of map functions so it doesn't need to be specified explicitly.

map_func = '''function(doc) {
  if(doc.torrent && doc.torrent.torrent && doc.torrent.torrent.filePath) {
  emit(doc.torrent.torrent.filePath, doc.torrent.torrent.fileList);
  }
}'''


def split_filelist(fileList):
    newList = []
    for f in fileList.split('|||'):
        parser = HTMLParser()
        name = parser.unescape(f.split('{{{')[0])
        size = f.split('{{{')[1].split('}}}')[0]
        newList.append({'path': name, 'size': size})

    return newList


# TODO iterate through a list of target directories found in config file
def find_torrents_for_dir(fname):
    fname = os.path.split(fname)[1]

    c = couchdb.Server(COUCHURI)
    allResults = []


    for s in SITES:
        try:
            db = c['torrents_{}'.format(s['name'])]
            results = db.query(map_func)
            siteResults = results[fname].rows
            for r in siteResults:
                allResults.append({'site': s['baseurl'],
                                'id': r.id,
                                'fileList': split_filelist(r.value)})
        except:
            continue

    return allResults


def filter_results(localpath, results):
    valid = []
    if not results:
        return []
    for possibleMatch in results:
        for file in possibleMatch['fileList']:
            validMatch = True
            fullPath = os.path.join(localpath, file['path'])
            try:
                size = os.path.getsize(fullPath)
                if size != int(file['size']):
                    print(u'wrong size on {}'.format(file['path']))
                    validMatch = False
            except:
                print(u'failed on {}'.format(file['path']))
                validMatch = False
        if validMatch:
            valid.append({'site': possibleMatch['site'],
                          'torrentId': int(possibleMatch['id'])})
    return valid


def post_torrent_path(localpath, results):
    URL = urljoin(SERVER['url'], '/torrents/submit')
    j = {}
    j[localpath] = results #{'site': site, 'torrentId': id}
    r = requests.post(URL, json=j, auth=(SERVER['username'], SERVER['password']))


for d in SEARCH_DIRS:
    for fname in os.listdir(d):
        fname = os.path.join(d, fname)
        allResults = find_torrents_for_dir(fname)
        filteredResults = filter_results(fname, allResults)
        if filteredResults:
            print(u'Found completed download of {}'.format(fname))
            post_torrent_path(fname, filteredResults)
