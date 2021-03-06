"""Cherryize

Tool for using the standalone CherryPy webserver to run WSGI compatible 
applications such as Django, Pylons etc...
"""

# Nick Snell <nick@orpo.co.uk>

import os
import os.path
import logging
import sys
import signal
import time
from optparse import OptionParser

import yaml

from cherryize.wsgiserver import CherryPyWSGIServer
from cherryize.utils import import_object, get_uid_gid, switch_uid_gid

__all__ = ('WSGIServer',)
__version__ = '0.9'

DEFAULTS = {
	'APP': '',
	'SERVER_NAME': 'localhost',
	'SERVER_THREADS': 10,
	'SERVER_RUN_DIR': '/tmp',
	'SERVER_DAEMONIZE': True,
	'SERVER_USER': 'nobody',
	'SERVER_GROUP': 'nobody',
	'SERVER_TIMEOUT': 60,
	'SERVER_IP': '127.0.0.1',
	'SERVER_PORT': 8080,
	'SERVER_REQUEST_QUEUE_SIZE': 5,
	'LOG': 'server.log',
	'LOG_FORMAT': '%(asctime)s %(levelname)s %(message)s',
	'PID_FILE': 'server.pid',
	'SSL_CERTIFICATE': '',
	'SSL_PRIVATE_KEY': '',
	'PATHS': [],
	'ENVIRON': {},
	'FORCE': False,
	'UMASK': 0
}

VALID_COMMANDS = 'START', 'STOP', 'RESTART'

class WSGIServer(object):
	"""A Basic WSGI Server"""
	
	def __init__(self, conf, runtime_conf={}):
		
		assert conf is not None, u'You must provide a configuration file to the server!'
		
		try:
			config = yaml.load(open(conf, 'r'))
		except Exception, e:
			# Can't read or can't parse, either way no good
			raise RuntimeError(u'Unable to read configuration file! %s' % e)
		
		config = dict([(k.upper(), v) for k, v in config.items()])
		
		server_config = DEFAULTS
		server_config.update(config)
		server_config.update(runtime_conf)
		
		self.config = server_config
		
		assert self.config['APP'], u'You must provide a WSGI application'
		
		# Setup the log...
		logging.basicConfig(
			level=logging.DEBUG,
			format=self.config['LOG_FORMAT'],
			filename=self.config['LOG'],
			filemode='a+'
		)
		
		self.log = logging.getLogger('cherryize')
	
	def run(self, cmd):
		"""Command line startup"""
		
		cmd = cmd.upper()
		
		assert cmd in VALID_COMMANDS, u'You must provide a valid commands!'
		
		if cmd == 'START':
			self.start()
		elif cmd == 'STOP':
			self.stop()
		elif cmd == 'RESTART':
			self.restart()
		else:
			self.log.critical(u'Unknown command "%s"!' % cmd)
			sys.exit(1)
		
	def start(self):
		"""Start a server running"""
		
		# Add nessecary paths
		sys.path.insert(0, self.config['SERVER_RUN_DIR'])
		
		for path in self.config['PATHS']:
			sys.path.insert(0, path)
		
		# Check if we are running a django project
		if 'DJANGO_SETTINGS' in self.config and self.config['DJANGO_SETTINGS']:
			os.environ['DJANGO_SETTINGS_MODULE'] = self.config['DJANGO_SETTINGS']
		
		if self.config['ENVIRON']:
			for k, v in self.config['ENVIRON'].items():
				os.environ[k] = v
		
		pid = None
		
		if self.config['SERVER_DAEMONIZE']:
			# Double fork magic!
			if os.path.exists(self.config['PID_FILE']):
				self.log.critical(u'Unable to start server! PID file exists!!')
				sys.exit(1)
			
			# The First Fork....
			try:
				pid = os.fork()
				
				if pid > 0:
					# Exit first parent
					sys.exit(0)
			except OSError, e:
				self.log.error(u'Unable to start server - Can not fork parent process: %s' % e) 
				sys.exit(1)
				
			# Decouple ourselves
			os.chdir(self.config['SERVER_RUN_DIR'])
			os.setsid()
			os.umask(self.config['UMASK'])
			
			# The Second fork....
			try:
				pid = os.fork()
				
				if pid > 0:
					# Exit from second parent, save the PID
					f = open(self.config['PID_FILE'], 'w')
					f.write('%d' % pid)
					f.close()
					
					# Set the PID file and change permissions
					uid, gid = get_uid_gid(self.config['SERVER_USER'], self.config['SERVER_GROUP'])
					
					if os.path.exists(self.config['PID_FILE']):
						os.chown(self.config['PID_FILE'], uid, gid)
					
					sys.exit(0)
					
			except OSError, e:
				self.log.error(u'Unable to start server - Cannot double fork: %s' % e)
				sys.exit(1)
				
			else:
				pid = os.getpid()
					
				# Redirect our standard file descriptors
				sys.stdout.flush()
				sys.stderr.flush()
				
				sys.stdin.close()
				sys.stdout.close()
				sys.stderr.close()
				
				os.close(2)
				os.close(1)
				
				sys.stdout = open(self.config['LOG'], 'a+', 1)
				os.dup2(1, 2)
				sys.stderr = os.fdopen(2, 'a+', 0)
				
			# Switch the user and group
			switch_uid_gid(self.config['SERVER_USER'], self.config['SERVER_GROUP'])
		
		else:
			# Non-demon
			pid = os.getpid()
			std_err = sys.stderr
			
		application = import_object(self.config['APP'])
		app = application()
		
		# Setup the server
		self.server = CherryPyWSGIServer(
			(self.config['SERVER_IP'], self.config['SERVER_PORT']),
			app,
			server_name=self.config['SERVER_NAME'],
			numthreads=self.config['SERVER_THREADS'],
			max=-1,
			request_queue_size=self.config['SERVER_REQUEST_QUEUE_SIZE'],
			timeout=self.config['SERVER_TIMEOUT']
		)
		
		self.server.environ['SERVER_SOFTWARE'] = 'Cherryize/%s %s' % (__version__, self.server.version)
		self.server.environ['wsgi.errors'] = sys.stderr
		
		# Setup SSL if it has been requested....
		if self.config['SSL_CERTIFICATE'] and self.config['SSL_PRIVATE_KEY']:
			self.server.ssl_certificate = self.config['SSL_CERTIFICATE']
			self.server.ssl_private_key = self.config['SSL_PRIVATE_KEY']
		
		# Init callback signals
		signal.signal(signal.SIGUSR1, self.signal_handler)
		signal.signal(signal.SIGHUP, self.signal_handler)
		signal.signal(signal.SIGTERM, self.signal_handler)
		
		# Start....
		try:
			self.log.info(u'Server is running. %s:%s / PID %s' % (self.config['SERVER_IP'], self.config['SERVER_PORT'], pid))
			self.server.start()
		except KeyboardInterrupt:
			self.log.info(u'Server received keyboard interrupt - shutting down')
			self.server.stop()
			self.clean()
		except Exception, e:
			self.log.error(u'Server failed %s' % e)
			self.clean()
	
	def stop(self):
		"""Stop a server if it's running"""
		
		# See if there is a valid process ID
		if not os.path.exists(self.config['PID_FILE']):
			# Server is already stopped
			self.log.warning(u'Trying to stop a server that does not exist! (PID file %s)' % self.config['PID_FILE'])
			return
		
		try:
			f = open(self.config['PID_FILE'], 'r')
			pid = f.read()
			f.close()
		except OSError:
			self.log.error(u'Unable to open PID file: %s' % self.config['PID_FILE'])
			sys.exit(1)
		
		try:
			pid = int(pid)
		except ValueError, e:
			self.log.critical(u'PID file does not contain a valid Process ID!')
			sys.exit(1)
		
		try:
			os.kill(pid, signal.SIGTERM)
		except OSError, e:
			self.log.critical(u'Unable to kill process - %s' % e)
			sys.exit(1)
	
	def restart(self):
		"""Attempt to restart a running server gracefully"""
		
		# @@ TODO: Add restart facility
		pass
		
	def clean(self):
		"""Attempt to clean up the environment if running as a deamon"""
		
		if self.config['SERVER_DAEMONIZE']:
			if os.path.exists(self.config['PID_FILE']):
				try:
					os.remove(self.config['PID_FILE'])
				except OSError:
					self.log.critical(u'Unable to remove PID file at: %s' % self.config['PID_FILE'])
	
	def signal_handler(self, sig, stack):
		"""Handle OS signals sent to the server"""
		
		if sig == signal.SIGUSR1:
			pass
			
		elif sig == signal.SIGHUP:
			self.log.info(u'Server recieved SIGHUP - restarting')
			
			self.restart()
			
		elif sig == signal.SIGTERM:
			self.log.info(u'Server recieved SIGTERM - shutting down')
			
			self.server.stop()
			self.clean()
			
			sys.exit(0)
			
		else:
			self.log.warning(u'Server recieved unknown signal "%s" - ignoring' % sig)
			
		# @@ Todo - any of these needed?
		# TERM, INT
		# QUIT
		# HUP
		# USR1
		# USR2
		# WINCH
		
def main():
	"""Run loop"""
	parser = OptionParser()
	parser.add_option('-c', '--conf', dest='conf', help='Webserver configuration file', default=None)
	parser.add_option('-f', '--force', dest='force', action='store_true', help='Force a restart', default=False)
	
	options, args = parser.parse_args()
	
	config_file_path = ''
	
	if options.conf is not None:
		config_file_path = options.conf
	else:
		print u'You must specify a webserver configuration file!'
		sys.exit(1)
	
	cmd = None
	
	if len(args) > 0:
		cmd = args[0].upper()
	else:
		cmd = 'START'
	
	cmd_line_override_conf = {
		'FORCE': options.force,
	}
	
	server = WSGIServer(config_file_path, runtime_conf=cmd_line_override_conf)
	server.run(cmd)
	
if __name__ == '__main__':
	main()