import time
import datetime

def fmtEpoch( t, fmt ):
  return datetime.datetime( *time.localtime( t )[0:5] ).strftime( fmt )


