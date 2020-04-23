"""
shareablebuffer.py

   wrapper for python3.8 ShareableList for datasharing
   between dxagent and dxtop

@author: K.Edeline

"""

import platform
import hashlib
from multiprocessing import shared_memory
from multiprocessing.resource_tracker import unregister

MAX_WIDTH=256
MAX_HEIGHT=2**14

class ShareableBuffer(shared_memory.ShareableList):

   """
   ShareableBuffer

   Stores a list of index sublists in shared memory.
   Each sublist contains 


   internal format:

   index;category
   index;
   index;name;value;dynamicity
   index;val0;val1;val2;val3;val4;val5;val6;val7;

   """


   def __init__(self, create=False, sublists=7):
      self.shm=None
      super(ShareableBuffer, self).__init__(
         sequence=[" "*MAX_WIDTH for _ in range(MAX_HEIGHT)] if create else None,
         name=hashlib.sha1(platform.node().encode('utf-8')).hexdigest())

      if not create:
         # avoid auto unlinking of SharedMemory segment
         # XXX: i'm guessing this is going to be fixed in later python versions
         unregister(self.shm._name, "shared_memory")

      self.index=0
      self._sublists=sublists

   def __del__(self):
      """
      close SharedMemory segment

      This does not unlink
      """
      if self.shm:
         self.shm.close()

   def close(self):
      self.shm.close()

   def unlink(self):
      """
      Release SharedMemory segment
      """
      self.shm.unlink()

   def __str__(self):
      l=[]
      for line in self:
         if not line or line.startswith(' '):
            break
         l.append(line)
      return str(l)

   def __repr__(self):
      return "ShareableBuffer(data={}, name='{}')".format(
         str(self),self.shm.name)

   def validate(self):
      """
      call this when append is over
      """
      self[self.index] = ""
      self.index = 0

   def read(self):
      """
      parse&copy data to a new list

      """
      data = [[] for _ in range(self._sublists)]
      for line in self:
         if not line or line.startswith(' '):
            break
         v = line.split(';')
         index = int(v[0])
         data[index].append(v[1:])
      return data

   def append(self, screen_index, s, *args):
      self[self.index] = ";".join([str(screen_index), s]+list(args))
      self.index += 1

   def reset(self):
      """
      reset index used for appending

      """
      self.index = 0

class ShareableBufferException(Exception):
   """
   ShareableBufferException(Exception)
   """
   
   def __init__(self, value):
      self.value = value
   
   def __str__(self):
      return repr(self.value)
   
