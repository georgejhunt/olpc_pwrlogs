#!/usr/bin/python
import serial
import sys
import time
import argparse

class WattsUp():
	def __init__(self,port='/dev/ttyUSB0'):
		self.ser = serial.Serial()
		self.ser.port = port
		self.ser.baudrate = 115200
		self.ser.timeout = 1
		self.result = ''
		self.readings = []
		self.reading_valid = False
		self.interval = 0;
		
		self.WATTS = 0
		self.PF = 13
	
	def set_port(self, port):
		self.ser.port = port
	
	def open(self):
		self.ser.open()
		return self.ser.isOpen()

	def close(self):
		self.ser.close()

	def read(self,tries=1):
		while (tries > 0):
			self.result = self.ser.readline()
#			print "Result: %s" % self.result
			if (len(self.result) >0):
				return True
			tries-=1
		return False
		
	def write(self,data):
		self.ser.write(data)

	def get_version(self):
		cmd = '#V,R,0;'
		self.write(cmd)
		self.ser.timeout = 5
		return self.ser.readline()

	def reset(self):
		cmd = '#V,W,0;'
		tries = 5
		while (tries > 0):
			self.write(cmd)
			self.read(3);
			if (self.result.startswith('Watts Up?')):
				self.read();
				self.read();
				break;
			tries-=1
		if (tries<=0):
			print "Reset failed"
			return False
		return True

	# Not sure if this works
	def abort(self):
		cmd = '#\x18;'
		self.write(cmd)

	def start_log(self,interval):
		self.interval = interval
		cmd = "#L,W,3,E,1,%d;" % interval
 		self.write(cmd)		

	def do_reading(self):
		self.reading_valid = False
		if not self.read(self.interval):
			return False
		if self.result.startswith('#d'):
			values = (self.result.strip()[:-1]).split(',')	
			self.readings = values[3:]
			self.reading_valid = True
			return True
		return False		
	
	def get_W(self):
		return float(self.readings[self.WATTS])/10.0
	def get_PF(self):
		return float(self.readings[self.PF])/100.0

	# Doesn't seem to work
	def stop_log(self):
		cmd = '#L,R,0;'
		self.write(cmd)

class Readings():
	def __init__(self):
		self.history = []
		self.wattage = 0.0
		self.wattseconds = 0.0
		self.last_readtime = 0.0
		self.last_wattseconds = 0.0
		self.nr_units = 1

	def set_nr_units(self,units):
		self.nr_units = units

	def add_reading(self,readtime,wattage,pf,first=False):
		if first:
			self.last_readtime = readtime

		self.total_wattage = wattage
		self.per_unit_wattage = wattage/self.nr_units
		self.wattseconds = (readtime - self.last_readtime) * self.per_unit_wattage
		self.last_readtime = readtime
		self.wattseconds = self.wattseconds + self.last_wattseconds
		self.last_wattseconds = self.wattseconds
		reading = dict(READTIME=readtime,TOT_WATTAGE=self.total_wattage,WATTAGE=self.per_unit_wattage,PF=pf,WATTSECONDS=self.wattseconds)
		self.history.append(reading)
		
	def get_last_reading(self):
		reading = self.history[len(self.history)]
		return reading

	def print_last_reading_csv(self):
		first = self.history[0]
		r = self.history[-1]
		print "%.1f, %.3f, %5.1f, %7.4f, %4.2f, %7.4f" % (r['READTIME'],(r['READTIME']-first['READTIME'])/3600,r['TOT_WATTAGE'],r['WATTAGE'],r['PF'],r['WATTSECONDS']/3600)
		sys.stdout.flush()

if __name__ == "__main__":

	parser = argparse.ArgumentParser(description='Meter interface to the WattsUp Pro .Net')
	parser.add_argument('-d','--delay', type=int, default=3, dest='delay',
                   help='Seconds per reading (default 2)')
	parser.add_argument('-u','--units', type=int, default=1,
                   help='Number of devices tested')
#	parser.add_argument('-c','--channels', type=int, default=2, dest='channels',
#                   help='Expected channels per reading (default 2)')
	parser.add_argument('-p','--port', default='/dev/ttyUSB0',
                   help='USB port to use default: /dev/ttyUSB0')
	
	args = parser.parse_args()

	meter = WattsUp(args.port)
	readings = Readings()

	def exit_program():
		meter.stop_log()
		meter.close()

	if not meter.open():
		print "open fail"
		sys.exit()

	readings.set_nr_units(args.units)
	meter.start_log(args.delay)

	try:
		# Need to do a special 1st read to init the time variable to Now.
		while True:
			meter.do_reading()
			if meter.reading_valid:
				readings.add_reading(readtime=time.time(),wattage=meter.get_W(),pf=meter.get_PF(),first=True)
				readings.print_last_reading_csv()
				break;
			
	except KeyboardInterrupt:
		exit_program()

	# Start the endless reading loop.
	try:	
		while True:
			meter.do_reading()
			if meter.reading_valid:
				readings.add_reading(readtime=time.time(),wattage=meter.get_W(),pf=meter.get_PF())
				readings.print_last_reading_csv()

	except KeyboardInterrupt:
		pass	

	exit_program()

