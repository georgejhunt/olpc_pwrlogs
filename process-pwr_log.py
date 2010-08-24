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

# Conversion defs
SEC 	= 0
SOC 	= 1
Vb 	= 2
Ib 	= 3
Tb 	= 4
ACR 	= 5

# Results defs
Line	= 0
Th 	= 1
Iavg 	= 2
NetACR	= 3
Deltat	= 4
Vavg	= 5
Watts	= 6
Wh	= 7
DeltaTb = 8

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
	result[Line]	= line_no
	result[Th] 	= (converted[SEC] - Tz) / 3600	
	result[Deltat] 	= converted[SEC] - converted_prev[SEC]
	if result[Deltat] == 0:
		return False
	result[Iavg] 	= (converted[ACR] - converted_prev[ACR]) / (result[Deltat] / 3600)
	result[NetACR]	= converted[ACR] - ACRz
	result[Vavg]	= (converted[Vb] + converted_prev[Vb]) / 2
	result[Watts]	= result[Vavg] * result[Iavg] / 1000
	result[Wh]	= result[Wh] + (result[Watts] * result[Deltat] / 3600) 
	result[DeltaTb] = converted[Tb] - Tbz 
	return True

def pretty_print(data):
	for each in data:
		print '%9.3f%c' % (each,summary_seperator) ,
	print

def pretty_out(data):
	retval = []
	retval.append('%12d' % data[0])
	for each in data[1:]:
		retval.append('%12.3f' % each)
	return retval

def usage():
	print 'process-pwr_log <options> <files>'
	print "-b, --batsort :  output bat sernum rather than filename for the summary info"
	print "-s, --sersort :  output laptop sernum rather than filename for summary info" 

def printfname(name,seperator,size=0):
	if (size == 0):
		print '%38s%c' % (name,seperator) ,
	else:
		print '%*s%c' % (size,name,seperator) ,

def printbuild(build,seperator):
	print '%10s%c' % (build,seperator),  
	
# Eeek. Globals.  Bad Richard.
converted 	= [0.,0.,0.,0.,0.,0.,0.]
converted_prev 	= [0.,0.,0.,0.,0.,0.,0.]
result 		= [0,0.,0.,0.,0.,0.,0.,0.,0.] 
Tz = 0.0
ACRz = 0.0
Tbz  = 0.0
batsort = 0
sersort = 0
showfile = 0
showcomment = 0
showxo = 0
summary_seperator = ','

try:
	opts, args = getopt.getopt(sys.argv[1:], "hbsfTcx", ["batsort", "help", "sersort", "showfile", "tabs", "comment","xo_ver"])
except getopt.GetoptError, err:
	# print help information and exit:
	print str(err) # will print something like "option -a not recognized"
	usage()
	sys.exit(2)

filenames = args

for o, a in opts:
        if o in ("-b", "--batsort"):
		batsort = 1
        elif o in ("-h", "--help"):
		usage()
		sys.exit(1)
	elif o in ("-s", "--sersort"):
		sersort = 1
	elif o in ("-f", "--showfile"):
		showfile = 1
	elif o in ("-T", "--tabs"):
		summary_seperator = '\t'
	elif o in ("-c", "--comment"):
		showcomment = 1
	elif o in ("-x", "--xo_ver"):
		showxo	= 1

# Summary header

printfname(" Filename  ",summary_seperator)
printbuild(" Build ",summary_seperator)
for each in ["Net time","Net ACR","Watthrs","Min W","Max W","Avg W","Crit time","Max temp","Temp rise","StartV","sec/mAh"]:
	print '%9s%c' % (each,summary_seperator) ,
print

for filename in filenames:

	converted 	= [0.,0.,0.,0.,0.,0.,0.]
	converted_prev 	= [0.,0.,0.,0.,0.,0.,0.]
	result 		= [0,0.,0.,0.,0.,0.,0.,0.,0.] 
	build_no	= 'Unknown'
	bat_ser		= 'None'
	lap_ser		= 'None'
	gen		= 'Unknown'
	xo_ver		= '1'
	kern_api	= 0

	output_filename = "processed-"+ os.path.splitext(filename)[0] + ".csv"
	writer = csv.writer(open(output_filename, "wb"))
	reader = csv.reader(open(filename,"rb"))
	for row in reader:
		writer.writerow(row)
		if not row:
			continue
		try:
			if row[0].startswith('BUILD:'):
				build_no = (row[0].split(':')[1]).strip()[:6]
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

		if row[0] == '<StartData>':	
			break
	# Header 
	
	if kern_api == 0:
		if xo_ver == '1.5':
			kern_api = 2
		else:
			kern_api = 1

	header = []
	for each in ['LineNo','Net T(hours)','I Avg(mA)','Net ACR(mA)','Delta T(sec)','V Avg','Watts','Net Wh','DeltaTb']:
		header.append("%12s" % each)
	writer.writerow(header)
	try:
		row = reader.next()
	except:
		print "Err: %s line %d " % (filename,reader.line_num)
		continue
	if not (convert_data(filename,kern_api)): print "line ",reader.line_num

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
	result[Deltat] = 0
	result[Wh] = 0
	crit_start = 0
	crit_time  = 0
	result[DeltaTb] = 0
	# Init min & Max.  This really should be initialized to the 
	# first real value but that does not happen until the 2nd interation
	# and I feel lazy.  If we ever hit 20W some thing else is wrong anyway
	# Famous last words. X0-1.5 can hit >20W up it to 50W
	minW 		= 50.0
	maxW 		= -50.0
	maxTb		= -40.0
	maxTb_rise	= 0
	writer.writerow(pretty_out(result))
	converted_prev = converted[:]
	# Run the rest of the data
	for row in reader:
		if not row:
			continue
		if not (convert_data(filename,kern_api)): print "line ", reader.line_num
		if not process_data(reader.line_num):
			continue
		if result[Watts] > maxW and (round(result[Watts],3) != 0.0) :
			maxW = result[Watts]
		if (result[Watts] < minW) and (round(result[Watts],3) != 0.0):
			minW = result[Watts]
		if (result[Vavg] < 5.75 and crit_start == 0 ):
			crit_start = result[Th]
		else:
			crit_time = (result[Th] - crit_start) * 60
		if converted[Tb] > maxTb:
			maxTb = converted[Tb]

		if result[DeltaTb] > maxTb_rise:
			maxTb_rise = result[DeltaTb]

		converted_prev = converted[:]
		writer.writerow(pretty_out(result))
	# Summary of the run
	summary = []
	summary.append(result[Th])
	summary.append(result[NetACR])
	summary.append(result[Wh])
	summary.append(minW)
	summary.append(maxW)

	if result[Th] != 0.0:
		summary.append(result[Wh]/result[Th])
	else:
		summary.append(0.0)
	summary.append(crit_time)
	summary.append(maxTb)
	summary.append(maxTb_rise)
	summary.append(Vz)
	if result[NetACR] != 0:
		summary.append( (converted[SEC] - Tz) / result[NetACR] )
	else:
		print "Err: %s : NetACR = 0? " % filename 

	if showfile:
		printfname(filename,summary_seperator)

	if sersort:
		print '%11s%c' % (lap_ser,summary_seperator) ,

	if batsort:
		printfname(bat_ser,summary_seperator) ,
	
	if showcomment:
		printfname(comment,summary_seperator,size=12) ,

	if showxo:
		printfname(xo_ver,summary_seperator)
	else:
		printfname(filename,summary_seperator)
	
	printbuild(build_no,summary_seperator),  
	pretty_print(summary)

