"""Utilities used by Cherryize"""

import os
import sys
import pwd
import grp

__all__

def import_module(name, globals=globals(), locals=locals(), fromlist=[], level=-1):
	__import__(name, globals, locals, fromlist, level)
	return sys.modules[name]

def import_object(module_path):
	dot = module_path.rindex('.')
	module, cls_name = module_path[:dot], module_path[dot+1:]
	cls_module = import_module(module)
	return getattr(cls_module, cls_name)

def get_uid_gid(uid, gid=None):
	"""Utility to get the current user and group ID"""
	uid, default_grp = pwd.getpwnam(uid)[2:4]
	
	if gid is None:
		gid = default_grp
	else:
		try:
			gid = grp.getgrnam(gid)[2]
		except KeyError:
			gid = default_grp
			
	return uid, gid

def switch_uid_gid(uid, gid=None):
	"""Change the current user (and group). Users should be specified as a 'name'"""
	
	if not os.geteuid() == 0:
		# We are not root so continue.
		return
		
	uid, gid = get_uid_gid(uid, gid)
	
	os.setgid(gid)
	os.setuid(uid)