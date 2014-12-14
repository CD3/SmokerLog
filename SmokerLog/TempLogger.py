
from .Units import *
from .Utils import *

import datetime
import time
import threading

import logging
import collections


class TempLogger(QtCore.QObject): # we inherit from QObject so we can emit signals
  new_data_read = QtCore.Signal( dict )
  timefmt = "%Y-%m-%d %H:%M:%S"

  def set_config_defaults(self):
    defaults = { "prefix" : "default"
               , "read_interval" : "1. min"
               , "cache_buffer_size" : 10
               }

    for opt in defaults:
      self.config.set( opt, self.config.get( opt, defaults[opt] ) )


  def __init__(self, source, config):
    super(TempLogger,self).__init__()
    logging.debug("constructing %s instance" % self.__class__.__name__)

    self.config = config
    self.set_config_defaults()

    # state information
    self.start = datetime.datetime.now()
    
    # data source
    self.data_source = source
    
    info = self.data_source.get_info()
    self.tempunits = info['tempunits']

    # read timer
    self.read_timer = QtCore.QTimer()
    self.read_timer.setInterval( unit(self.config.get("read_interval"),units.minute).to( units.millisecond ).magnitude )


    # data
    self.cache = collections.deque()

 
    # connect signals
    logging.debug("[%s] connecting signals/slots" % self.__class__.__name__)
    self.new_data_read.connect( self.append_to_cache )  # make sure data is appended to cache as it is read
    self.read_timer.timeout.connect( self.read )        # trigger a read on a regular basis


  def start_reading(self):
    logging.debug("starting read timer")
    self.read_timer.start()



  def read(self):
    logging.debug("retrieving data from source")
    btime = datetime.datetime.now()
    temps = self.data_source.get_data()
    if temps == None:
      logging.debug("Source returned None. Will try again later.")
      return
    logging.debug("recieved data")
    etime = datetime.datetime.now()

    data = { "time"    : etime.strftime( self.timefmt )
           , "sensors" : temps }



    self.new_data_read.emit( data )

  def write(self):
    logging.debug("Writing %d items in data cache to file." % len(self.cache))
    while len( self.cache ):
      item = self.cache.popleft()
      for (name,temp) in item["sensors"].items():
        filename = "%s-%s.txt" % (self.config.get("prefix"),name)
        with open( filename, 'a' ) as f:
          f.write( "%s %s\n" % (item["time"],temp) )

  def append_to_cache( self, data ):
    # the cache is used to write data to file
    logging.debug("appending data to cache")
    self.cache.append(data)
    if len( self.cache ) >= int( self.config.get("cache_buffer_size") ):
      self.write()

  def log_event(self, event, time = None):
    if time is None:
      time = datetime.datetime.now()
    filename = "%s-%s.txt" % (self.config.get("prefix"),"eventLog")
    with open( filename, 'a' ) as f:
      f.write( "%s '%s'\n" % (str(time),event) )

  def print_status(self):
    print "data source: %s" % self.data_source
    print "read interval: %s" % unit(self.config.get("read_interval") )

  def clear(self):
    self.cache.clear()

    
