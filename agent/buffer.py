"""
buffer.py

   buffer class for input metric monitoring

@author: K.Edeline
"""

import numpy as np
import collections

# max number of collected values
_BUFFER_SIZE=10

class RingBuffer(collections.deque):

   def __init__(self, max_len=_BUFFER_SIZE):
      super().__init__(max_len=max_len)

   def top(self):
      """
      return last value

      """
      try:
         return self.__getitem__(-1)
      except:
         return 0

   def mean(self):
      """
      
      """
      try:
         return np.mean(self)
      except:
         return 0
