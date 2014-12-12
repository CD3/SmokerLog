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







#                                               _     
#  ___ ___  _ __ ___  _ __ ___   __ _ _ __   __| |___ 
# / __/ _ \| '_ ` _ \| '_ ` _ \ / _` | '_ \ / _` / __|
#| (_| (_) | | | | | | | | | | | (_| | | | | (_| \__ \
# \___\___/|_| |_| |_|_| |_| |_|\__,_|_| |_|\__,_|___/
                                                     


def quit(*args):
  logging.info( "shutting down..." )
  templogger.stop_loops()
  templogger.write()
  sys.exit(0)

def log(*args):
  for event in args:
    templogger.log_event(event)

def plot(*args):
  plot.display()

def status(*args):
  print "Number of active threads: %d" % threading.active_count()
  print "Run time: %s"                 % (datetime.datetime.now() - templogger.start)
  print "Last read time: %s"           % fmtEpoch( plot.getMaxTime(), plot.timefmt )
  templogger.print_status()

def clear(*args):
  templogger.clear()
  plot.clear()

def stats(*args):
  stats = dict()

  def calc_stats(t,T):
    stats =  {}
    # we need to convert all calculations to float
    stats['domain']    = "%s - %s" % ( fmtEpoch( min( t), plot.timefmt ), fmtEpoch( max( t), plot.timefmt ) )
    stats['current']  = float( max( T) )
    stats['max']      = float( max( T) )
    stats['min']      = float( min( T) )
    stats['avg']      = float( sum( T) / len( T ) )
    stats['stdev']    = float( math.sqrt( sum( (T - stats['avg'])**2 ) ) )

    return stats


  stats["Total"] = {}
  for sensor in plot.get_data():
    t = plot.data[sensor]['t']
    T = plot.data[sensor]['T']
    stats["Total"][sensor] = calc_stats( t, T )

  stats["Selected"] = {}
  
  region_data = plot.get_region_data()
  if region_data:
    for sensor in region_data:
      t = region_data[sensor]['t']
      T = region_data[sensor]['T']
      stats["Selected"][sensor] = calc_stats( t, T )


  print yaml.dump( stats, default_flow_style=False )

def dump(*args):
    pprint.pprint( plot.data )

def msg(*args):
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

def set(*args):
  myargparser = argparse.ArgumentParser()
  myargparser.add_argument("option" )
  myargs = myargparser.parse_args(args = args)

def help(*args):
  print "commands:"
  for command in commands.keys():
    print "\t",command





commands = { "quit":   {'func' : quit }
           , "log":    {'func' : log }
           , "plot":   {'func' : plot }
           , "status": {'func' : status }
           , "clear":  {'func' : clear }
           , "stats":  {'func' : stats }
           , "dump":   {'func' : dump }
           , "msg":    {'func' : msg }
           , "help":   {'func' : help }
           }










if __name__ == '__main__':

  # parse the command line
  mainargparser = argparse.ArgumentParser()
  mainargparser.add_argument("--host"           ,default="192.168.1.3" )
  mainargparser.add_argument("--read_interval"  ,default=1.)
  mainargparser.add_argument("--write_interval" ,default=1.)
  mainargparser.add_argument("--debug"          ,default=False, action='store_true')

  args = mainargparser.parse_args(args = sys.argv[1:])

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
  templogger = TempLogger( datasource
                         , read_interval  = float(args.read_interval)*units.min
                         , write_interval = float(args.write_interval)*units.min )

  # create the temperature plotter
  plot = TempPlotter()

  # connect plot slot to logger signal so plot will be updated as new data is available
  templogger.new_data_read.connect( plot.append_to_data )

  # create threads to run read and write loops of the temperature logger

  threads = [] 
  #threads.append( threading.Thread( target = templogger.read_loop ) )
  #threads.append( threading.Thread( target = templogger.write_loop ) )
  for t in threads:
    t.start()


  # configure the readline library
  readline.parse_and_bind('tab: complete')
  readline.parse_and_bind('set editing-mode vi') # most important option. allows vi style command line editing

  # start command prompt loop
  while 1:
    # get user input
    input = shlex.split( raw_input('> ') )

    # give new prompt if user not text was given
    if len(input) < 1:
      continue

    # get command
    command = input.pop(0)
    # find the command (we support command abbreviations)
    candidates = dpath.util.search( commands, command+"*" )
    if len( candidates ) > 1:
      print "'"+command+"' is ambiguous (did you mean "+ ', '.join( candidates.keys() )
      continue

    if len( candidates ) < 1:
      print "'"+command+"' is not a recognized command."
      help()
      continue

    command = candidates.keys()[0]

    commands[command]['func'](*input)




