#! /bin/env python

from SmokerLog.Utils import *
from SmokerLog.Units import *
from SmokerLog.TempLogger import *
from SmokerLog.TempPlotter import *
from SmokerLog.DataSources.StokerWebSource import *

import threading
import sys
import dpath.util
import argparse
import shlex
import os
import pprint
import numpy
import math
import yaml
import readline









class Main(QtCore.QObject):
  finished = QtCore.Signal()
  started = QtCore.Signal()

  def __init__(self,argv):
    super(Main,self).__init__()
    # parse the command line
    mainargparser = argparse.ArgumentParser()
    mainargparser.add_argument("--host"           ,default="192.168.1.3" )
    mainargparser.add_argument("--read_interval"  ,default=1.)
    mainargparser.add_argument("--debug"          ,default=False, action='store_true')

    args = mainargparser.parse_args(args = argv[1:])

    # set configuration options

    logfilename = "SmokerLog.log"

    if args.debug:
      loglevel = logging.DEBUG
    else:
      loglevel = logging.INFO


    # configure logger
    logging.basicConfig(filename=logfilename
                       ,level=loglevel
                       , format='[%(levelname)s] (%(threadName)s) %(asctime)s - %(message)s')



    # create the data source
    #datasource = StokerWebSource( args.host )
    #datasource = DataSource( )
    datasource = IntermittentDataSource( )
    # create the temperature logger
    self.templogger = TempLogger( datasource
                                , read_interval  = float(args.read_interval)*units.min )

    # create the temperature plotter
    self.plot = TempPlotter()

    # connect plot slot to logger signal so plot will be updated as new data is available
    self.templogger.new_data_read.connect( self.plot.append_to_data )


    # configure the readline library
    readline.parse_and_bind('tab: complete')
    readline.parse_and_bind('set editing-mode vi') # most important option. allows vi style command line editing

    # set the running flag to false
    self.running = False



  def run(self):
    # create a thread to run the logger in
    #readwrite_thread = QtCore.QThread()
    #readwrite_thread.start()
    ## move the logger to the thread
    #templogger.moveToThread( readwrite_thread )
    #readwrite_thread.finished.connect( app.quit )

    # start reading data
    self.templogger.start_reading()

    # start command prompt loop
    self.running = True
    while self.running:
      # get user input
      input = shlex.split( raw_input('> ') )

      # give new prompt if user not text was given
      if len(input) < 1:
        continue

      # get command
      command = input.pop(0)
      # find the command (we support command abbreviations)
      candidates = filter( lambda x: re.match( "command_%s.*"%command, x) , dir(self) )

      if len( candidates ) > 1:
        print "'%s' is ambiguous" % command
        print "matching commands:"
        for command in candidates:
          print "\t%s" % command.replace("command_","")

        continue

      if len( candidates ) < 1:
        print "'"+command+"' is not a recognized command."
        help()
        continue

      command = candidates[0]

      getattr( self, command)(*input)

    # make sure to emit the finished signal
    self.finished.emit()
                                                       


  #                                               _     
  #  ___ ___  _ __ ___  _ __ ___   __ _ _ __   __| |___ 
  # / __/ _ \| '_ ` _ \| '_ ` _ \ / _` | '_ \ / _` / __|
  #| (_| (_) | | | | | | | | | | | (_| | | | | (_| \__ \
  # \___\___/|_| |_| |_|_| |_| |_|\__,_|_| |_|\__,_|___/


  def command_quit(self,*args):
    logging.info( "shutting down..." )
    self.templogger.read_timer.stop()
    self.running = False

  def command_log(self,*args):
    for event in args:
      self.templogger.log_event(event)

  def command_plot(self,*args):
    self.plot.display()

  def command_status(self,*args):
    print "Number of active threads: %d" % threading.active_count()
    print "Run time: %s"                 % (datetime.datetime.now() - self.templogger.start)
    print "Last read time: %s"           % fmtEpoch( self.plot.getMaxTime(), self.plot.timefmt )
    self.templogger.print_status()

  def command_clear(self,*args):
    self.templogger.clear()
    self.plot.clear()

  def command_stats(self,*args):
    stats = dict()

    def calc_stats(t,T):
      stats =  {}
      # we need to convert all calculations to float
      stats['domain']    = "%s - %s" % ( fmtEpoch( min( t), self.plot.timefmt ), fmtEpoch( max( t), self.plot.timefmt ) )
      stats['current']  = float( max( T) )
      stats['max']      = float( max( T) )
      stats['min']      = float( min( T) )
      stats['avg']      = float( sum( T) / len( T ) )
      stats['stdev']    = float( math.sqrt( sum( (T - stats['avg'])**2 ) ) )

      return stats


    stats["Total"] = {}
    for sensor in self.plot.get_data():
      t = self.plot.data[sensor]['t']
      T = self.plot.data[sensor]['T']
      stats["Total"][sensor] = calc_stats( t, T )

    stats["Selected"] = {}
    
    region_data = self.plot.get_region_data()
    if region_data:
      for sensor in region_data:
        t = region_data[sensor]['t']
        T = region_data[sensor]['T']
        stats["Selected"][sensor] = calc_stats( t, T )


    print yaml.dump( stats, default_flow_style=False )

  def command_dump(self,*args):
      pprint.pprint( self.plot.data )

  def command_msg(self,*args):
    if len(args) < 1:
      args = ('all',)

    myargparser = argparse.ArgumentParser()
    myargparser.add_argument("type", default="all")
    myargs = myargparser.parse_args(args = args)

    # get all logged messages
    with open( logfilename, 'r' ) as f:
      msgs = dict()
      for line in f:
        line = line.strip()
        match = re.match("\[([a-zA-z]+)\]",line)
        if match:
          msgtype = match.group(1)
        else:
          msgtype = "UNKNOWN"
        
        msgtype = msgtype.lower()

        if not msgtype in msgs:
          msgs[msgtype] = []
        
        msgs[msgtype].append(line)

      
    # now show the ones the user wants to see
    if myargs.type == "all":
      msgtypes = msgs.keys()
    else:
      msgtypes = [args.type]

    for msgtype in msgtypes:
      if msgtype not in msgs:
        print "log file does not contain messages of type %s" % msgtype
        print "types found in log:"
        for tmp in msgs:
          print "\t%s" % tmp

      for line in msgs[msgtype]:
        print line

  def command_set(self,*args):
    myargparser = argparse.ArgumentParser()
    myargparser.add_argument("option" )
    myargs = myargparser.parse_args(args = args)

  def command_help(self,*args):
    commands = filter( lambda x: re.match( "command_.*", x) , dir(self) )
    print "commands:"
    for command in commands:
      print "\t%s" % command.replace("command_","")












if __name__ == '__main__':

  # create the main event loop
  app = QtCore.QCoreApplication([])

  # create the main class
  main = Main(sys.argv)
  main.finished.connect( app.exit )

  # start running the main class in 10 ms

  QtCore.QTimer.singleShot( 10, main.run )

  sys.exit( app.exec_() )
