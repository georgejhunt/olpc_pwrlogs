#!/usr/bin/python

# Copyright One Laptop Per Child
# Released under GPLv2 or later
# Version 0.0.3


import sys
import csv
import os
import traceback
from numpy import *
from matplotlib import mlab
from matplotlib.ticker import MultipleLocator
from pylab import figure, show
import matplotlib.pyplot as plt
import argparse
from datetime import datetime, date, time
from dateutil import tz, parser
from matplotlib.backends.backend_pdf import PdfPages

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
		self.darray	= zeros(3)
		self.min_sample_interval = 0
		self.charge_limit=30
		self.enable_charge_limit=False
		self.local_tz = tz.tzutc()

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

		if result[self.Watts] > self.charge_limit and self.enable_charge_limit:
			result[self.Watts] = self.charge_limit

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

		# Now read in the data
		try:
			converted = self.convert_data(reader.next())
			converted_prev = converted[:]
		except:
			print 'Conversion error in %s line: %d' % (filename,reader.line_num)
			traceback.print_exc(file=sys.stdout)

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

		# read the rest of the file
		for row in reader:
			if not row:
				continue
			try:
				converted = self.convert_data(row)
				results,error = self.process_data(converted, converted_prev)
				if error:
					continue
				self.Wh_sum = results[self.Wh]
				converted_prev = converted[:]
				converted.extend(results)
				data.append(converted)
			except:
				print 'Conversion error in %s line: %d' % (filename,reader.line_num)
		# Add the various init things to the header info for all the net diff calcs

		self.darray = rec.fromrecords(data,names='sec,soc,vb,ib,tb,acr,th,iavg,netacr,deltat,vavg,watts,wh,wavg,tod,zavg')

	def set_min_sample_interval(self,interval):
		self.min_sample_interval=interval

	def set_charge_limit(self,limit):
		self.enable_charge_limit=True
		self.charge_limit=limit

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

def process_logs(filenames,opt):
	# scatter plots need lists of numbers

	show_avgpwr = 0
	show_instpwr = 0
	show_voltcur = 0
	show_todpwr  = 0
	save_graphs  = 1
	dont_show    = 0
	show_volt    = 0
	show_zavg    = 1

	netacrs = []
	runtimes = []
	whs	= []
	wavgs	= []
	pl = PwrLogfile()
	figures = []

	pl.set_min_sample_interval(opt.compress)

# 	Seems broken
#	if hasattr(opt,"chg_limit"):
#		pl.set_charge_limit(opt.chg_limit)

	if save_graphs:
		pp = PdfPages('graphs.pdf')

	if show_avgpwr:
		fig = figure()
		ax = fig.add_subplot(111)
		ax.set_title('Avg Power vs Time' )
		figures.append(fig)

# Bat current vs SOC.
	if dont_show:
		fig2 = figure()
		ax2 = fig2.add_subplot(111)
		figures.append(fig2)

	if show_instpwr:
		fig3 = figure()
		ax3 = fig3.add_subplot(111)
		ax3.set_xlabel('Delta Time (Hours)')
		ax3.set_ylabel('Inst Power (Watts)')
		ax3.set_title('Power vs Delta Time' )
		figures.append(fig3)

	if show_voltcur:
		fig4 = figure()
		ax4 = fig4.add_subplot(211)
		ax4.set_title('Voltage vs Time' )
		ax4_2 = fig4.add_subplot(212)
		ax4_2.set_title('Current vs Time' )
		figures.append(fig4)

	if show_todpwr:
		fig5 = figure()
		ax5 = fig5.add_subplot(111)
		ax5.set_xlabel('Time of Day (H.M/60)')
		ax5.set_ylabel('Inst Power (Watts)')
		ax5.set_title('Power vs Time of day')
		figures.append(fig5)

	if show_volt:
		fig6 = figure()
		ax6 = fig6.add_subplot(111)
		ax6.set_title('Voltage vs Time' )
		figures.append(fig6)
	if show_zavg:
		fig7 = figure()
		ax7 = fig7.add_subplot(111)
		ax7.set_title('Impeadance vs Time' )
		figures.append(fig7)

	SKIP = 1
	for filename in filenames:
		pl.read_file(filename)

		if show_avgpwr:
			ax.plot(pl.darray.th[SKIP:],pl.darray.wavg[SKIP:])

		if show_instpwr:
			ax3.plot(pl.darray.th[SKIP:],pl.darray.watts[SKIP:])

		if show_voltcur:
			ax4.plot(pl.darray.th[SKIP:],pl.darray.vb[SKIP:])
			ax4_2.plot(pl.darray.th[SKIP:],pl.darray.ib[SKIP:])

		if dont_show:
			ax2.plot(pl.darray.soc[SKIP:],pl.darray.ib[SKIP:])

		if show_todpwr:
			ax5.plot(pl.darray.tod[SKIP:],pl.darray.watts[SKIP:])

		if show_volt:
			ax6.plot(pl.darray.th[SKIP:],pl.darray.vb[SKIP:])
		if show_zavg:
			ax7.plot(pl.darray.th[SKIP:],pl.darray.zavg[SKIP:])


#		ax6.set_title('Runtime vs Batt Temp' )
#		ax6.plot(pl.darray.th[SKIP:],pl.darray.tb[SKIP:])

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

	if save_graphs:
		for each in figures: pp.savefig(each)
		pp.close()


def main():
# 	filenames = sys.argv[1:]

	parser = argparse.ArgumentParser(description='Make power log graph')
	parser.add_argument('filenames', nargs='+', help='files to process')
	parser.add_argument('--compress', action='store',type=int,default=60,
		help='Minumum number of elapsed seconds for each datapoint')
	parser.add_argument('--chg_limit',type=float,
		help='Limit charge wattage')

	args = parser.parse_args()

	process_logs(args.filenames,args)

main()

