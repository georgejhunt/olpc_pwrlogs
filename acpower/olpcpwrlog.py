#!/usr/bin/python

# Copyright One Laptop Per Child
# Released under GPLv2 or later
# Version 0.1.0


import sys
import csv
import os
import traceback
import argparse
from datetime import datetime, date, time
from dateutil import tz, parser

class pwr_trace:
	def __init__(self):

		self.header = {}

		self.Tz	     	= 0.
		self.ACRz	= 0.
		self.Wh_sum	= 0.

		# Small arrry for a place holder will will replace this once we have built the data list
		self.darray	= zeros(3)

class PwrLogfile:
	def __init__(self):
		self.header = {}
		# 6.5uV / .015 mOhm sense resistor / 1000 = raw ACR -> ACR in mAh
		self.ACR2mAh = 6.25 / .015 / 1000
		# Conversion defs
		self.SEC     = 0
		self.SOC     = 1
		self.Vb      = 2
		self.Ib      = 3
		self.Tb      = 4
		self.ACR     = 5
		self.STATUS  = 6
		self.EVENT   = 7
		self.DATESTR = 8

		self.Tz	     	= 0.
		self.ACRz	= 0.
		self.Wh_sum	= 0.

		# Results defs
		self.Th      = 0
		self.Iavg    = 1
		self.NetACR  = 2
		self.Deltat  = 3
		self.Vavg    = 4
		self.Watts   = 5
		self.Wh      = 6
		self.Wavg    = 7
		self.Ttod    = 8
		self.Zavg    = 9

		# Small arrry for a place holder will will replace this once we have built the data list
#		self.darray	= zeros(3)
		self.min_sample_interval = 0
		self.charge_limit=30
		self.enable_charge_limit=False
		self.local_tz = tz.tzutc()
		# The wattage calcs should never be outside these ranges.  If they are 
		# then there is some sort of error.
		self.max_watts_limit = 20
		self.min_watts_limit = -15
		self.max_Th	     = 50
		self.powerd_log	     = False

	def convert_data(self,row):
		converted = [0.,0.,0.,0.,0.,0.,"","",""]
                # Seconds
                converted[self.SEC] = float(row[self.SEC])
                # State of Charge (Convert to float just for consistency)
                converted[self.SOC] = float(row[self.SOC])
                # Volts V
                converted[self.Vb] = float(row[self.Vb])/1000000
                # Current A
                converted[self.Ib] = float(row[self.Ib])/1000000
                # Batt Temp in C
                converted[self.Tb] = float(row[self.Tb])/100
	        # ACR mAh
	        # Old versions of the logging script have this number as an unsinged 16-bit
                # But its really a 2's complement so you have to fixup to make the math work across
        	# a rollover.
		if self.header['XOVER'] == '1.5' or self.header['KERNAPI'] == '2' :
                        # in gen 1.5 this value is reported converted into uAh
                        converted[self.ACR] = float(row[self.ACR]) / 1000.0
		else:
	                if int(row[self.ACR]) < 0:
        	                # Allready converted. So good go
                	        converted[self.ACR] = float(row[self.ACR])*self.ACR2mAh
	                else:
                	        intval = int(row[self.ACR])
        	                if (intval & 0x8000):
                        	        intval = -((~intval & 0xffff) +1)

	                        converted[self.ACR] = float(intval)*self.ACR2mAh
		# Status string
		converted[self.STATUS] = row[self.STATUS]
	
		# powerd files have an event column
		if self.powerd_log:
			converted[self.EVENT] = row[self.EVENT]
		
		dt_sample = datetime.fromtimestamp(converted[self.SEC],tz.tzutc())
		converted[self.DATESTR] = dt_sample.strftime("%Y-%m-%d %H:%M:%S")
		return converted

	def process_data(self,converted, converted_prev):
		result = [0.,0.,0.,0.,0.,0.,0.,0.,0.,0.]
		dt_sample = datetime.fromtimestamp(converted[self.SEC],tz.tzutc())
		dt_tz = dt_sample.astimezone(self.local_tz).timetuple()
		result[self.Ttod] = float(dt_tz.tm_hour) + float(dt_tz.tm_min)/60.0
	        result[self.Th]      = (converted[self.SEC] - self.Tz) / 3600
        	result[self.Deltat]  = converted[self.SEC] - converted_prev[self.SEC]
		if result[self.Deltat] == 0:
			#avoid the /0 error
			result[self.Deltat] = 1.0;
		DeltaACR = (converted[self.ACR] - converted_prev[self.ACR])

		# If either of these are small then we want to skip to the next reading
		# because of the error associated with small values
		if abs(result[self.Deltat]) < self.min_sample_interval or abs(DeltaACR) < .5:
			return (result,1)

	        result[self.Iavg]    = DeltaACR / (result[self.Deltat] / 3600)
	        result[self.NetACR]  = converted[self.ACR] - self.ACRz
	        result[self.Vavg]    = (converted[self.Vb] + converted_prev[self.Vb]) / 2
        	result[self.Watts]   = result[self.Vavg] * (result[self.Iavg] / 1000)

		if result[self.Watts] > self.max_watts_limit or result[self.Watts] < self.min_watts_limit: 
			return (result,2)

		if result[self.Th] > self.max_Th or result[self.Th] < 0:
			return (result,3)

	        result[self.Wh]      = self.Wh_sum + (result[self.Watts] * result[self.Deltat] / 3600)
		if result[self.Th] != 0.0:
			result[self.Wavg]    = result[self.Wh] / result[self.Th]
		else:
			result[self.Wavg] = 0.

		if result[self.Iavg] != 0.0:
			result[self.Zavg] = result[self.Vavg] / result[self.Iavg]
		else:
			result[self.Zavg] = 0

		return (result,0)

	def parse_header(self,filename):
		self.filename = filename
		self.reader = csv.reader(open(filename,"rb"))
		# Read the header into a dictionary
		# Default to XO version 1 since it does not exist in earlier
		# header formats
		self.header['XOVER'] = '1'
		self.header['KERNAPI'] = '0'
        	for row in self.reader:
                	if not row:
                        	continue
		        if row[0] == '<StartData>':
        	                break

                        if row[0].startswith('DATE:'):
				# Dates can have commas and they get pased as csv so reconstruct
				# the full string.
				dstring = ''
				for each in row:
					dstring += each
				dcolon = dstring.find(":")+1
				dstring = dstring[dcolon:]
				self.header['date_string'] = dstring
                                rundate = parser.parse(dstring,fuzzy=True)
				self.header['DATE'] = rundate
				continue

			if row[0].startswith('powerd_log_ver:'):
				self.powerd_log = True
                        	values = row[0].split(':')
				self.header['log_source'] = values[0].strip()
				if len(values) > 1:
					self.header['source_ver'] = values[1].strip()
				continue

			if row[0].startswith('pwr_log Ver:'):
				self.powerd_log = False
                        	values = row[0].split(':')
				self.header['log_source'] = values[0].strip()
				if len(values) > 1:
					self.header['source_ver'] = values[1].strip()
				continue
			
	                try:
                        	values = row[0].split(':')
				if len(values) > 1:
					self.header[values[0]] = values[1].strip()
				elif len(values) > 0:
					self.header[values[0]] = ''
                	except:
				print 'Error in header: %s' % (filename)

		# Set the local timzone for where the data came from
		self.local_tz = self.header['DATE'].tzinfo
		if self.local_tz == None:
			print "File: %s Unknown TZ: %s" % (filename,dstring)
			self.local_tz = tz.tzutc()
		
		self.header['log_date'] = self.header['DATE'].astimezone(tz.tzutc())
		self.header['log_tz'] = str(self.header['log_date'])[-6:]
		self.header['filename'] = filename


	def dump_header(self):
		for (k,v) in self.header.iteritems():
			print k,v

	def get_headers(self):
		return self.header

	def parse_records(self):
		records = []
		errors = []
		for row in self.reader:
			if not row:
				continue
			try:
				converted = self.convert_data(row)
			except:
				errors.append( (self.reader.line_num,sys.exc_info()) )
				continue
			records.append(converted)
				
		return (records,errors)

	def read_file(self,filename):
		data = []
		reader = csv.reader(open(filename,"rb"))
		# Read the header into a dictionary
		# Default to XO version 1 since it does not exist in earlier
		# header formats
		self.header['XOVER'] = '1'
		self.header['KERNAPI'] = '0'
        	for row in reader:
                	if not row:
                        	continue
		        if row[0] == '<StartData>':
        	                break

                        if row[0].startswith('DATE:'):
				# Dates can have commas and they get pased as csv so reconstruct
				# the full string.
				dstring = ''
				for each in row:
					dstring += each
				dcolon = dstring.find(":")+1
				dstring = dstring[dcolon:]
                                rundate = parser.parse(dstring,fuzzy=True)
				self.header['DATE'] = rundate
				continue

	                try:
                        	values = row[0].split(':')
				if len(values) > 1:
					self.header[values[0]] = values[1].strip()
				elif len(values) > 0:
					self.header[values[0]] = ''
                	except:
				print 'Error in header: %s' % (filename)

		# Set the local timzone for where the data came from
		self.local_tz = self.header['DATE'].tzinfo
		if self.local_tz == None:
			print "File: %s Unknown TZ: %s" % (filename,dstring)
			self.local_tz = tz.tzutc()

		# Now read in the data
		try:
			converted = self.convert_data(reader.next())
			converted_prev = converted[:]
		except:
			print 'Conversion error in %s line: %d' % (filename,reader.line_num)
			traceback.print_exc(file=sys.stdout)
			return False

		self.Tz   = converted_prev[self.SEC]
		self.ACRz = converted_prev[self.ACR]
		self.Wh_sum = 0.
		# This keeps the division by zero error from occurring but does not generate
		# a huge number because the ACRs are equal and you get zero for the result
		converted_prev[self.SEC] = self.Tz-1

		# Process the first line with my fabricated previous data
		results,error = self.process_data(converted, converted_prev)
		self.Wh_sum = results[self.Wh]
		# Start real previous data
		converted_prev = converted[:]

		converted.extend(results)
		data.append(converted)

		power_data_valid = False

		# read the rest of the file
		for row in reader:
			if not row:
				continue
			try:
				converted = self.convert_data(row)
				results,error = self.process_data(converted, converted_prev)
				if error == 2:
					print '%s : Wattage error line: %d' % (filename,reader.line_num)
					return False
				if error == 3:
					print '%s : Elapsed time error line: %d' % (filename,reader.line_num)
					return False	
				if error:
					continue
			except:
				print '%s : Conversion error line: %d' % (filename,reader.line_num)
				continue

			power_data_valid = True
			self.Wh_sum = results[self.Wh]
			converted_prev = converted[:]
			converted.extend(results)
			data.append(converted)

		# Add the various init things to the header info for all the net diff calcs
		self.darray = rec.fromrecords(data,names='sec,soc,vb,ib,tb,acr,th,iavg,netacr,deltat,vavg,watts,wh,wavg,tod,zavg')

		if not power_data_valid:
			return False
		else: 
			return True

	def set_min_sample_interval(self,interval):
		self.min_sample_interval=interval

	def set_charge_limit(self,limit):
		self.enable_charge_limit=True
		self.charge_limit=limit


