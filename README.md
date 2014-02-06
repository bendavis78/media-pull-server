media-pull-server is a static media HTTP server which pulls missing files
on-demand from a remote location, and stores them locally. This is useful for
development environments that need to be matched up with a production
environment while not having to worry about downloading or rsyncing an entire
directory of media files from the production server. This static media server
only pulls remote files when they are requested, and then stores the file
locally for future requests.
