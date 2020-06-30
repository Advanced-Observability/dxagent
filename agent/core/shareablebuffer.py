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

from agent.core.rbuffer import MDict

#
# line width
MAX_WIDTH=256
#
# line height
MAX_HEIGHT=2**14

class ShareableBuffer(shared_memory.ShareableList):

   """
   ShareableBuffer

   Stores a dictionnary of RingBuffers in shared memory.

   """

   def __init__(self, create=False, sublists=7):
      self.shm=None
      super(ShareableBuffer, self).__init__(
         sequence=[" "*MAX_WIDTH for _ in range(MAX_HEIGHT)] if create else None,
         name=hashlib.sha1((platform.node()+"-dxagent").encode('utf-8'))
              .hexdigest())

      if not create:
         # avoid auto unlinking of SharedMemory segment
         unregister(self.shm._name, "shared_memory")
      self.index=0
      self._sublists=sublists
      self._last_rb_count=0

   def __del__(self):
      """
      close SharedMemory segment

      This does not unlink
      """
      self.close()

   def close(self):
      if self.shm:
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
         # special case: symptoms
         if split[0] == "symptoms":
            symptom=(split[1],split[2],split[3])
            data.setdefault("symptoms",[]).append(symptom)
            continue
         elif split[0] == "health_scores":
            path,score=split[1],split[2]
            data.setdefault("health_scores",{})[path] = int(score)
            continue
         # set default dicts
         d = data
         for category_index in range(len(split)-5):
            category = split[category_index]
            d = d.setdefault(category, {})
         # write content
         name, v, s, dv, ds = split[-5:]
         content = [v, int(s), dv, int(ds)]
         d[name] = content
      return data

   def _get_content(self, rb):
      value, severity = rb.top()
      value = str(value)
      if rb.unit():
         value += (" {}").format(rb.unit())
      dvalue, dseverity = rb.dynamicity()
      return (value, str(severity.value),
             str(dvalue), str(dseverity.value))
             
   def _rb_count_rec(self, d):
      if isinstance(d, dict):
         count = 0
         for kk, dd in d.items():
            count += self._rb_count_rec(dd)
         return count
      else: # trivial case
         if not d.is_empty():
            return 1
         else:
            return 0        

   def _rb_count(self, data, skip=[]):
      """
      count the amount of RBs

      """
      count=0
      for k,d in data.items():
         if k in skip:
            continue
         count += self._rb_count_rec(d)
      return count

   def write(self, data, skip=[], info=None):

      """
      write dict to ShareableMemory

      """
      skip.append("symptoms")
      skip.append("health_scores")
      rb_count = self._rb_count(data, skip=skip)
      if rb_count != self._last_rb_count:
         self._write(data, write_all=True, skip=skip, info=info)
      else:
         self._write(data, write_all=False, skip=skip, info=info)
      self._last_rb_count = rb_count
      
   def _write_dict_rec(self, d, write_all, *args):
      """
      recursively write dictionnary to shareableMemory
      
      @param d the dictionary
      @param args parent keys to be written aswell 
      """
      for kk, dd in d.items():
         if isinstance(dd, dict):
            # avoid race condition with threads writing in dicts
            if isinstance(dd, MDict):
               dd.acquire()
            self._write_dict_rec(dd, write_all, *args, kk)
            if isinstance(dd, MDict):
               dd.release()
         else:
            if dd.is_empty():
               continue
            if not write_all and not dd.has_changed(count=2):
               self.index += 1
               continue
            # write a line to ShareableMemory
            v,s,dv,ds = self._get_content(dd)
            self.append(*args, kk, v,s,dv,ds)

   def _write(self, data, write_all=True, skip=[], info=None):
      """
      write dict to ShareableMemory

      only write fields that changed
           if total datafield changed, rewrite all
            otherwise skip all if not has_changed()

      """
      for k,d in data.items():
         if k in skip:
            continue
         self._write_dict_rec(d, write_all, k)
      # special entry: symptom
      for s in data["symptoms"]:
         for arg in s.args:
            self.append("symptoms", s.name, str(s.severity.value), arg)
      for path,score in data["health_scores"].items(): 
         self.append("health_scores", path, str(score))         
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
   
