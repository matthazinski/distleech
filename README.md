## Introduction

**Under development** - basic functionality likely works though

*distleech* is a distributed torrent download queue for Gazelle-based music
trackers. This was originally designed to assist in an effort to find digital
versions of albums listed in a CSV file without manually querying each tracker. 

A central Flask app handles dispatching requests and receiving responses from
client nodes. Client nodes are responsible for either performing API requests
(if they accept a metadata download task) or downloading torrents (if they
accept a torrent download task). 

CouchDB is used to store metadata about torrents and artists. There are several
reasons for this. Client nodes can cache artist information to avoid an
expensive (2 second) API call to Gazelle; if multiple albums for a given artist
exist in the metadata download queue, there is no guarantee that they will be
dispatched to the same client. Storing torrent file lists and directory names
also allows easy identification of the torrent associated with a given
directory via a CouchDB query.

If multiple clients are needed, a central CouchDB server is recommended.
Bidirectional replication can then be configured with all client nodes syncing
to the central database server.

For now, files must be transferred out of band between a seedbox and central
file server. I can't think of an elegant way to do this securely with NFSv4.
Object storage is probably more suitable in the long run, since we don't need
to preserve owner information.


## distleech.py

`distleech.py` is the client application.

### Getting started

* Copy config.py.example to config.py and edit the appropriate values.
* Install CouchDB on your client machine. Either create databases for
  "torrents_$sitename" for every site you'll be using, or ensure you have admin
  privileges on the database.
* Setup CouchDB replication with the instance running on the server
  (recommended)

### Metadata downloading

Syntax: `distleech.py metadata NUMBER` where NUMBER is an integer between 1 and
100, inclusive.

This will search all sites configured in config.py and use CouchDB as a
metadata cache. Torrent IDs corresponding to the server's AlbumInventory are
relayed to the server and become DownloadTasks.

### Torrent downloading

Syntax: `distleech.py torrent SITE NUMBER SEEDBOX` where:

* NUMBER is an integer between 1 and 100, inclusive.
* SITE is the name of the site configured in config.py
* SEEDBOX is a name of the seedbox configured in config.py

This will search all sites configured in config.py and use CouchDB as a
metadata cache. Torrent IDs corresponding to the server's AlbumInventory are
relayed to the server and become DownloadTasks.

## distleech_server.py

`distleech_server.py` is the Flask server component which acts as a central
manager and dispatcher of metadata and torrent download requests.

### Getting started

* Copy config.py.example to config.py. Ensure you can write to the DB_PATH
  selected.
* Install CouchDB and configure authentication
* Initialize the database
  
```
$ python2
>>> from distleech_server import init_db
>>> init_db()
```

* Add your inventory CSVs. Ideally this would be done with a cronjob that grabs the latest data.

```
$ python2
>>> from distleech_server import add_csv_to_db
>>> add_csv_to_db('/tmp/INVENTORY_Rock_CDs.csv')
```

* `$ export FLASK_APP=distleech_server.py`
* `$ flask2 run`

### Accepting metadata download requests

Visiting `/metadata/<rows>` will give the user `<rows>`
number of albums to find metadata for. If metadata is not returned within an
hour, the tasks may be reallocated to another user. Up to 100 metadata requests
may be accepted at a time. JSON is returned.

```
$ curl http://localhost:5000/metadata/2
{
  "albums": [
    {
      "album": "You've Never Seen Everything", 
      "id": 231, 
      "sortArtist": "Cockburn, Bruce"
    }, 
    {
      "album": "Life Short Call Now", 
      "id": 232, 
      "sortArtist": "Cockburn, Bruce"
    }
  ]
}
```

### Submitting metadata

Once a client has attempted to locate torrents corresponding to rows in the
AlbumInventory table, it should submit those to the distleech server. The
following example sends the following data:

  * Entry #111 in the AlbumInventory table is available as torrent number 37 on
    PTH
  * Entry #444 in the AlbumInventory table could not be located

`$ curl -H "Content-type: application/json" -X POST http://localhost:5000/metadata/submit -d '{"111": [{"site":"https://passtheheadphones.me/", "torrentId":37}], "444":[]}'`

This will result in:

  * Further attempts to find entry #444
  * PTH torrent #37 will become available in the download queue for the next
    client willing to accept it

Note that you must send AlbumInventory ID numbers as strings. Flask's JSON
parser can't handle integer dict keys (nor can JavaScript).

### Accepting torrent download requests

Send the "site" and "rows" POST form fields to `/torrents` accept "rows" number
of torrents to download from the given site. A JSON response is returned,
containing the user-specified site's hostname and a list of torrents.

```
$ curl -X POST http://localhost:5000/torrents -d 'site=https://passtheheadphones.me&rows=5'
{
  "site": "passtheheadphones.me", 
  "torrents": [
    {
      "id": 1, 
      "siteTorrentId": 1337
    }
  ]
}
```

### Submitting torrents

Similar to the metadata submission, torrent submission uses the `/torrents/submit` endpoint. You should submit a JSON dict in the form of: "{localPath: [{'site': site, 'torrentId', tid}]}"

```
$ curl -X POST http://localhost:5000/torrents/submit -d '{"/path/to/dir": [{"site": "https://what.cd", "torrentId": 5555}]}'
```

Since Gazelle provides a file list in the torrent API, we can figure out which
torrent a given directory in the ingest volume corresponds to, as long as the
client that uploaded it also uploaded the torrent metadata to CouchDB. The
DownloadTasks table will be updated to indicate that the torrent's download has
completed, and the local file path will also be specified should the files be
moved into a long-term folder structure. This also allows us to quickly
determine where a torrent's files live should a reseed request be received.

### Monitoring

Check `/stats` to get some quick statistics.

## TODO

* Native basic auth in distleech_server. Currently you can run this behind
  nginx and have it handle auth for you.
* Handling submitted torrents with CouchDB and mapreduce
* CouchDB replication
* Consider moving to a single "torrents" CouchDB database
