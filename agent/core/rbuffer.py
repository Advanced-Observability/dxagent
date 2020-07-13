"""
rbuffer.py

   buffer class for input metric monitoring

@author: K.Edeline
"""

import statistics
import collections
import threading
from contextlib import contextmanager
import itertools
from enum import Enum

# max number of collected values
_BUFFER_SIZE=60

def init_rb_dict(keys, type=int, types=None, 
                       counter=False, counters=None, 
                       unit=None, units=None,metric=False,
                       thread_safe=False):
   """
   initalize a dict of ringbuffers

   @keys the dict keys 
   @type the type of elements stored
   @types per-rb type list
   @counter is True if the monitored value is a counter
   @counters per-rb counter list
   @unit the unit of elements stored
   @units per-rb unit list
   
   @thread_safe the dict is replaced by a thread-safe MDict
   """
   if thread_safe:
      return MDict({attr:RingBuffer(attr, type=types[i] if types else type, 
                              counter=counters[i] if counters else counter,
                              metric=metric,
                              unit=units[i] if units else unit) 
               for i,attr in enumerate(keys)})
   else:
      return {attr:RingBuffer(attr, type=types[i] if types else type, 
                              counter=counters[i] if counters else counter,
                              metric=metric,
                              unit=units[i] if units else unit) 
               for i,attr in enumerate(keys)}

class Severity(Enum):
   """
   Severity indicator

   """
   GREEN=0
   ORANGE=1
   RED=2
   
   def weight(self):
      """
      @returns health malus of given severity
      """
      _weights = {
      "GREEN":0,
      "ORANGE":10,
      "RED":50,
      }
      return _weights[self.name]
      

class MDict(dict):
   """Multithread Dict, a dict that with an integrated threading.Lock.
   Use acquire(), release() or lock().
   
   """
   def __init__(self, *args, **kwargs):
      """Base (dict) accepts mappings or iterables as first argument."""
      super(MDict, self).__init__(*args, **kwargs)
      self._lock = threading.Lock()    

   def acquire(self):
      self._lock.acquire()
      return self

   def release(self):
      self._lock.release()

   @contextmanager
   def lock(self):
      l = self._lock.acquire()
      try:
         yield l
      finally:
         self._lock.release()

class RingBuffer(collections.deque):

   def __init__(self, attr_name, maxlen=_BUFFER_SIZE, 
                      type=int, counter=False, unit="",
                      metric=False):
      """
      RingBuffer

      @param maxlen the size of the ring buffer,
      @param type the type of stored elements (int, float or str)
                  note that str is a scalar type, it does not exclude int
      @param counter is True if the monitored value is a counter
      @param metric True if ringbuffer contains vendor-independant metric

      """
      super().__init__(maxlen=maxlen)

      self.attr_name=attr_name
      self._unit=unit
      self.type=type
      self.counter=counter
      self.metric=metric

   def is_empty(self):
      return not self
   def is_metric(self):
      return self.metric
      
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
            
   def _tops(self, c):
      """
      @return last c value

      """
      try:
         return [self.__getitem__(-i) for i in range(c,0,-1)]
      except:
         return []

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

   def mean(self, count=0):
      """
      @return mean value on entire buffer

      """
      if len(self) == 0:
         return 0
      if count==0:
         count = len(self)
      
      try:
         if self.type == float:
            return round(statistics.mean(self._tops(count)), 2)
         elif self.type == int:
            return int(statistics.mean(self._tops(count)))
         else:
            return 0

      except:
         return 0

   def min(self):
      return min(self)

   def max(self):
      return max(self)

   def is_number(self):
      return self.type == int or self.type == float

   def delta(self, count=0):
      """
      the delta value is the difference between the first and
      last observed values. Applicable for counters.
      
      @return delta value on entire buffer.
      
      @param count the number of *other* elements to consider (max: len(rb)-1)
                   e.g. delta(count=1) returns rb[-1]-rb[-2]
                      
      """
      if count == 0:
         first = 0
      else:
         first = max(-count-1,-len(self))
      
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

   def has_changed(self, count=0):
      """
      indicates if the ringbuffer has observed a value change

      @param count the number of value to consider
                     
      """
      if count == 0:
         count = len(self)
      if len(self) == 0 or len(self) < count:
         return False
         
      return self._tops(count).count(self.__getitem__(-1)) != count

   def _dynamicity(self, count=0):
      """

      @return delta() if counter is True
              has_changed() if type is str
              mean() else
      """
      if self.type == str:
         return int(self.has_changed(count=count))
      elif self.counter:
         return self.delta(count=count)
      else:
         return self.mean(count=count)

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


