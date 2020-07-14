"""
health.py

   health engine and subservice dependency graph

@author: K.Edeline

"""
import csv
import os
import builtins
import sys
import itertools
import time
import json
import re
import statistics
import math

from ..core.rbuffer import init_rb_dict, Severity
from ..input.sysinfo import SysInfo
from ..constants import AGENT_INPUT_PERIOD
from ..input.vpp_input import vpp_support
from ..input.vm_input import hypervisors_support
from .symptoms import Symptom, RuleException

class Metric():
   def __init__(self, name, node, _type, unit, islist, counter):
      self.name=name
      self.node=node
      self._type=_type
      self.unit=unit
      self.islist=bool(int(islist))
      self.counter=bool(counter)
      
class HealthEngine():
   def __init__(self, data, info, parent):      
      self._data = data
      self.info = info
      self.parent = parent
      self.sysinfo = SysInfo()
      
      self._data["/node/vm"], self._data["/node/kb"] = {}, {}
      self._data["symptoms"] = []
      self._data["health_scores"] = {}
      self.sample_per_min = int(60/AGENT_INPUT_PERIOD)
      self.types_map = { "vm": VM, "kb": KBNet}
      self.vbox_supported = hypervisors_support()
      self.vpp_api_supported, self.vpp_stats_supported, self.vpp_gnmi_supported=vpp_support()
      
      self._read_metrics_file()
      self._read_rule_file()
      self._build_dependency_graph()
      self._update_graph_changed_timestamp()
      
   def _read_rule_file(self):
      self._symptoms_args=[]
      file_loc = os.path.join(self.parent.args.ressources_dir,"rules.csv")
      metrics = list(self.metrics.keys())
      
      with open(file_loc) as csv_file:
         for r in csv.DictReader(csv_file):
            name, path, rule = r["name"], r["path"], r["rule"]
            try:
               severity = Severity[str.upper(r["severity"])]
            except KeyError as e:
               self.info("Invalid rule Severity: {}".format(r["severity"]))
               continue
#            try:
#               symptom = Symptom(name, path, severity, rule, self)
#            except Exception as e:
#               self.info("Invalid rule syntax: {}".format(rule))
#               continue       
            symptom = Symptom(name, path, severity, rule, self)
            if not symptom._safe_rule(metrics):
               self.info("Invalid rule: {}".format(rule))
               continue
            
            self._symptoms_args.append((name, path, severity, rule, self))
            
   def get_symptoms(self, node):
      """
      Return a list of newly instantiated symptoms for given node
      
      """
      return [Symptom(*args, node=node) for args
              in self._symptoms_args 
              if args[1] == node.path]
      
   def _read_metrics_file(self):
      self.metrics_lookup = {}
      self.metrics = {}
      file_loc = os.path.join(self.parent.args.ressources_dir,"metrics.csv")
      with open(file_loc) as csv_file:
         for r in csv.DictReader(csv_file):
                 
            key = (r["subservice"],)
            rec = self.metrics_lookup.setdefault(key,
                     {"types":[],"units":[],"names":[], "counters":[]})
            rec["names"].append(r["name"])
            rec["types"].append(getattr(builtins, r["type"]))
            rec["units"].append(r["unit"])
            rec["counters"].append(r["counter"])
            metric = Metric(r["name"], r["subservice"],
                            getattr(builtins, r["type"]),
                            r["unit"], r["is_list"], r["counter"])
            self.metrics[r["name"]] = metric
            
   def _update_graph_changed_timestamp(self):
      self.dependency_graph_changed = str(time.time())

   def _build_dependency_graph(self):
      """
      build deps graph and insert symptoms in nodes
      """
      self.root = Node("node", self.sysinfo.node, self)

   def _update_dependency_graph(self):
      """
      add & remove nodes, and elements in metrics dict based on self._data

      """
      root_path = self.root.fullname
      
      # 1. update vms&kbs
      if self.vbox_supported:
         vms = set(s.name for s in self.root.dependencies if isinstance(s, VM))
         monitored_vms = set(self._data["virtualbox/vms"].keys())
         # remove expired nodes
         for vm in vms - monitored_vms:
            #self.remove_node(self.root, vm, "vm")
            # do not remove, keep it as inactive
            pass
         for vm in monitored_vms - vms:
            self.add_node(self.root, vm, "vm", hypervisor="virtualbox")
         
      kbs = set(s.name for s in self.root.dependencies if isinstance(s, KBNet))
      monitored_kbs = set(self._data["vpp/gnmi"].keys())
      # local vpp 
      if self.vpp_api_supported and "vpp/system" in self._data:
         monitored_kbs.add("localhost")
      for kb in kbs - monitored_kbs:
         #self.remove_node(self.root, kb, "kb")
         # do not remove, keep it as inactive
         pass
      for kb in monitored_kbs - kbs:
         self.add_node(self.root, kb, "kb", framework="vpp")
         
      # 2. interfaces
      # 2.a bm interfaces
      parent = self.get_node(root_path+"/bm/net")
      current=set(self._data["net/dev"].keys())
      previous=set(self._data["/node/bm/net/if"].keys())
      self._update_childs(previous, current, parent, "if")

      # 2.b vm interfaces
      if self.vbox_supported:
         vms = set(s.name for s in self.root.dependencies if isinstance(s, VM))
         for vm in vms:
            parent = self.get_node(root_path+"/vm[name={}]/net".format(vm))
            previous = set(s.name for s in parent.dependencies) 
            current = set()
            prefixes = {}
            net_count=(self._data["virtualbox/vms"][vm]
                    ["/VirtualBox/GuestInfo/Net/Count"])._top()     
            for net_index in range(net_count):
               attr="/VirtualBox/GuestInfo/Net/{}/Name".format(net_index)
               if_name=self._data["virtualbox/vms"][vm][attr]._top()
               current.add(if_name)
               prefixes[if_name] = ttr="/VirtualBox/GuestInfo/Net/{}".format(net_index)
            
            self._update_childs(previous, current, parent, "if",
                                subdict=self._data["/node/vm"][vm])                    
            # set internal prefixes
            for if_name in current:
               if if_name in previous:
                  continue
               if_node = self.get_node(root_path+"/vm[name={}]/net/if[name={}]".format(
                              vm, if_name))
               if_node._vbox_api_prefix = prefixes[if_name]
            
      # 2.c kb interfaces
      kbs = set(s.name for s in self.root.dependencies if isinstance(s, KBNet))       
      for kb in kbs:
         parent = self.get_node(root_path+"/kb[name={}]/net".format(kb))
         previous = set(s.name for s in parent.dependencies) 
         if kb == "localhost":
            current = set(self._data["vpp/stats/if"].keys())
         else:
            current = set(self._data["vpp/gnmi"][kb]["net_if"])
         self._update_childs(previous, current, parent, "if",
                             subdict=self._data["/node/kb"][kb])
      
      # 3. disks
      parent = self.get_node(root_path+"/bm/disks")
      # init metric rbs if needed
      if "/node/bm/disks/disk" not in self._data:
         self._data["/node/bm/disks/disk"] = {}
      previous=set(self._data["/node/bm/disks/disk"].keys())
      current=set(list(self._data["diskstats"].keys())
                  +list(self._data["swaps"].keys()))
      self._update_childs(previous, current, parent, "disk")
            
      # 4. sensors
      parent = self.get_node(root_path+"/bm/sensors")
      if "/node/bm/sensors/sensor" not in self._data:
         self._data["/node/bm/sensors/sensor"] = {}
      previous=set(self._data["/node/bm/sensors/sensor"].keys())
      current=set(
         [k+":"+d["type"]._top() for k,d in self._data["sensors/thermal"].items()]
       + [k+":"+d["label"]._top() for k,d in self._data["sensors/fans"].items()]
       + [k+":"+d["label"]._top() for k,d in self._data["sensors/coretemp"].items()]
      )
      self._update_childs(previous, current, parent, "sensor")
      
      # 5. cpus (they are dynamic if agent is ran in vm)
      parent = self.get_node(root_path+"/bm/cpus")
      if "/node/bm/cpus/cpu" not in self._data:
         self._data["/node/bm/cpus/cpu"] = {}
      
      previous=set(self._data["/node/bm/cpus/cpu"].keys())
      current=set(self._data["stat/cpu"].keys())
      self._update_childs(previous, current, parent, "cpu")
      
      # 5.a vm cpus
      if self.vbox_supported:
         for vm in vms:
            parent = self.get_node(root_path+"/vm[name={}]/cpus".format(vm))
            previous = set(s.name for s in parent.dependencies)
            current = set()
            if parent.parent.hypervisor == "virtualbox":
               # the 'total' cpu
               current.add("cpu") 
            self._update_childs(previous, current, parent, "cpu",
                                subdict=self._data["/node/vm"][vm])

   def _update_childs(self, previous, current, parent, _type, subdict=None):
      """
      Compute difference between previous and current childs of type _type
      of node parent, and modify dependencies accordingly
      """
      if subdict:
         data=subdict
      else:
         data=self._data
      
      for label in current-previous:
         node = self.get_node(parent.path+"/"+_type+"[name={}]".format(label))
         if node: 
            node.active = True
         else: 
            path = "{}/{}".format(parent.path,_type)
            data[path][label] = self._init_metrics_rb(_type)
            self.add_node(parent, label, _type)
      for label in previous-current:
         #del data[parent_path][cpu]
         node = self.get_node(parent.path+"/"+_type+"[name={}]".format(label))
         node.active = False
         
   def _init_metrics_rb(self, subservice):
      """
      return metrics ringbuffers for subservices monitoring

      @param subservice the name of the subservice for which rbs
                        are getting initialized

      XXX: class name != parent subservice name in metrics.csv
      
      """
      key = (subservice,)
      rec = self.metrics_lookup[key]
      return init_rb_dict(rec["names"], metric=True,
                          types=rec["types"],
                          units=rec["units"],
                          counters=rec["counters"])
   
   def get_node(self, path):
      return self.root.get_node(path)
         
   def get_node_type(self, _type):
      """
      @return node type from string 
      """
      return self.types_map.get(_type, Subservice)
         
   def add_node(self, parent, name, _type, **kwargs):
      """
      Add a node the deps graph
      
      @param parent the subservice of which added node will be a dep
      @param name the key/name of the added subservice
      @param _type the type of subservice (see self.get_node_type)
      @param kwargs extra special args 
             (hypervisor for vm, framework for kb)
      
      """
      parent.add_node(name, _type, self.get_node_type(_type), **kwargs)
      self._update_graph_changed_timestamp()
      
   def remove_node(self, parent, name, _type):
      parent.remove_node(name, _type)
      self._update_graph_changed_timestamp()
      
   def update_health(self):
      self._update_dependency_graph()
      self.root.update_metrics()
      self._data["symptoms"], self._data["health_scores"] = self.root.update_symptoms()
      #for node in self:
      #   self.info(node)
         
   def __iter__(self, current=None):
      """
      Return a subservices iterator 
      
      """
      if not current:
         current = self.root
      yield current
      for dep in current.dependencies:
         yield from self.__iter__(dep)
      
class Subservice():
   """
   Base class that represents a subservice in the dependency graph.
   It is responsible of dependencies, symptoms and health scores.
   """
   def __init__(self, _type, name, engine,
                parent=None, impacting=True):
      # The type of subservice e.g., vm, bm, kb, node, net, if, etc
      self._type = _type
      # The unique identifier of the subservice
      # e.g., VM id, VPP id, or net, cpu, proc for Subservices
      self.name = name
      self.engine = engine
      self._data = self.engine._data
      self.sysinfo = self.engine.sysinfo
      self.parent = parent
      # impacting
      # if True:  dependencies transmit symptoms and health score malus
      #           to parent.
      # if False: symptoms and health score are displayed but not transmitted
      #           to parent.
      self.impacting = impacting
      self.dependencies = []
      self.active = True
      self.fullname = self.find_fullname()
      self.path = self.find_path()
      self.health_score = 100
      self.symptoms = self.engine.get_symptoms(self)
      self._update_graph_changed_timestamp()
      
   def __str__(self):
      s = "<{} type:{} name:{} fullname:{}>".format(type(self),
            self._type, self.name, self.fullname)
      return s
      
   def add_node(self, name, _type, _class, **kwargs):
      self.dependencies.append(_class(_type, name, self.engine, parent=self, **kwargs))
      
   def get_child(self, name, _type):
      for subservice in self.dependencies:
         if subservice._type == _type and subservice.name == name:
            return subservice
      return None
      
   def parse_element(self, element):
      """
      parse an element (subpath)
         e.g., /node[name=ko] returns 'node', 'ko'
      
      @return _type, name  
      """
      element = element.lstrip("/")
      m=re.search("/?(\w+)((\[name\=)([^/\]]+)(\]))?", element)
      return m.group(1), m.group(4)
      
   def get_node(self, path):
      path_elements = path.lstrip("/").split("/")
      subpath = self._type
      if self.name:
         subpath = "{}[name={}]".format(subpath,self.name)
         
      if subpath == path_elements[0]:
         if len(path_elements) == 1:
            return self
         child_type, child_name = self.parse_element(path_elements[1])
         child = self.get_child(child_name, child_type)
         if child:
            return child.get_node("/".join(path_elements[1:]))
      return None
      
   def remove_node(self, name, _type):
      for i, subservice in enumerate(self.dependencies):
         if subservice._type == _type and subservice.name == name:
            subservice.del_metrics()
            del self.dependencies[i]
            break      
      
   def _update_graph_changed_timestamp(self):
      self.dependency_graph_changed = str(time.time())
      
   def find_fullname(self):
      """
      compute fullname string, similar to the path string
      with additional name/index.
      
         /node[name=machine1]/vm[name=vagrant_default_158504808]/net/if[name=vboxnet0]
         
         compatible with gRPC path
      """
      fullname="/"+self._type
      if self.name:
         fullname = "{}[name={}]".format(fullname,self.name)
      if self.parent:
         fullname = "{}{}".format(self.parent.fullname,fullname)
      return fullname
      
   def find_path(self):
      """
      compute path string (e.g., /node/bm/sensors/fan)
      
      NOTE: there are no key/name in path (see fullname)
      """
      path="/"+self._type
      if self.parent:
         path = "{}{}".format(self.parent.path,path)
      return path
      
   def json_bag(self):
      """
      @return a json string that describes this subservice, formatted as
              specified by ietf-service-assurance.yang
              See https://tools.ietf.org/html/draft-claise-opsawg-service-assurance-yang-04
      {
         "type": "subservice-idty",
         "id": "/node[name=ko]",
         "subservice-parameters": {
              "service": "custom_service", 
              "instance-name": "initial_custom_service"
         },
         
         "last-change":"2020-12-30T12:00:00-08:00",
         "label": "The ko node ",

         "health-score": 100,
         
         "symptoms": [
            {
               "id": 6834403197888517606,
               "health-score-weight": 50,
               "label": "test",
               "start-date-time": 1593792317.5360885
            }
         ],
         "dependencies" : [
           {
             "type": "xconnect-idty",
             "id": "('sain-pe-1', 'l2vpn', 'P2P_BNP')",
             "dependency-type": "impacting-dependency"
            }   
         ]
         
      }          
              
      """
      bag =  { "type": "subservice-idty",
               "id": self.fullname,
               "subservice-parameters": {
                 "service": self.path, 
                 "instance-name": self.name
                },
               "last-change":self.dependency_graph_changed,
               "label": self.fullname,
               "health-score": self.health_score,
            
               "symptoms": [ 
                  {
                     "id": s.id,
                     "health-score-weight": s.severity.weight(),
                     "label": s.name,
                     "start-date-time":s.timestamp
                  
                  } for s in self.positive_symptoms
               ],
               "dependencies" : [ 
                  { 
                     "type": "subservice-idty",
                     "id" : dep.fullname,
                     "dependency-type": "impacting-dependency" if dep.impacting
                                        else "informational-dependency"
                  } for dep in self.dependencies
               ] 
            }
      
      return json.dumps(bag)

   def __contains__(self, item):
      return any(subservice._type == item for subservice in self.dependencies)

   def del_metrics(self):
      """
      subservice cleanup, overload in child if needed.
      """
      pass
   def propagate_scores(self, deps_scores, method="quadratic-mean"):
      """
      propagate scores from dependencies to parent node
      """
      score = 100
      if not deps_scores:
         return score
      if method == "malus":
         for dep_score in deps_scores:
            malus = 100-dep_score
            score -= malus
      elif method == "mean":
         score = round(statistics.mean(deps_scores))
      elif method == "geometric-mean":
         score = round(statistics.geometric_mean(deps_scores))
      elif method == "harmonic-mean":
         score = round(statistics.harmonic_mean(deps_scores))
      elif method == "quadratic-mean":
         squares = [dep_score*dep_score for dep_score in deps_scores]
         score = round(math.sqrt(statistics.mean(squares)))
      return max(score, 0)
      
   def update_symptoms(self):
      """
      bottom-up check of symptoms and update of health score
      
      @return (symptoms,health_scores) 
              symptoms: the list of positive symptoms
              health
      """
      self.health_score = 100
      self.positive_symptoms = []
      positives, health_scores = [], {}
      
      # update symptoms&health_score from deps
      deps_scores = []
      for subservice in self.dependencies:
         p, hs = subservice.update_symptoms()
         positives.extend(p)
         health_scores.update(hs)
         if subservice.impacting and subservice.active:
            deps_scores.append(subservice.health_score)
      self.health_score = self.propagate_scores(deps_scores)
      
      # update for node
      for symptom in self.symptoms:
         result = symptom.check(self._data)
         if result:
            self.positive_symptoms.append(symptom)
            self.health_score = max(0,self.health_score-symptom.weight)
            
      positives.extend(self.positive_symptoms)
      health_scores[self.fullname] = self.health_score
      return positives, health_scores

   def _init_metrics_rb(self, subservice):
      return self.engine._init_metrics_rb(subservice)
      
   def update_metrics(self):
      """
      update metrics for this subservice and its dependencies

      """
      self._update_metrics()
      if not self.active:
         return
      for subservice in self.dependencies:
         subservice.update_metrics()

   def _update_metrics(self):
      """
      update metrics for this subservice 

      Pick the right function based on host OS and subservice.
      
      """
      key = (self.sysinfo.system,
             self.path)
      funcs = {
   ("Linux","/node/bm/cpus")          : self._update_metrics_linux_bm_cpus,
   ("Linux","/node/bm/cpus/cpu")      : self._update_metrics_linux_bm_cpus_cpu,
   ("Linux","/node/bm/sensors")    : self._update_metrics_linux_bm_sensors,
   ("Linux","/node/bm/sensors/sensor"): self._update_metrics_linux_bm_sensors_sensor,
   ("Linux","/node/bm/disks")      : self._update_metrics_linux_bm_disks,
   ("Linux","/node/bm/disks/disk") : self._update_metrics_linux_bm_disks_disk,
   ("Linux","/node/bm/mem")        : self._update_metrics_linux_bm_mem,
   ("Linux","/node/bm/proc")       : self._update_metrics_linux_bm_proc,
   ("Linux","/node/bm/net")        : self._update_metrics_linux_bm_net,
   ("Linux","/node/bm/net/if")     : self._update_metrics_linux_bm_net_if,
   ("Linux","/node/vm/cpus")       : self._update_metrics_linux_vm_cpus,
   ("Linux","/node/vm/cpus/cpu")   : self._update_metrics_linux_vm_cpus_cpu,
   ("Linux","/node/vm/mem")        : self._update_metrics_linux_vm_mem,
   ("Linux","/node/vm/net")        : self._update_metrics_linux_vm_net,
   ("Linux","/node/vm/net/if")        : self._update_metrics_linux_vm_net_if,
   ("Linux","/node/vm/proc")       : self._update_metrics_linux_vm_proc,
   ("Linux","/node/kb/proc")       : self._update_metrics_linux_kb_proc,
   ("Linux","/node/kb/mem")        : self._update_metrics_linux_kb_mem,
   ("Linux","/node/kb/net")        : self._update_metrics_linux_kb_net,
   ("Linux","/node/kb/net/if")        : self._update_metrics_linux_kb_net_if,
   
   ("Windows","/node/bm/cpus") : self._update_metrics_win_bm_cpu,
   ("MacOS","/node/bm/cpus")   : self._update_metrics_macos_bm_cpu,
      }
      return funcs[key]()
      
   def _update_metrics_linux_bm_cpus_cpu(self):
      """Update metrics for linux a BM cpu subservice
      
      """
      cpu_label = self.name
      rbs = self._data["stat/cpu"].get(cpu_label)
      if rbs:
         self._data["/node/bm/cpus/cpu"][cpu_label]["idle_time"].append(
            rbs["idle_all_perc"]._top())
         self._data["/node/bm/cpus/cpu"][cpu_label]["system_time"].append(
            rbs["system_all_perc"]._top())
         self._data["/node/bm/cpus/cpu"][cpu_label]["user_time"].append(
            rbs["user_perc"]._top())
         self._data["/node/bm/cpus/cpu"][cpu_label]["guest_time"].append(
            rbs["guest_all_perc"]._top())      

   def _update_metrics_linux_bm_cpus(self):
      """Update metrics for linux BM cpu subservice

      """
      pass
            
   def _update_metrics_linux_bm_sensors_sensor(self):
      """Update metrics for linux a BM sensor subservice

      """
      sensor_label = self.name
      
      # thermal zones
      rbs = self._data["sensors/thermal"].get(sensor_label)
      if rbs:
         self._data["/node/bm/sensors/sensor"][sensor_label]["type"].append("zone")
         attr_mapping = {"temperature": "input_temp",}
         for attr,metric in attr_mapping.items():
            if attr in rbs:
               self._data["/node/bm/sensors/sensor"][sensor_label][metric].append(
                 rbs[attr]._top())
        
      # fan sensors
      rbs = self._data["sensors/fans"].get(sensor_label)
      if rbs:
         self._data["/node/bm/sensors/sensor"][sensor_label]["type"].append("fan")
         attr_mapping = {"input": "input_fanspeed",
                         "temperature": "input_temp",}
         for attr,metric in attr_mapping.items():
            if attr in rbs:
               self._data["/node/bm/sensors/sensor"][sensor_label][metric].append(
                 rbs[attr]._top())
                 
      # core sensors
      rbs = self._data["sensors/coretemp"].get(sensor_label)
      if rbs:
         self._data["/node/bm/sensors/sensor"][sensor_label]["type"].append("cpu")
         attr_mapping = {"input": "input_temp",
                         "max": "max_temp",
                         "critical": "critical_temp",}
         for attr,metric in attr_mapping.items():
            if attr in rbs:
               self._data["/node/bm/sensors/sensor"][sensor_label][metric].append(
                 rbs[attr]._top())

   def _update_metrics_linux_bm_sensors(self):
      """Update metrics for linux BM sensors subservice

      """
      pass            
                 
   def _update_metrics_linux_bm_disks_disk(self):
      """Update metrics for a linux BM disk subservice
      
      """
      disk = self.name
      rbs  = self._data["diskstats"].get(disk)
      if rbs:
         self._data["/node/bm/disks/disk"][disk]["type"].append(
            rbs["fs_vfstype"]._top())
         self._data["/node/bm/disks/disk"][disk]["total_user"].append(
            rbs["total"]._top()/1000.0)
         self._data["/node/bm/disks/disk"][disk]["free_user"].append(
            rbs["free_user"]._top()/1000.0)
         self._data["/node/bm/disks/disk"][disk]["read_time"].append(
            rbs["perc_reading"]._top())
         self._data["/node/bm/disks/disk"][disk]["write_time"].append(
            rbs["perc_writting"]._top())
         self._data["/node/bm/disks/disk"][disk]["io_time"].append(
            rbs["perc_io"]._top())
         self._data["/node/bm/disks/disk"][disk]["discard_time"].append(
            rbs["perc_discarding"]._top())

      rbs = self._data["swaps"].get(disk)
      if rbs:
         self._data["/node/bm/disks/disk"][disk]["type"].append(
            "swap")#rbs["type"]._top()
         self._data["/node/bm/disks/disk"][disk]["total_user"].append(
            rbs["size"]._top()/1000.0)
         self._data["/node/bm/disks/disk"][disk]["swap_used"].append(
            rbs["used"]._top())
   def _update_metrics_linux_bm_disks(self):
      """Update metrics for linux BM disks subservice

      """
      pass

   def _update_metrics_linux_bm_mem(self):
      """Update metrics for linux BM mem subservice

      """
      self._data["/node/bm/mem"]["total"].append(
         self._data["meminfo"]["MemTotal"]._top()/1000)
      self._data["/node/bm/mem"]["free"].append(
         self._data["meminfo"]["MemFree"]._top()/1000)
      self._data["/node/bm/mem"]["available"].append(
         self._data["meminfo"]["MemAvailable"]._top()/1000)
      self._data["/node/bm/mem"]["buffers"].append(
         self._data["meminfo"]["Buffers"]._top()/1000)
      self._data["/node/bm/mem"]["cache"].append(
         self._data["meminfo"]["Cached"]._top()/1000)
      self._data["/node/bm/mem"]["active"].append(
         self._data["meminfo"]["Active"]._top()/1000)
      self._data["/node/bm/mem"]["inactive"].append(
         self._data["meminfo"]["Inactive"]._top()/1000)
      self._data["/node/bm/mem"]["pages_total"].append(
         self._data["meminfo"]["HugePages_Total"]._top())
      self._data["/node/bm/mem"]["pages_free"].append(
         self._data["meminfo"]["HugePages_Free"]._top())
      self._data["/node/bm/mem"]["pages_reserved"].append(
         self._data["meminfo"]["HugePages_Rsvd"]._top())
      self._data["/node/bm/mem"]["pages_size"].append(
         self._data["meminfo"]["Hugepagesize"]._top()/1000)

   def _update_metrics_linux_bm_proc(self):
      """Update metrics for linux BM proc subservice

      """
      self._data["/node/bm/proc"]["total_count"].append(
         self._data["stats_global"]["proc_count"]._top())
      self._data["/node/bm/proc"]["run_count"].append(
         self._data["stats_global"]["run_count"]._top())
      self._data["/node/bm/proc"]["sleep_count"].append(
         self._data["stats_global"]["sleep_count"]._top())
      self._data["/node/bm/proc"]["idle_count"].append(
         self._data["stats_global"]["idle_count"]._top())
      self._data["/node/bm/proc"]["wait_count"].append(
         self._data["stats_global"]["wait_count"]._top())
      self._data["/node/bm/proc"]["zombie_count"].append(
         self._data["stats_global"]["zombie_count"]._top())
      self._data["/node/bm/proc"]["dead_count"].append(
         self._data["stats_global"]["dead_count"]._top())


   def _update_metrics_linux_bm_net_if(self):
      attr_mapping = {"rx_packets": "rx_packets",
                      "rx_bytes": "rx_bytes",
                      "rx_errs": "rx_error",
                      "rx_drop": "rx_drop",
                      "tx_packets": "tx_packets",
                      "tx_bytes": "tx_bytes",
                      "tx_errs": "tx_error",
                      "tx_drop": "tx_drop",
                      "carrier_up_count": "up_count",
                      "carrier_down_count": "down_count",
                      "carrier_changes": "changes_count",
                      "operstate": "state",
                      "mtu": "mtu",
                      "numa_node": "numa",
                      "local_cpulist": "cpulist",
                      "tx_queue_len": "tx_queue",
                      "wireless":"wireless",
                      "dns_server":"dns_server",
                      "dhcp_server":"dhcp_server",
                      "type": "type", "driver": "driver",
                      "bus_info": "bus_info",  "ufo": "ufo",
#                      "tso": "tso", "gso": "gso",
#                      "gro": "gro", "sg": "sg", 
                          
                      "tx-checksum-ipv4":"tx-checksum-ipv4",
                      "tx-checksum-ip-generic":"tx-checksum-ip-generic",
                      "tx-checksum-ipv6":"tx-checksum-ipv6", 
                      "tx-generic-segmentation":"tx-generic-segmentation",
                      "tx-lockless":"tx-lockless",
                      "rx-gro":"rx-gro","rx-lro":"rx-lro",
                      "tx-tcp-segmentation":"tx-tcp-segmentation",
                      "tx-gso-robust":"tx-gso-robust",
                      "tx-tcp-ecn-segmentation":"tx-tcp-ecn-segmentation",
                      "tx-tcp6-segmentation":"tx-tcp6-segmentation",
                      "tx-gre-segmentation":"tx-gre-segmentation",
                      "tx-gre-csum-segmentation":"tx-gre-csum-segmentation",
                      "tx-udp-segmentation":"tx-udp-segmentation",
                      "rx-hashing":"rx-hashing",
                      "rx-checksum":"rx-checksum",
         
                      "bus_info": "bus_info",
                      "wireless_protocol": "wireless_protocol",
                      "broadcast": "broadcast", "debug": "debug",
                      "point_to_point": "point_to_point",
                      "notrailers": "notrailers", "running": "running",
                      "noarp": "noarp", "promisc": "promisc",
                      "allmulticast": "allmulticast",
                      "multicast_support": "multicast_support",
                      }
      
      rbs = self._data["net/dev"][self.name]
      # direct mapping
      for attr,metric in attr_mapping.items():
         if attr in rbs and not rbs[attr].is_empty():
            self._data["/node/bm/net/if"][self.name][metric].append(
              rbs[attr]._top())
      # other fields
      if "ip4_gw_addr" in rbs:
         self._data["/node/bm/net/if"][self.name]["gw_in_arp"].append(
            rbs["ip4_gw_addr"]._top() in self._data["net/arp"])      

   def _update_metrics_linux_bm_net(self):
      """Update metrics for linux BM net subservice

      """
      # non interface-related fields
      for field, rb in self._data["snmp"].items():
         metric_name = "snmp_"+field
         if metric_name not in self._data["/node/bm/net"]:
            continue
         self._data["/node/bm/net"][metric_name].append(rb._top())
         
   def _update_metrics_linux_vm_cpus(self):
      """Update metrics for linux VM cpu subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
   
   def _update_metrics_linux_vm_cpus_cpu(self):
      vm_name=self.parent.parent.name
      hypervisor=self.parent.parent.hypervisor
      cpu_label = self.name
      
      self._data["/node/vm"][vm_name]["/node/vm/cpus/cpu"][cpu_label]["cpu_count"].append(
         self._data[hypervisor+"/vms"][vm_name]["cpu"]._top())
      self._data["/node/vm"][vm_name]["/node/vm/cpus/cpu"][cpu_label]["user_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/User"]._top())
      self._data["/node/vm"][vm_name]["/node/vm/cpus/cpu"][cpu_label]["system_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/Kernel"]._top())
      self._data["/node/vm"][vm_name]["/node/vm/cpus/cpu"][cpu_label]["idle_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/Idle"]._top())

   def _update_metrics_linux_vm_mem(self):
      """Update metrics for linux VM mem subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
      self._data["/node/vm"][vm_name]["/node/vm/mem"]["total"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Total"]._top()/1000.0)
      self._data["/node/vm"][vm_name]["/node/vm/mem"]["free"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Free"]._top()/1000.0)
      self._data["/node/vm"][vm_name]["/node/vm/mem"]["cache"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Cache"]._top()/1000.0)
      
   def _update_metrics_linux_vm_net(self):
      """Update metrics for linux VM net subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
            
      # global metrics
      self._data["/node/vm"][vm_name]["/node/vm/net"]["ssh"].append(
          self._data[hypervisor+"/vms"][vm_name]["accessible"]._top())
          
   def _update_metrics_linux_vm_net_if(self):
      vm_name=self.parent.parent.name
      hypervisor=self.parent.parent.hypervisor
      if_name=self.name
   
      # per-interface metrics
      prefix=self._vbox_api_prefix
      attrs_suffix = ["MAC", "V4/IP", "V4/Broadcast",
                    "V4/Netmask", "Status"]
      # translate data
      for suffix in attrs_suffix:
         attr="{}/Status".format(prefix)
         self._data["/node/vm"][vm_name]["/node/vm/net/if"][if_name]["state"].append(
            self._data[hypervisor+"/vms"][vm_name][attr]._top().lower())
         # XXX: per-interface instead of total rate
         attr="Net/Rate/Rx"
         self._data["/node/vm"][vm_name]["/node/vm/net/if"][if_name]["rx_bytes"].append(
            self._data[hypervisor+"/vms"][vm_name][attr]._top()/1000.0)
         attr="Net/Rate/Tx"
         self._data["/node/vm"][vm_name]["/node/vm/net/if"][if_name]["tx_bytes"].append(
            self._data[hypervisor+"/vms"][vm_name][attr]._top()/1000.0)        
   def _update_metrics_linux_vm_proc(self):
      """Update metrics for linux VM proc subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
         
   def _update_metrics_linux_kb_proc(self):
      """Update metrics for linux KB proc subservice

      """
      kb_name=self.parent.name
      framework=self.parent.framework
      
      # vpp/local
      if kb_name == "localhost":
         worker_count = self._data["vpp/stats/sys"]["/sys/num_worker_threads"]._top() 
      # vpp/gNMI
      else:
         worker_count = self._data[framework+"/gnmi"][kb_name]["/sys/num_worker_threads"]._top()
      
      self._data["/node/kb"][kb_name]["/node/kb/proc"]["worker_count"].append(
         worker_count)

   def _update_metrics_linux_kb_mem(self):
      """Update metrics for linux KB mem subservice

      """
      kb_name=self.parent.name
      framework=self.parent.framework
      
      # vpp/local
      if kb_name == "localhost":
         # stats-segment
         mem_total = self._data["vpp/stats/sys"]["/mem/statseg/total"]._top()/1000000.0
         mem_used = self._data["vpp/stats/sys"]["/mem/statseg/used"]._top()/1000000.0
         mem_free = mem_total-mem_used
         # buffers
         numa_node = "default-numa-0"
         buffer_free = self._data["vpp/stats/buffer-pool"][numa_node]["available"]._top()
         buffer_used = self._data["vpp/stats/buffer-pool"][numa_node]["used"]._top()
         buffer_total = buffer_free + buffer_used
         buffer_cache = self._data["vpp/stats/buffer-pool"][numa_node]["cached"]._top()         
      # vpp/gNMI
      else:
         # stats-segment
         mem_total = self._data[framework+"/gnmi"][kb_name]["/mem/statseg/total"]._top()/1000000.0
         mem_used = self._data[framework+"/gnmi"][kb_name]["/mem/statseg/used"]._top()/1000000.0
         mem_free = mem_total-mem_used
         # buffers
         buffer_free = self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/available"]._top()
         buffer_used = self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/used"]._top()
         buffer_total = buffer_free + buffer_used
         buffer_cache = self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/cached"]._top()
      
      self._data["/node/kb"][kb_name]["/node/kb/mem"]["total"].append(mem_total)
      self._data["/node/kb"][kb_name]["/node/kb/mem"]["free"].append(mem_free)
      self._data["/node/kb"][kb_name]["/node/kb/mem"]["buffer_total"].append(buffer_total)
      self._data["/node/kb"][kb_name]["/node/kb/mem"]["buffer_free"].append(buffer_free)
      self._data["/node/kb"][kb_name]["/node/kb/mem"]["buffer_cache"].append(buffer_cache)
      
   def _update_metrics_linux_kb_net(self):
      pass
      
   def _update_metrics_linux_kb_net_if(self):
      """Update metrics for linux KB net subservice

      """
      kb_name=self.parent.parent.name
      framework=self.parent.parent.framework
      if_name=self.name
      
      # vpp/local
      if kb_name == "localhost":
  
         metric_dict = self._data["/node/kb"][kb_name]["/node/kb/net/if"][if_name]
         md_dict = self._data["vpp/stats/if"][if_name]

         metric_dict["vector_rate"].append(
            self._data["vpp/stats/sys"]["/sys/vector_rate"]._top())
         metric_dict["rx_packets"].append(md_dict["/if/rx-packets"]._top())
         metric_dict["rx_bytes"].append(md_dict["/if/rx-bytes"]._top()/1000000.0)
         metric_dict["rx_error"].append(md_dict["/if/rx-error"]._top())
         metric_dict["rx_drop"].append(md_dict["/if/rx-miss"]._top())
         metric_dict["tx_packets"].append(md_dict["/if/tx-packets"]._top())
         metric_dict["tx_bytes"].append(md_dict["/if/tx-bytes"]._top()/1000000.0)
         metric_dict["tx_error"].append(md_dict["/if/tx-error"]._top())
                    
      # vpp/gNMI
      else: 
         metric_dict = self._data["/node/kb"][kb_name]["/node/kb/net/if"][if_name]
         md_dict = self._data[framework+"/gnmi"][kb_name]["net_if"][if_name]
         
         metric_dict["vector_rate"].append(
            self._data[framework+"/gnmi"][kb_name]["/sys/vector_rate"]._top())
         metric_dict["rx_packets"].append(md_dict["/if/rx/T0/packets"]._top())
         metric_dict["rx_bytes"].append(md_dict["/if/rx/T0/bytes"]._top()/1000000.0)
         metric_dict["rx_error"].append(md_dict["/if/rx-error/T0"]._top())
         metric_dict["rx_drop"].append(md_dict["/if/rx-miss/T0"]._top())  
         metric_dict["tx_packets"].append(md_dict["/if/tx/T0/packets"]._top())
         metric_dict["tx_bytes"].append(md_dict["/if/tx/T0/bytes"]._top()/1000000.0)
         metric_dict["tx_error"].append(md_dict["/if/tx-error/T0"]._top())
         #metric_dict["tx_drop"].append(md_dict["/if/tx/T0/packets"]._top())
         
   def _update_metrics_macos_bm_cpu(self):
      pass
   def _update_metrics_win_bm_cpu(self):
      pass

class Node(Subservice):
   """A device/physical node
   Includes 1 BM subservice, N VMs, N gnmi clients for VPP, 0-1 BM VPP

   """
   def __init__(self, _type, name, engine, parent=None):
      super(Node, self).__init__(_type, name, engine, parent=parent)
      self.dependencies = [Baremetal("bm", None, self.engine, parent=self)]

   def _update_metrics(self):
      """
      update metrics for this subservice 

      """
      pass

class Baremetal(Subservice):
   """Baremetal subservice assurance
   
   """
   def __init__(self, _type, name, engine, parent=None):
      super(Baremetal, self).__init__(_type, name, engine, parent=parent)
      
      deps = ["cpus", "sensors", "disks", "mem", "proc", "net"]
      self.dependencies = [Subservice(dep, None, self.engine, parent=self) for dep in deps]
      # init metrics for non-list RBs
      self._data["/node/bm/net/if"] = {}
      self._data["/node/bm/net"] = self._init_metrics_rb("net")
      self._data["/node/bm/mem"] = self._init_metrics_rb("mem")
      self._data["/node/bm/proc"] = self._init_metrics_rb("proc")

   def _update_metrics(self):
      """
      update metrics for this subservice 

      """
      pass

class VM(Subservice):
   """VM subservice assurance
   
   """
   def __init__(self, _type, name, engine, hypervisor, parent=None):
      super(VM, self).__init__(_type, name, engine, parent=parent)
      self.hypervisor=hypervisor
      
      deps = ["cpus", "mem", "net", "proc"]
      self.dependencies = [Subservice(dep, None, self.engine, parent=self) for dep in deps]
      # init metrics for non-list RBs
      self._data["/node/vm"][self.name] = {}
      self._data["/node/vm"][self.name]["/node/vm"] = self._init_metrics_rb("vm")
      self._data["/node/vm"][self.name]["/node/vm/cpus/cpu"] = {}
      self._data["/node/vm"][self.name]["/node/vm/net/if"] = {}
      self._data["/node/vm"][self.name]["/node/vm/proc"] = self._init_metrics_rb("proc")
      self._data["/node/vm"][self.name]["/node/vm/net"] = self._init_metrics_rb("net")
      self._data["/node/vm"][self.name]["/node/vm/mem"] = self._init_metrics_rb("mem")

   def _update_metrics(self):
      """
      update metrics for this subservice 

      """
      vm_name=self.name
      hypervisor=self.hypervisor
      self.active = self._data[hypervisor+"/vms"][vm_name]["state"]._top() == "Running"
      self._data["/node/vm"][vm_name]["/node/vm"]["active"].append(self.active)

   def del_metrics(self):
      """
      remove this VM metrics ringbuffers
      """
      del self._data["/node/vm"][self.name]
      
class KBNet(Subservice):
   """Kernel Bypassing Networks subservice assurance
   
   """
   def __init__(self, _type, name, engine, framework, parent=None):
      super(KBNet, self).__init__(_type, name, engine, parent=parent)
      self.framework=framework
      
      deps = ["proc", "mem", "net"]
      self.dependencies = [Subservice(dep, None, self.engine, parent=self) for dep in deps]
      # init metrics for non-list RBs
      self._data["/node/kb"][self.name] = {}
      self._data["/node/kb"][self.name]["/node/kb"] = self._init_metrics_rb("kb")
      self._data["/node/kb"][self.name]["/node/kb/net/if"] = {}
      self._data["/node/kb"][self.name]["/node/kb/mem"] = self._init_metrics_rb("mem")
      self._data["/node/kb"][self.name]["/node/kb/proc"] = self._init_metrics_rb("proc")

   def _update_metrics(self):
      """
      update metrics for this subservice 

      """
      kb_name=self.name
      framework=self.framework
      
      if kb_name == "localhost":
         self.active = True
      else:
         self.active = self._data[framework+"/gnmi"][kb_name]["status"]._top() == "synced"
      self._data["/node/kb"][kb_name]["/node/kb"]["active"].append(self.active)

   def del_metrics(self):
      """
      remove this VM metrics ringbuffers
      """
      del self._data["/node/kb"][self.name]


