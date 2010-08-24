#!/usr/bin/python

# Copyright One Laptop Per Child 
# Released under GPLv2 or later
# Version 0.0.1


import sys
import csv
import os
import getopt
import traceback
from numpy import *
from matplotlib import mlab
from matplotlib.ticker import MultipleLocator
from pylab import figure, show
import matplotlib.pyplot as plt

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

		# Small arrry for a place holder will will replace this once we have built the data list
		self.darray	= zeros(3)	

	def convert_data(self,row):
		converted = [0.,0.,0.,0.,0.,0.]
                # Seconds
                converted[self.SEC] = float(row[self.SEC])
                # State of Charge (Convert to float just for consistency)
                converted[self.SOC] = float(row[self.SOC])
                # Volts
                converted[self.Vb] = float(row[self.Vb])/1000000
                # Current mA
                converted[self.Ib] = float(row[self.Ib])/1000
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

		return converted

	def process_data(self,converted, converted_prev):
		result = [0.,0.,0.,0.,0.,0.,0.,0.]
	        result[self.Th]      = (converted[self.SEC] - self.Tz) / 3600
        	result[self.Deltat]  = converted[self.SEC] - converted_prev[self.SEC]
	        result[self.Iavg]    = (converted[self.ACR] - converted_prev[self.ACR]) / (result[self.Deltat] / 3600)
	        result[self.NetACR]  = converted[self.ACR] - self.ACRz
	        result[self.Vavg]    = (converted[self.Vb] + converted_prev[self.Vb]) / 2	
        	result[self.Watts]   = result[self.Vavg] * (result[self.Iavg] / 1000)
	        result[self.Wh]      = self.Wh_sum + (result[self.Watts] * result[self.Deltat] / 3600)
		if result[self.Th] != 0.0:
			result[self.Wavg]    = result[self.Wh] / result[self.Th]
		else:
			result[self.Wavg] = 0.

		return result

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
	                try:
                        	values = row[0].split(':')
				if len(values) > 1:
					self.header[values[0]] = values[1].strip()
				elif len(values) > 0:
					self.header[values[0]] = ''
                	except:
                        	print 'Error in header: %s' & (filename)

		# Now read in the data
		try:
			converted = self.convert_data(reader.next())
			converted_prev = converted[:]
		except:
			print 'Coversion error in %s line: %d' % (filename,reader.line_num) 
			traceback.print_exc(file=sys.stdout)

		self.Tz   = converted_prev[self.SEC]
		self.ACRz = converted_prev[self.ACR]
		self.Wh_sum = 0.
		# This keeps the division by zero error from occurring but does not generate 
		# a huge number because the ACRs are equal and you get zero for the result
		converted_prev[self.SEC] = self.Tz-1
		
		# Process the first line with my fabricated previous data
		results = self.process_data(converted, converted_prev)
		self.Wh_sum = results[self.Wh]
		# Start real previous data
		converted_prev = converted[:]

		converted.extend(results)
		data.append(converted)
		
		# read the rest of the file
		for row in reader:
			if not row:
				continue
			try:
				converted = self.convert_data(row)
				results = self.process_data(converted, converted_prev)
				self.Wh_sum = results[self.Wh]
				converted_prev = converted[:]
				converted.extend(results)
				data.append(converted)
			except:
				print 'Coversion error in %s line: %d' % (filename,reader.line_num) 
		# Add the various init things to the header info for all the net diff calcs

		self.darray = rec.fromrecords(data,names='sec,soc,vb,ib,tb,acr,th,iavg,netacr,deltat,vavg,watts,wh,wavg')

def histo():
	filenames = sys.argv[1:]
	
	pdat = mlab.csv2rec(filenames[0], names=None)

	abs_pwr = pdat.avg_w * -1.0
	abs_pwr.sort()

	time_max = pdat.total_time.max()
	abs_nacr = pdat.netacr * -1
	nacr_max = abs_nacr.max()

	runs = len(abs_pwr)

	fig = figure()
	ax = fig.add_subplot(111)
	majorTick = MultipleLocator(.1)
	minorTick = MultipleLocator(.05)
	n, bins, patches = ax.hist(abs_pwr, 10, normed=False, facecolor='green', alpha=0.75)
	ax.set_title('Idle power histogram: %d runs' % (runs) )
	ax.set_xlabel('Avg Power (Watts)')
	ax.set_ylabel('Occurance')
	ax.xaxis.set_major_locator(majorTick)
	ax.xaxis.set_minor_locator(minorTick)

	plt.figure()
	plt.hist(pdat.total_time, 10, normed=False, facecolor='blue',alpha=.75)
	
	plt.figure()
	plt.hist(abs_nacr, 10, normed=False, facecolor='red',alpha=.75)
 
	show()

def process_logs(filenames):
	# scatter plots need lists of numbers
	netacrs = []
	runtimes = []
	whs	= []
	wavgs	= []
	pl = PwrLogfile()
	
#	fig = figure()
#	ax = fig.add_subplot(111)

#	fig2 = figure()
#	ax2 = fig2.add_subplot(111)

	fig3 = figure()
	ax3 = fig3.add_subplot(111)

	fig4 = figure()
	ax4 = fig4.add_subplot(211)
	ax5 = fig4.add_subplot(212)

	fig5 = figure()
	ax6 = fig5.add_subplot(111)


	SKIP = 2	
	for filename in filenames:
		pl.read_file(filename)
#		ax.set_title('Runtime vs Avg Power' )
#		ax.plot(pl.darray.th[SKIP:],pl.darray.wavg[SKIP:])

		ax3.set_title('Runtime vs Power' )
		ax3.plot(pl.darray.th[SKIP:],pl.darray.watts[SKIP:])

		ax4.set_title('Runtime vs Voltage' )
		ax4.plot(pl.darray.th[SKIP:],pl.darray.vb[SKIP:])
		ax5.set_title('Runtime vs Current' )
		ax5.plot(pl.darray.th[SKIP:],pl.darray.ib[SKIP:])

		ax6.set_title('Runtime vs Batt Temp' )
		ax6.plot(pl.darray.th[SKIP:],pl.darray.tb[SKIP:])

		runtimes.append(pl.darray.th[-1])
		netacrs.append(pl.darray.netacr[-1])
		whs.append(pl.darray.wh[-1]*-1)
		wavgs.append(pl.darray.wavg[-1]*-1)

#	ax.set_title('Wavg vs netACR')
#	ax.scatter(wavgs,netacrs)
#	ax2.scatter(runtimes,netacrs)
#	plt.figure()
#	ax2.scatter(runtimes,whs)
#	plt.figure()
#	plt.scatter(runtimes,wavgs)
#	plt.figure()
#	plt.hist(wavgs,10, normed=False, facecolor='green')	

	show()
		

def main():
 	filenames = sys.argv[1:]

	process_logs(filenames)

main()

