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

   _format_attrs_list_rb: 
   category;subcategory;name;value;severity;dynamicity;severity
   _format_attrs_rb:
   category;value;name;severity;dynamicity;severity
   _format_attrs_list_rb_percpu: (similar to _format_attrs_list_rb)
   category;cpu_index;name;value;severity;dynamicity;severity
   _format_attrs_list:

   """


   def __init__(self, create=False, sublists=7):
      self.shm=None
      super(ShareableBuffer, self).__init__(
         sequence=[" "*MAX_WIDTH for _ in range(MAX_HEIGHT)] if create else None,
         name=hashlib.sha1((platform.node()+"-dxagent").encode('utf-8'))
              .hexdigest())

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

   def dict(self,info=None):
      """
      parse data into a new list

      _format_attrs_list_rb: 
      category;subcategory;name;value;severity;dynamicity;severity

      _format_attrs_rb:
      category;name;value;severity;dynamicity;severity

      _format_attrs_list_rb_percpu: (similar to _format_attrs_list_rb)
      category;cpu_index;name;value;severity;dynamicity;severity

      """
      data = {}
      for line in self:
         if not line or line.startswith(' '):
            break

         split = line.split(';')
         category = split[0]
         if category not in data:
            data[category] = {}

         v, s, dv, ds = split[-4:]
         content = [v, int(s), dv, int(ds)]

         # _format_attrs_list_rb
         # or _format_attrs_list_rb_percpu
         if len(split) == 7:
            subcategory = split[1]
            if subcategory not in data[category]:
               data[category][subcategory] = {}
            name = split[2]
            data[category][subcategory][name] = content

         # _format_attrs_rb
         elif len(split) == 6:
            name = split[1]
            data[category][name] = content

      return data

   def _get_content(self, rb):
      value, severity = rb.top()
      value = str(value)
      if rb.unit():
         value += (" {}").format(rb.unit())
      dvalue, dseverity = rb.dynamicity()
      return (value, str(severity.value),
             str(dvalue), str(dseverity.value))

   def write(self, data, skip=[], info=None):
      """
      write dict to ShareableMemory

      XXX: only write fields that changed

      """
      for k,d in data.items():
         if type(d) is list:
            continue
         if k in skip:
            continue

         for kk, dd in d.items():
            if type(dd) is dict:
               for kkk, ddd in dd.items():
                  if ddd.is_empty():
                     continue
                  v,s,dv,ds = self._get_content(ddd)
                  self.append(k, kk, kkk, v,s,dv,ds)
            else:
               if dd.is_empty():
                  continue
               v,s,dv,ds = self._get_content(dd)
               self.append(k, kk, v,s,dv,ds)

      self.validate()

   def append(self, *args):
      self[self.index] = ";".join(list(args))
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
   
