#! /bin/env python

from SmokerLog.Utils import *
from SmokerLog.Units import *
from SmokerLog.TempLogger import *
from SmokerLog.TempPlotter import *
from SmokerLog.DataSources.StokerWebSource import *

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
import inspect







# a class for getting user input.
# we need to create a class so we can put the object in its own thread
class InputReader(QtCore.QObject):
  input_available = QtCore.Signal( str )
  
  def __init__(self):
    super(InputReader,self).__init__()

    # configure the readline library
    readline.parse_and_bind('tab: complete')
    readline.parse_and_bind('set editing-mode vi') # most important option. allows vi style command line editing

  def read_input(self):
    logging.debug("reading input from user")
    input = raw_input('smokerlog> ')
    self.input_available.emit( input )





class Main(QtCore.QObject):
  finished = QtCore.Signal()
  started = QtCore.Signal()

  trigger_input_read = QtCore.Signal()
  trigger_temp_reading = QtCore.Signal()

  def set_default_config(self):
    pass

  def __init__(self,argv):
    super(Main,self).__init__()
    # parse the command line
    mainargparser = argparse.ArgumentParser()
    mainargparser.add_argument("--host"           ,default="192.168.1.3" )
    mainargparser.add_argument("--read_interval"  ,default="1. min")
    mainargparser.add_argument("--debug"          ,default=False, action='store_true')

    args = mainargparser.parse_args(args = argv[1:])

    # set configuration options
    self.config = PyOptionTree()
    
    self.config.set( "data/source"                  , args.host                                                    )
    self.config.set( "templogger/read_interval"     , args.read_interval                                           )
    self.config.set( "templogger/cache_buffer_size" , 10                                                           )
    self.config.set( "app/log/filename"             , "SmokerLog.log"                                              )
    self.config.set( "app/log/level"                , logging.DEBUG if args.debug else logging.INFO                )
    self.config.set( "app/log/format"               , '[%(levelname)s] (%(threadName)s) %(asctime)s - %(message)s' )

    # configure logger
    logging.basicConfig(filename=self.config.get("app/log/filename")
                       ,level   =self.config.get("app/log/level"   )
                       , format =self.config.get("app/log/format"  )
                       )



#          _                 _                   _                        _           
# ___  ___| |_ _   _ _ __   (_)_ __  _ __  _   _| |_   _ __ ___  __ _  __| | ___ _ __ 
#/ __|/ _ \ __| | | | '_ \  | | '_ \| '_ \| | | | __| | '__/ _ \/ _` |/ _` |/ _ \ '__|
#\__ \  __/ |_| |_| | |_) | | | | | | |_) | |_| | |_  | | |  __/ (_| | (_| |  __/ |   
#|___/\___|\__|\__,_| .__/  |_|_| |_| .__/ \__,_|\__| |_|  \___|\__,_|\__,_|\___|_|   
#                   |_|             |_|                                               

    self.inputreader = InputReader()                                 # create the input reader
    self.inputreader.input_available.connect( self.process_command ) # connect input reader to the command processor

    self.input_thread = QtCore.QThread(self)                         # create a thread to run the input reader to run in
    self.inputreader.moveToThread( self.input_thread )               # move the logger to the thread
    self.trigger_input_read.connect( self.inputreader.read_input )   # connect the thread's start signal to the input readers command prompt loop
    self.finished.connect( self.input_thread.quit )                  # connect our finish signal to the threads quit slot so the thread will be terminated when quit



#          _                 _                             
# ___  ___| |_ _   _ _ __   | | ___   __ _  __ _  ___ _ __ 
#/ __|/ _ \ __| | | | '_ \  | |/ _ \ / _` |/ _` |/ _ \ '__|
#\__ \  __/ |_| |_| | |_) | | | (_) | (_| | (_| |  __/ |   
#|___/\___|\__|\__,_| .__/  |_|\___/ \__, |\__, |\___|_|   
#                   |_|              |___/ |___/           

    # create the data source
    if args.debug:
      #datasource = DataSource( )
      datasource = IntermittentDataSource( )
    else:
      datasource = StokerWebSource( self.config.get("data/source") )
    # the temperature logger
    self.templogger = TempLogger( datasource, self.config( "templogger" ) )


    self.templog_thread = QtCore.QThread(self)
    self.templogger.moveToThread( self.templog_thread )
    self.trigger_temp_reading.connect( self.templogger.start_reading )
    self.finished.connect( self.templog_thread.quit )


#          _                       _       _   _            
# ___  ___| |_ _   _ _ __    _ __ | | ___ | |_| |_ ___ _ __ 
#/ __|/ _ \ __| | | | '_ \  | '_ \| |/ _ \| __| __/ _ \ '__|
#\__ \  __/ |_| |_| | |_) | | |_) | | (_) | |_| ||  __/ |   
#|___/\___|\__|\__,_| .__/  | .__/|_|\___/ \__|\__\___|_|   
#                   |_|     |_|                             


    # the temperature plotter
    self.plot = TempPlotter()
    self.templogger.new_data_read.connect( self.plot.append_to_data )



  def run(self):

    # we are creating a loop here, but it is not immediatly obvious how.
    # in order to keep the user console from blocking the main event loop, we
    # need to have it run in its own thread. so, we will create an instance of the
    # InputReader class and move it to a thread.
    # 
    # we could have the input reader just run a loop to get user input and emit signals
    # with each input. however, this will cause problems with how the prompt is displayed becasue
    # user commands will print to the console as well.
    #
    # instead, we will put the input reader into its own thread and then call the read_input member.
    # this member will wait for user input, then emit a singnal when some is recieved and return. (i.e. NOT loop)
    # we connect our process_command slot to the signal that is emitted to handle the input.
    # after the process_command function processes the data, it calls read_input member on the input reader.
    # 
    # the complication comes from the fact that we can't just call the read_input member, because functions
    # get ran in the thread of the caller. so, we instead have to emit a signal that will trigger the read_input
    # function to be ran. the signal will be recieved by the object and the member will be ran in the thread
    # that owns the object
    #
    # P.S. input reader and thread initialization has been moved to the constructor
    #
    # all righty then...


    # start reading data
    self.templog_thread.start()    # start temp logger
    self.trigger_temp_reading.emit()    # start reading data

    self.input_thread.start()    # start the user input thread
    self.process_command("help") # kick off the input loop by processing the "help" command



  def process_command(self,input):
    input = shlex.split(input)

    # don't do anything on blank input
    if len(input) < 1:
      self.trigger_input_read.emit()
      return

    # get command
    command = input.pop(0)
    # find the command (we support command abbreviations)
    candidates = filter( lambda x: re.match( "command_%s.*"%command, x) , dir(self) )

    if len( candidates ) > 1:
      print "'%s' is ambiguous" % command
      print "matching commands:"
      for command in candidates:
        print "\t%s" % command.replace("command_","")

      self.trigger_input_read.emit()
      return

    if len( candidates ) < 1:
      print "'%s' is not a recognized command." % command
      self.command_help()
      self.trigger_input_read.emit()
      return

    command = candidates[0]

    getattr( self, command)(*input)

    # read another command
    self.trigger_input_read.emit()
    return

                                                       
  
  def quit(self):
    self.finished.emit()
    # wait for threads to exit
    self.input_thread.wait()
    


  #                                               _     
  #  ___ ___  _ __ ___  _ __ ___   __ _ _ __   __| |___ 
  # / __/ _ \| '_ ` _ \| '_ ` _ \ / _` | '_ \ / _` / __|
  #| (_| (_) | | | | | | | | | | | (_| | | | | (_| \__ \
  # \___\___/|_| |_| |_|_| |_| |_|\__,_|_| |_|\__,_|___/


  def command_quit(self,*args):
    '''Quit the application, making sure that all threads have been cleaned up.'''
    logging.info( "shutting down..." )
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    self.templogger.read_timer.stop()
    self.quit()

  def command_log(self,*args):
    '''Log a string. The string is timestamped and written to file.'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    myargparser.add_argument("events", nargs="+")
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    for event in myargs.events:
      self.templogger.log_event(event)

  def command_plot(self,*args):
    '''Display an interactive plot of the recorded temperatures'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    self.plot.display()

  def command_status(self,*args):
    '''Print status information.'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    #print "Number of active threads: %d" % threading.active_count()
    print "user input thread: %s"        % (  "active" if self.input_thread.isRunning() else "inactive" )
    print "temp logger thread: %s"       % (  "active" if self.templog_thread.isRunning() else "inactive" )
    print "Run time: %s"                 % (datetime.datetime.now() - self.templogger.start)
    print "Last read time: %s"           % fmtEpoch( self.plot.getMaxTime(), self.plot.timefmt )
    self.templogger.print_status()

  def command_clear(self,*args):
    '''Clear all logged data. This will clear a plot.'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    self.templogger.clear()
    self.plot.clear()

  def command_stats(self,*args):
    '''Compute and print some statistics of the recoreded temperatures (avg, min, max, etc.)'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    stats = dict()

    def calc_stats(t,T):

      stats =  {}
      # we need to convert all calculations to float
      stats['domain']    = "%s - %s" % ( fmtEpoch( min( t), self.plot.timefmt ), fmtEpoch( max( t), self.plot.timefmt ) )
      stats['current']  = float(      T[-1])
      stats['max']      = float( max( T)   )
      stats['min']      = float( min( T)   )
      stats['avg']      = float( sum( T) / len( T ) )
      stats['stdev']    = float( math.sqrt( sum( (T - stats['avg'])**2 )/len( T ) ) )

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
    '''Print a data dump of the recorded data.'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    pprint.pprint( self.plot.data )

  def command_msg(self,*args):
    '''Print logged messages. For example, any debug messages that have been logged by the application.'''
    if len(args) < 1:
      args = ('all',)

    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return


    # get all logged messages
    with open( self.logfilename, 'r' ) as f:
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
    '''Set the value of a configuration option.'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    myargparser.add_argument("option" )
    myargparser.add_argument("value" )
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    logging.debug( "setting '%s' to '%s'" % ( myargs.option, myargs.value ) )

    self.config.set( myargs.option, myargs.value )

  def command_help(self,*args):
    '''This output.'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    commands = filter( lambda x: re.match( "command_.*", x) , dir(self) )
    print "commands:"
    for command in sorted(commands):
      print "\t%s - %s" % ( command.replace("command_",""), getattr(self,command).__doc__ )


  def command_print(self,*args):
    '''Print the value of a configuration option or tree'''
    me  = inspect.stack()[0][3]
    cmd = me.replace("command_","")
    doc = getattr(self,me).__doc__
    myargparser = argparse.ArgumentParser(prog=cmd, description=doc)
    myargparser.add_argument("option", nargs="?", default="all" )
    try:
      myargs = myargparser.parse_args(args = args)
    except SystemExit:
      return

    if not self.config.isValid( myargs.option ) and myargs.option != "all":
      print "'%s' does not exist. Here is the config tree." % myargs.option
    print self.config.get( myargs.option, self.config )











if __name__ == '__main__':

  # create the main event loop
  # we can't use QCoreApplication here becasue pyqtgraph will be creating qt windows and widgets
  app = QtGui.QApplication(sys.argv)

  # create the main class
  main = Main(sys.argv)

  # connect our main class's finished signal to the event loop's exit function
  main.finished.connect( app.exit )

  # start running the main class 10 ms after event loop starts
  QtCore.QTimer.singleShot( 10, main.run )

  app.setQuitOnLastWindowClosed(False)
  
  sys.exit( app.exec_() )
