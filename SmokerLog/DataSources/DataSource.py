import collections
from ..Units import *

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


