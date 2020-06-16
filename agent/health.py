"""
health.py

   Key Performance Indicators & symptom rules

@author: K.Edeline

"""
import csv
import os
import builtins
import sys
import ast
import operator

from agent.rbuffer import init_rb_dict, Severity
from agent.sysinfo import SysInfo
from agent import AGENT_INPUT_RATE

class RuleException(Exception):
   """
   RuleException(Exception)
   """
   
   def __init__(self, value):
      self.value = value
   def __str__(self):
      return repr(self.value)
      
class Symptom():
   def __init__(self, name, severity, rule, engine):
      self.name = name
      self.severity = severity
      self.rule = rule
      self.engine = engine
      self._compile_rule()

   def _compile_rule(self):
      class RewriteName(ast.NodeTransformer):
         def visit_Name(self, node):
            # only if parent is not a func
            if node.id.startswith("_"):
               return node
            return ast.Call(func=ast.Name(id="access", ctx=node.ctx),
                            args=[ast.Constant(value=node.id)],
                            keywords=[])
                            
      # 1. string-level replacement
      alias=[("1min","_1min"), ("5min","_5min")]
      for old,new in alias:
         self.rule=self.rule.replace(old,new)
      # 2. ast-level replacement
      node = ast.parse(self.rule, mode='eval')
      node = ast.fix_missing_locations(RewriteName().visit(node))
      self._o=compile(node, '<string>', 'eval')
         
   def check(self, data):
      """
      Check if the node exhibit this symptom
      
      """
      engine = self.engine
      kpis = self.engine.kpis
      
      class Comparator():
         def __init__(self, rb):
            self.islist=isinstance(rb,list)
            self.rb=rb
            # how many samples are considered
            self.count=1
         def indexes(self):
            return [index for (index,_) in self.rb]
         def compare(self, other, _operator):
            """
            compare a Comparator with a constant or another Comparator
            """
            if not self.islist:
               # not enough samples, skip
               if len(self.rb) < self.count:
                  return False
               return all(_operator(v,other) for v in self.rb._tops(self.count))
            ret=[]
            for index, rb in self.rb:
               if len(rb) < self.count:
                  continue
               if all(_operator(v,other) for v in rb._tops(self.count)):
                  ret.append((index,rb))
            # return a comparator if it matched
            if not ret:
               return False
            self.rb = ret
            return self         
         
         def __lt__(self, other):
            return self.compare(other, operator.__lt__)
         def __le__(self, other):
            return self.compare(other, operator.__le__)
         def __eq__(self, other):
            return self.compare(other, operator.__eq__)
         def __ne__(self, other):
            return self.compare(other, operator.__ne__)
         def __gt__(self, other):
            return self.compare(other, operator.__gt__)
         def __ge__(self, other):
            return self.compare(other, operator.__ge__)
            
         def __and__(self, other):
            engine.info("and")
            if (not self.islist 
                 or not isinstance(other,Comparator) 
                 or not other.islist):
               return self and other
            intersection=list(set(self.indexes) & set(other.indexes))
            self.rb = filter(lambda e: e[0] in intersection, self.rb)
            if not self.rb:
               return False
            return self
            
         def __or__(self, other):
            engine.info("or")
            if (not self.islist 
                 or not isinstance(other,Comparator) 
                 or not other.islist):
               return self and other
            for e in other.rb:
               if e not in self.rb:
                  self.rb.append(e)
            if not self.rb:
               return False
            return self
      
      def access(var):
         kpi = kpis[var]
         prefix=kpi.prefix
         split = var.split("_")
         
         if split[0] == "vm" or split[0] == "kb":
            prefix2=split[0]
            if not kpi.islist:
               return Comparator([(dev, b[var]) for dev,b in data[prefix2].items()])
            # double list
            ret=[]
            for dev,b in data[prefix2].items():
               ret += [(dev+":"+dev2,rb[var]) for dev2,rb in b[prefix].items()]
            return Comparator(ret)
               
         if not kpi.islist:
            return Comparator(data[prefix][var])
         return Comparator([(dev, b[var]) for dev,b in data[prefix].items()])
         
      def _1min(rb):
         rb.count = engine.sample_per_min
         return rb
      def _5min(var):
         rb.count = engine.sample_per_min*5
         return rb
         
      ret=eval(self._o, globals(), locals())
      
      try:
         self.args = []
         if ret:
            if isinstance(ret, Comparator):
               #engine.info(ret.rb)
               self.args = ret.indexes()
            return True
         return False
      except Exception as e:
         self.engine.info("Evaluating rule {} raised error ".format(self.rule, e))
         return False
      
   def __str__(self):
      return "{} {} {}".format(self.name, self.severity, self.rule)

class KPI():
   def __init__(self, name, _type, unit, islist):
      self.name=name
      self._type=_type
      self.unit=unit
      self.islist=int(islist)
      split=name.split("_")
      if len(split) >= 3 and split[2] in ["if"]:
         self.prefix="_".join(split[:3])
      else:
         self.prefix="_".join(split[:2])
      

class HealthEngine():
   def __init__(self, data, info, parent):      
      self._data = data
      self.info = info
      self.parent = parent
      self.sysinfo = SysInfo()
      self._data["vm"], self._data["kb"] = {}, {}
      self._data["symptoms"] = []
      self.sample_per_min = int(60/AGENT_INPUT_RATE)
      
      self._read_kpi_file()
      self._read_rule_file()
      self._build_dependency_graph()
      
   def _safe_rule(self, rule):
      return True
      
   def _read_rule_file(self):
      self.symptoms=[]
      file_loc = os.path.join(self.parent.args.ressources_dir,"rules.csv")
      with open(file_loc) as csv_file:
         for r in csv.DictReader(csv_file):
            name = r["name"]
            try:
               severity = Severity[str.upper(r["severity"])]
            except KeyError as e:
               self.info("Invalid rule Severity: {}".format(r["severity"]))
               continue
            rule = r["rule"]
            if not self._safe_rule(rule):
               self.info("Invalid rule: {}".format(rule))
               continue
            self.symptoms.append(Symptom(name, severity, rule, self))
#            try:
#               self.symptoms.append(Symptom(name, severity, rule, self))
#            except Exception as e:
#               self.info("Invalid rule syntax: {}".format(rule))
#               continue
      
   def _read_kpi_file(self):
      self.kpi_attrs, self.kpi_types, self.kpi_units = {}, {}, {}
      self.kpis = {}
      file_loc = os.path.join(self.parent.args.ressources_dir,"kpi.csv")
      with open(file_loc) as csv_file:
         for r in csv.DictReader(csv_file):
            name,_type,unit,islist= r["name"], r["type"],r["unit"],r["is_list"]
            # we use (node,subservice) tuples as key
            # e.g., ("bm", "net")
            split = name.split('_')
            parent = split[0]
            # subservice name might need an extension when it includes
            # both list and non-list dependencies (ie., bm_net_if and bm_net_snmp
            # or vm_net_if and other vm_net_ attrs)
            dependency = "_".join(split[1:3]) if len(split) >= 3 and split[2] in ["if"] else split[1]
            
            key = (parent, dependency)
            self.kpi_attrs.setdefault(key,[]).append(name)
            # string to type conversion
            self.kpi_types.setdefault(key,[]).append(getattr(builtins, _type))
            self.kpi_units.setdefault(key,[]).append(unit)
            kpi = KPI(name, getattr(builtins, _type), unit, islist)
            self.kpis[name] = kpi

   def _build_dependency_graph(self):
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

   def update_kpis(self):
      """
      Update deps graph and subservices KPIs.

      """
      self._update_dependency_graph()
      self.node.update_kpis()

   def _update_kpis_bm(self):
      pass

   def _update_kpis_vm(self):
      pass

   def _update_kpis_kb(self):
      pass

   def update_symptoms(self):
      self._data["symptoms"].clear()
      for symptom in self.symptoms:
         result = symptom.check(self._data)
         if result:
            self.info(symptom.name)
            self._data["symptoms"].append(symptom)
      
            
class Subservice():
   """
   
   """
   def __init__(self, name, engine, parent=None, is_leaf=False):
      # The unique identifier of the subservice
      # e.g., VM id, VPP id, or net, cpu, proc for Subservices
      self.name = name
      self.engine = engine
      self._data = self.engine._data
      self.sysinfo = self.engine.sysinfo
      self.parent = parent
      self.is_leaf = is_leaf
      self.dependencies = []
      # The type of subservice e.g., Subservice, VM, BareMetal, etc
      self._type = type(self).__name__
      self.fullname = self._type+"."+self.name
      self.active = False

   def __contains__(self, item):
      return any(subservice.name == item for subservice in self.dependencies)

   def del_kpis(self):
      """
      subservice cleanup, overload in child if needed.
      """
      pass
   def get_symptoms(self):
      for subservice in self.dependencies:
         pass
   def get_health_score(self):
      return self.health_score

   def _init_kpis_rb(self, parent, dependency):
      """
      return KPIs ringbuffers for subservices monitoring

      @param parent the name of the parent node
      @param dependency the name of the subservice for which rbs
                        are getting initialized

      XXX: class name != parent subservice name in kpi.csv
      
      """
      category = parent+"_"+dependency
      attrs = self.engine.kpi_attrs[(parent, dependency)]
      types = self.engine.kpi_types[(parent, dependency)]
      units = self.engine.kpi_units[(parent, dependency)]
      return init_rb_dict(attrs,
                          types=types,
                          units=units)
   def update_kpis(self):
      """
      update KPIs for this subservice and its dependencies

      """
      self._update_kpis()
      if not self.active:
         return
      for subservice in self.dependencies:
         subservice.update_kpis()

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      Pick the right function based on host OS and subservice.
      
      """
      key = (self.sysinfo.system,
             self.parent._type if self.parent else None, 
             self.name)
      funcs = {
         ("Linux","Baremetal","cpu")     : self._update_kpis_linux_bm_cpu,
         ("Linux","Baremetal","sensors") : self._update_kpis_linux_bm_sensors,
         ("Linux","Baremetal","disk")    : self._update_kpis_linux_bm_disk,
         ("Linux","Baremetal","mem")     : self._update_kpis_linux_bm_mem,
         ("Linux","Baremetal","proc")    : self._update_kpis_linux_bm_proc,
         ("Linux","Baremetal","net")     : self._update_kpis_linux_bm_net,
         ("Linux","VM","cpu")  : self._update_kpis_linux_vm_cpu,
         ("Linux","VM","mem")  : self._update_kpis_linux_vm_mem,
         ("Linux","VM","net")  : self._update_kpis_linux_vm_net,
         ("Linux","VM","proc") : self._update_kpis_linux_vm_proc,
         ("Linux","KBNet","proc") : self._update_kpis_linux_kb_proc,
         ("Linux","KBNet","mem")  : self._update_kpis_linux_kb_mem,
         ("Linux","KBNet","net")  : self._update_kpis_linux_kb_net,
        
         ("Windows","BareMetal","cpu") : self._update_kpis_win_bm_cpu,
         ("MacOS","BareMetal","cpu") : self._update_kpis_macos_bm_cpu,
      }
      return funcs[key]()

   def _update_kpis_linux_bm_cpu(self):
      """Update KPIs for linux BM cpu subservice

      """
      # init KPI rbs if needed
      if "bm_cpu" not in self._data:
         self._data["bm_cpu"] = {}
         for cpu_label in self._data["stat/cpu"]:
            self._data["bm_cpu"][cpu_label] = self._init_kpis_rb("bm", "cpu")

      # fill them
      for cpu_label in self._data["stat/cpu"]:
         self._data["bm_cpu"][cpu_label]["bm_cpu_idle_time"].append(
            self._data["stat/cpu"][cpu_label]["idle_all_perc"]._top())
         self._data["bm_cpu"][cpu_label]["bm_cpu_system_time"].append(
            self._data["stat/cpu"][cpu_label]["system_all_perc"]._top())
         self._data["bm_cpu"][cpu_label]["bm_cpu_user_time"].append(
            self._data["stat/cpu"][cpu_label]["user_perc"]._top())
         self._data["bm_cpu"][cpu_label]["bm_cpu_guest_time"].append(
            self._data["stat/cpu"][cpu_label]["guest_all_perc"]._top())

   def _update_kpis_linux_bm_sensors(self):
      """Update KPIs for linux BM sensors subservice

      """
      # init KPI rbs if needed
      if "bm_sensors" not in self._data:
         self._data["bm_sensors"] = {}
         # thermal zones
         for zone_label,d in self._data["sensors/thermal"].items():
            zone_label += ":"+d["type"]._top()
            self._data["bm_sensors"][zone_label] = self._init_kpis_rb("bm", "sensors")
            self._data["bm_sensors"][zone_label]["bm_sensors_type"].append("zone")
         # fan sensors
         for fan_label,d in self._data["sensors/fans"].items():
            fan_label += ":"+d["label"]._top()
            self._data["bm_sensors"][fan_label] = self._init_kpis_rb("bm", "sensors")
            self._data["bm_sensors"][fan_label]["bm_sensors_type"].append("fan")
         # core sensors
         for core_label,d in self._data["sensors/coretemp"].items():
            core_label += ":"+d["label"]._top()
            self._data["bm_sensors"][core_label] = self._init_kpis_rb("bm", "sensors")
            self._data["bm_sensors"][core_label]["bm_sensors_type"].append("cpu")

      # thermal zones
      for zone_label,d in self._data["sensors/thermal"].items():
         zone_label += ":"+d["type"]._top()
         attr_mapping = {"temperature": "bm_sensors_input_temp",}
         for attr,kpi in attr_mapping.items():
            if attr in d:
               self._data["bm_sensors"][zone_label][kpi].append(
                 d[attr]._top())
      # fan sensors
      for fan_label,d in self._data["sensors/fans"].items():
         fan_label += ":"+d["label"]._top()
         attr_mapping = {"input": "bm_sensors_input_fanspeed",
                         "temperature": "bm_sensors_input_temp",}
         for attr,kpi in attr_mapping.items():
            if attr in d:
               self._data["bm_sensors"][fan_label][kpi].append(
                 d[attr]._top())
      # core sensors
      for core_label,d in self._data["sensors/coretemp"].items():
         core_label += ":"+d["label"]._top()
         attr_mapping = {"input": "bm_sensors_input_temp",
                         "max": "bm_sensors_max_temp",
                         "critical": "bm_sensors_critical_temp",}
         for attr,kpi in attr_mapping.items():
            if attr in d:
               self._data["bm_sensors"][core_label][kpi].append(
                 d[attr]._top())

   def _update_kpis_linux_bm_disk(self):
      """Update KPIs for linux BM disk subservice

      """
      # init KPI rbs if needed
      if "bm_disk" not in self._data:
         self._data["bm_disk"] = {}
      previous=set(self._data["bm_disk"].keys())
      current=set(list(self._data["diskstats"].keys())
                  +list(self._data["swaps"].keys()))
      # add new disks
      for disk in current-previous:
         self._data["bm_disk"][disk] = self._init_kpis_rb("bm", "disk")
      # remove unmounted disks
      for disk in previous-current:
         del self._data["bm_disk"][disk]

      for disk,rbs in self._data["diskstats"].items():
         self._data["bm_disk"][disk]["bm_disk_type"].append(
            rbs["fs_vfstype"]._top())
         self._data["bm_disk"][disk]["bm_disk_total_user"].append(
            rbs["total"]._top()/1000.0)
         self._data["bm_disk"][disk]["bm_disk_free_user"].append(
            rbs["free_user"]._top()/1000.0)
         self._data["bm_disk"][disk]["bm_disk_read_time"].append(
            rbs["perc_reading"]._top())
         self._data["bm_disk"][disk]["bm_disk_write_time"].append(
            rbs["perc_writting"]._top())
         self._data["bm_disk"][disk]["bm_disk_io_time"].append(
            rbs["perc_io"]._top())
         self._data["bm_disk"][disk]["bm_disk_discard_time"].append(
            rbs["perc_discarding"]._top())

      for disk,rbs in self._data["swaps"].items():
         self._data["bm_disk"][disk]["bm_disk_type"].append(
            "swap")#rbs["type"]._top()
         self._data["bm_disk"][disk]["bm_disk_total_user"].append(
            rbs["size"]._top()/1000.0)
         self._data["bm_disk"][disk]["bm_disk_swap_used"].append(
            rbs["used"]._top())

   def _update_kpis_linux_bm_mem(self):
      """Update KPIs for linux BM mem subservice

      """
      self._data["bm_mem"]["bm_mem_total"].append(
         self._data["meminfo"]["MemTotal"]._top()/1000)
      self._data["bm_mem"]["bm_mem_free"].append(
         self._data["meminfo"]["MemFree"]._top()/1000)
      self._data["bm_mem"]["bm_mem_available"].append(
         self._data["meminfo"]["MemAvailable"]._top()/1000)
      self._data["bm_mem"]["bm_mem_buffers"].append(
         self._data["meminfo"]["Buffers"]._top()/1000)
      self._data["bm_mem"]["bm_mem_cache"].append(
         self._data["meminfo"]["Cached"]._top()/1000)
      self._data["bm_mem"]["bm_mem_active"].append(
         self._data["meminfo"]["Active"]._top()/1000)
      self._data["bm_mem"]["bm_mem_inactive"].append(
         self._data["meminfo"]["Inactive"]._top()/1000)
      self._data["bm_mem"]["bm_mem_pages_total"].append(
         self._data["meminfo"]["HugePages_Total"]._top())
      self._data["bm_mem"]["bm_mem_pages_free"].append(
         self._data["meminfo"]["HugePages_Free"]._top())
      self._data["bm_mem"]["bm_mem_pages_reserved"].append(
         self._data["meminfo"]["HugePages_Rsvd"]._top())
      self._data["bm_mem"]["bm_mem_pages_size"].append(
         self._data["meminfo"]["Hugepagesize"]._top()/1000)

   def _update_kpis_linux_bm_proc(self):
      """Update KPIs for linux BM proc subservice

      """
      self._data["bm_proc"]["bm_proc_total_count"].append(
         self._data["stats_global"]["proc_count"]._top())
      self._data["bm_proc"]["bm_proc_run_count"].append(
         self._data["stats_global"]["run_count"]._top())
      self._data["bm_proc"]["bm_proc_sleep_count"].append(
         self._data["stats_global"]["sleep_count"]._top())
      self._data["bm_proc"]["bm_proc_idle_count"].append(
         self._data["stats_global"]["idle_count"]._top())
      self._data["bm_proc"]["bm_proc_wait_count"].append(
         self._data["stats_global"]["wait_count"]._top())
      self._data["bm_proc"]["bm_proc_zombie_count"].append(
         self._data["stats_global"]["zombie_count"]._top())
      self._data["bm_proc"]["bm_proc_dead_count"].append(
         self._data["stats_global"]["dead_count"]._top())

   def _update_kpis_linux_bm_net(self):
      """Update KPIs for linux BM net subservice

      """
      # init KPI rbs if needed
      previous=set(self._data["bm_net_if"].keys())
      current=set(self._data["net/dev"].keys())
      # add new ifs
      for net in current-previous:
         self._data["bm_net_if"][net] = self._init_kpis_rb("bm", "net_if")
      # remove down ifs
      for net in previous-current:
         del self._data["bm_net_if"][net]
         
      attr_mapping = {"rx_packets": "bm_net_if_rx_packets",
                      "rx_bytes": "bm_net_if_rx_bytes",
                      "rx_errs": "bm_net_if_rx_error",
                      "rx_drop": "bm_net_if_rx_drop",
                      "tx_packets": "bm_net_if_tx_packets",
                      "tx_bytes": "bm_net_if_tx_bytes",
                      "tx_errs": "bm_net_if_tx_error",
                      "tx_drop": "bm_net_if_tx_drop",
                      "carrier_up_count": "bm_net_if_up_count",
                      "carrier_down_count": "bm_net_if_down_count",
                      "operstate": "bm_net_if_state",
                      "mtu": "bm_net_if_mtu",
                      "numa_node": "bm_net_if_numa",
                      "local_cpulist": "bm_net_if_cpulist",
                      "tx_queue_len": "bm_net_if_tx_queue"}
      for net,rbs in self._data["net/dev"].items():
         # direct mapping
         for attr,kpi in attr_mapping.items():
            if attr in rbs:
               self._data["bm_net_if"][net][kpi].append(
                 rbs[attr]._top())
         # other fields
         if "ip4_gw_addr" in rbs:
            self._data["bm_net_if"][net]["bm_net_if_gw_in_arp"].append(
               rbs["ip4_gw_addr"]._top() in self._data["net/arp"])
      # non interface-related fields
      for field, rb in self._data["snmp"].items():
         self._data["bm_net"]["bm_net_snmp_"+field].append(rb._top())

   def _update_kpis_linux_vm_cpu(self):
      """Update KPIs for linux VM cpu subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
      self._data["vm"][vm_name]["vm_cpu_count"].append(
         self._data[hypervisor+"/vms"][vm_name]["cpu"]._top())
      self._data["vm"][vm_name]["vm_cpu_user_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/User"]._top())
      self._data["vm"][vm_name]["vm_cpu_system_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/Kernel"]._top())
      self._data["vm"][vm_name]["vm_cpu_idle_time"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/CPU/Load/Idle"]._top())
   
   def _update_kpis_linux_vm_mem(self):
      """Update KPIs for linux VM mem subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
      self._data["vm"][vm_name]["vm_mem_total"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Total"]._top()/1000.0)
      self._data["vm"][vm_name]["vm_mem_free"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Free"]._top()/1000.0)
      self._data["vm"][vm_name]["vm_mem_cache"].append(
         self._data[hypervisor+"/vms"][vm_name]["Guest/RAM/Usage/Cache"]._top()/1000.0)
      
   def _update_kpis_linux_vm_net(self):
      """Update KPIs for linux VM net subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor

      # per-interface KPIs
      prefix="/VirtualBox/GuestInfo/Net/"
      attrs_suffix = ["MAC", "V4/IP", "V4/Broadcast",
                    "V4/Netmask", "Status"]
      net_count=(self._data["virtualbox/vms"][vm_name]
                          ["/VirtualBox/GuestInfo/Net/Count"])._top()
      for net_index in range(net_count):
         # add if if needed
         attr="{}{}/Name".format(prefix, net_index)
         if_name=self._data[hypervisor+"/vms"][vm_name][attr]._top()
         if if_name not in self._data["vm"][vm_name]["vm_net_if"]:
            self._data["vm"][vm_name]["vm_net_if"][if_name] = self._init_kpis_rb("vm", "net_if")
         # translate data
         for suffix in attrs_suffix:
            # if status
            attr="{}{}/Status".format(prefix, net_index)
            self._data["vm"][vm_name]["vm_net_if"][if_name]["vm_net_if_state"].append(
               self._data[hypervisor+"/vms"][vm_name][attr]._top().lower())
            # XXX: per-interface instead of total rate
            attr="Net/Rate/Rx"
            self._data["vm"][vm_name]["vm_net_if"][if_name]["vm_net_if_rx_bytes"].append(
               self._data[hypervisor+"/vms"][vm_name][attr]._top()/1000.0)
            attr="Net/Rate/Tx"
            self._data["vm"][vm_name]["vm_net_if"][if_name]["vm_net_if_tx_bytes"].append(
               self._data[hypervisor+"/vms"][vm_name][attr]._top()/1000.0)
            
      # global KPIs
      self._data["vm"][vm_name]["vm_net_ssh"].append(
          self._data[hypervisor+"/vms"][vm_name]["accessible"]._top())
          
   def _update_kpis_linux_vm_proc(self):
      """Update KPIs for linux VM proc subservice

      """
      vm_name=self.parent.name
      hypervisor=self.parent.hypervisor
         
   def _update_kpis_linux_kb_proc(self):
      """Update KPIs for linux KB proc subservice

      """
      kb_name=self.parent.name
      framework=self.parent.framework
      self._data["kb"][kb_name]["kb_proc_thread_count"].append(
         self._data[framework+"/gnmi"][kb_name]["/sys/num_worker_threads"]._top())
      
   def _update_kpis_linux_kb_mem(self):
      """Update KPIs for linux KB mem subservice

      """
      kb_name=self.parent.name
      framework=self.parent.framework
      # stats-segment
      mem_total = self._data[framework+"/gnmi"][kb_name]["/mem/statseg/total"]._top()/1000000.0
      mem_used = self._data[framework+"/gnmi"][kb_name]["/mem/statseg/used"]._top()/1000000.0
      mem_free = mem_total-mem_used
      self._data["kb"][kb_name]["kb_mem_total"].append(mem_total)
      self._data["kb"][kb_name]["kb_mem_free"].append(mem_free)
      # buffers
      buffer_free = self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/available"]._top()
      buffer_used = self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/used"]._top()
      buffer_total = buffer_free + buffer_used
      self._data["kb"][kb_name]["kb_mem_buffer_total"].append(buffer_total)
      self._data["kb"][kb_name]["kb_mem_buffer_free"].append(buffer_free)
      self._data["kb"][kb_name]["kb_mem_buffer_cache"].append(self._data[framework+"/gnmi"][kb_name]["/buffer-pools/default-numa-0/cached"]._top())
      
   def _update_kpis_linux_kb_net(self):
      """Update KPIs for linux KB net subservice

      """
      kb_name=self.parent.name
      framework=self.parent.framework
      for if_name, d in self._data[framework+"/gnmi"][kb_name]["kb_net_if"].items():
         # create interface entry if needed
         if if_name not in self._data["kb"][kb_name]["kb_net_if"]:
            self._data["kb"][kb_name]["kb_net_if"][if_name] = self._init_kpis_rb("kb", "net_if")
         kpi_dict = self._data["kb"][kb_name]["kb_net_if"][if_name]
         md_dict = self._data[framework+"/gnmi"][kb_name]["kb_net_if"][if_name]
         kpi_dict["kb_net_if_vector_rate"].append(
            self._data[framework+"/gnmi"][kb_name]["/sys/vector_rate"]._top())
         kpi_dict["kb_net_if_rx_packets"].append(md_dict["/if/rx/T0/packets"]._top())
         kpi_dict["kb_net_if_rx_bytes"].append(md_dict["/if/rx/T0/bytes"]._top()/1000000.0)
         kpi_dict["kb_net_if_rx_error"].append(md_dict["/if/rx-error/T0"]._top())
         kpi_dict["kb_net_if_rx_drop"].append(md_dict["/if/rx-miss/T0"]._top())  
         kpi_dict["kb_net_if_tx_packets"].append(md_dict["/if/tx/T0/packets"]._top())
         kpi_dict["kb_net_if_tx_bytes"].append(md_dict["/if/tx/T0/bytes"]._top()/1000000.0)
         kpi_dict["kb_net_if_tx_error"].append(md_dict["/if/tx-error/T0"]._top())
         #kpi_dict["kb_net_tx_drop"].append(md_dict["/if/tx/T0/packets"]._top())
      
   def _update_kpis_macos_bm_cpu(self):
      pass
   def _update_kpis_win_bm_cpu(self):
      pass

class Node(Subservice):
   """A device/physical node
   Includes 1 BM subservice, N VMs, N gnmi clients for VPP, 0-1 BM VPP

   """
   def __init__(self, name, engine, parent=None):
      super(Node, self).__init__(name, engine, parent=parent)
      self.active = True
      self.name = self.sysinfo.node
      self.dependencies = [Baremetal(self.name, self.engine, parent=self)]
      
   def add_vm(self, name, hypervisor):
      self.dependencies.append(VM(name, self.engine, hypervisor, parent=self))
   def add_kbnet(self, name, framework):
      self.dependencies.append(KBNet(name, self.engine, framework, parent=self))
   def remove_vm(self, name):
      for i, subservice in enumerate(self.dependencies):
         if isinstance(subservice, VM) and subservice.name == name:
            subservice.del_kpis()
            del self.dependencies[i]
            break
   def remove_kbnet(self, name):
      for i, subservice in enumerate(self.dependencies):
         if isinstance(subservice, KBNet) and subservice.name == name:
            subservice.del_kpis()
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
   def __init__(self, name, engine, parent=None):
      super(Baremetal, self).__init__(name, engine, parent=parent)
      self.active = True
      
      deps = ["cpu", "sensors", "disk", "mem", "proc", "net"]
      self.dependencies = [Subservice(dep, self.engine, parent=self) for dep in deps]
      # init KPIs for non-list RBs
      self._data["bm_net_if"] = {}
      self._data["bm_net"] = self._init_kpis_rb("bm", "net")
      self._data["bm_mem"] = self._init_kpis_rb("bm", "mem")
      self._data["bm_proc"] = self._init_kpis_rb("bm", "proc")

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      pass

class VM(Subservice):
   """VM subservice assurance
   
   """
   def __init__(self, name, engine, hypervisor, parent=None):
      super(VM, self).__init__(name, engine, parent=parent)
      self.hypervisor=hypervisor
      
      deps = ["cpu", "mem", "net", "proc"]
      self.dependencies = [Subservice(dep, self.engine, parent=self) for dep in deps]
      # init KPIs for non-list RBs
      self._data["vm"][self.name] = {"vm_net_if": {}}
      self._data["vm"][self.name].update(self._init_kpis_rb("vm", "proc"))
      self._data["vm"][self.name].update(self._init_kpis_rb("vm", "net"))
      self._data["vm"][self.name].update(self._init_kpis_rb("vm", "mem"))
      self._data["vm"][self.name].update(self._init_kpis_rb("vm", "cpu"))

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      vm_name=self.name
      hypervisor=self.hypervisor
      self.active = self._data[hypervisor+"/vms"][vm_name]["state"]._top() == "Running"
      self._data["vm"][vm_name]["vm_proc_active"].append(self.active)

   def del_kpis(self):
      """
      remove this VM KPIs ringbuffers
      """
      del self._data["vm"][self.name]
      
class KBNet(Subservice):
   """Kernel Bypassing Networks subservice assurance
   
   """
   def __init__(self, name, engine, framework, parent=None):
      super(KBNet, self).__init__(name, engine, parent=parent)
      self.framework=framework
      
      deps = ["proc", "mem", "net"]
      self.dependencies = [Subservice(dep, self.engine, parent=self) for dep in deps]
      # init KPIs for non-list RBs
      self._data["kb"][self.name] = {"kb_net_if": {}}
      self._data["kb"][self.name].update(self._init_kpis_rb("kb", "mem"))
      self._data["kb"][self.name].update(self._init_kpis_rb("kb", "proc"))

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      kb_name=self.name
      framework=self.framework
      self.active = self._data[framework+"/gnmi"][kb_name]["status"]._top() == "synced"
      self._data["kb"][kb_name]["kb_proc_active"].append(self.active)

   def del_kpis(self):
      """
      remove this VM KPIs ringbuffers
      """
      del self._data["kb"][self.name]


