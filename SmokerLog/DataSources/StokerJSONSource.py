from .DataSource import *
import requests
import re
import logging
from io import StringIO
import json



class StokerJSONSource( DataSource ):
  '''Data source that parses the Stoker JSON interface.'''
        
  def __init__(self, host):
    self.version = '2.7.x'
    self.host = host
    self.url = "http://%(host)s/stoker.json" % {'host': self.host}
    self.timeout = 5*units.second

  def __str__(self):
    return "Stoker JSON Interface (%s)" % self.host

  def get_data(self):
    try:
      logging.debug("Requesting data from host (url: %s)" % self.url)
      # get the status page
      page = requests.get(self.url, timeout=self.timeout.to(units.second).magnitude)
      # raise an exception for error codes
      page.raise_for_status()
      # get the raw json to parse
      datatree = json.loads( page.text )


    except requests.exceptions.Timeout, e:
      logging.debug( "Request timed out. If this keeps happening, check that the host is up.")
      return None

    except Exception, e:
      logging.debug( "Exception occured while requesting data: '%s'" % e.message )
      return None
#   From the Stoker firmware README

#   The idea is this:
#       1 global Stoker object
#       Stoker object contains two other objects
#       First object is called "sensors"
#           "sensors" object is an array of sensor entries
#           Each sensor entry has:
#               id - 16 character serial number
#               name - User defined name
#               al - alarm, which can be 0, 1, 2
#                   0 - no alarms
#                   1 - Target
#                   2 - Fire hi/low
#               ta - Target temperature
#               th - Fire high
#               tl - Fire low
#               tc - Current temp
#               blower - 16 character serial number of the blower, if any.
#                   If no blower, then the value is null
#
#       The second object is called "blowers"
#           "blowers" is an array of blower entries
#           Each blower entry has:
#               id - 16 character name
#               name - User defined name
#               on - 0 for blower off, 1 for blower on


    data = collections.OrderedDict()
    for sensor in datatree['stoker']['sensors']:
      data[sensor['name']] = sensor['tc']
    # for sensor in datatree['stoker']['sensors']:
      # data[sensor['name']+':Target'] = sensor['ta']

    return data

