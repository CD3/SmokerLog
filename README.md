SmokerLog
=========

A command line BBQ logger written in Python.

SmokerLog is most useful with a Rock's Bar-B-Que Stoker, where it is capable of extracting and logging sensor readings from the Stoker's web interface. These temperatures
can then be plotted on an interactive graph. It is also possible to log events (for example, if you want to record the time that the brisket was put on).

Currently, only temperature readings from the Stoker are supported, but the data extraction code has been written in a way that should make it easy to extend to support other
systems.
