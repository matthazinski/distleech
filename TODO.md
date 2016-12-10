Here's some things in the pipeline I haven't yet had time to work on:

* Native basic auth in distleech_server. Currently you can run this behind
  nginx and have it handle auth for you.
* Handling submitted torrents with CouchDB and mapreduce
* CouchDB replication
* Consider moving to a single "torrents" CouchDB database
* Use some sort of WAN-accessible object store (e.g. S3-compatible server) to
  move data between seedboxes and final storage nodes.
* Replace /stats with a JSON API and more human-parseable content depending on
  "Accept" header.
* Add more useful queries to /stats
