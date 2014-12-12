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




class DataSource:
  def get_data(self):
    '''Returns an ordered dict of temperature keyed on the sensor/probe name'''
    return collections.OrderedDict( [ ('sens1', 80), ('sens2', 87) ] )

  def get_info(self):
    info = {'tempunits' : 'F' }
    return info

class IntermittentDataSource(DataSource):
  iter = 0
  def get_data(self):
    self.iter += 1
    if (self.iter%3) == 0: # drop every 3rd data
      return None

    return collections.OrderedDict( [ ('sens1', 30 + self.iter*2.), ('sens2', 40 + self.iter*1.1) ] )

  def get_info(self):
    info = {'tempunits' : 'F' }
    return info

class StokerWebSource( DataSource ):
  def __init__(self, host):

    # html scraper
    self.host = host
    self.parser = etree.HTMLParser()
    self.url = "http://%(host)s" % {'host': self.host}
    self.timeout = 5*units.second


  def get_data(self):
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
      return None

    except Exception, e:
      logging.debug( "Exception occured while requesting data: '%s'" % e.message )
      logging.debug( "Will try again later")
      return None


    tree   = etree.parse( StringIO(html), self.parser )
    (sysinfo_table, data_table, trash, trash) = tree.xpath("body/table/form/tr")

    status = SystemInfo( sysinfo_table )
    sensors = list()
    rows = data_table.xpath("td/table/tr")
    for i in range(4,len(rows)-1):
      sensors.append( Sensor( rows[i] ) )

    data = collections.OrderedDict()
    for sensor in sensors:
      data[sensor.name] = sensor.temp

    return data




# functions


def epoch2humanTime( t ):
  return datetime.datetime( *time.localtime( t )[0:5] ).strftime( TempPlot.timefmt )



# classes

class TempPlot(QtCore.QObject): # we inherit from QObject so we can emit signals

  data_changed = QtCore.Signal( )
  timefmt = "%H:%M:%S"


  def __init__(self, **kargs):
    super(TempPlot,self).__init__()

    # configuration options
    self.do_pickle_data = True
    self.data_pickle_filename = ".TempLogger.plotdata.pickle"
    self.tempunits = "F"
    self.colors = [ 'r', 'b', 'g', 'y' ]

    if os.path.isfile( self.data_pickle_filename ):
      logging.info("pickled plot data exists, loading now")
      self.data = pickle.load( open( self.data_pickle_filename, "rb" ) )
    else:
      self.init_data()

    if self.do_pickle_data:
      self.data_changed.connect( self.pickle_data )








  def display(self):

    # create the plot window and set it's title
    self.plotwin = pg.GraphicsWindow()
    self.plotwin.setWindowTitle("Temperature Logs")

    # add items to window.
    # put a label at the top to display coordinates
    self.zCoordsLabel = pg.LabelItem(justify='right')
    self.zCoordsLabel.setText( "(0,0)", row = 0, col = 0 )


    # add plots to the window
    self.plotwin.addItem( self.zCoordsLabel )
    # zoom window
    self.zplot = self.plotwin.addPlot( row=1, col=0 )

    self.zplot.addLegend()


    # region window
    self.rplot = self.plotwin.addPlot( row=3, col=0 )

    # configure the axises (labels and tics)
    axis = self.zplot.getAxis('bottom')
    axis.setLabel("time")
    # swap out the bottom axis tickStrings function so it will display the date corrrectly
    def dateTickStrings(self, values, scale, spacing):
        # PySide's QTime() initialiser fails miserably and dismisses args/kwargs
        # times will be in number of seconds since...
        # need to convert this to a tuple, create a datetime object, and output it in the correct format
        return [ epoch2humanTime( value ) for value in values]


    axis.tickStrings = types.MethodType( dateTickStrings, axis )
    axis = self.zplot.getAxis('left')
    axis.setLabel("temperature (%s)" % self.tempunits)

    axis = self.rplot.getAxis('bottom')
    axis.setLabel("time")
    axis.tickStrings = types.MethodType( dateTickStrings, axis )
    axis = self.rplot.getAxis('left')
    axis.setLabel("temperature (%s)" % self.tempunits)



    # ad a text item to display current temperatures
    self.tempDispHeader = '<div style="text-align: left"><span style="color: #FFF;">Current Temps</span></div>'
    self.tempDisp = pg.TextItem( html=self.tempDispHeader, anchor=(1,0) )
    self.rplot.addItem( self.tempDisp )



    # add cross hair to the zoom plot
    self.crosshair = dict()
    self.crosshair['v'] = pg.InfiniteLine(angle=90, movable=False)
    self.crosshair['h'] = pg.InfiniteLine(angle=0 , movable=False)
    self.zplot.addItem( self.crosshair['v'], ignoreBounds=True )
    self.zplot.addItem( self.crosshair['h'], ignoreBounds=True )

    def mouseMoved(evt):
      # slot to update the crosshairs
      pos = evt
      if self.zplot.sceneBoundingRect().contains(pos):
          mousePoint = self.zplot.vb.mapSceneToView(pos)
          index = int(mousePoint.x())

          self.zCoordsLabel.setText( "(%(x)s, %(y).1f)" % {'x' : epoch2humanTime( mousePoint.x() ), 'y' : mousePoint.y()}  )

          self.crosshair['v'].setPos(mousePoint.x())
          self.crosshair['h'].setPos(mousePoint.y())




    # add region to the region plot
    self.plotregion = pg.LinearRegionItem()
    self.plotregion.setZValue(100) # make sure region gets displayed on top
    self.rplot.addItem( self.plotregion, ignoreBounds=True )
    self.rplot.setAutoVisible(y=True)

    self.plotregion.setRegion( [self.getMinTime(), self.getMaxTime()] )

    def updateZoomPlot():
      # slot to update zoom plot range when region is changed
      self.plotregion.setZValue(100)
      mint,maxt = self.plotregion.getRegion()
      self.zplot.setXRange( mint, maxt, padding=0 )

    def updateRegion(wind, viewRange):
      # slot to update the region when zoom plot range changes
      self.plotregion.setRegion( viewRange[0] )






    # initialize the list of plot curves (actually, it is a dict)
    self.plotcurves = {}

    # connect signals
    self.zplot.scene().sigMouseMoved.connect(mouseMoved)
    self.data_changed.connect( self.plot )
    self.plotregion.sigRegionChanged.connect( updateZoomPlot )
    self.zplot.sigRangeChanged.connect( updateRegion )

    # emit signal that will cause plot to update
    self.data_changed.emit()




  def append_to_data( self, data ):
    # data contains all of the time-temperature history data points that will be
    # plotted. we store a seprate time-temperature pair for every sensor.
    t = datetime.datetime.strptime( data["time"], TempLogger.timefmt )
    for name in data["sensors"]:
      if not name in self.data:
        self.data[name] = { 't' : numpy.array([]), 'T' : numpy.array([]) }

      self.data[name]['t'] = numpy.append( self.data[name]['t'], time.mktime( t.timetuple() ) )
      self.data[name]['T'] = numpy.append( self.data[name]['T'], data["sensors"][name] )

    self.data_changed.emit()


  def plot(self):
    i = 0
    N = len( self.data )


    for name in self.data:
      if name not in self.plotcurves:
        self.plotcurves[name] = dict()
        self.plotcurves[name]['region'] = self.rplot.plot( name = name )
        self.plotcurves[name]['zoom']   = self.zplot.plot( name = name )

      self.plotcurves[name]['region'].setData(x = self.data[name]['t'], y = self.data[name]['T'], pen=pg.mkPen( self.colors[i] ) )
      self.plotcurves[name]['zoom'  ].setData(x = self.data[name]['t'], y = self.data[name]['T'], pen=pg.mkPen( self.colors[i] ) )
      i += 1

    self.drawCurrentTemps()

  def show(self):
    pass


  def drawCurrentTemps(self):
    view = self.rplot.viewRange()

    self.tempDisp.setPos( view[0][1], view[1][1] )

  def getMinTime(self):
    if len( self.data ) == 0:
      return 0
    else:
      return min( [ min(self.data[sensor]['t']) for sensor in self.data ] )

  def getMaxTime(self):
    if len( self.data ) == 0:
      return 0
    else:
      return max( [ max(self.data[sensor]['t']) for sensor in self.data ] )


  def pickle_data(self):
    pickle.dump( self.data, open( self.data_pickle_filename, "wb" ) )

  def clear(self):
    self.init_data()
    os.remove( self.data_pickle_filename )
  
  def init_data(self):
    self.data = collections.OrderedDict()

class TempLogger(QtCore.QObject): # we inherit from QObject so we can emit signals

  new_data_read = QtCore.Signal( dict )
  timefmt = "%Y-%m-%d %H:%M:%S"

  def __init__(self, source, prefix = "default", read_interval = 1.*units.min, write_interval = 1.*units.min):
    super(TempLogger,self).__init__()

    # state information
    self.start = datetime.datetime.now()
    
    # data source
    self.data_source = source
    
    info = self.data_source.get_info()
    self.tempunits = info['tempunits']

    # configuration
    self.prefix = prefix
    self.read_interval = read_interval
    self.read_stop = threading.Event()
    self.write_interval = write_interval
    self.write_stop = threading.Event()

    # data
    self.cache = collections.deque()

 
    # connect signals
    self.new_data_read.connect( self.append_to_cache )


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
    temps = self.data_source.get_data()
    if temps == None:
      return

    etime = datetime.datetime.now()

    data = { "time"    : etime.strftime( self.timefmt )
           , "sensors" : temps }

    self.new_data_read.emit( data )

  def write(self):
    logging.debug("Writing %d items in data cache to file." % len(self.cache))
    while len( self.cache ):
      item = self.cache.popleft()
      for (name,temp) in item["sensors"].items():
        filename = "%s-%s.txt" % (self.prefix,name)
        with open( filename, 'a' ) as f:
          f.write( "%s %s\n" % (item["time"],temp) )



  def log_event(self, event, time = None):
    if time is None:
      time = datetime.datetime.now()
    filename = "%s-%s.txt" % (self.prefix,"eventLog")
    with open( filename, 'a' ) as f:
      f.write( "%s '%s'\n" % (str(time),event) )

  def append_to_cache( self, data ):
    # the cache is used to write data to file
    self.cache.append(data)

  def print_status(self):
    print "data source: %s" % self.host
    print "read interval: %s" % self.read_interval
    print "write interval: %s" % self.write_interval

  def clear(self):
    self.cache.clear()
    










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
  plot.display()

def status(*args):
  print "Number of active threads: %d" % threading.active_count()
  print "Run time: %s"                 % (datetime.datetime.now() - templogger.start)
  print "Last read time: %s"           % epoch2humanTime( plot.getMaxTime() )
  templogger.print_status()

def clear(*args):
  templogger.clear()
  plot.clear()

def stats(*args):
  stats = dict()
  stats["Total"] = {}
  for sensor in plot.data:
    T = plot.data[sensor]['T']

    stats["Total"][sensor] = {}
    # we need to convert all calculations to float
    stats["Total"][sensor]['current']  = float( max( T) )
    stats["Total"][sensor]['max']      = float( max( T) )
    stats["Total"][sensor]['min']      = float( min( T) )
    stats["Total"][sensor]['avg']      = float( sum( T) / len( T ) )
    stats["Total"][sensor]['stdev']    = float( math.sqrt( sum( (T - stats["Total"][sensor]['avg'])**2 ) ) )

  print yaml.dump( stats, default_flow_style=False )


def dump(*args):
    pprint.pprint( plot.data )

commands = { "quit" : quit
           , "log"  : log
           , "plot"  : plot
           , "status"  : status
           , "clear"  : clear
           , "stats"  : stats
           , "dump"  : dump
           }






mainargparser = argparse.ArgumentParser()
mainargparser.add_argument("--host"           ,default="192.168.1.3" )
mainargparser.add_argument("--read_interval"  ,default=1.)
mainargparser.add_argument("--write_interval" ,default=1.)

args = mainargparser.parse_args(args = sys.argv[1:])



datasource = StokerWebSource( args.host )
#datasource = DataSource( )
#datasource = IntermittentDataSource( )
templogger = TempLogger( datasource
                       , read_interval  = float(args.read_interval)*units.min
                       , write_interval = float(args.write_interval)*units.min )

threads = [] 
threads.append( threading.Thread( target = templogger.read_loop ) )
threads.append( threading.Thread( target = templogger.write_loop ) )

plot = TempPlot()

templogger.new_data_read.connect( plot.append_to_data )

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




