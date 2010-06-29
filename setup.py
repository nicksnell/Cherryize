#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Cherryize setup script

from setuptools import setup, find_packages

long_description = """Cherryize is simple wrapper around the CherryPy WSGI server. 
It can be used to run WSGI compatible applications such as Django, Pylons etc... """

setup(
	name='Cherryize',
	version=0.1,
	description='Cherryize - CherryPy WSGI Server wrapper',
	long_description=long_description,
	author='Nick Snell',
	author_email='nick@orpo.co.uk',
	url='http://orpo.co.uk/code/',
	download_url='',
	license='BSD',
	platforms=['All',],
	classifiers=[
		'Development Status :: 4 - Beta',
		'Environment :: Web Environment',
		'License :: OSI Approved :: BSD License',
		'Natural Language :: English',
		'Operating System :: OS Independent',
		'Programming Language :: Python',
	],
	zip_safe=True,
	packages=find_packages(exclude=['tests',]),
	dependency_links = [
	
	],
	entry_points = {
		'console_scripts': [
			'cherryize = cherryize.server:main',
		]
	},
	install_requires=[
		'PyYAML>=3.09'
	]
)