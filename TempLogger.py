#! /bin/env python

from lxml import html, etree
from io import StringIO
import requests
import datetime
import time
import re
import pint
import threading
import collections
import signal
import sys
import dpath.util
import argparse
import shlex
import pyqtgraph as pg
import pyqtgraph.multiprocess as mp
import logging
import types
import pickle
import os
import numpy
import pprint
import math
import yaml

from PySide import QtCore

units = pint.UnitRegistry()
loglevel = logging.DEBUG

logging.basicConfig(filename='TempLogger.log',level=loglevel, format='[%(levelname)s] (%(threadName)s) %(asctime)s - %(message)s')

class DataExtractor:
  def __init__(self, elem = None):
    self.load(elem)
  def dump(self):
    print self.__dict__

class Sensor(DataExtractor):
  def load(self, elem):
    if elem is not None:
      cols = elem.xpath("td")

      # columns
      # 0 - serial number (plain text)
      # 1 - name          (input element)
      # 2 - temperature   (plain text)
      # 3 - target temp   (input element)
      # 4 - alarm         (select element)
      # 5 - low set       (input element)
      # 6 - high set      (input element)
      # 7 - blower        (select element)
      self.serial   =        cols[0].text.strip()
      self.name     =        cols[1].xpath("input")[0].get("value").strip()
      self.temp     = float( cols[2].text)
      self.target   = float( cols[3].xpath("input")[0].get("value") )

      self.low_set  = float( cols[5].xpath("input")[0].get("value") )
      self.high_set = float( cols[6].xpath("input")[0].get("value") )
      
    else:
      self.name = ""
      self.serial = ""
      self.temp = 0
      self.target = 0
      self.low_set = 0
      self.high_set = 0

class SystemInfo(DataExtractor):
  def load(self, elem):
    if elem is not None:
      self.system = "Stoker"
      info = elem.xpath("td/p")[0]

      self.version = info.xpath("br")[1].tail
      match = re.search( "(\d+\.*){1,4}", self.version )
      if match:
        self.version = match.group(0)
      
    else:
      self.version = ""

  def dump(self):
    print self.__dict__







def dateTickStrings(self, values, scale, spacing):
    # PySide's QTime() initialiser fails miserably and dismisses args/kwargs
    # times will be in number of seconds since...
    # need to convert this to a tuple, create a datetime object, and output it in the correct format
    return [datetime.datetime( *time.localtime( value )[0:5] ) for value in values]


class TempLogger(QtCore.QObject): # we inherit from QObject so we can emit signals
  new_data_read = QtCore.Signal( dict )
  plotdata_changed = QtCore.Signal( )
  timefmt = "%Y-%m-%d %H:%M:%S"

  def __init__(self, host, prefix = "default", read_interval = 1.*units.min, write_interval = 1.*units.min):
    super(TempLogger,self).__init__()

    # state information
    self.start = datetime.datetime.now()

    
    # html scraper
    self.parser = etree.HTMLParser()
    self.host = host
    self.url = "http://%(host)s" % {'host': self.host}
    self.timeout = 5*units.second

    # configuration
    self.prefix = prefix
    self.read_interval = read_interval
    self.read_stop = threading.Event()
    self.write_interval = write_interval
    self.write_stop = threading.Event()
    self.do_pickle_plotdata = True
    self.plotdata_pickle_filename = ".TempLogger.plotdata.pickle"




    # data
    self.cache = collections.deque()
    if os.path.isfile( self.plotdata_pickle_filename ):
      logging.info("pickled plotdata exists, loading now")
      self.plotdata = pickle.load( open( self.plotdata_pickle_filename, "rb" ) )
    else:
      self.init_plotdata()

 
    # connect signals
    self.new_data_read.connect( self.update_cache )
    self.new_data_read.connect( self.update_plotdata )

    if self.do_pickle_plotdata:
      self.plotdata_changed.connect( self.pickle_plotdata )






  def init_plotdata(self):
      self.plotdata = collections.OrderedDict()


  def read_loop(self):
    self.read_stop.clear()
    while not self.read_stop.is_set():
      self.read()
      self.read_stop.wait( self.read_interval.to( units.second ).magnitude )

  def write_loop(self):
    self.write_stop.clear()
    while not self.write_stop.is_set():
      self.write()
      self.write_stop.wait( self.write_interval.to( units.second ).magnitude )

  def stop_loops(self):
    self.read_stop.set()
    self.write_stop.set()



  def read(self):
    btime = datetime.datetime.now()
    try:
      logging.debug("Requesting data from host (url: %s)" % self.url)
      # get the status page
      page = requests.get(self.url, timeout=self.timeout.to(units.second).magnitude)
      # raise an exception for error codes
      page.raise_for_status()
      # get the raw html to parse
      html = page.text

    except requests.exceptions.Timeout, e:
      logging.debug( "Request timed out. Will try again later. If this keeps happening, check that the host is up.")
      return

    except Exception, e:
      logging.debug( "Exception occured while requesting data: '%s'" % e.message )
      logging.debug( "Will try again later")
      return

    etime = datetime.datetime.now()

    tree   = etree.parse( StringIO(html), self.parser )
    (sysinfo_table, data_table, trash, trash) = tree.xpath("body/table/form/tr")

    status = SystemInfo( sysinfo_table )
    sensors = list()
    rows = data_table.xpath("td/table/tr")
    for i in range(4,len(rows)-1):
      sensors.append( Sensor( rows[i] ) )

    data = { "time"    : etime.strftime( self.timefmt )
           , "sensors" : collections.OrderedDict() }

    for sensor in sensors:
      data["sensors"][sensor.name] = sensor.temp


    self.new_data_read.emit( data )

  def write(self):
    logging.debug("Writing %d items in data cache to file." % len(self.cache))
    while len( self.cache ):
      item = self.cache.popleft()
      for (name,temp) in item["sensors"].items():
        filename = "%s-%s.txt" % (self.prefix,name)
        with open( filename, 'a' ) as f:
          f.write( "%s %s\n" % (item["time"],temp) )

  def setup_plot(self):
    self.plotwin = pg.plot(title="Temperature Logs")
    self.plotwin.addLegend()
    axis = self.plotwin.getAxis('bottom')
    # swap out the bottom axis tickStrings function so it will display the date corrrectly
    axis.tickStrings = types.MethodType( dateTickStrings, axis )

    self.plotwin.getPlotItem().getAxis('bottom').setLabel("time")
    self.plotwin.getPlotItem().getAxis('left').setLabel("temperature (F)")

    self.plotcurves = {}
    self.plotdata_changed.connect( self.plot )
    self.plotdata_changed.emit()

  def teardown_plot(self):
    self.plotdata_changed.disconnect( self.plot )

  def plot(self):
    i = 0
    N = len( self.plotdata )
    for name in self.plotdata:
      i += 1
      if name not in self.plotcurves:
        self.plotcurves[name] = self.plotwin.plot( name = name )

      self.plotcurves[name].setData(x = self.plotdata[name]['t'], y = self.plotdata[name]['T'])
      self.plotcurves[name].setPen( (i,N) )

  def log_event(self, event, time = None):
    if time is None:
      time = datetime.datetime.now()
    filename = "%s-%s.txt" % (self.prefix,"eventLog")
    with open( filename, 'a' ) as f:
      f.write( "%s '%s'\n" % (str(time),event) )

  def update_cache( self, data ):
    # the cache is used to write data to file
    self.cache.append(data)

  def update_plotdata( self, data ):
    # plotdata contains all of the time-temperature history data points that will be
    # plotted. we store a seprate time-temperature pair for every sensor.
    t = datetime.datetime.strptime( data["time"], self.timefmt )
    for name in data["sensors"]:
      if not name in self.plotdata:
        self.plotdata[name] = { 't' : numpy.array([]), 'T' : numpy.array([]) }

      self.plotdata[name]['t'] = numpy.append( self.plotdata[name]['t'], time.mktime( t.timetuple() ) )
      self.plotdata[name]['T'] = numpy.append( self.plotdata[name]['T'], data["sensors"][name] )

    self.plotdata_changed.emit()

  def print_status(self):
    print "data source: %s" % self.host
    print "read interval: %s" % self.read_interval
    print "write interval: %s" % self.write_interval

  def pickle_plotdata(self):
    pickle.dump( self.plotdata, open( self.plotdata_pickle_filename, "wb" ) )

  def pickle_plotdata(self):
    pickle.dump( self.plotdata, open( self.plotdata_pickle_filename, "wb" ) )

  def clear(self):
    self.cache.clear()
    self.init_plotdata()
    os.remove( self.plotdata_pickle_filename )
    
 def get_stats(self, period = None ):
    if period == None:
      starti = 0
    else:
      pass

    stats = {}
    for sensor in self.plotdata:
      stats[sensor] = {}
      T = self.plotdata[sensor]['T']

      # we need to convert all calculations to float
      stats[sensor]['max']   = float( max( T[starti:]) )
      stats[sensor]['min']   = float( min( T[starti:]) )
      stats[sensor]['avg']   = float( sum( T[starti:]) / len( T[starti:] ) )
      stats[sensor]['stdev'] = float( math.sqrt( sum( (T[starti:] - stats[sensor]['avg'])**2 ) ) )


    return stats












# commands

def quit(*args):
  logging.info( "shutting down..." )
  templogger.stop_loops()
  templogger.write()
  sys.exit(0)

def log(*args):
  for event in args:
    templogger.log_event(event)

def plot(*args):
  templogger.setup_plot()

def status(*args):
  print "Number of active threads: %d" % threading.active_count()
  print "Run time: %s"                 % (datetime.datetime.now() - templogger.start)
  templogger.print_status()

def clear(*args):
  templogger.clear()

def stats(*args):
  statistics = templogger.get_stats()
  print yaml.dump( statistics, default_flow_style=False )

commands = { "quit" : quit
           , "log"  : log
           , "plot"  : plot
           , "status"  : status
           , "clear"  : clear
           , "stats"  : stats
           }






mainargparser = argparse.ArgumentParser()
mainargparser.add_argument("--host"           ,default="192.168.1.3" )
mainargparser.add_argument("--read_interval"  ,default=1.)
mainargparser.add_argument("--write_interval" ,default=1.)

args = mainargparser.parse_args(args = sys.argv[1:])



templogger = TempLogger( args.host
                   , read_interval  = float(args.read_interval)*units.min
                   , write_interval = float(args.write_interval)*units.min )

threads = [] 
threads.append( threading.Thread( target = templogger.read_loop ) )
threads.append( threading.Thread( target = templogger.write_loop ) )

for t in threads:
  t.start()



while 1:
  input = shlex.split( raw_input('> ') )
  if len(input) < 1:
    continue
  command = input.pop(0)
  candidates = dpath.util.search( commands, command+"*" )
  if len( candidates ) > 1:
    print "'"+command+"' is ambiguous (did you mean "+ ', '.join( candidates.keys() )
    continue

  if len( candidates ) < 1:
    print "'"+command+"' is not a recognized command."
    print "commands:"
    for command in commands.keys():
      print "\t",command
    continue

  command = candidates.keys()[0]

  commands[command](*input)




