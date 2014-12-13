import time
import datetime
from PySide import QtCore,QtGui

def fmtEpoch( t, fmt ):
  return datetime.datetime( *time.localtime( t )[0:6] ).strftime( fmt )


def strptime( t, fmt ):
  return datetime.datetime.strptime( t, fmt )
