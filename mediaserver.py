#!/usr/bin/env python
import argparse
import getpass
import logging
import os
import os.path
import shutil
import sys
import textwrap
from urlparse import urlparse

from twisted.web.server import Site
from twisted.web.resource import Resource, NoResource
from twisted.web.static import File
from twisted.internet import reactor

import paramiko as ssh
from paramiko import config as ssh_cfg

logging.basicConfig(format='%(message)s', level=logging.INFO)


class Client(object):
    def __init__(self, url):
        self.url = url
        self.configure()
        self.logger = logging.getLogger(__name__)

    def configure(self):
        if not hasattr(self, '_config'):
            self._config = ssh_cfg.SSHConfig()
        try:
            self._config.parse(open(os.path.expanduser('~/.ssh/config')))
        except (IOError, ssh_cfg.error) as e:
            self.logger.error('error: {0}'.format(e))

    @property
    def host(self):
        if not hasattr(self, '_host'):
            self._host = dict({
                'user': self.url.username or None,
                'port': self.url.port or 22
            }, **self._config.lookup(self.url.hostname))
        return self._host

    def close(self):
        if hasattr(self, '_sftp'):
            self._sftp.close()
            del self._sftp
        if hasattr(self, '_client'):
            self._ssh.close()
            del self._ssh

    def _connect(self, password=None):
        sock = None
        if self.host.get('proxycommand'):
            sock = ssh.ProxyCommand(self.host['proxycommand'])

        self._ssh = ssh.SSHClient()
        self._ssh.load_system_host_keys()
        self._ssh.set_missing_host_key_policy(ssh.AutoAddPolicy())

        self._ssh.connect(
            self.host['hostname'], self.host['port'],
            username=self.host.get('user'),
            key_filename=self.host.get('identityfile'),
            sock=sock, password=password
        )

    def connect(self):
        if hasattr(self, '_client'):
            return

        try:
            self._connect()
        except ssh.PasswordRequiredException:
            msg = "Enter passphrase for private key: "
            passwd = getpass.getpass(msg)
            self._connect(password=passwd)


class MediaResource(Resource):
    def __init__(self, config):
        Resource.__init__(self)
        self._url = config.url
        self._base_dir = config.dir
        self._client = Client(config.remote)
        self._config = config
        self._remote = config.remote
        self._client.connect()
        self._sftp = self._client._ssh.open_sftp()
        self.logger = logging.getLogger(__name__)
        self.logger.info('connected to remote: {0}'
                         .format(config.remote.geturl()))

    def render_GET(self, request):
        relpath = None
        remote_dir = None
        path = request.path

        if path.startswith(self._url):
            relpath = path[len(self._url):].strip('/')
            remote_dir = self._remote.path.rstrip('/')

        if not relpath:
            # not found
            msg = "Invalid URL"
            return NoResource(msg).render(request)

        local_dir = self._base_dir.rstrip('/')
        local_path = os.path.join(local_dir, relpath)

        # return local file if found
        if os.path.exists(local_path):
            self.logger.info('*** ' + local_path)
            return File(local_path).render_GET(request)

        # get remote file
        remote_path = os.path.join(remote_dir, relpath)
        try:
            rfile = self._sftp.open(remote_path)
        except (OSError, IOError):
            # not found
            msg = "File not found on local or remote"
            return NoResource(msg).render(request)

        self.logger.info('>>> ' + local_path)
        # downloaded file locally
        local_path_dir = os.path.dirname(local_path)
        if not os.path.exists(local_path_dir):
            os.makedirs(local_path_dir)

        with open(local_path, 'w'):
            shutil.copyfileobj(rfile, open(local_path, 'w'))
            rfile.close()

        return File(local_path).render_GET(request)

    def getChild(self, name, request):
        return self


def cmdline():
    desc, epilog = """
    Runs a local static media http server which pulls missing files on-demand
    from a remote location, and stores them locally. This is useful for
    development environments that need to be matched up with a production
    environment while not having to worry about downloading or rsyncing an
    entire directory from the production server. This static media server only
    pulls remote files when they are requested, and then stores the file
    locally for future requests.
    """, """
    The following environment variables can also be used in place of arguments:

      {0}REMOTE
      {0}LISTEN
      {0}URL
      {0}DIR
    """

    parser = argparse.ArgumentParser(add_help=False, description=desc)
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.description

    parser.add_argument('remote', metavar='<remote-host-spec>', action='store',
                        help="remote host specifier (see --help-remote for "
                        "remote host specification)", type=urlparse, nargs='?')
    parser.add_argument('listen', metavar='listen-host[:port]', action='store',
                        help='host/port on which to run static webserver '
                        '(default: %(default)s)', default='localhost:8001',
                        nargs='?')
    parser.add_argument('--url', action='store', metavar='path',
                        help="root url path under which files are served "
                        "(default: %(default)s)", default='/')
    parser.add_argument('--dir', action='store', metavar='directory',
                        help="root directory from which static media files "
                        "are served (default: current dir)", default='.media')
    parser.add_argument('--help', action='help', default=argparse.SUPPRESS,
                        help='show this help message and exit')

    parser.usage = '%(prog)s <remote-url> [listen-host:[port]] [options]'

    progname = os.path.splitext(parser.prog)[0]

    logger = logging.getLogger(__name__)

    env_prefix = progname.upper() + '_'
    parser.epilog = textwrap.dedent(epilog.format(env_prefix)) + '  \n'

    defaults = dict((k[len(env_prefix):].lower(), v)
                    for k, v in os.environ.items()
                    if k.startswith(env_prefix))
    parser.set_defaults(**defaults)

    parser.description = textwrap.dedent(desc.format(env_prefix))
    args = parser.parse_args()

    if not args.remote:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    host, port = args.listen.partition(':')[::2]

    if not port:
        port = 8001
    port = int(port)

    resource = MediaResource(args)
    factory = Site(resource)
    reactor.listenTCP(interface=host, port=port, factory=factory)
    logger.info("local media dir: {0.dir}".format(args))
    logger.info("running web server at http://{0.listen}{0.url}"
                .format(args))
    reactor.run()


if __name__ == '__main__':
    cmdline()
