
from .Units import *

import datetime
import time
import threading

import logging
import collections


class TempLogger(QtCore.QObject): # we inherit from QObject so we can emit signals
  new_data_read = QtCore.Signal( dict )
  timefmt = "%Y-%m-%d %H:%M:%S"

  def __init__(self, source, prefix = "default", read_interval = 1.*units.min, write_interval = 1.*units.min):
    super(TempLogger,self).__init__()
    logging.debug("constructing %s instance" % self.__class__.__name__)

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
    logging.debug("[%s] connecting signals/slots" % self.__class__.__name__)
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
    print "APPEND"
    # the cache is used to write data to file
    logging.debug("appending data to cache")
    self.cache.append(data)

  def print_status(self):
    print "data source: %s" % self.data_source
    print "read interval: %s" % self.read_interval
    print "write interval: %s" % self.write_interval

  def clear(self):
    self.cache.clear()
    
