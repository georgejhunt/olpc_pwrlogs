#!/usr/bin/python

# Copyright (C) 2011 One Laptop per Child
# Released under GPLv2 or later

# dependencies on debian
# python-argparse python-matplotlib python-dateutil

import sys
import csv
import os
import traceback
import numpy as np
import matplotlib
import matplotlib.mlab as mlab
from matplotlib.ticker import MultipleLocator
from pylab import figure, show, normpdf
import matplotlib.pyplot as plt
import argparse
from datetime import datetime, date, time
from dateutil import tz, parser
from matplotlib.backends.backend_pdf import PdfPages
from scipy.interpolate import interp1d

class pwr_trace:
	def __init__(self):

		self.header = {}

		self.Tz	     	 = 0.
		self.ACRz	 = 0.
		self.Wh_sum	 = 0.
		self.interval_Wh = 0.

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
		self.darray	= np.zeros(3)
		self.min_sample_interval = 0
		self.charge_limit=30
		self.enable_charge_limit=False
		self.local_tz = tz.tzutc()
		# The wattage calcs should never be outside these ranges.  If they are
		# then there is some sort of error.
		self.max_watts_limit = 20
		self.min_watts_limit = -15
		self.max_Th	     = 50

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
		if self.header['XOVER'] == '1.5' or self.header['KERNAPI'] == '2':
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

	def process_data(self,converted, converted_prev, skip_short_checks=False):
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
			if not skip_short_checks:
				return (result,1)

	        result[self.Iavg]    = DeltaACR / (result[self.Deltat] / 3600)
	        result[self.NetACR]  = converted[self.ACR] - self.ACRz
	        result[self.Vavg]    = (converted[self.Vb] + converted_prev[self.Vb]) / 2
        	result[self.Watts]   = result[self.Vavg] * (result[self.Iavg] / 1000)

		if result[self.Watts] > self.max_watts_limit or result[self.Watts] < self.min_watts_limit:
			return (result,2)

		if result[self.Th] > self.max_Th or result[self.Th] < 0:
			return (result,3)

		# Keep a copy of the sample Wh so we can adjust things correctly when computing
		# the final interval
		self.interval_Wh     =  (result[self.Watts] * result[self.Deltat] / 3600)
	        result[self.Wh]      = self.Wh_sum + self.interval_Wh

		if result[self.Th] != 0.0:
			result[self.Wavg]    = result[self.Wh] / result[self.Th]
		else:
			result[self.Wavg] = 0.

		if result[self.Iavg] != 0.0:
			result[self.Zavg] = result[self.Vavg] / result[self.Iavg]
		else:
			result[self.Zavg] = 0

		return (result,0)

	def read_file(self,filename,builds=[],serials=[],xovers=[]):
		data = []
		if os.stat(filename).st_size == 0:
			return False

		reader = csv.reader(open(filename,"rb"))
		# Read the header into a dictionary
		# Default to XO version 1 since it does not exist in earlier
		# header formats
		self.header['XOVER'] = '1'
		self.header['KERNAPI'] = '0'
		try:
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
		except:
			print 'Read error in %s line: %d' % (filename,reader.line_num)

		if len(builds) > 0:
			found = False
			buildstr = self.header['BUILD'].lower()
			for each in builds:
				if each in buildstr:
					found = True
					break
			if not found:
				return False

		if len(serials) > 0:
			if not (self.header['SERNUM'].upper() in serials):
				return False

		if len(xovers) > 0:
			if not self.header['XOVER'] in xovers:
				return False

		# Set the local timzone for where the data came from
		try:
			self.local_tz = self.header['DATE'].tzinfo

			if self.local_tz == None:
				print "File: %s Unknown TZ: %s" % (filename,dstring)
				self.local_tz = tz.tzutc()
		except:
			print "File: %s 'DATE' processing problem" % (filename)
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
		row_processed = False

		# read the rest of the file
		try:
			for row in reader:
				if not row:
					continue
				row_processed = False
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

				row_processed = True
				power_data_valid = True
				self.Wh_sum = results[self.Wh]
				converted_last_full_interval = converted_prev[:]
				converted_prev = converted[:]
				converted.extend(results)
				data.append(converted)
		except:
			print '%s : Read error line: %d' % (filename,reader.line_num)

		# If the last row of the file is not processed due to short a time period
		# then back up to the start of the last good interval and process the last entry
		# using that as the start interval.  This still gives us good results and includes
		# the final numbers in the counts for net time and net ACR.
		# This helps up when processing the olpc-batcap logs which have lots of 1 second
		# samples near the end
		if not row_processed:
			# We should have already caught any serious errors when we tried to process it the
			# first time.  So if it fails for some reason then just ignore it.
			try:
				# Back out the Wh sum from the record we are about to replace
				self.Wh_sum -= self.interval_Wh
				# Compute the results from the last good intervals start until the
				# end of the file.
				results,error = self.process_data(converted, converted_last_full_interval)
				power_data_valid = True
				self.Wh_sum = results[self.Wh]
				converted.extend(results)
				# Replace the last interval calc with this new one.
				data[-1] = converted
			except:
				pass

		# Add the various init things to the header info for all the net diff calcs
		self.darray = np.rec.fromrecords(data,names='sec,soc,vb,ib,tb,acr,th,iavg,netacr,deltat,vavg,watts,wh,wavg,tod,zavg')

		if not power_data_valid:
			return False
		else:
			return True

	def set_min_sample_interval(self,interval):
		self.min_sample_interval=interval

	def set_charge_limit(self,limit):
		self.enable_charge_limit=True
		self.charge_limit=limit

def acr_trend_compare(a, b):
	return cmp(a[0],b[0])

def filter_data(series,size=5):
	# we only do odd filter sizes
	if not (size % 2):
		size += 1

	center = int(size/2)
	filtered_data = []
	filter_series = []
	flist = series.tolist()

	# Create the data series with the ends extended
	# so we don't have to special case the fist and last
	# point.  Repeating the beginning and end values help
	# weight the start and end points more toward the real
	# values.
	for x in xrange(0,center):
		filter_series.append(flist[0])
	filter_series.extend(flist[:])
	# One more item on the end so we don't thow an out
	# of range index error.
	for x in xrange(0,center+1):
		filter_series.append(flist[-1])
	end = len(filter_series)-center-1
	for index in xrange(center,end):
		chunk = sorted(filter_series[index-center:index+center+1])[1:-1]
		filtered_data.append(np.average(chunk))
	return filtered_data

def process_logs(filenames,opt):
	# scatter plots need lists of numbers

	show_avgpwr 		= opt.avgpwr
	show_instpwr 		= opt.pwr
	show_voltcur 		= 1
	show_todpwr  		= 0
	save_graphs  		= opt.pdf
	dont_show    		= 0
	show_volt    		= 0
	show_zavg    		= 0
	show_acrhist 		= opt.acrhist or opt.autoacrhist
	acrhist_autorange 	= opt.autoacrhist
	show_cur     		= opt.current
	show_wavg_vs_acr 	= opt.wavgacr
	show_raw_data 		= opt.raw
	do_averages 		= 0
	SKIP 			= opt.skip
	show_temp 		= opt.temp
	debug_show_filenames 	= opt.debug
	title_append	 	= opt.title
	show_acr_trend		= opt.acrtrend
	ignore_date_before	= False
	serial_numbers		= []
	build_list		= []
	xover_list		= []

	if opt.build:
		build_list	= [ x.lower() for x in opt.build.split(',') ]

	if opt.sernum:
		serial_numbers	= [ x.upper() for x in opt.sernum.split(',') ]

	if opt.xover:
		xover_list 	= opt.xover.split(',')

	if opt.dignore:
		try:
			ignore_date_before = True
			ignore_date = parser.parse(opt.dignore,fuzzy=True)
			ignore_date = ignore_date.replace(tzinfo=tz.tzutc())
		except:
			print "Can't parse ignore date"
			ignore_date_before = False


	netacrs = []
	runtimes = []
	whs	= []
	wavgs	= []
	pl = PwrLogfile()
	figures = []
	average_ib = np.arange(1)
	average_W  = np.arange(1)
	nr_data_series = 0
	acr_trend = {}
	acr_trend_avg = []

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
		if not opt.voltcur:
			show_voltcur = 0
		fig3 = figure()
		ax3 = fig3.add_subplot(111)
		ax3.set_xlabel('Delta Time (Hours)')
		ax3.set_ylabel('Inst Power (Watts)')
		if show_raw_data:
			title = 'Power vs Time'
		else:
			title ='Power (filtered) vs Time'
		if title_append:
			title = title + (' (%s)' % title_append)
		ax3.set_title(title)
		ax3.grid()
		ax3.minorticks_on()
		figures.append(fig3)

	if show_voltcur:
		fig4 = figure()
		ax4 = fig4.add_subplot(211)
		ax4.grid()
		title = 'Voltage vs Time'
		if title_append:
		    title = title + (' (%s)' % title_append)
		ax4.set_title(title)
		ax4.set_ylabel('Volts')

		ax4_2 = fig4.add_subplot(212)
		title = 'Current vs Time'
		if title_append:
		    title = title + (' (%s)' % title_append)
		ax4_2.set_title(title)
		ax4_2.grid()
		ax4_2.set_ylabel('mA')
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

	if show_acrhist:
		fig8= figure()
		ax8 = fig8.add_subplot(111)
		if title_append:
		    ax8.set_title('Capacity Histogram (%s)' % title_append)
		else:
		    ax8.set_title('Capacity Histogram')
		ax8.set_xlabel('mAh')
		ax8.set_ylabel('Runs (nomalized)')
		if not acrhist_autorange:
	#		majorTick = MultipleLocator(0)
			minorTick = MultipleLocator(10)
	#		ax8.xaxis.set_major_locator(majorTick)
			ax8.xaxis.set_minor_locator(minorTick)
		ax8.grid()
		figures.append(fig8)
	if show_cur:
		fig9=figure()
		ax9 = fig9.add_subplot(111)
		if show_raw_data:
		    title = 'Current vs Time'
		else:
		    title = 'Current (filtered) vs Time'
		if title_append:
		    title = title + (' (%s)' % title_append)
		ax9.set_title(title)
		ax9.set_xlabel('Delta Time (Hours)')
		ax9.set_ylabel('Current (mA)')
		figures.append(fig9)

	if show_wavg_vs_acr:
		fig10=figure()
		ax10 = fig10.add_subplot(111)
		ax10.set_title('Average Wattage vs Net Acr')
		ax10.set_ylabel('Net ACR')
		ax10.set_xlabel('Average Wattage')
		ax10.grid()
		figures.append(fig10)

	if show_temp:
		fig11 = figure()
		ax11 = fig11.add_subplot(111)
		ax11.set_title('Battery Temperature vs Time' )
		ax11.set_ylabel('Battery Temperature degC')
		ax11.set_xlabel('Delta Time (Hours)')

	if show_acr_trend:
		fig12 = figure()
		ax12 = fig12.add_subplot(111)
		ax12.set_title('Per Battery net ACR Trend ' )
		ax12.set_ylabel('Net ACR (mAh)')
		ax12.set_xlabel('Test Run')
		minorTick = MultipleLocator(10)
		ax12.yaxis.set_minor_locator(minorTick)
		ax12.grid()
#		ax12_2 = fig12.add_subplot(212)

	for filename in filenames:
		read_result = pl.read_file(filename,builds=build_list,serials=serial_numbers,xovers=xover_list)

		if debug_show_filenames:
			print filename
			if not read_result:
				print "Skipped"

		if not read_result:
			continue

		if show_avgpwr:
			ax.plot(pl.darray.th[SKIP:],pl.darray.wavg[SKIP:])

		if show_instpwr:
			if show_raw_data:
				ax3.plot(pl.darray.th[SKIP:],pl.darray.watts[SKIP:])
			else:
				mavg = filter_data(pl.darray.watts[SKIP:])
				ax3.plot(pl.darray.th[SKIP:],mavg)
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
		if show_cur:
			if show_raw_data:
				ax9.plot(pl.darray.th[SKIP:],pl.darray.ib[SKIP:])
			else:
				mavg = filter_data(pl.darray.ib[SKIP:],5)
				ax9.plot(pl.darray.th[SKIP:],mavg)

		if show_wavg_vs_acr:
			ax10.scatter(abs(pl.darray.wavg[-1]),abs(pl.darray.netacr[-1]))

		if show_temp:
			ax11.plot(pl.darray.th[SKIP:],pl.darray.tb[SKIP:])

		if show_acr_trend:
			use_this_point = True
			if ignore_date_before and pl.header['DATE'] < ignore_date:
				use_this_point = False

			if use_this_point:
				batser = pl.header['BATSER']
				if batser in acr_trend:
					 point_list = acr_trend[batser]
				else:
					point_list = []

				# List elemets are a tuple of (date,ACR)
				point_list.append( (pl.header['DATE'],abs(pl.darray.netacr[-1])) )
				acr_trend[batser] = point_list

		runtimes.append(pl.darray.th[-1])
		netacrs.append(pl.darray.netacr[-1])
		whs.append(pl.darray.wh[-1]*-1)
		wavgs.append(pl.darray.wavg[-1]*-1)

	if show_acrhist:
		abs_acr = [abs(x) for x in netacrs]
		mu    = np.mean(abs_acr)
		stdev = np.std(abs_acr)
		textstr = '$\mu=%.2f$\n$\sigma=%.2f$'%(mu, stdev)
		if acrhist_autorange:
			# 30 bins but let matplotlib sort out the range.
			counts, bins, patches = ax8.hist(abs_acr,30,normed=True, facecolor='g',alpha=.75)
		else:
			# Scale the histogram so we can compare different graphs easily.
			counts, bins, patches = ax8.hist(abs_acr,30,range=(2700,3000), normed=True, facecolor='g',alpha=.75)
			ax8.set_ylim(0,.035)

		props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
		ax8.text(0.05, 0.95, textstr, transform=ax8.transAxes, fontsize=14,
			verticalalignment='top', bbox=props)
		# Set the ticks to be at the edges of the bins
#		ax8.set_xticks(bins)
#		labels = ax8.get_xticklabels()
#		for label in labels:
#			label.set_rotation(40)
		npdf  = normpdf(bins, mu, stdev)
		ax8.plot(bins,npdf,'k--',linewidth=1.5)

	if show_acr_trend:
		for k,v in acr_trend.iteritems():
			# sort the tuples by date rundate
			v.sort(acr_trend_compare)
			# Break the (date,value) tuple apart and replace the date with number starting at 1 continuing to the
			# end of this list.  This make the plots regular on the X axis
			item_index=0
			acr_val = []
			for each in v:
				acr_val.append(each[1])

				try:
					value, count = acr_trend_avg[item_index]
					value+=each[1]
					count+=1
					acr_trend_avg[item_index] = (value,count)
				except IndexError:
					acr_trend_avg.append( (float(each[1]),1) )

				item_index+=1

			ax12.plot(range(1,len(acr_val)+1),acr_val,alpha=.75)
#			pf = np.polyfit(xval,acr_val,3)
#			fit = np.poly1d(pf)
#			ax12_2.plot(xval,fit(xval))

		avg_result = []
		for each in acr_trend_avg:
			value, count = each
			value/= count
			avg_result.append(value)

		ax12.plot(range(1,len(avg_result)+1),avg_result,'s-',linewidth=2,color='black')
		ax12.set_xlim(left=1)

	if save_graphs:
		for each in figures:
			pp.savefig(each)
		pp.close()

	show()

def main():

	parser = argparse.ArgumentParser(description='Make power log graph')
	parser.add_argument('filenames', nargs='+', help='files to process')
	parser.add_argument('--compress', action='store',type=int,default=60,
		help='Minumum number of elapsed seconds for each datapoint')
	parser.add_argument('--chg_limit',type=float,
		help='Limit charge wattage')
	parser.add_argument('--debug', action='store_true',default=False,
		help='Enabled debug output')
	parser.add_argument('--pdf', action='store_true',default=False,
		help='Create pdf of all graphs')
	parser.add_argument('--current', action='store_true',default=False,
		help='Plot current vs time')
	parser.add_argument('--wavgacr', action='store_true',default=False,
		help='Plot average wattage vs net ACR')
	parser.add_argument('--raw', action='store_true',default=False,
		help="Don't filter the data")
	parser.add_argument('--avgpwr', action='store_true',default=False,
		help="Output average power for all series")
	parser.add_argument('--acrhist', action='store_true',default=False,
		help="Show net ACR histogram")
	parser.add_argument('--skip', action='store',type=int,default=1,
		help='Number of data points from the start to skip when plotting')
	parser.add_argument('--autoacrhist', action='store_true',default=False,
		help="Allow acr histogram to autorange")
	parser.add_argument('--temp', action='store_true',default=False,
		help="Plot battery temperature vs time")
	parser.add_argument('--pwr', action='store_true',default=False,
		help="Plot instant power vs time")
	parser.add_argument('--title',
		help="Text to append to the plot titles")
	parser.add_argument('--acrtrend', action='store_true',default=False,
		help="Plot net ACR trend per battery")
	parser.add_argument('--dignore',
		help="Ignore dates eariler than this for ACR trend")
	parser.add_argument('--byxo', action='store_true',default=False,
		help="Break plots into per machine type")
	parser.add_argument('--voltcur', action='store_true',default=False,
		help="Plot voltage and current vs time")
	parser.add_argument('--build', action='store',type=str,default=None,
		help="Only plot files with the OS build containing the substring. Multiple strings in a quoted csv string")
	parser.add_argument('--sernum', action='store',type=str,default=None,
		help="Only plot files matching serial numbers.  Multiple SN's can be in a quoted csv string")
	parser.add_argument('--xover', action='store',type=str,default=None,
		help="Only plot files matching XO generation. [1|1.5|1.75|4]  Multiple generations can be in a quoted csv string")

	args = parser.parse_args()

	if len(args.filenames) != 0:
	    process_logs(args.filenames,args)
	else:
	    print "No files found to process"

main()

