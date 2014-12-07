#! /bin/env python

from lxml import html, etree
from io import StringIO
import requests
import datetime
import time
import re
import pint
import time
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


class Status(DataExtractor):
  def load(self, elem):
    if elem is not None:
      self.system = "Stoker"
      info = elem.xpath("td/p")[0]

      # columns
      # 0 - serial number (plain text)
      # 1 - name          (input element)
      # 2 - temperature   (plain text)
      # 3 - target temp   (input element)
      # 4 - alarm         (select element)
      # 5 - low set       (input element)
      # 6 - high set      (input element)
      # 7 - blower        (select element)

      self.version = info.xpath("br")[1].tail
      match = re.search( "(\d+\.*){1,4}", self.version )
      if match:
        self.version = match.group(0)
      
    else:
      self.version = ""

  def dump(self):
    print self.__dict__


class TempLogger:
  def __init__(self, host, prefix = "default", read_interval = 1.*units.min, write_interval = 1.*units.min, plot_interval=1.*units.min):
    self.parser = etree.HTMLParser()
    self.host = host
    #self.url = "http://%(host)s/index.html" % {'host': self.host}
    self.url = "http://%(host)s" % {'host': self.host}
    self.timeout = 5*units.second

    self.prefix = prefix

    self.read_interval = read_interval
    self.read_stop = threading.Event()
    self.write_interval = write_interval
    self.write_stop = threading.Event()
    self.plot_interval = plot_interval
    self.plot_stop = threading.Event()
    self.plot_thread = None

    self.cache = collections.deque()



    # get the process ready for plotting
    pg.mkQApp()
    self.plotproc = mp.QtProcess()
    self.rpg      = self.plotproc._import('pyqtgraph')


    self.plotdata = { "time" : self.plotproc.transfer([])
                    , "temps" : {} }



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

  def plot_loop(self):

    self.plot_stop.clear()
    while not self.plot_stop.is_set():
      self.plot()
      self.plot_stop.wait( self.plot_interval.to( units.second ).magnitude )

  def stop_loops(self):
    self.read_stop.set()
    self.write_stop.set()
    self.plot_stop.set()

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

    status = Status( sysinfo_table )
    sensors = list()
    rows = data_table.xpath("td/table/tr")
    for i in range(4,len(rows)-1):
      sensors.append( Sensor( rows[i] ) )

    data = { "time": str(etime)
           , "temps" : {} }
    for sensor in sensors:
      data["temps"][sensor.name] = sensor.temp


    # the cache is used to write data to file
    self.cache.append(data)

    # the plotdata is used to display a live plot of the temp curves
    self.plotdata['time'].append( time.mktime( etime.timetuple() ) / 60. ,_callSync='off' )
    for name in data["temps"]:
      if not name in self.plotdata["temps"]:
        self.plotdata["temps"][name] = self.plotproc.transfer([])

      self.plotdata["temps"][name].append( data["temps"][name], _callSync='off' )

  def write(self):
    logging.debug("Writing %d items in data cache to file." % len(self.cache))
    while len( self.cache ):
      item = self.cache.popleft()
      for (name,temp) in item["temps"].items():
        filename = "%s-%s.txt" % (self.prefix,name)
        with open( filename, 'a' ) as f:
          f.write( "%s %s\n" % (item["time"],temp) )

  def setup_plot(self):
    self.plotwin = self.rpg.plot()
    self.plotcurves = {}

  def plot(self):

    i = 0
    N = len( self.plotdata["temps"] )
    for name in self.plotdata["temps"]:
      i += 1
      if name not in self.plotcurves:
        self.plotcurves[name] = self.plotwin.plot()

      self.plotcurves[name].setData(x = self.plotdata['time'], y = self.plotdata['temps'][name], _callSync='off')
      self.plotcurves[name].setPen( (i,N) )

  def log_event(self, event, time = None):
    if time is None:
      time = datetime.datetime.now()
    filename = "%s-%s.txt" % (self.prefix,"eventLog")
    with open( filename, 'a' ) as f:
      f.write( "%s '%s'\n" % (str(time),event) )
    
  def print_status(self):
    print "data source: %s" % self.host



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
  if templogger.plot_thread == None:
    pass
  else:
    templogger.plot_stop.set()
    templogger.plot_thread.join()
    templogger.plot_thread = None


  templogger.plot_thread = threading.Thread( target = templogger.plot_loop )
  templogger.plot_thread.start()


def status(*args):
  print "Number of active threads: %d" % threading.active_count()
  templogger.print_status()

commands = { "quit" : quit
           , "log"  : log
           , "plot"  : plot
           , "status"  : status
           }



mainargparser = argparse.ArgumentParser()
mainargparser.add_argument("--host"           ,default="192.168.1.2" )
mainargparser.add_argument("--read_interval"  ,default=1.)
mainargparser.add_argument("--write_interval" ,default=1.)
mainargparser.add_argument("--plot_interval"  ,default=1.)

args = mainargparser.parse_args(args = sys.argv[1:])



templogger = TempLogger( args.host
                   , read_interval  = float(args.read_interval)*units.min
                   , write_interval = float(args.write_interval)*units.min
                   , plot_interval  = float(args.plot_interval)*units.min )

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




