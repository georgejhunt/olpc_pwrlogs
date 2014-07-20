#!/usr/bin/python

#import MySQLdb
#import MySQLdb.cursors
import os.path
import sys
from datetime import datetime
import argparse

import olpcpwrlog
#import powerlogsdb

def main():

	parser = argparse.ArgumentParser(description='add pwrlogs to database')
	parser.add_argument('filenames', nargs='+', help='files to process')
	parser.add_argument('--replace', action='store_true',
                help='Overwrite existing datafiles')

	args = parser.parse_args()
	"""
	dbc = powerlogsdb.db_conn()
	dbc.connect()
	"""
	pl = olpcpwrlog.PwrLogfile()

	# Some feilds are named differently in the database due to them 
	# being keywords.
	fxlate = {}
	fxlate['COMMENT'] = 'log_comment'
	fxlate['Format']  = 'log_format'

	numfiles = len(args.filenames)
	filenum = 0
	for fname in args.filenames:
		filenum+=1
		print "%d of %d\r" % (filenum,numfiles),
		sys.stdout.flush()
		fields = []
		values = []
		try:
			pl.parse_header(fname)
		except:
			print "%s : Could not parse header. Error: " % fname,
			print sys.exc_info()
			continue
	
		samples,errors = pl.parse_records()
		if len(errors):
			print "%s : Skipping.  Line errors: " % fname
			for e in errors:
				print e
			continue

		# Create the entry in the file table from the headers
		headers = pl.get_headers()
		for (k,v) in headers.iteritems():
			if k == 'DATE':
				# DATE has time zone imfo which is not handled by the datetime field so skip log_date and log_tz have info 
				continue
			if k in fxlate:
				fields.append(fxlate[k])
			else:
				fields.append(k)
			values.append(v) 
		"""	
		# if replace is active and we exist then we need to delete all this files
		# records first
		findcmd = "SELECT file_id from files WHERE"
		findcmd += " date_string = '%s'" % headers['date_string'] 
		findcmd += " AND sernum = '%s'" % headers['SERNUM']
		findcmd += " AND batser = '%s'" % headers['BATSER']
		findcmd += ';'

		if args.replace:
			# Find the file_id for the file and delete the samples
			dbc.do_query(findcmd)
			row = dbc.get_row()
			if row: 
				file_id = row[0]
				cmd = "DELETE from files WHERE file_id = '%s'" % file_id
				dbc.do_query(cmd)
				cmd = "DELETE from samples WHERE file_id = '%s'" % file_id
				dbc.do_query(cmd)

		try:	
			dbc.insert_row('files',fields,values)
		except:
			print "%s: Could not create file entry. Error: " % fname,
			print sys.exc_info()
			continue
	
		dbc.do_query(findcmd)
		file_id = dbc.get_row()[0]
		"""
		# Now insert all the sampels from the log file using 
		# the file_id just created.
		
		#fields = ["file_id","date_sec","soc","voltage","amperage","temp","acr","status","event","date_dtval"]
		fields = ["date_sec","soc","voltage","amperage","temp","acr","status","event","date_dtval"]
		print(fields)			 
		for sval in samples:
			values = []
			#values.append(file_id) 
			values.append(int(sval[0]))
			values.append(int(sval[1]))
			values.extend(sval[2:])
			#dbc.insert_row('samples',fields,values)
			print(values)




main()
