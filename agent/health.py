"""
health.py

   Key Performance Indicators & symptom rules

@author: K.Edeline

"""
import csv

from agent.buffer import init_rb_dict
from agent.sysinfo import SysInfo

class HealthEngine():
   def __init__(self, data, info, parent):      
      self._data = data
      self.info = info
      self.parent = parent
      self.sysinfo = SysInfo()

      self._data["kpi"] = {"bm" : {}, "vm" : {}, "kb" : {}}
      self._bm_attrs, self._bm_types, self._bm_units = [], [], []
      self._vm_attrs, self._vm_types, self._vm_units = [], [], []
      self._kb_attrs, self._kb_types, self._kb_units = [], [], []
      # mappings for easy initialization
      attrs = {"bm": (self._bm_attrs, self._bm_types, self._bm_units),
               "vm": (self._vm_attrs, self._vm_types, self._vm_units),
               "kb": (self._kb_attrs, self._kb_types, self._kb_units)}
      # read kpi file
      with open("res/kpi.csv") as csv_file:
         for r in csv.DictReader(csv_file):
            name,type,unit= r["name"], r["type"],r["unit"]
            category = name.split("_")[0]
            attrs[category][0].append(name)
            attrs[category][1].append(type)
            attrs[category][2].append(unit)

      self._build_dependency_graph()

   def _build_dependency_graph(self):
      self.node = Node(self.sysinfo.node)

   def _update_dependency_graph(self):
      """
      add & remove nodes based on self._data

      """
      vms, kbs = set(), set()
      for subservice in self.node.dependencies:
         if isinstance(subservice, VM):
            vms.add(subservice.name)
         elif isinstance(subservice, KBNet):
            kbs.add(subservice.name)
      monitored_vms = set(self._data["virtualbox/vms"].keys())
      monitored_kbs = set(self._data["vpp/gnmi"].keys())
 
      # remove expired nodes
      for vm in vms - monitored_vms:
         self.remove_vm(vm)
      for kb in kbs - monitored_kbs:
         self.remove_kbnet(kb)
      # add new nodes
      for vm in monitored_vms - vms:
         self.add_vm(vm)
      for kb in monitored_kbs - kbs:
         self.add_kbnet(kb)      

   def add_vm(self, name):
      self.node.add_vm(name)
   def add_kbnet(self, name):
      self.node.add_kbnet(name)
   def remove_vm(self, name):
      self.node.remove_vm(name)
   def remove_kbnet(self, name):
      self.node.remove_kbnet(name)

   def update_kpis(self):
      self._update_dependency_graph()
      self.node.update_kpis()

   def _update_kpis_bm(self):
      pass

   def _update_kpis_vm(self):
      pass

   def _update_kpis_kb(self):
      pass

   def update_symptoms(self):
      pass

class Symptoms():
   def __init__(self, name, severity, rule):
      self.name = name
      self.severity = severity
      self.rule = rule

class Subservice():
   """
   
   """
   def __init__(self, name, parent=None, is_leaf=False):
      self.name = name
      self.parent = parent
      self.is_leaf = is_leaf
      self.dependencies = []

   def __contains__(self, item):
      for subservice in self.dependencies:
         if item == subservice.name:
            return True
      return False

   def update_kpis(self):
      """
      update KPIs for this subservice and its dependencies

      """
      if not self.dependencies:
         self._update_kpis()
      for subservice in self.dependencies:
         subservice.update_kpis()

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      pass

   def get_symptoms(self):
      for subservice in self.dependencies:
         pass
   def get_health_score(self):
      return self.health_score

class Node(Subservice):
   """A device/physical node
   Includes 1 BM subservice, N VMs, N gnmi clients for VPP, 0-1 BM VPP

   """
   def __init__(self, name, parent=None):
      super(Node, self).__init__(name, parent=parent)
      self.sysinfo = SysInfo()
      self.name = self.sysinfo.node
      self.dependencies = [Baremetal(self.name, parent=self)]

   def add_vm(self, name):
      self.dependencies.append(VM(name, parent=self))
   def add_kbnet(self, name):
      self.dependencies.append(KBNet(name, parent=self))
   def remove_vm(self, name):
      for i, subservice in enumerate(self.dependencies):
         if isinstance(subservice, VM) and subservice.name == name:
            del self.dependencies[i]
            break
   def remove_kbnet(self, name):
      for i, subservice in enumerate(self.dependencies):
         if isinstance(subservice, KBNet) and subservice.name == name:
            del self.dependencies[i]
            break

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      pass

class Baremetal(Subservice):
   """Baremetal subservice assurance
   
   """
   def __init__(self, name, parent=None):
      super(Baremetal, self).__init__(name, parent=parent)
      self.fullname = type(self).__name__+"."+self.name

      deps = ["cpu", "sensors", "disk", "mem", "proc", "net"]
      self.dependencies = [Subservice(dep, parent=self) for dep in deps]

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      pass

class VM(Subservice):
   """VM subservice assurance
   
   """
   def __init__(self, name, parent=None):
      super(VM, self).__init__(name, parent=parent)
      self.fullname = type(self).__name__+"."+self.name

      deps = ["cpu", "mem", "net"]
      self.dependencies = [Subservice(dep, parent=self) for dep in deps]

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      pass
      
class KBNet(Subservice):
   """Kernel Bypassing Networks subservice assurance
   
   """
   def __init__(self, name, parent=None):
      super(KBNet, self).__init__(name, parent=parent)
      self.fullname = type(self).__name__+"."+self.name

      deps = ["proc", "mem", "net"]
      self.dependencies = [Subservice(dep, parent=self) for dep in deps]

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      pass


