from .DataSource import *
import requests
import re
import logging
from lxml import html, etree
from io import StringIO



class StokerWebSource( DataSource ):
  class DataExtractor:
    def __init__(self, elem = None):
      self.valid = False
      self.load(elem)
    def dump(self):
      print self.__dict__

  class Sensor(DataExtractor):
    def load(self, elem):
      self.name = ""
      self.serial = ""
      self.temp = 0
      self.target = 0
      self.low_set = 0
      self.high_set = 0

      # if the element is None, we can't do anything
      if elem == None:
        return None

      cols = elem.xpath("td")

      # make sure we have everything we need before going on
      # immediatly return if not.

      # first and third columns need to have text
      if len(cols) < 1 or cols[0] == None or cols[0].text == None:
        return None
      
      # ...and third
      if len(cols) < 3 or cols[2] == None or cols[2].text == None:
        return None

      # columns
      # 0 - serial number (plain text)
      # 1 - name          (input element)
      # 2 - temperature   (plain text)
      # 3 - target temp   (input element)
      # 4 - alarm         (select element)
      # 5 - low set       (input element)
      # 6 - high set      (input element)
      # 7 - blower        (select element)
      self.serial   =        cols[0].text.strip()                           if cols[0] is not None else ""
      self.name     =        cols[1].xpath("input")[0].get("value").strip() if cols[1] is not None else ""
      self.temp     = float( cols[2].text)                                  if cols[2] is not None else 0.
      self.target   = float( cols[3].xpath("input")[0].get("value") )       if cols[3] is not None else 0.

      self.low_set  = float( cols[5].xpath("input")[0].get("value") )       if cols[5] is not None else 0.
      self.high_set = float( cols[6].xpath("input")[0].get("value") )       if cols[6] is not None else 0.

      self.valid = True
        

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


  def __init__(self, host):

    # html scraper
    self.version = '2.0.x'
    self.host = host
    self.parser = etree.HTMLParser()
    self.url = "http://%(host)s" % {'host': self.host}
    self.timeout = 5*units.second



  def __str__(self):
    return "Stoker Web Interface (%s)" % self.host


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
      logging.debug( "Request timed out. If this keeps happening, check that the host is up.")
      return None

    except Exception, e:
      logging.debug( "Exception occured while requesting data: '%s'" % e.message )
      return None


    tree   = etree.parse( StringIO(html), self.parser )
    (sysinfo_table, data_table, trash, trash) = tree.xpath("body/table/form/tr")

    sensors = list()
    rows = data_table.xpath("td/table/tr")

    for i in xrange(1,len(rows)-1):
      sens = self.Sensor( rows[i] )
      if sens.valid:
        sensors.append( sens )

    data = collections.OrderedDict()
    for sensor in sensors:
      data[sensor.name] = sensor.temp

    return data

