#!/usr/bin/python

#import MySQLdb
#import MySQLdb.cursors
import os.path
import os
import sys
from datetime import datetime
import argparse

from acrecord import ShowPowerHistory, Tools
import olpcpwrlog
#import powerlogsdb
#DATAROOT = '/home/olpc/power-logs'
DATAROOT = './power-logs'

def main():

	parser = argparse.ArgumentParser(description='Summarize AC Grid pwrlogs')
	parser.add_argument('-n', '--newlog', action='store_true',
                help='ignore log accumulated before now')
	parser.add_argument('-d', '--daily', action='store_true',
                help='show power by day and hour')
	parser.add_argument('-s', '--start', 
                help='start report this dd/mm/yy')
	parser.add_argument('-e', '--daily',
                help='end report this dd/mm/yy')
	parser.add_argument('-v', '--verbose', action='store_true',
                help='show debugging information')
    args = parser.parse_args()

    if os.path.exists("/proc/device-tree/mfg-data/CP"):
        print "The CP manufacturing tag is not set.  Please read the instructions"
        print "at /usr/local/acpowerREADME.rst"
        sys.exit(1)

	pl = olpcpwrlog.PwrLogfile()
	# Some feilds are named differently in the database due to them 
	# being keywords.
	fxlate = {}
	fxlate['COMMENT'] = 'log_comment'
	fxlate['Format']  = 'log_format'
	
	filenames = []
	for root, subdirs, names in os.walk(DATAROOT):
		filenames.extend(names)
	numfiles = len(filenames)
	filenum = 0
	filenames.sort()
	selected_values = []
	for fname in filenames:
		fname = os.path.join(root,fname)
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

		fields = ["date_sec","soc","voltage","amperage","temp","acr","status","event","date_dtval"]
		#print(fields)			 
		samples.sort(key=lambda x:x[0])
		for sval in samples:
			values = []
			#values.append(file_id) 
			values.append(int(sval[0]))
			values.append(int(sval[1]))
			values.extend(sval[2:])
			#dbc.insert_row('samples',fields,values)
			if values[7].find("ac") != -1 or \
			   values[7].find("startup") != -1 or \
			   values[7].find("shutdown") != -1:
				selected_values.append(values)
	selected_values.sort(key=lambda x:x[0])
	#print(selected_values)

	sph = ShowPowerHistory()
	sph.output_summary(selected_values,args)


main()
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4