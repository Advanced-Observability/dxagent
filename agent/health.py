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

from agent.rbuffer import init_rb_dict, Severity
from agent.sysinfo import SysInfo
from agent import AGENT_INPUT_RATE
from agent.symptoms import Symptom, RuleException

class Metric():
   def __init__(self, name, node, _type, unit, islist):
      self.name=name
      self.node=node
      self._type=_type
      self.unit=unit
      self.islist=int(islist)
      
class HealthEngine():
   def __init__(self, data, info, parent):      
      self._data = data
      self.info = info
      self.parent = parent
      self.sysinfo = SysInfo()
      self._data["vm"], self._data["kb"] = {}, {}
      self._data["symptoms"] = []
      self.sample_per_min = int(60/AGENT_INPUT_RATE)
      
      self._read_metrics_file()
      self._read_rule_file()
      self._build_dependency_graph()
      
   def _read_rule_file(self):
      self._symptoms=[]
      file_loc = os.path.join(self.parent.args.ressources_dir,"rules.csv")
      metrics = list(itertools.chain.from_iterable(self.metrics_attrs.values()))
      
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
            self._symptoms.append(symptom)
      
   def _read_metrics_file(self):
      self.metrics_attrs, self.metrics_types, self.metrics_units = {}, {}, {}
      self.metrics = {}
      file_loc = os.path.join(self.parent.args.ressources_dir,"metrics.csv")
      with open(file_loc) as csv_file:
         for r in csv.DictReader(csv_file):
            name,_type,unit,islist,subservice= r["name"],r["type"],r["unit"],r["is_list"],r["subservice"]
            key = (subservice,)
            self.metrics_attrs.setdefault(key,[]).append(name)
            self.metrics_types.setdefault(key,[]).append(getattr(builtins, _type))
            self.metrics_units.setdefault(key,[]).append(unit)
            
            metric = Metric(name, subservice, getattr(builtins, _type), unit, islist)
            self.metrics[name] = metric

   def _build_dependency_graph(self):
      """
      build deps graph and insert symptoms in nodes
      """
      self.node = Node(self.sysinfo.node, self)

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

   def add_vm(self, name, hypervisor="virtualbox"):
      self.node.add_vm(name, hypervisor)
   def add_kbnet(self, name, framework="vpp"):
      self.node.add_kbnet(name, framework)
   def remove_vm(self, name):
      self.node.remove_vm(name)
   def remove_kbnet(self, name):
      self.node.remove_kbnet(name)
      
   def update_health(self):
      self._update_dependency_graph()
      self.node.update_metrics()
      self._data["symptoms"].clear()
      self._data["symptoms"] = self.node.update_symptoms()
      #self.info()
      #self.walk(self.node)
      
   def walk(self, current):
      self.info("path: {} fullname: {}".format(current.path, current.fullname))
      #self.info("+".join([s.name for s in current.symptoms]))
      for dep in current.dependencies:
         self.walk(dep)

   def _update_metrics_bm(self):
      pass

   def _update_metrics_vm(self):
      pass

   def _update_metrics_kb(self):
      pass
      
class Subservice():
   """
   
   """
   def __init__(self, _type, name, engine, parent=None, is_leaf=False):
      # The type of subservice e.g., vm, bm, kb, node, net, if, etc
      self._type = _type
      # The unique identifier of the subservice
      # e.g., VM id, VPP id, or net, cpu, proc for Subservices
      self.name = name
      self.engine = engine
      self._data = self.engine._data
      self.sysinfo = self.engine.sysinfo
      self.parent = parent
      self.is_leaf = is_leaf
      self.dependencies = []
      self.active = True
      self.fullname = self.find_fullname()
      self.path = self.find_path()
      self.health_score = 100
      self.symptoms = [symptom for symptom in self.engine._symptoms if symptom.path == self.path]
      
   def find_fullname(self):
      """
      compute fullname string, similar to the path string
      with additional name/index (e.g.,
         node:machine1.vm:vagrant_default_158504808.net.if:vboxnet0 )
         
         compatible with gRPC path
      """
      fullname="/"+self._type
      if self.name:
         fullname = "{}[key={}]".format(fullname,self.name)
      if self.parent:
         fullname = "{}{}".format(self.parent.fullname,fullname)
      return fullname
      
   def find_path(self):
      """
      compute path string (e.g., node.bm.sensors.fan)
      """
      path=self._type
      if self.parent:
         path = "{}.{}".format(self.parent.path,path)
      return path

   def __contains__(self, item):
      return any(subservice._type == item for subservice in self.dependencies)

   def del_metrics(self):
      """
      subservice cleanup, overload in child if needed.
      """
      pass
   def update_symptoms(self):
      """
      bottom-up check of symptoms and update of health score
      
      @return the list of positive symptoms
      """
      self.health_score = 100
      positives = []
      # update symptoms&health_score from deps
      for subservice in self.dependencies:
         positives.extend(subservice.update_symptoms())
         self.health_score = min(0,self.health_score-(100-subservice.health_score))
      # update for node
      for symptom in self.symptoms:
         result = symptom.check(self._data)
         if result:
            #self.engine.info(symptom.name)
            positives.append(symptom)
            self.health_score = min(0,self.health_score-symptom.weight)
      return positives
         
   def get_health_score(self):
      return self.health_score

   def _init_metrics_rb(self, subservice):
      """
      return metrics ringbuffers for subservices monitoring

      @param subservice the name of the subservice for which rbs
                        are getting initialized

      XXX: class name != parent subservice name in metrics.csv
      
      """
      key = (subservice,)
      attrs = self.engine.metrics_attrs[key]
      types = self.engine.metrics_types[key]
      units = self.engine.metrics_units[key]
      return init_rb_dict(attrs, metric=True,
                          types=types,
                          units=units)
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
         ("Linux","node.bm.cpu")     : self._update_metrics_linux_bm_cpu,
         ("Linux","node.bm.sensors") : self._update_metrics_linux_bm_sensors,
         ("Linux","node.bm.disk")    : self._update_metrics_linux_bm_disk,
         ("Linux","node.bm.mem")     : self._update_metrics_linux_bm_mem,
         ("Linux","node.bm.proc")    : self._update_metrics_linux_bm_proc,
         ("Linux","node.bm.net")     : self._update_metrics_linux_bm_net,
        # ("Linux","node.bm.net.if")  : self._update_metrics_linux_bm_net_if,
         ("Linux","node.vm.cpu")     : self._update_metrics_linux_vm_cpu,
         ("Linux","node.vm.mem")     : self._update_metrics_linux_vm_mem,
         ("Linux","node.vm.net")     : self._update_metrics_linux_vm_net,
         ("Linux","node.vm.proc")    : self._update_metrics_linux_vm_proc,
         ("Linux","node.kb.proc")    : self._update_metrics_linux_kb_proc,
         ("Linux","node.kb.mem")     : self._update_metrics_linux_kb_mem,
         ("Linux","node.kb.net")     : self._update_metrics_linux_kb_net,
         
        
         ("Windows","node.bm.cpu") : self._update_metrics_win_bm_cpu,
         ("MacOS","node.bm.cpu")   : self._update_metrics_macos_bm_cpu,
      }
      return funcs[key]()

   def _update_metrics_linux_bm_cpu(self):
      """Update metrics for linux BM cpu subservice

      """
      # init metric rbs if needed
      if "node.bm.cpu" not in self._data:
         self._data["node.bm.cpu"] = {}
         for cpu_label in self._data["stat/cpu"]:
            self._data["node.bm.cpu"][cpu_label] = self._init_metrics_rb("cpu")

      # fill them
      for cpu_label in self._data["stat/cpu"]:
         self._data["node.bm.cpu"][cpu_label]["idle_time"].append(
            self._data["stat/cpu"][cpu_label]["idle_all_perc"]._top())
         self._data["node.bm.cpu"][cpu_label]["system_time"].append(
            self._data["stat/cpu"][cpu_label]["system_all_perc"]._top())
         self._data["node.bm.cpu"][cpu_label]["user_time"].append(
            self._data["stat/cpu"][cpu_label]["user_perc"]._top())
         self._data["node.bm.cpu"][cpu_label]["guest_time"].append(
            self._data["stat/cpu"][cpu_label]["guest_all_perc"]._top())

   def _update_metrics_linux_bm_sensors(self):
      """Update metrics for linux BM sensors subservice

      """
      # init metric rbs if needed
      if "node.bm.sensors" not in self._data:
         self._data["node.bm.sensors"] = {}
         # thermal zones
         for zone_label,d in self._data["sensors/thermal"].items():
            zone_label += ":"+d["type"]._top()
            self._data["node.bm.sensors"][zone_label] = self._init_metrics_rb("sensors")
            self._data["node.bm.sensors"][zone_label]["type"].append("zone")
         # fan sensors
         for fan_label,d in self._data["sensors/fans"].items():
            fan_label += ":"+d["label"]._top()
            self._data["node.bm.sensors"][fan_label] = self._init_metrics_rb("sensors")
            self._data["node.bm.sensors"][fan_label]["type"].append("fan")
         # core sensors
         for core_label,d in self._data["sensors/coretemp"].items():
            core_label += ":"+d["label"]._top()
            self._data["node.bm.sensors"][core_label] = self._init_metrics_rb("sensors")
            self._data["node.bm.sensors"][core_label]["type"].append("cpu")

      # thermal zones
      for zone_label,d in self._data["sensors/thermal"].items():
         zone_label += ":"+d["type"]._top()
         attr_mapping = {"temperature": "input_temp",}
         for attr,metric in attr_mapping.items():
            if attr in d:
               self._data["node.bm.sensors"][zone_label][metric].append(
                 d[attr]._top())
      # fan sensors
      for fan_label,d in self._data["sensors/fans"].items():
         fan_label += ":"+d["label"]._top()
         attr_mapping = {"input": "input_fanspeed",
                         "temperature": "input_temp",}
         for attr,metric in attr_mapping.items():
            if attr in d:
               self._data["node.bm.sensors"][fan_label][metric].append(
                 d[attr]._top())
      # core sensors
      for core_label,d in self._data["sensors/coretemp"].items():
         core_label += ":"+d["label"]._top()
         attr_mapping = {"input": "input_temp",
                         "max": "max_temp",
                         "critical": "critical_temp",}
         for attr,metric in attr_mapping.items():
            if attr in d:
               self._data["node.bm.sensors"][core_label][metric].append(
                 d[attr]._top())

   def _update_metrics_linux_bm_disk(self):
      """Update metrics for linux BM disk subservice

      """
      # init metric rbs if needed
      if "node.bm.disk" not in self._data:
         self._data["node.bm.disk"] = {}
      previous=set(self._data["node.bm.disk"].keys())
      current=set(list(self._data["diskstats"].keys())
                  +list(self._data["swaps"].keys()))
      # add new disks
      for disk in current-previous:
         self._data["node.bm.disk"][disk] = self._init_metrics_rb("disk")
      # remove unmounted disks
      for disk in previous-current:
         del self._data["node.bm.disk"][disk]

      for disk,rbs in self._data["diskstats"].items():
         self._data["node.bm.disk"][disk]["type"].append(
            rbs["fs_vfstype"]._top())
         self._data["node.bm.disk"][disk]["total_user"].append(
            rbs["total"]._top()/1000.0)
         self._data["node.bm.disk"][disk]["free_user"].append(
            rbs["free_user"]._top()/1000.0)
         self._data["node.bm.disk"][disk]["read_time"].append(
            rbs["perc_reading"]._top())
         self._data["node.bm.disk"][disk]["write_time"].append(
            rbs["perc_writting"]._top())
         self._data["node.bm.disk"][disk]["io_time"].append(
            rbs["perc_io"]._top())
         self._data["node.bm.disk"][disk]["discard_time"].append(
            rbs["perc_discarding"]._top())

      for disk,rbs in self._data["swaps"].items():
         self._data["node.bm.disk"][disk]["type"].append(
            "swap")#rbs["type"]._top()
         self._data["node.bm.disk"][disk]["total_user"].append(
            rbs["size"]._top()/1000.0)
         self._data["node.bm.disk"][disk]["swap_used"].append(
            rbs["used"]._top())

   def _update_metrics_linux_bm_mem(self):
      """Update metrics for linux BM mem subservice

      """
      self._data["node.bm.mem"]["total"].append(
         self._data["meminfo"]["MemTotal"]._top()/1000)
      self._data["node.bm.mem"]["free"].append(
         self._data["meminfo"]["MemFree"]._top()/1000)
      self._data["node.bm.mem"]["available"].append(
         self._data["meminfo"]["MemAvailable"]._top()/1000)
      self._data["node.bm.mem"]["buffers"].append(
         self._data["meminfo"]["Buffers"]._top()/1000)
      self._data["node.bm.mem"]["cache"].append(
         self._data["meminfo"]["Cached"]._top()/1000)
      self._data["node.bm.mem"]["active"].append(
         self._data["meminfo"]["Active"]._top()/1000)
      self._data["node.bm.mem"]["inactive"].append(
         self._data["meminfo"]["Inactive"]._top()/1000)
      self._data["node.bm.mem"]["pages_total"].append(
         self._data["meminfo"]["HugePages_Total"]._top())
      self._data["node.bm.mem"]["pages_free"].append(
         self._data["meminfo"]["HugePages_Free"]._top())
      self._data["node.bm.mem"]["pages_reserved"].append(
         self._data["meminfo"]["HugePages_Rsvd"]._top())
      self._data["node.bm.mem"]["pages_size"].append(
         self._data["meminfo"]["Hugepagesize"]._top()/1000)

   def _update_metrics_linux_bm_proc(self):
      """Update metrics for linux BM proc subservice

      """
      self._data["node.bm.proc"]["total_count"].append(
         self._data["stats_global"]["proc_count"]._top())
      self._data["node.bm.proc"]["run_count"].append(
         self._data["stats_global"]["run_count"]._top())
      self._data["node.bm.proc"]["sleep_count"].append(
         self._data["stats_global"]["sleep_count"]._top())
      self._data["node.bm.proc"]["idle_count"].append(
         self._data["stats_global"]["idle_count"]._top())
      self._data["node.bm.proc"]["wait_count"].append(
         self._data["stats_global"]["wait_count"]._top())
      self._data["node.bm.proc"]["zombie_count"].append(
         self._data["stats_global"]["zombie_count"]._top())
      self._data["node.bm.proc"]["dead_count"].append(
         self._data["stats_global"]["dead_count"]._top())

   def _update_metrics_linux_bm_net(self):
      """Update metrics for linux BM net subservice

      """
      # init metric rbs if needed
      previous=set(self._data["node.bm.net.if"].keys())
      current=set(self._data["net/dev"].keys())
      # add new ifs
      for net in current-previous:
         self._data["node.bm.net.if"][net] = self._init_metrics_rb("if")
      # remove down ifs
      for net in previous-current:
         del self._data["node.bm.net.if"][net]
         
      # non interface-related fields
      for field, rb in self._data["snmp"].items():
         self._data["node.bm.net"]["snmp_"+field].append(rb._top())
         
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
                      "operstate": "state",
                      "mtu": "mtu",
                      "numa_node": "numa",
                      "local_cpulist": "cpulist",
                      "tx_queue_len": "tx_queue"}
      for net,rbs in self._data["net/dev"].items():
         # direct mapping
         for attr,metric in attr_mapping.items():
            if attr in rbs:
               self._data["node.bm.net.if"][net][metric].append(
                 rbs[attr]._top())
         # other fields
         if "ip4_gw_addr" in rbs:
            self._data["node.bm.net.if"][net]["gw_in_arp"].append(
               rbs["ip4_gw_addr"]._top() in self._data["net/arp"])

   def _update_metrics_linux_vm_cpu(self):
      """Update metrics for linux VM cpu subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
      self._data["vm"][vm_name]["node.vm.cpu"]["cpu_count"].append(
         self._data[hypervisor+"/vms"][vm_name]["cpu"]._top())
      self._data["vm"][vm_name]["node.vm.cpu"]["user_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/User"]._top())
      self._data["vm"][vm_name]["node.vm.cpu"]["system_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/Kernel"]._top())
      self._data["vm"][vm_name]["node.vm.cpu"]["idle_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/Idle"]._top())
   
   def _update_metrics_linux_vm_mem(self):
      """Update metrics for linux VM mem subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
      self._data["vm"][vm_name]["node.vm.mem"]["total"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Total"]._top()/1000.0)
      self._data["vm"][vm_name]["node.vm.mem"]["free"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Free"]._top()/1000.0)
      self._data["vm"][vm_name]["node.vm.mem"]["cache"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Cache"]._top()/1000.0)
      
   def _update_metrics_linux_vm_net(self):
      """Update metrics for linux VM net subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor

      # per-interface metrics
      prefix="/VirtualBox/GuestInfo/Net/"
      attrs_suffix = ["MAC", "V4/IP", "V4/Broadcast",
                    "V4/Netmask", "Status"]
      net_count=(self._data["virtualbox/vms"][vm_name]
                          ["/VirtualBox/GuestInfo/Net/Count"])._top()
      for net_index in range(net_count):
         # add if if needed
         attr="{}{}/Name".format(prefix, net_index)
         if_name=self._data[hypervisor+"/vms"][vm_name][attr]._top()
         if if_name not in self._data["vm"][vm_name]["node.vm.net.if"]:
            self._data["vm"][vm_name]["node.vm.net.if"][if_name] = self._init_metrics_rb("if")
         # translate data
         for suffix in attrs_suffix:
            # if status
            attr="{}{}/Status".format(prefix, net_index)
            self._data["vm"][vm_name]["node.vm.net.if"][if_name]["state"].append(
               self._data[hypervisor+"/vms"][vm_name][attr]._top().lower())
            # XXX: per-interface instead of total rate
            attr="Net/Rate/Rx"
            self._data["vm"][vm_name]["node.vm.net.if"][if_name]["rx_bytes"].append(
               self._data[hypervisor+"/vms"][vm_name][attr]._top()/1000.0)
            attr="Net/Rate/Tx"
            self._data["vm"][vm_name]["node.vm.net.if"][if_name]["tx_bytes"].append(
               self._data[hypervisor+"/vms"][vm_name][attr]._top()/1000.0)
            
      # global metrics
      self._data["vm"][vm_name]["node.vm.net"]["ssh"].append(
          self._data[hypervisor+"/vms"][vm_name]["accessible"]._top())
          
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
      self._data["kb"][kb_name]["node.kb.proc"]["worker_count"].append(
         self._data[framework+"/gnmi"][kb_name]["/sys/num_worker_threads"]._top())
      
   def _update_metrics_linux_kb_mem(self):
      """Update metrics for linux KB mem subservice

      """
      kb_name=self.parent.name
      framework=self.parent.framework
      # stats-segment
      mem_total = self._data[framework+"/gnmi"][kb_name]["/mem/statseg/total"]._top()/1000000.0
      mem_used = self._data[framework+"/gnmi"][kb_name]["/mem/statseg/used"]._top()/1000000.0
      mem_free = mem_total-mem_used
      self._data["kb"][kb_name]["node.kb.mem"]["total"].append(mem_total)
      self._data["kb"][kb_name]["node.kb.mem"]["free"].append(mem_free)
      # buffers
      buffer_free = self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/available"]._top()
      buffer_used = self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/used"]._top()
      buffer_total = buffer_free + buffer_used
      self._data["kb"][kb_name]["node.kb.mem"]["buffer_total"].append(buffer_total)
      self._data["kb"][kb_name]["node.kb.mem"]["buffer_free"].append(buffer_free)
      self._data["kb"][kb_name]["node.kb.mem"]["buffer_cache"].append(self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/cached"]._top())
      
   def _update_metrics_linux_kb_net(self):
      """Update metrics for linux KB net subservice

      """
      kb_name=self.parent.name
      framework=self.parent.framework
      for if_name, d in self._data[framework+"/gnmi"][kb_name]["net_if"].items():
         # create interface entry if needed
         if if_name not in self._data["kb"][kb_name]["node.kb.net.if"]:
            self._data["kb"][kb_name]["node.kb.net.if"][if_name] = self._init_metrics_rb("if")
         
         metric_dict = self._data["kb"][kb_name]["node.kb.net.if"][if_name]
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
   def __init__(self, name, engine, parent=None):
      super(Node, self).__init__("node", name, engine, parent=parent)
      self.dependencies = [Baremetal("", self.engine, parent=self)]
      
   def add_vm(self, name, hypervisor):
      self.dependencies.append(VM(name, self.engine, hypervisor, parent=self))
   def add_kbnet(self, name, framework):
      self.dependencies.append(KBNet(name, self.engine, framework, parent=self))
   def remove_vm(self, name):
      for i, subservice in enumerate(self.dependencies):
         if isinstance(subservice, VM) and subservice.name == name:
            subservice.del_metrics()
            del self.dependencies[i]
            break
   def remove_kbnet(self, name):
      for i, subservice in enumerate(self.dependencies):
         if isinstance(subservice, KBNet) and subservice.name == name:
            subservice.del_metrics()
            del self.dependencies[i]
            break

   def _update_metrics(self):
      """
      update metrics for this subservice 

      """
      pass

class Baremetal(Subservice):
   """Baremetal subservice assurance
   
   """
   def __init__(self, name, engine, parent=None):
      super(Baremetal, self).__init__("bm", name, engine, parent=parent)
      
      deps = ["cpu", "sensors", "disk", "mem", "proc", "net"]
      self.dependencies = [Subservice(dep, "", self.engine, parent=self) for dep in deps]
      # init metrics for non-list RBs
      self._data["node.bm.net.if"] = {}
      self._data["node.bm.net"] = self._init_metrics_rb("net")
      self._data["node.bm.mem"] = self._init_metrics_rb("mem")
      self._data["node.bm.proc"] = self._init_metrics_rb("proc")

   def _update_metrics(self):
      """
      update metrics for this subservice 

      """
      pass

class VM(Subservice):
   """VM subservice assurance
   
   """
   def __init__(self, name, engine, hypervisor, parent=None):
      super(VM, self).__init__("vm", name, engine, parent=parent)
      self.hypervisor=hypervisor
      
      deps = ["cpu", "mem", "net", "proc"]
      self.dependencies = [Subservice(dep, "", self.engine, parent=self) for dep in deps]
      # init metrics for non-list RBs
      self._data["vm"][self.name] = {}
      self._data["vm"][self.name]["node.vm"] = self._init_metrics_rb("vm")
      self._data["vm"][self.name]["node.vm.net.if"] = {}
      self._data["vm"][self.name]["node.vm.proc"] = self._init_metrics_rb("proc")
      self._data["vm"][self.name]["node.vm.net"] = self._init_metrics_rb("net")
      self._data["vm"][self.name]["node.vm.mem"] = self._init_metrics_rb("mem")
      self._data["vm"][self.name]["node.vm.cpu"] = self._init_metrics_rb("cpu")

   def _update_metrics(self):
      """
      update metrics for this subservice 

      """
      vm_name=self.name
      hypervisor=self.hypervisor
      
      self.active = self._data[hypervisor+"/vms"][vm_name]["state"]._top() == "Running"
      self._data["vm"][vm_name]["node.vm"]["active"].append(self.active)

   def del_metrics(self):
      """
      remove this VM metrics ringbuffers
      """
      del self._data["vm"][self.name]
      
class KBNet(Subservice):
   """Kernel Bypassing Networks subservice assurance
   
   """
   def __init__(self, name, engine, framework, parent=None):
      super(KBNet, self).__init__("kb", name, engine, parent=parent)
      self.framework=framework
      
      deps = ["proc", "mem", "net"]
      self.dependencies = [Subservice(dep, "", self.engine, parent=self) for dep in deps]
      # init metrics for non-list RBs
      self._data["kb"][self.name] = {}
      self._data["kb"][self.name]["node.kb"] = self._init_metrics_rb("kb")
      self._data["kb"][self.name]["node.kb.net.if"] = {}
      self._data["kb"][self.name]["node.kb.mem"] = self._init_metrics_rb("mem")
      self._data["kb"][self.name]["node.kb.proc"] = self._init_metrics_rb("proc")

   def _update_metrics(self):
      """
      update metrics for this subservice 

      """
      kb_name=self.name
      framework=self.framework
      
      self.active = self._data[framework+"/gnmi"][kb_name]["status"]._top() == "synced"
      self._data["kb"][kb_name]["node.kb"]["active"].append(self.active)

   def del_metrics(self):
      """
      remove this VM metrics ringbuffers
      """
      del self._data["kb"][self.name]


