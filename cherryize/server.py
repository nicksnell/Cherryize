"""Cherryize

Tool for using the standalone CherryPy webserver to run WSGI compatible 
applications such as Django...
"""

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

log = logging.getLogger('cherryize')

DEFAULTS = {
	'APP': 'django.core.handlers.wsgi.WSGIHandler',
	'SERVER_NAME': 'localhost',
	'SERVER_THREADS': 10,
	'SERVER_RUN_DIR': '/tmp',
	'SERVER_DAEMONIZE': True,
	'SERVER_USER': 'nobody'
	'SERVER_GROUP': 'nobody',
	'IP_ADDRESS': '127.0.0.1',
	'PORT': 8080,
	'LOG': 'server.log',
	'PID_FILE': 'server.pid',
	'SSL': False,
	'SSL_CERTIFICATE': '',
	'SSL_PRIVATE_KEY': '',
}

class WSGIServer(object):
	"""A Basic WSGI Server"""
	
	def __init__(self, conf):
		
		assert conf is not None, u'You must provide a configuration file to the server!'
		
		try:
			config = yaml.load(open(conf, 'r'))
		except Exception, e:
			# Can't read or can't parse, either way no good
			raise RuntimeError(u'Unable to read configuration file! %s' % e)
		
		server_config = DEFAULTS
		server_config.update(config)
		
		self.config = dict([(k.upper(), v) for k, v in server_config.items()])
		
	def clean(self):
		"""Attempt to clean up the environment if running as a deamon"""
		
		if self.config['DAEMONIZE']:
			if os.path.exists(self.config['PID_FILE']):
				try:
					os.remove(self.config['PID_FILE'])
				except IOError:
					log.error(u'Unable to remove PID file at: %s' % self.config['PID_FILE'])
		
	def run(self):
		"""Main run loop"""
		
		# Check if we are running a django project
		if self.config['DJANGO_SETTINGS']:
			os.environ['DJANGO_SETTINGS'] = self.config['DJANGO_SETTINGS']
		
		if self.config['DAEMONIZE']:
			# Double fork magic!
			if os.path.exists(self.config['PID_FILE']):
				current_pid = open(self.config['PID_FILE'], 'r').read()
				log.error(u'Unable to start server - already running! @ PID = %s' % current_pid)
				sys.exit(1)
			
			# The First Fork....
			try:
				pid = os.fork()
				
				if pid > 0:
					# Exit first parent
					sys.exit(0)
			except OSError, e:
				log.error(u'Unable to start server - Can not fork parent process: %s' % e) 
				sys.exit(1)
				
			# Decouple ourselves
			os.chdir(self.config['SERVER_RUN_DIR'])
			os.setsid()
			os.umask(0)
			
			# The Second fork....
			try:
				pid = os.fork()
				
				if pid > 0:
					# Exit from second parent, save the PID
					open(self.config['PID_FILE'], 'w').write('%d' % pid)
					
					# Set the PID file and change permissions
					uid, gid = get_uid_gid(self.config['SERVER_USER'], self.config['SERVER_GROUP'])
					
					if os.path.exists(self.config['PID_FILE']):
						os.chown(self.config['PID_FILE'], uid, gid)
					
					sys.exit(0)
					
			except OSError, e:
				log.error(u'Unable to start server - Can not double fork: %s' % e)
				sys.exit(1)
			
			# Switch the user and group
			switch_uid_gid(self.config['SERVER_USER'], self.config['SERVER_GROUP'])
		
		else:
			# Non-demon
			pid = os.getpid()
		
		application = import_object(self.config['APP'])
		app = application()
		
		# Setup the server
		self.server = CherryPyWSGIServer(
			(self.config['IP'], self.config['PORT']), 
			app, 
			server_name=self.config['SERVER_NAME'], 
			numthreads=self.config['SERVER_THREADS'], 
			max=-1, 
			request_queue_size=5, 
			timeout=60
		)
		
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
			if self.verbose:
				print u'Server is running. %s:%s / PID %s' % (self.ip, self.port, pid)
			
			log.info(u'Server is running. %s:%s / PID %s' % (self.ip, self.port, pid))
			
			self.server.start()
			
		except KeyboardInterrupt:
			if self.verbose:
				print u'Server received keyboard interrupt - shutting down.... ',
			
			log.info(u'Server received keyboard interrupt - shutting down')
			
			self.server.stop()
			self.clean()
			
			if self.verbose:
				print u'Done.'
		
	def signal_handler(self, sig, stack):
		"""Handle OS signals sent to the server"""
		
		if sig == signal.SIGUSR1:
			pass
			
		elif sig == signal.SIGHUP:
			log.info(u'Server recieved SIGHUP - restarting')
			
		elif sig == signal.SIGTERM:
			log.info(u'Server recieved SIGTERM - shutting down')
			
			self.server.stop()
			self.clean()
			
			sys.exit(0)
			
		else:
			log.info(u'Server recieved unknown signal "%s" - ignoring' % sig)
			
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
	
	options, args = parser.parse_args()
	
	config_file_path = ''
	
	if options.conf is not None:
		config_file_path = options.conf
	elif len(args) > 1:
		config_file_path = args[1]
	else:
		print 'You must specify a webserver configuration file!'
		sys.exit(1)
	
	server = WSGIServer(config_file_path)
	server.run()
	
if __name__ == '__main__':
	main()