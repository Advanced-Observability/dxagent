"""
buffer.py

   buffer class for input metric monitoring

@author: K.Edeline
"""

import numpy as np
import collections
from enum import Enum

# max number of collected values
_BUFFER_SIZE=60

def init_rb_dict(keys, type=int, types=None, 
                       counter=False, counters=None, 
                       unit=None, units=None):
   """
   initalize a dict of ringbuffers

   @keys the dict keys 
   @type the type of elements stored
   @types per-rb type list
   @counter is True if the monitored value is a counter
   @counters per-rb counter list
   @unit the unit of elements stored
   @units per-rb unit list
   

   """
   return {attr:RingBuffer(attr, type=types[i] if types else type, 
                           counter=counters[i] if counters else counter, 
                           unit=units[i] if units else unit) 
            for i,attr in enumerate(keys)}

class Severity(Enum):
   """
   Severity indicator

   """
   GREEN=0
   ORANGE=1
   RED=2

class RingBuffer(collections.deque):

   def __init__(self, attr_name, maxlen=_BUFFER_SIZE, 
                      type=int, counter=False, unit=""):
      """
      RingBuffer

      @maxlen the size of the ring buffer,
      @type the type of stored elements (int, float or str)
            note that str is a scalar type, it does not exclude int
      @counter is True if the monitored value is a counter

      """
      super().__init__(maxlen=maxlen)

      self.attr_name=attr_name
      self._unit=unit
      self.type=type
      self.counter=counter

   def is_empty(self):
      return not self

   def append(self, e):
      """
      overload collections.deque to cast val before
      appending

      """
      if self.type == int:
         super().append(int(e))
      elif self.type == float:
         super().append(float(e))
      elif self.type == str:
         super().append(str(e))    

   def _top(self):
      """
      @return last value

      """
      try:
         return self.__getitem__(-1)
      except:
         if self.type == str:
            return ""
         else:
            return 0

   def top(self):
      """
      @return a tuple composed of
         top value
         severity indicator

      """
      return self._top(), self._top_severity()

   def _top_severity(self):
      """
      @return a severity level for monitored value

      """
      if not self.counter and (self.type == int or self.type == float):

         if self._top() > self.mean()*10:
            return Severity.RED
         elif self._top() > self.mean()*3:
            return Severity.ORANGE

      elif self.type == str:
         return Severity.GREEN

      return Severity.GREEN

   def mean(self):
      """
      @return mean value on entire buffer

      """
      
      try:
         if self.type == float:
            return round(np.mean(list(self)), 2)
         elif self.type == int:
            return int(np.mean(list(self)))
         else:
            return 0

      except:
         return 0

   def min(self):
      return min(self)

   def max(self):
      return max(self)

   def delta(self, first=0):
      """
      @return delta value on entire buffer.
      
      the delta value is the difference between the first and
      last observed values. Applicable for counters.
         
      """
      
      try:
         delta = self.__getitem__(-1) - self.__getitem__(first)
         if self.type == float:
            return round(delta, 2)
         elif self.type == int:
            return delta
         else:
            return 0

      except:
         return 0

   def has_changed(self):
      """
      indicates if the ringbuffer has observed a value change
      """
      return not self.is_empty() and self.count(self.__getitem__(0)) != len(self)

   def _dynamicity(self):
      """

      @return delta() if counter is True
              has_changed() if type is str
              mean() else
      """
      if self.type == str:
         return int(self.has_changed())
      elif self.counter:
         return self.delta()
      else:
         return self.mean()

   def dynamicity(self):
      """
      @return a tuple composed of
         dynamicity value
         severity indicator

      """
      return self._dynamicity(), self._dynamicity_severity()

   def _dynamicity_severity(self):
      """
      @return a severity level for monitored value dynamicity

      """

      if self.type == str and self.has_changed():
         return Severity.ORANGE
      elif self.counter:
         return Severity.GREEN
      else:
         return Severity.GREEN

      return Severity.GREEN

   def unit(self):
      return self._unit

   def name(self):
      return self.attr_name

   def is_counter(self):
      return self.counter

   def __repr__(self):
      return self.__str__()

   def __str__(self):
      if self.type == str:
         return "'{}'".format(self.top()[0])
      else:
         return "{}".format(self.top()[0])


