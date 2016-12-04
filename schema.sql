CREATE TABLE AlbumInventory(Id INTEGER PRIMARY KEY AUTOINCREMENT, Album TEXT, SortArtist TEXT, LastDispatched TIMESTAMP, LastNacked TIMESTAMP);
CREATE TABLE DownloadTasks(Id INTEGER PRIMARY KEY AUTOINCREMENT, User TEXT, SiteUrl TEXT, SiteTorrentId INTEGER, LastDispatched TIMESTAMP, Filled INTEGER, LocalUri TEXT, AlbumRequest INTEGER, FOREIGN KEY(AlbumRequest) REFERENCES AlbumInventory(id));