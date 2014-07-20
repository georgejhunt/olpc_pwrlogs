#!/usr/bin/env python
# Copyright 2012 George Hunt -- georgejhunt@gmail.com
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

# reminder to myself:
# Try to keep the transitory state in a tmpfs, so as to
# minimize the writes to a SD card or flash. Notice if the tmpfs file is missing, in the
# presence of the summary file, if the power was last seen as out, it will be
# recorded as the end of the power outage
# This implimentation requires that DATA_FILE be in a temporary file system -- check fstab
#
# Time Zones are really difficult. datetime.now() returns local time, and 
# tstampto string also generates a tz offset string.  Perhaps simplist is to 
# do allmy processing in UTC.

import time
from subprocess import Popen, PIPE
import datetime
import os, sys
import gconf
import logging
import json
import glob
from gettext import gettext as _

DATA_FILE = "/tmp/mains_power"
# data_dict is global config file initialized in is_exist_data_file - used throughout
data_dict = {}

WORK_DIR = "/root/acpower"
SUMMARY_PREFIX = WORK_DIR
SUMMARY_SUFFIX = "_ac_power_summary"
SUMMARY_CURRENT = "current_ac_summary"
CRONFILE = "acrecord_cron"
ACRECORD_CRON = "%s/%s" % (SUMMARY_PREFIX,CRONFILE,)
summary_dict = {}

VERSION = "0.1"
ENABLED = 'ENABLED'
debug = False

SYS_AC = "  /sys/class/power_supply/olpc-ac/online"

logger = logging.getLogger('acpower')
hdlr = logging.FileHandler(os.path.join(WORK_DIR,'acpower.log'))
formatter = logging.Formatter('%(asctime)s %(levelname)s %(messages)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
#logger.setLevel(logging.DEBUG)
logger.setLevel(logging.WARNING)

"""the following class is stolen from dateutil -- becuse dateutil needs to be installed online and we're trying to make an offline install """
ZERO = datetime.timedelta(0)
EPOCHORDINAL = datetime.datetime.utcfromtimestamp(0).toordinal()

class tzlocal(datetime.tzinfo):

    _std_offset = datetime.timedelta(seconds=-time.timezone)
    if time.daylight:
        _dst_offset = datetime.timedelta(seconds=-time.altzone)
    else:
        _dst_offset = _std_offset

    def utcoffset(self, dt):
        if self._isdst(dt):
            return self._dst_offset
        else:
            return self._std_offset

    def dst(self, dt):
        if self._isdst(dt):
            return self._dst_offset-self._std_offset
        else:
            return ZERO

    def tzname(self, dt):
        return time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        # We can't use mktime here. It is unstable when deciding if
        # the hour near to a change is DST or not.
        # 
        # timestamp = time.mktime((dt.year, dt.month, dt.day, dt.hour,
        #                         dt.minute, dt.second, dt.weekday(), 0, -1))
        # return time.localtime(timestamp).tm_isdst
        #
        # The code above yields the following result:
        #
        #>>> import tz, datetime
        #>>> t = tz.tzlocal()
        #>>> datetime.datetime(2003,2,15,23,tzinfo=t).tzname()
        #'BRDT'
        #>>> datetime.datetime(2003,2,16,0,tzinfo=t).tzname()
        #'BRST'
        #>>> datetime.datetime(2003,2,15,23,tzinfo=t).tzname()
        #'BRST'
        #>>> datetime.datetime(2003,2,15,22,tzinfo=t).tzname()
        #'BRDT'
        #>>> datetime.datetime(2003,2,15,23,tzinfo=t).tzname()
        #'BRDT'
        #
        # Here is a more stable implementation:
        #
        timestamp = ((dt.toordinal() - EPOCHORDINAL) * 86400
                     + dt.hour * 3600
                     + dt.minute * 60
                     + dt.second)
        return time.localtime(timestamp+time.timezone).tm_isdst

    def __eq__(self, other):
        if not isinstance(other, tzlocal):
            return False
        return (self._std_offset == other._std_offset and
                self._dst_offset == other._dst_offset)
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "%s()" % self.__class__.__name__

    __reduce__ = object.__reduce__

class tzutc(datetime.tzinfo):

    def utcoffset(self, dt):
        return ZERO
     
    def dst(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def __eq__(self, other):
        return (isinstance(other, tzutc) or
                (isinstance(other, tzoffset) and other._offset == ZERO))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "%s()" % self.__class__.__name__

    __reduce__ = object.__reduce__

class AcException():
    def __init__(self, msg):
        print(msg)
        sys.exit(1)
# get a global instance of the tzlocal class
tz = tzlocal()
tzu = tzutc()
UTC2LOCAL = datetime.datetime.now(tz) - datetime.datetime.now(tzu)
UTC2LOCALSECONDS = UTC2LOCAL.total_seconds()

class Tools:
    def __init__(self):
        pass

    def cli(self, cmd):
        """send cmd line to shell, rtn (text,error code)"""
        logger.debug('command_line cmd:%s'%cmd)
        p1 = Popen(cmd,stdout=PIPE, shell=True)
        output = p1.communicate()
        if p1.returncode != 0 :
            logger.debug('error returned from shell command: %s was %s'%(cmd,output[0]))
        return output[0],p1.returncode

    def get_ac_status(self):
        """ get the "1" or "0" strings indicating power state from kernel """
        line,err = self.cli('cat %s' % (SYS_AC,))
        return line.strip()

    def is_exist_data_file(self):
        #get the tmp data file
        global data_dict
        if (len(data_dict)> 0):
            return True
        try:
            fd = file(DATA_FILE,'r')
            data_str = fd.read()
            data_dict = json.loads(data_str)
            fd.close()
            return True
        except IOError:
            return False

    def put_data_file(self):
        """ writes the data_dict to tmp file system """
        try:
            fd = file(DATA_FILE,'w')
            data_str = json.dumps(data_dict)
            fd.write(data_str)
            fd.close()
        except IOError,e:
            logging.exception("failed to write data file. error:%s"% (e,))
            raise AcException("Datafile write error")

    def get_summary_filename(self):
        """ returns the filename of current summary file or "" if it doesn't exist """
        fn = os.path.join(SUMMARY_PREFIX,SUMMARY_CURRENT)
        if (os.path.isfile(fn)):
            try:
                fd = open(fn,"r")
                fname = fd.read()
            except :
                cmd = "rm -f %s"%fn
                result,status = self.cli(cmd)
                return ""
            return fname
        return ""

    def put_summary_filename(self, fname):
        """ places the filename of current summary file in pointer file"""
        fn = os.path.join(SUMMARY_PREFIX,SUMMARY_CURRENT)
        try:
            fd = open(fn,"w")
            fd.write(fname)
            fd.close()
        except IOError,e:
            logging.exception("failed to write summary file name. error:%s"% (e,))
            raise AcException("Summary file write name error. path:%s"%fname)

    def is_exist_summary_file(self):
        """does the permanent  record exist? """
        fn = self.get_summary_filename()
        if (fn  == ""):
            return False
        try:
            fd = file(fn,'r')
            fd.close()
            return True
        except IOError,e:
            logging.exception("failed to read summary file. error:%s"% (e,))
            raise AcException("Summary file write key value error")

    def write_current_ac_status(self):
        """ write ac status to tmp file (catches reboot or loss of battery) """
        global data_dict
        """
        try:
            fd = file(DATA_FILE,'r')
            data_str = fd.read()
            data_dict = json.loads(data_str)
        except:
            pass
        """
        # if the status of power has changed, record the new state
        #last_summary_ac = self.last_summary_ac_state()
        #if last_summary_ac != self.get_ac_status():
        if self.last_summary_ac_state() != self.get_ac_status():
            self.write_summary()
        now = datetime.datetime.now(tzu)
        nowdatetime = now.astimezone(tz)
        nowstr = self.format_datetime(nowdatetime)
        print("nowstr %s"% nowstr)
        data_dict[nowstr] = self.get_ac_status()
        self.put_data_file()

    def write_summary(self):
        """ record the change in ac power to permanent record """
        self.write_summary_key_value(self.format_datetime(datetime.datetime.now(tz)),
                                    self.get_ac_status())

    def write_summary_key_value(self, key="", value=""):
        """ write summary file as key, value pair """
        global summary_dict
        name = self.get_summary_filename()
        if (len(name)>0):
            try:
                fsummary = file(name,'r')
                data_str = fsummary.read()
                summary_dict = json.loads(data_str)
            except:
                print("write_summary_error. name:%s"%name)
                raise AcException("Summary file write key value error")
        else:
            #we need to generate a new file name and file
            name = self.format_datetime(datetime.datetime.now(tz))
            name = name.replace("/","_")
            name = name.replace(":","-")
            name = os.path.join(SUMMARY_PREFIX,name) + SUMMARY_SUFFIX
            self.put_summary_filename(name)
            summary_dict = {}
        summary_dict[key] = value
        data_str = json.dumps(summary_dict)
        try:
            #print data_str
            fsummary = file(name,'w')
            fsummary.write(data_str)
            fsummary.close()
        except IOError,e:
            logging.exception("failed to write summary file. error:%s"% (e,))
            raise AcException("Summary file write key value error")

    def get_summary_dict(self):
        global summary_dict
        name = self.get_summary_filename()
        if (len(name)>0 and len(summary_dict) == 0):
            try:
                fsummary = file(name,'r')
                data_str = fsummary.read()
                summary_dict = json.loads(data_str)
            except IOError:
                return False
            return True

    def last_summary_ac_state(self, return_key=False):
        """ return the key (datestring) of the most recently recorded change """
        global summary_dict
        if self.get_summary_dict():
            keylist = sorted(summary_dict.keys())
            #print(keylist)
            last_key = keylist[-1]
            if return_key:
                return last_key
            else:
                return summary_dict[last_key]
        else:
            return ""

    def get_datetime(self, datestr):
        """ translate ymdhms string into datetime """
        dt = datetime.datetime.strptime(datestr, "%Y/%m/%d-%H:%M:%S-%Z")
        if datestr.find("GMT"):
            tzaware = dt.replace(tzinfo=tzu)
        else:
            tzaware = dt.replace(tzinfo=tz)
        return tzaware

    def tstamp(self, dtime):
        '''return a UNIX style seconds since 1970 for datetime input'''
        epoch = datetime.datetime(1970, 1, 1,tzinfo=tz)
        newdtime = dtime.astimezone(tz)
        since_epoch_delta = newdtime - epoch
        return since_epoch_delta.total_seconds()

    def get_utc_tstamp_from_local_string(self,instr):
        localdt = self.get_datetime(instr)
        return self.tstamp(localdt)  + tzoffset

    def str2tstamp(self, thestr):
        '''return a UNIX style seconds since 1970 for string input'''
        dtime = datetime.datetime.strptime(thestr.strip(), "%Y/%m/%d-%H:%M:%S-%Z")
        awaredt = dtime.replace(tzinfo=tz)
        newdtime = awaredt.astimezone(tz)
        epoch = datetime.datetime(1970, 1, 1,tzinfo=tz)
        since_epoch_delta = newdtime - epoch
        return since_epoch_delta.total_seconds()

    def tstamp_now(self):
        """ return seconds since 1970 """
        return self.tstamp(datetime.datetime.now(tz))

    def format_datetime(self, dt):
        """ return ymdhms string """
        awaredt = dt.astimezone(tz)
        return datetime.datetime.strftime(awaredt, "%Y/%m/%d-%H:%M:%S-%Z")

    def dhm_from_seconds(self,s):
        """ translate seconds into days, hour, minutes """
        #print s
        days, remainder = divmod(s, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, remainder = divmod(remainder, 60)
        return (days, hours, minutes)

    def ts2str(self,ts):
        """ change a time stamp into a string expressed in local time zone"""
        unaware = datetime.datetime.fromtimestamp(ts)
        aware = unaware.replace(tzinfo=tzu)
        return self.format_datetime(aware)

    def enable(self):
        timezone = None
        # get the time zone from the environment
        if os.environ.has_key("TZ"):
            timezone = os.environ["TZ"]
            try:
                tzfile = open("%s/timezone"%WORK_DIR,"w")
                tzfile.write(timezone + "\n")
                tzfile.close()
            except IOError:
                pass
        else:
            print("No time zone (TZ environment variable). Aborting")
            return
        self.write_summary_key_value(self.format_datetime(datetime.datetime.now(tz)),"1")
        result, flag = self.cli("grep -e acrecord /etc/crontab")
        print("result:%s  flag:%s"%(result,flag,))
        if flag != 0:
            line = "*/5 * * * * root %s\n" % (ACRECORD_CRON,) 
            try:
                    
                ctab = file('/etc/crontab','a')
                if timezone:
                    ctab.write("TZ = %s\n" % timezone)
                ctab.write(line)
                ctab.close()
            except IOError:
                raise AcException("crontab file write error in enable")

    def isenabled(self):
            #check that the cron pointer is in place
            cmd = "grep -e %s  /etc/crontab" % (ACRECORD_CRON,) 
            result, flag = self.cli(cmd)
            if flag == 0:
                return True
            return False

    def disable(self):
        """ remove the entry in crontab that samples the AC power state """
        cmd = "sed -i -e /^CRON_TZ/d /etc/crontab"
        result, flag = self.cli(cmd)
        cmd = "sed -i -e /%s/d /etc/crontab" % ACRECORD_CRON
        result, flag = self.cli(cmd)

        #record the current status -- And mark the end of the series
        cd = CollectData()

        # by removing the file that points to the current power series, the next
        #    call to make an entry will generate a new file
        fn = os.path.join(SUMMARY_PREFIX,SUMMARY_CURRENT)
        cmd = "rm -f %s" % fn
        result, status = self.cli(cmd)
        if self.is_exist_data_file:
            self.cli("rm -f %s"% DATA_FILE)

    def delete(self):
        """ add the suffix .ignore to all the files in working directory ending with AC_POWER_SUFFIX"""
        dirlist = glob.glob(os.path.join(SUMMARY_PREFIX,"*" + SUMMARY_SUFFIX))
        for fname in dirlist:
            cmd = "mv %s %s.ignore"%(fname,fname,)
            result, status = self.cli(cmd)

    def get_battery_percent(self):
        """ read battery from sys fs, return as percentage string"""

        cmd = """cat /sys/class/power_supply/olpc-battery/uevent | 
                gawk 'BEGIN {FS="="};/CAPACITY=/{print $2}'"""
        (pcent,err,) = self.cli(cmd)
        if err == 0:
            return pcent
        return "99"

class ShowPowerHistory(Tools):
    def __init__(self):
        global summary_dict, data_dict
        number_of_gaps = 0
        if not self.is_exist_summary_file() or not self.is_exist_data_file():
            # this is the first invocation of the AC logger
            self.write_summary()
        #record the current status -- primarily useful for debugging
        cd = CollectData()
        if debug:
            self.output_state()
        self.write_summary()
        self.output_all_summaries(SUMMARY_PREFIX)

    def output_all_summaries(self, summary_path):
        dirlist = glob.glob(os.path.join(SUMMARY_PREFIX,"*" + SUMMARY_SUFFIX))
        #for fname in sorted(dirlist,reverse=True):
        for fname in sorted(dirlist):
            self.output_summary(fname)


    def output_summary(self,fname):
        #get the summary file so we can operate upon the values (local time)
        try:
            fsummary = file(fname,'r')
            data_str = fsummary.read()
        except IOError:
            raise AcException("Summaary file read error in init of ShowPowerHistory")
        fsummary.close()
        summary_dict = json.loads(data_str)
        keylist = sorted(summary_dict.keys())
        if not self.is_exist_data_file():
            last = self.format_datetime(datetime.datetime.now(tz))
        else:
            last = keylist[-1]
        # assume that the test starts with power on
        current_state = '1'

        # gaps is power outages in seconds
        gaps = {}
        gap_start = None
        print("\nGAPS IN AC POWER DURING %s to %s:" % (keylist[0], last,))
        #print("File Name: %s\n"%(fname,))
        #print("last:%s"%last)
        
        first = None
        gap_start = None
        ts_list = []
        for key in keylist:
            print(key, summary_dict[key])
            if not first:
                first = key
                #print("first:%s"%first)
            if summary_dict[key] == "exhausted":
                summary_dict[key] = 0
            if summary_dict[key] == "0" and not gap_start:
                gap_start = key
                if key == keylist[-1]:
# create a fake gap which includes current time as it's end
                    gaps[key] =  self.str2tstamp(last) - self.str2tstamp(key)
            if gap_start and summary_dict[key] == "1":
                gaps[gap_start] = self.str2tstamp(key) - self.str2tstamp(gap_start)
                gap_start = None
            utc_ts = self.get_utc_tstamp_from_local_string(key)
            ts_list.append((utc_ts,summary_dict[key],))
        #print("first:%s, last:%s"%(first,last,))
        sys.stdout.flush()
        total_seconds = self.str2tstamp(last) - self.str2tstamp(first)
        (days, hours, minutes) = self.dhm_from_seconds(total_seconds)
        print "length of log %s days, %s hours, %s minutes" % (days, hours, minutes)
        number_of_gaps = len(gaps)
        print "number of power outages: %s" % number_of_gaps
        mysum = 0L
        if number_of_gaps > 0:
            for k,v in gaps.iteritems():
                mysum += v
            average_seconds = mysum / float(number_of_gaps)
            (days, hours, minutes) = self.dhm_from_seconds(average_seconds)
            print "average length of outage: %s days %s hours %s minutes" % \
                                (days, hours,minutes)
            gap_length_list = []
            temp_list = []
# up to this point, all the keys (times) are in local, and the values are in seconds.here we'll change to UTC          
            for k,v in gaps.iteritems():
                utc_index = round(self.get_utc_tstamp_from_local_string(k))
                gap_length_list.append((utc_index,v))
                temp_list.append((utc_index,v))
            gap_list = sorted(gap_length_list, key=lambda x:x[1])
            power_list = sorted(temp_list)
            """
            for item, value in power_list:
                print item, value
            """
            shortest_gap = gap_list[0][1]
            if shortest_gap < 60:
                print "shortest outage: %s seconds " % (shortest_gap)
            else:
                (days, hours, minutes) = self.dhm_from_seconds(shortest_gap)
                print "shortest outage: %s days %s hours %s minutes " % \
                            (days, hours, minutes,)
            longest_gap = gap_list[-1][1]
            (days, hours, minutes) = self.dhm_from_seconds(longest_gap)
            print "longest outage: %s days %s hours %s minutes " % \
                                            (days,hours, minutes,)
            average_per_day = (1 - float(mysum)/total_seconds) * 24
            print("Average power within 24 hours:%2.2f hours"%average_per_day)

            print "\n\nDISTRUBUTION OF POWER OVER THE DAY"
            buckets = []

            """divide up the total time into 15 minute chunks and distribute
            X's across the 96 columns of a day for each chunk that has power"""

           # first get the offset of the first entry from midnight
            firstdt = self.get_datetime(first)
            first_midnight_local = self.get_datetime(first) - datetime.timedelta(\
                    hours=firstdt.hour,minutes=firstdt.minute, seconds=firstdt.second)
            # lets do all the time in seconds since 1970 (tstamp) and in UTC
            midnight = self.format_datetime(first_midnight_local)
            print("midnight should be:%s"%midnight)
            first_midnight_seconds = self.get_utc_tstamp_from_local_string(midnight)
            last_seconds = self.get_utc_tstamp_from_local_string(last)
            current_bucket_seconds = first_midnight_seconds
            current_power_state = False  # we backtracked from the time when the monitor was enabled
            key_index = 0
            power_on_seconds = self.get_utc_tstamp_from_local_string(first)
            power_off_seconds = power_on_seconds + power_list[0][1] 
            seconds_in_day = 24.0 * 60 * 60
            seconds_in_current_day = 1000
            bucket_size = 60 * 15.0
            
            """
            for k,v in ts_list:
                print("key:%s, string:%s, value:%s"%(k,self.ts2str(k), v,))
            print("Before loop begins: on:%s, off:%s,bucket_seconds:%s"%(\
                self.ts2str(power_on_seconds),self.ts2str(power_off_seconds),\
                self.ts2str(current_bucket_seconds),))
            """
            graph = True
            buckets = []
            for j in range(96):
                buckets.append(0)
            while current_bucket_seconds < last_seconds:
                for index in range(len(ts_list)):
                    if ts_list[index][0] > current_bucket_seconds:
                        break
                    if ts_list[index][1] == "1":
                        current_power_state = True
                    else:
                        current_power_state = False
                if matrix:
                    if current_power_state:
                        sys.stdout.write("X")
                    else:
                        sys.stdout.write(" ")
                if graph:
                    bucket_index = int(seconds_in_current_day / bucket_size)
                    if current_power_state:
                        buckets[bucket_index] += 1


                current_bucket_seconds += bucket_size
                seconds_in_current_day = (current_bucket_seconds - first_midnight_seconds) % seconds_in_day
                if seconds_in_current_day < 10 and matrix:
                    print
            if graph:
# find the max of the buckets
                print("\nGraph")
                bucket_max = max(buckets)
                if debug:
                    print("bucket_max:%s"%bucket_max)
                for row in range(bucket_max - 1,-1,-1):
                    for i in range(96):
                        if row + 1 - buckets[i] <= 0:
                            sys.stdout.write("X")
                        else:
                            sys.stdout.write(" ")
                    print

            print "\n0   1   2   3   4   5   6   7   8   9   10  11  12  13  14  15  16  17  18  19  20  21  22  23"

            print("\nINDIVIDUAL POWER DISRUPTIONS:")
            for item, value in power_list:
                localts = item  + tzoffset
                localstr = self.ts2str(localts)
                (days, hours, minutes) = self.dhm_from_seconds(value)
                print "%s %s days %s hours and %s minutes" % \
                            (localstr, days, hours, minutes, )

    def output_state(self):
        if self.isenabled():
            state = "ENABLED"
        else:
            state = "DISABLED"
        print("")
        print("AC Power Monitor is currently %s"%state)

class CollectData(Tools):
    def __init__(self):
        global summary_dict
        if not self.is_exist_summary_file():
            # this is the first invocation of the AC logger
            self.write_summary()
        if not self.is_exist_data_file():
            # this is a startup after a reboot, or battery run down
            self.write_summary()
            self.put_data_file()

        # if the status of power has changed, record the new state
        last_summary_ac = self.last_summary_ac_state()
        #print("last_summary_ac: %s ac_status: %s"%(last_summary_ac,
                                        #self.get_ac_status()))
        if last_summary_ac != self.get_ac_status():
            self.write_summary()
        
        # record the current status
        self.write_current_ac_status()

        # check for battery exhaustion
        battery_pct = self.get_battery_percent()
        if debug:
            print("battery percent:%s"%battery_pct)
        if battery_pct < "25" and self.get_ac_status() != "1":
            # record the fact, and shutdown
            self.write_summary_key_value(self.format_datetime(datetime.datetime.now(tz)),
                                    "exhausted")
            cmd = "poweroff"
            self.cli(cmd)
            sys.exit(0)

class RawData(Tools):
    def __init__(self):
        global data_dict
        datafile_exists = False
        try:
            fd = file(DATA_FILE,'r')
            data_str = fd.read()
            data_dict = json.loads(data_str)
            fd.close()
            datafile_exists = True
        except IOError,e:
            logging.exception("failed to write data file. error:%s"% (e,))
            #raise AcException("Datafile read error in RawData")
        if datafile_exists:
            keylist = sorted(data_dict.keys())
            print "Current data file:"
            for item in keylist:
                print item, data_dict[item]
        print("Battery state percent:%s"%(self.get_battery_percent(),))

        global summary_dict
        name = self.get_summary_filename()
        if (len(name)>0):
            try:
                fsummary = file(name,'r')
                data_str = fsummary.read()
                summary_dict = json.loads(data_str)
            except IOError:
                raise AcException("Summaary file read error in init of RawData")
        keylist = sorted(summary_dict.keys())
        print "Summary file:"
        for item in keylist:
            print item, summary_dict[item]

if __name__ == "__main__":
    tls = Tools()
    try:
        tzfile = open("%s/timezone"%WORK_DIR, "r")
        timezone = tzfile.read()
        tzfile.close()
    except IOError:
        Print("could not set timezone")
        exit(1)
    print("Timezone is set to %s"%timezone)    
    local_ts = tls.tstamp(datetime.datetime.now(tz)) #returns local time
    tzoffset = time.time()-local_ts #time returns UTC
    matrix = False
    """
    print("tz offset in seconds:%s"%tzoffset)
    mystrnow = tls.format_datetime(datetime.datetime.now(tz))
    print("the string version of now:%s"%mystrnow)
    mydt = tls.get_datetime(mystrnow)
    myts = tls.tstamp(mydt)
    print("the timestamp is %s"%myts)
    print("The UTC timestame is %s"%time.time())
    print("returned by get_utc_from_string:%s"%tls.get_utc_tstamp_from_local_string(mystrnow))
    mynewstr = tls.ts2str(myts)
    print("and the final string is %s"%mynewstr)
    print("utc2local:%s"%UTC2LOCALSECONDS)
    dif = time.time()-myts
    print("the difference between local ts and utc is %s"%dif)
    print("the corrected version o string is %s"%tls.ts2str(myts))
    """
    if len(sys.argv) == 1:
        pi = ShowPowerHistory()
    elif (len(sys.argv )== 2):
        # if coming from cron, the check for an action to do
        if sys.argv[1] == '--timeout':
            print("environment value of TZ:%s"%os.environ["TZ"])
            pa = CollectData()
        # dump the data in understandable form
        if sys.argv[1] == '--debug':
            debug = True
            matrix = True
            pa = RawData()
            pi = ShowPowerHistory()
            matrix = False
            debug = False
        if sys.argv[1] == '--delete':
            tools = Tools()
            tools.disable()
            tools.delete()
        if sys.argv[1] == '--enable':
            tools = Tools()
            tools.enable()
        if sys.argv[1] == '--disable':
            tools = Tools()
            tools.disable()
            sys.exit(0)

    # pop up the GUI
    #Gtk.main()
    sys.exit(0)
