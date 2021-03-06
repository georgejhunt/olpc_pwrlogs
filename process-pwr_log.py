#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright One Laptop Per Child
# Released under GPLv2 or later
# Version 1.6

# Quick and dirty script to calculate the things I was doing with a spreadsheet in OpenOffice

import sys
import csv
import os
import getopt
from datetime import datetime
from dateutil.parser import *
import traceback

# Conversion defs
SEC 	= 0
SOC 	= 1
Vb 	= 2
Ib 	= 3
Tb 	= 4
ACR 	= 5

# Results defs
#Line	= 0
#Th 	= 1
#Iavg 	= 2
#NetACR	= 3
#Deltat	= 4
#Vavg	= 5
#Watts	= 6
#Wh	= 7
#DeltaTb = 8
#DeltaACR = 9

# 6.5uV / .015 mOhm sense resistor / 1000 = raw ACR -> ACR in mAh
ACR2mAh = 6.25 / .015 / 1000

def convert_data(filename,api):
	try:
		# Seconds
		converted[SEC] = float(row[SEC])
		# State of Charge (Convert to float just for consistency)
		converted[SOC] = float(row[SOC])
		# Volts
		converted[Vb] = float(row[Vb])/1000000
		# Current
		# Gen 1 units have current in uA
		if api == 2:
			converted[Ib] = float(row[Ib])/1000000
		else:
			converted[Ib] = float(row[Ib])/1000
		# Batt Temp in C
		converted[Tb] = float(row[Tb])/100
	except:
		if not quiet:
			print "Convert Error: %s" % filename
			print row
		return False

	try:
		# ACR mAh
		# Old versions of the logging script have this number as an unsinged 16-bit
		# But its really a 2's complement so you have to fixup to make the math work across
		# a rollover.
		if api == 2 :
			# in gen 1.5 this value is reported converted into uAh
			converted[ACR] = float(row[ACR]) / 1000.0
		else:
			if int(row[ACR]) < 0:
				# Allready converted. So good go
				converted[ACR] = float(row[ACR])*ACR2mAh
			else:
				intval = int(row[ACR])
				if (intval & 0x8000):
					intval = -((~intval & 0xffff) +1)
				converted[ACR] = float(intval)*ACR2mAh
	except:
		print "ACR Error: %s" % filename
		print row[ACR]
		return False

	return True

def process_data(line_no):
	result['Line']		= line_no
	result['Th'] 		= (converted[SEC] - Tz) / 3600
	result['Deltat']	= converted[SEC] - converted_prev[SEC]
	if result['Deltat'] == 0:
		# Keep /0 from happening
		result['Deltat'] = 1.0
	result['DeltaACR'] = (converted[ACR] - converted_prev[ACR])

	# Small number for these values give high error rates
	# we want to skip the calc interval in these cases
	if abs(result['Deltat']) < min_sample_interval or abs(result['DeltaACR']) < .5:
		return False

	result['Iavg'] 	= result['DeltaACR'] / (result['Deltat'] / 3600)
	result['NetACR']	= converted[ACR] - ACRz
	result['Vavg']	= (converted[Vb] + converted_prev[Vb]) / 2
	result['Watts']	= result['Vavg'] * result['Iavg'] / 1000
	Wh = (result['Watts'] * result['Deltat'] / 3600)
	result['Wh']	= result['Wh'] + Wh
	if Wh > 0:
		result['ChgWh'] = result['ChgWh'] + Wh
	else:
		result['DiscWh'] = result['DiscWh'] + Wh

	result['DeltaTb'] = converted[Tb] - Tbz
	if result['Iavg'] != 0.0:
		result['Zavg'] = result['Vavg'] / result['Iavg']
	else:
		result['Zavg'] = 0

	return True

def pretty_print(data):
	for each in data:
		print '%9.3f%c' % (each,summary_separator) ,
	print

def pretty_out(data):
	retval = []
	retval.append('%12d' % data['Line'])
	for each in result_items[1:]:
		retval.append('%12.3f' % data[each])
	return retval

def gnuplot_out(data):
	retval = []
	retval.append('%f %f' % (data['Th'],data['Watts'] ) )
	return retval

def usage():
	print 'process-pwr_log <options> <files>'
	print "-b, --batsort :  output bat sernum rather than filename for the summary info"
	print "-s, --sersort :  output laptop sernum rather than filename for summary info"

def printfname(name,separator,size=0):
	if (size == 0):
		print '"%38s"%c' % (name,separator) ,
	else:
		print '"%*s"%c' % (size,name,separator) ,

def printbuild(build,separator):
	print '%10s%c' % (build,separator),

def show_summary(summary):
	if showfile:
		printfname(filename,summary_separator)

	if sersort:
		print '%11s%c' % (lap_ser,summary_separator) ,

	if batsort:
		printfname(bat_ser,summary_separator,size=16) ,

	if showcomment:
		printfname(comment,summary_separator,size=12) ,

	if datesort:
		printfname(rundate_str,summary_separator,size=12)

	if showxo:
		printfname(xo_ver,summary_separator,size=4)

	printfname(filename,summary_separator)

	printbuild(build_no,summary_separator),
	pretty_print(summary)

# Eeek. Globals.  Bad Richard.
Tz = 0.0
ACRz = 0.0
Tbz  = 0.0
batsort = 0
sersort = 0
showfile = 0
showcomment = 0
showxo = 0
summary_separator = ','
min_sample_interval = 60
positive = 0
negative = 0
quiet = 1
datesort = 0
include_errors = False
min_power_limit = -15
max_power_limit = 20
only_errors = False
show_cvpoint = 0
cv_acr = 0
cv_point_reached = 0
make_process_file = 0
gnuplot = 0
terse = 0

try:
	opts, args = getopt.getopt(sys.argv[1:], "hbsfTcxpnqdzeEvPgt", ["batsort", "help", "sersort", "showfile", "tabs", "comment","xo_ver","positive","negative", "quiet", "datesort", "ztest","include-errors","only-errors","cvpoint","process","gnuplot","terse"])
except getopt.GetoptError, err:
	# print help information and exit:
	print str(err) # will print something like "option -a not recognized"
	usage()
	sys.exit(2)

filenames = args

for o, a in opts:
        if o in ("-b", "--batsort"):
		batsort = 1
       	elif o in ("-c", "--comment"):
		showcomment = 1
	elif o in ("-d", "--datesort"):
		datesort = 1
	elif o in ("-e", "--include-errors"):
		include_errors = True
	elif o in ("-E", "--only-errors"):
		include_errors = True
		only_errors = True
	elif o in ("-f", "--showfile"):
		showfile = 1
	elif o in ("-h", "--help"):
		usage()
		sys.exit(1)
	elif o in ("-n", "--negative"):
		negative = 1
	elif o in ("-p", "--positive"):
		positive = 1
	elif o in ("-q", "--quiet"):
		quiet = 1
	elif o in ("-s", "--sersort"):
		sersort = 1
	elif o in ("-P", "--process"):
		make_process_file = 1
	elif o in ("-T", "--tabs"):
		summary_separator = '\t'
	elif o in ("-v", "--cvpoint"):
		show_cvpoint = 1
	elif o in ("-x", "--xo_ver"):
		showxo	= 1
	elif o in ("-g","--gnuplot"):
		gnuplot = 1
	elif o in ("-t", "--terse"):
		terse = 1
	elif o in ("-z","--ztest"):
		print a
		sys.exit(1)

# Summary header

if batsort:
	printfname(" Batserial  ", summary_separator,size=17)

printfname(" Filename  ",summary_separator)
printbuild(" Build ",summary_separator)

if terse:
	summary_header = ["Net time","Net ACR","Watthrs","Min W","Max W","Avg W","Chg Wh","Disc Wh"]
elif show_cvpoint:
	summary_header = ["Net time","Net ACR","CV ACR","CV Time","Watthrs","Min W","Max W","Avg W","Chg Wh","Disc Wh","Crit time","CritACR","Max temp","Temp rise","StartV","Cticks","Dticks"]
else:
	summary_header = ["Net time","Net ACR","Watthrs","Min W","Max W","Avg W","Chg Wh","Disc Wh","Crit time","CritACR","Max temp","Temp rise","StartV","Cticks","Dticks"]

for each in summary_header:
	print '%9s%c' % (each,summary_separator) ,
print
# Results defs
# The order of this list is the order of output in the results file.
# 'Line' is fixed and needs to be item 0 but all others are fungable.
result_items = ['Line','Th','Iavg','NetACR','Deltat','Vavg','Watts','Wh','DeltaTb','DeltaACR','Zavg','ChgWh','DiscWh']
# Init the results_header dict
result_headers = dict( [(i,'') for i in result_items] )

result_headers['Line']	= 'LineNo'
result_headers['Th'] 	= 'Net T(hours)'
result_headers['Iavg'] 	= 'I Avg(mA)'
result_headers['NetACR'] = 'Net ACR(mA)'
result_headers['Deltat'] = 'dT(sec)'
result_headers['Vavg']	= 'V Avg'
result_headers['Watts'] = 'Watts'
result_headers['Wh']	= 'Net Wh'
result_headers['DeltaTb'] = 'dTb(C)'
result_headers['DeltaACR'] = 'dACR(mA)'
result_headers['Zavg'] = 'Zavg'
result_headers['Cticks'] = 'Cticks'
result_headers['Dticks'] = 'Dticks'
result_headers['ChgWh']  = 'Chg Wh'
result_headers['DiscWh']  = 'Dischg Wh'


for filename in filenames:

	converted	= [0.,0.,0.,0.,0.,0.]
	converted_prev 	= converted[:]
	result 		= dict( [ (i,0.) for i in result_items ] )

	build_no	= 'Unknown'
	bat_ser		= 'None'
	lap_ser		= 'None'
	gen		= 'Unknown'
	xo_ver		= '1'
	kern_api	= 0

	output_filename = "processed-"+ os.path.splitext(filename)[0] + ".csv"
	if make_process_file:
		writer = csv.writer(open(output_filename, "wb"),quoting=csv.QUOTE_NONE)

	reader = csv.reader(open(filename,"rb"))
	try:
		for row in reader:
			if make_process_file:
				if not gnuplot:
					writer.writerow(row)
			if not row:
				continue
			try:
				if row[0].startswith('BUILD:'):
					build_no = (row[0].split(':')[1]).strip()[:10]
			except:
				build_no = 'Err'
			try:
				if row[0].startswith('BATSER:'):
					bat_ser = row[0].split(':')[1]
			except:
				bat_ser = 'Err'

			try:
				if row[0].startswith('SERNUM:'):
					lap_ser = row[0].split(':')[1]
			except:
				lap_ser = 'Err'

			try:
				if row[0].startswith('XOVER:'):
					xo_ver = (row[0].split(':')[1]).strip()
			except:
				xo_ver ='Err'
			try:
				if row[0].startswith('KERNAPI:'):
					kern_api = int((row[0].split(':')[1]).strip())
			except:
				kern_api = 0
			try:
				if row[0].startswith('COMMENT:'):
					comment = row[0].split(':')[1].strip()
			except:
				lap_ser = 'Err'
			try:
				if row[0].startswith('DATE:'):
                                       # Dates can have commas and they get pased as csv so reconstruct
                                        # the full string.
                                        dstring = ''
                                        for each in row:
                                                dstring += each
                                        dcolon = dstring.find(":")+1
                                        dstring = dstring[dcolon:]
                                        rundate = parse(dstring,fuzzy=True)
					rundate_str = datetime.strftime(rundate,"%Y/%m/%d %H:%M:%S")
			except:
				rundate_str = 'Err'
				traceback.print_exc(file=sys.stdout)

			try:
				if row[0].startswith('CHGCNT:'):
					value = row[0].split(':')[1].strip()
					chg_msb = int(value.split(' ')[0].strip(),16)
					chg_lsb = int(value.split(' ')[1].strip(),16)
					charge_cnt = (chg_msb*128)+chg_lsb
			except:
				charge_cnt = -1
				traceback.print_exc(file=sys.stdout)

			try:
				if row[0].startswith('CHGSOC:'):
					value 	= row[0].split(':')[1].strip()
					charge_soc = int(value.split(' ')[0].strip(),16)
			except:
				charge_soc = -1
				traceback.print_exc(file=sys.stdout)

			try:
				if row[0].startswith('DISCNT:'):
					value = row[0].split(':')[1].strip()
					dischg_msb = int(value.split(' ')[0].strip(),16)
					dischg_lsb = int(value.split(' ')[1].strip(),16)
					discharge_cnt = (chg_msb*128)+chg_lsb
			except:
				discharge_cnt = -1
				traceback.print_exc(file=sys.stdout)

			try:
				if row[0].startswith('DISSOC:'):
					value 	= row[0].split(':')[1].strip()
					discharge_soc = int(value.split(' ')[0].strip(),16)
			except:
				discharge_soc = -1
				traceback.print_exc(file=sys.stdout)

			if row[0] == '<StartData>':
				break
	except:
		print "Read Error in: %s" % (filename)
		continue
	# Header

	if kern_api == 0:
		if xo_ver == '1.5':
			kern_api = 2
		else:
			kern_api = 1

	try:
		row = reader.next()
	except:
		if not quiet:
			print "Err: %s line %d " % (filename,reader.line_num)
		continue
	if not (convert_data(filename,kern_api)):
		if not quiet:
			print "1-line ",reader.line_num
		continue

	if (charge_cnt > -1 and charge_soc > -1):
		charge_ticks = charge_cnt + charge_soc
	else:
		charge_ticks = -1

	if (discharge_cnt > -1 and discharge_soc > -1):
		discharge_ticks = discharge_cnt + discharge_soc
	else:
		discharge_ticks = -1

	header = []
	for each in result_items:
		header.append("%12s" % result_headers[each])
	if make_process_file:
		if not gnuplot:
			writer.writerow(header)

	# Starting point for relative measuements
	Tz = converted[SEC]
	ACRz = converted[ACR]
	Tbz  = converted[Tb]
	Vz   = converted[Vb]
	# Setup the first calculation
	converted_prev = converted[:]
	# Keep the div by zero from occuring
	converted_prev[SEC] = Tz-1
	process_data(reader.line_num)
	# Fixup the errors from the starting entry
	result['Deltat'] = 0
	result['Wh'] = 0
	result['ChgWh'] = 0
	result['DiscWh'] = 0
	crit_start = 0
	crit_time  = 0
	crit_acr_start = 0
	crit_acr = 0
	result['DeltaTb'] = 0
	# Init min & Max.  This really should be initialized to the
	# first real value but that does not happen until the 2nd interation
	# and I feel lazy.  If we ever hit 20W some thing else is wrong anyway
	# Famous last words. X0-1.5 can hit >20W so up this to 50W
	minW 		= 50.0
	maxW 		= -50.0
	maxTb		= -40.0
	maxTb_rise	= 0
	cv_point_reached = 0
	cv_acr = 0
	cv_time = 0
	if make_process_file:
		if gnuplot:
			out = []
			out.append('#xo:%s | build:%s' % (xo_ver,build_no))
			writer.writerow(out)
			writer.writerow(gnuplot_out(result))
		else:
			writer.writerow(pretty_out(result))
	converted_prev = converted[:]
	# Short log files generated from powerd often don't have enough data in them to meet
	# minimum sample period for good power readings.  If we get one of those files then
	# we should just skip it.
	time_period_valid = False
	power_output_valid = True

	# Run the rest of the data
	for row in reader:
		if not row:
			continue
		if not (convert_data(filename,kern_api)):
			if not quiet:
				print "line ", reader.line_num
			else:
				continue
		if not process_data(reader.line_num):
			#print result[Line],result[Deltat],result[DeltaACR]
			continue

		if result['Watts'] > max_power_limit or result['Watts'] < min_power_limit:
			if not include_errors:
				power_output_valid = False
				continue

		# Getting here means we got at least 1 power reading that meets the minimum sample
		# period.
		time_period_valid = True
		if result['Watts'] > maxW and (round(result['Watts'],3) != 0.0) :
			maxW = result['Watts']
		if (result['Watts'] < minW) and (round(result['Watts'],3) != 0.0):
			minW = result['Watts']
		if (result['Vavg'] < 5.725 and crit_start == 0 ):
			crit_start = result['Th']
			crit_acr_start = abs(result['NetACR'])
		else:
			if crit_start > 0:
				crit_time = (result['Th'] - crit_start) * 60
				crit_acr = abs(result['NetACR']) - crit_acr_start;

		if converted[Tb] > maxTb:
			maxTb = converted[Tb]

		if result['DeltaTb'] > maxTb_rise:
			maxTb_rise = result['DeltaTb']
		if result['Vavg'] >= 7.2 and cv_point_reached==0:
			cv_point_reached = 1
			cv_acr  = result['NetACR']
			cv_time = result['Th']

		converted_prev = converted[:]
		if make_process_file:
			if gnuplot:
				writer.writerow(gnuplot_out(result))
			else:
				writer.writerow(pretty_out(result))

	# Blank lines separate datasets in gnuplot
	if gnuplot:
		writer.writerow('');
		writer.writerow('');

	# If the sample period is not enough or the power numbers have impossible
	# values in them then don't include this file in the summary
	if not time_period_valid or not power_output_valid:
		if not include_errors:
			continue

	# When dealing with lots of files its usefull to be able to
	# generate a list of files with errors so they can be
	# bulk moved for further processing
	if only_errors:
		if time_period_valid and power_output_valid:
			continue


	# Summary of the run
	summary = []
	summary.append(result['Th'])
	summary.append(result['NetACR'])
	if show_cvpoint:
		summary.append(result['NetACR']-cv_acr)
		summary.append(result['Th']-cv_time)

	summary.append(result['Wh'])
	summary.append(minW)
	summary.append(maxW)

	if result['Th'] != 0.0:
		summary.append(result['Wh']/result['Th'])
	else:
		summary.append(0.0)

	summary.append(result['ChgWh'])
	summary.append(result['DiscWh'])

	if not terse:
		summary.append(crit_time)
		summary.append(crit_acr)
		summary.append(maxTb)
		summary.append(maxTb_rise)
		summary.append(Vz)
		summary.append(charge_ticks)
		summary.append(discharge_ticks)

	if positive or negative:
		if positive and result['NetACR'] > 0:
			show_summary(summary)
		if negative and result['NetACR'] < 0:
			show_summary(summary)
	else:
		show_summary(summary)

