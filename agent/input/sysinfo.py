"""
sysinfo.py

   obtain system informations

@author: K.Edeline
"""

import platform

class SysInfo():
   """

   extend me

   """
   def __init__(self):
   
      self.system = platform.system()
      self.node = platform.node()
      self.release = platform.release()
      self.version = platform.version()
      self.machine = platform.machine()
      self.processor = platform.processor()
      self.platform = platform.platform()
      self.architecture = platform.architecture()

   def __str__(self):
      return "node: {} system: {} release: {} arch: {}".format(self.node,
                  self.system, self.release, self.processor)

