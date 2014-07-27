acpower
=======

A recorder of AC power, runs on XO1, installs on a developer-key enabled XO1 offline

How to install
==============
1. Start with a clean install of HaitiOS or the most recent XO operating system 13.2.1 available at 
   http://wiki.laptop.org/go/Release_notes/13.2.1#XO-1 (whichever is easier.  HaitiOS requires assembling a 
   number of pieces. 13.2.1 is a single download). Instructios for assembling HaitiOS can be found at 
   http://wiki.laptop.org/go/HaitiOS
2. Download the most recent acpower.zip from http://download.unleashkids.org/xsce/testing/acpower/. 
   Place the zip file in the root of a USB stick that has at least 120MB of free space, and run the command 
   "unzip acrecord\*.zip".  This will create a number of subdirecties.
#. Set the time zonel. Go back to the spiral desktop. (right click on XO,left click on "My Settings",left 
   click on "date and Time", then highlight your time zone, click the check mark. You will be asked to reboot.
#. Verify that the internal clock is set correctly by typing *date* in terminal. If not use the following two commands::

       date \<mmddhhssyyyy\> to set the software version of the clock
       hwclock --systohc to set the hardware from the software version
#. Then, if it were me, I'd reboot, and verify that the software date is properly being set by the hardware.
#. To install the ACPower Recorder, you must have an unlocked XO. See http://wiki.laptop.org/go/Activation_and_developer_keys#Getting_a_developer_key. (To determine if the
   security is on or off, power on the XO, and immediately press the esc --upper left corner--.  If you get an "ok" prompt,
   the security is disabled).
#. If you need to disable security, see http://wiki.laptop.org/go/Activation_and_developer_keys#Getting_a_developer_key. 
#. XO1 laptops that have been stored for a long time may fail to boot properly due to the internal Real Time Clock (RTC) being
   incorect. Refer to http://wiki.laptop.org/go/Fix_Clock
#. Actual installation of the ACPower software is easy, once the pre-requisites are completed. Just insert the USB stick
   that you created into the XO.  Turn the power off, and then turn it on again.  You will get a mesage on the screen 
   confirming that the software has been installed.
#. Then remove the USB stick, and reboot the machine
#. Test for success by unplugging the power adapter, turning off the XO, and then plugging the adapter back in. It 
   should turn on immediately when power is restored.

Using ACPOWER
=============
 
Plug the XO into the AC power you want to record.  The software will record the time when the power goes on and off.  If it goes off for longer than a few hours, the XO's battery will become exhausted, and the screen will go blank.

When the AC power returns, the XO will turn on again.

At a terminal command line, type "acpower". The output will be similar to the following::


     SUMMARY OF AC POWER DURING PERIOD: 2014/07/23 to 2014/07/26:

 length of log 2 days, 10 hours, 7 minutes
 number of power outages: 4
 average length of outage: 0.0 days 7.0 hours 52.0 minutes
 shortest outage: 0 days 0 hours 16 minutes 
 longest outage: 0 days 10 hours 23 minutes 
 Average power within 24 hours:13.01 hours


 DISTRUBUTION OF POWER OVER THE DAY

 Bar Graph
                                                                                       X        
                        XXXXXXXXXXXXXXXXXXXXXX                                        XXXXX      
 XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX                   XXXXXXXXXXXXXXXXXXXXXXXXXXXXX

 0   1   2   3   4   5   6   7   8   9   10  11  12  13  14  15  16  17  18  19  20  21  22  23

The first block provides some statistics about the AC power record.

The second block shows a Bar Graph, where the height of the bar shows how many times the power was on in that 15 minute 
segment of the day.
There are options which can be used to summarize just a limited subset of the log. There is a help/usage screen
which is available by typing 

   *acpower -h*

usage: acpower [-h] [-n] [-d] [-s START] [-e END] [-p] [-v]

Summarize AC Grid pwrlogs

optional arguments:
  -h, --help            show this help message and exit
  -n, --newlog          ignore log accumulated before now
  -d, --daily           show power by day and hour
  -s START, --start START
                        start report this dd/mm/yy
  -e END, --end END     end report this dd/mm/yy
  -p, --powersegments   list individual power details
  -v, --verbose         show debugging information

The -d --daily option shows an x-y scattergram with days growing down, and hours spreading across. The scattergram which generated the above bar chart looks like::

 One line per day. Current day: 2014/07/23
                                                                                     XXXXXXXXXXX
 XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX                                          XXX      
                        XXXXXXXXXXXXXXXXXXXXXXXXX                   XXXXXXXXXXXXXXXXXXXXX        
                            

The -p option will list the details of each segment of available power::

 INDIVIDUAL POWER PERIODS:
 2014/07/23-20:41:18- 0 days 0 hours and 3 minutes
 2014/07/23-21:00:37- 0 days 14 hours and 12 minutes
 2014/07/24-21:37:04- 0 days 0 hours and 47 minutes
 2014/07/25-05:41:53- 0 days 6 hours and 5 minutes
 2014/07/25-16:31:16- 0 days 5 hours and 28 minutes


If you want to record the listing, and send it via email, or print it, you can redirect the output from the screen to a file, and then copy that file to a USB stick.

        - Use "df -h" to see the path associated with your USB stick (Usually it is /run/media/olpc/<USB stick label>
        - Redirect the ouptup of the *acpower* to a file :
          
           *acpower > /run/media/olpc/1838-1234/mypowersummary*

        - Take the USB stick to an internet connected computer and email the report. or
        - Put the USB stick in a computer that is connected to a printer, open the file in a text editor, and print it.

For the hackers, please note that the ACPower zip file is actually generated as a mktinycorexo xo-client, and the code resides at: https://github.com/georgejhunt/mktinycorexo/tree/acpower/xo-client as a branch off of that cloned repo.  The original git repo is at http://dev/laptop.org/git/user/quozl/mktinycorexo
