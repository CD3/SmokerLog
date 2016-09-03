
from .Units import *
from .Utils import *
from TempLogger import TempLogger

import pyqtgraph as pg
import logging
import pickle
import numpy
import types
import os
import collections
import datetime


class TempPlotter(QtCore.QObject): # we inherit from QObject so we can emit signals
  data_changed = QtCore.Signal( )
  timefmt = "%H:%M:%S"

  def set_config_defaults(self):
    defaults = { "pickle/enabled" : True
               , "pickle/filename" : ".TempPlotter.data.pickle"
               , "temperature/units" : "F"
               , "temperature/display/template" : '<div style="text-align: left"><span style="color: white;">Current Temps</span><br>%(temps)s</br></div>'
               , "plot/colors/0" : 'red'
               , "plot/colors/1" : 'blue'
               , "plot/colors/2" : 'green'
               , "plot/colors/3" : 'yellow'
               }
    for opt in defaults:
      self.config.set( opt, self.config.get( opt, defaults[opt] ) )

  def __init__(self, config = PyOptionTree() ):
    super(TempPlotter,self).__init__()
    logging.debug("constructing "+self.__class__.__name__+" instance")

    self.config = config
    self.set_config_defaults()

    # initialize data
    if os.path.isfile( self.config.get("pickle/filename") ):
      logging.debug("pickled plot data exists, loading now")
      self.data = pickle.load( open( self.config.get("pickle/filename"), "rb" ) )
    else:
      logging.debug("no pickled data found (didn't find '%s'), initializing data" % self.config.get("pickle/filename") )
      self.init_data()






    logging.debug("[%s] connecting signals/slots" % self.__class__.__name__)
    if self.config.get( "pickle/enabled" ):
      self.data_changed.connect( self.pickle_data )


    # declare attributes we will use in the methods
    self.plotregion = None




  def get_data(self):
    return self.data

  def get_region_data(self):
    if self.plotregion == None:
      return None

    regioned_data = collections.OrderedDict()
    mint,maxt = self.plotregion.getRegion()
    for sensor in self.data:
      mini = numpy.searchsorted( self.data[sensor]['t'], mint )
      maxi = numpy.searchsorted( self.data[sensor]['t'], maxt )
      regioned_data[sensor] = { 't' : self.data[sensor]['t'][mini:maxi]
                              , 'T' : self.data[sensor]['T'][mini:maxi] }

    return regioned_data




  def display(self):

    logging.debug( "setting up plot window for display" )
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
        return [ fmtEpoch( value, TempPlotter.timefmt ) for value in values]


    axis.tickStrings = types.MethodType( dateTickStrings, axis )
    axis = self.zplot.getAxis('left')
    axis.setLabel("temperature (%s)" % self.config.get("temperature/units"))

    axis = self.rplot.getAxis('bottom')
    axis.setLabel("time")
    axis.tickStrings = types.MethodType( dateTickStrings, axis )
    axis = self.rplot.getAxis('left')
    axis.setLabel("temperature (%s)" % self.config.get("temperature/units"))



    # ad a text item to display current temperatures
    text = self.config.get("temperature/display/template")
    self.tempDisp = pg.TextItem( html=text, anchor=(1,0) )
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

          self.zCoordsLabel.setText( "(%(x)s, %(y).1f)" % {'x' : fmtEpoch( mousePoint.x(), self.timefmt ), 'y' : mousePoint.y()}  )

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
    self.rplot.sigRangeChanged.connect( self.displayCurrentTemps )

    # emit signal that will cause plot to update
    self.data_changed.emit()




  def append_to_data( self, data ):
    # data contains all of the time-temperature history data points that will be
    # plotted. we store a seprate time-temperature pair for every sensor.
    logging.debug( "appending data to plot data")
    t = strptime( data["time"], TempLogger.timefmt )
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

      self.plotcurves[name]['region'].setData(x = self.data[name]['t'], y = self.data[name]['T'], pen=pg.mkPen( self.config.get("plot/colors/%d"%i)[0] ) )
      self.plotcurves[name]['zoom'  ].setData(x = self.data[name]['t'], y = self.data[name]['T'], pen=pg.mkPen( self.config.get("plot/colors/%d"%i)[0] ) )
      i += 1

    self.displayCurrentTemps()

  def show(self):
    pass


  def displayCurrentTemps(self):
    disp = ""
    i = 0
    now = time.mktime( datetime.datetime.now().timetuple() )
    for sensor in self.data:
      T = self.data[sensor]['T'][-1]
      t = self.data[sensor]['t'][-1]
      dt = (now - t)/60.
      disp = disp + '<br><span style="color:%(color)s;font-size:36pt">%(temp).2f@%(time).2f<span></br>' % {'color' : self.config.get("plot/colors/%d"%i), 'temp' : T, 'time' : dt}
      i += 1
    
    text = self.config.get("temperature/display/template") % {'temps' : disp}
    self.tempDisp.setHtml( text )
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
    logging.debug("pickling data to %s" % self.config.get("pickle/filename") )
    pickle.dump( self.data, open( self.config.get("pickle/filename"), "wb" ) )

  def unpickle_data(self):
    logging.debug("unpickling data from %s" % self.config.get("pickle/filename") )
    self.data = pickle.load( open( self.config.get("pickle/filename"), "rb" ) )

  def clear(self):
    self.init_data()
    os.remove( self.config.get("pickle/filename") )
  
  def init_data(self):
    self.data = collections.OrderedDict()

