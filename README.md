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

Torrent submission has not yet been implemented. Eventually this will involve
mapreduce queries upon CouchDB. Since Gazelle provides a file list in the
torrent API, we can figure out which torrent a given directory in the ingest
volume corresponds to, as long as the client that uploaded it also uploaded the
torrent metadata to CouchDB. The DownloadTasks table will be updated to
indicate that the torrent's download has completed, and the local file path
will also be specified should the files be moved into a long-term folder
structure. This also allows us to quickly determine where a torrent's files
live should a reseed request be received.

### Monitoring

Check `/stats` to get some quick statistics.

## TODO

* Native basic auth in distleech_server. Currently you can run this behind
  nginx and have it handle auth for you.
* Handling submitted torrents with CouchDB and mapreduce
* CouchDB replication
