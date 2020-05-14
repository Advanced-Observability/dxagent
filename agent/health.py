"""
health.py

   Key Performance Indicators & symptom rules

@author: K.Edeline

"""
import csv
import os
import builtins

from agent.buffer import init_rb_dict
from agent.sysinfo import SysInfo

class HealthEngine():
   def __init__(self, data, info, parent):      
      self._data = data
      self.info = info
      self.parent = parent
      self.sysinfo = SysInfo()
      self._data["vm"], self._data["kb"] = {}, {}
      # read kpi file
      self.kpi_attrs, self.kpi_types, self.kpi_units = {}, {}, {}
      with open(os.path.join(self.parent.args.ressources_dir,"kpi.csv")) as csv_file:
         for r in csv.DictReader(csv_file):
            name,type,unit= r["name"], r["type"],r["unit"]
            # we use (node,subservice) tuples as key
            # e.g., ("bm", "net")
            key = tuple(name.split('_')[:2])
            self.kpi_attrs.setdefault(key,[]).append(name)
            self.kpi_types.setdefault(key,[]).append(getattr(builtins, type))
            self.kpi_units.setdefault(key,[]).append(unit)

      self._build_dependency_graph()

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

   def add_vm(self, name):
      self.node.add_vm(name)
   def add_kbnet(self, name):
      self.node.add_kbnet(name)
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
      pass

class Symptoms():
   def __init__(self, name, severity, rule):
      self.name = name
      self.severity = severity
      self.rule = rule

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
      self.type = type(self).__name__
      self.fullname = self.type+"."+self.name

   def __contains__(self, item):
      for subservice in self.dependencies:
         if item == subservice.name:
            return True
      return False
   def _del_kpis(self):
      """
      subservice cleanup, overload in child if needed.
      """
      pass
   def __del__(self):
      self._del_kpis()
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
      if not self.dependencies:
         self._update_kpis()
      for subservice in self.dependencies:
         subservice.update_kpis()

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      Pick the right function based on host OS and subservice.
      
      """
      key = (self.sysinfo.system,
             self.parent.type if self.parent else None, 
             self.name)
      funcs = {
         ("Linux","Baremetal","cpu")     : self._update_kpis_linux_bm_cpu,
         ("Linux","Baremetal","sensors") : self._update_kpis_linux_bm_sensors,
         ("Linux","Baremetal","disk")    : self._update_kpis_linux_bm_disk,
         ("Linux","Baremetal","mem")     : self._update_kpis_linux_bm_mem,
         ("Linux","Baremetal","proc")    : self._update_kpis_linux_bm_proc,
         ("Linux","Baremetal","net")     : self._update_kpis_linux_bm_net,
         ("Linux","VM","cpu") : self._update_kpis_linux_vm_cpu,
         ("Linux","VM","mem") : self._update_kpis_linux_vm_mem,
         ("Linux","VM","net") : self._update_kpis_linux_vm_net,
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
      return
      self._data["bm_net"]["bm_net_rx_packets"].append(10)
      self._data["bm_net"]["bm_net_rx_bytes"].append(10)
      self._data["bm_net"]["bm_net_rx_error"].append(10)
      self._data["bm_net"]["bm_net_rx_drop"].append(10)
      self._data["bm_net"]["bm_net_tx_packets"].append(10)
      self._data["bm_net"]["bm_net_tx_bytes"].append(10)
      self._data["bm_net"]["bm_net_tx_error"].append(10)
      self._data["bm_net"]["bm_net_tx_drop"].append(10)
      self._data["bm_net"]["bm_net_up_count"].append(10)
      self._data["bm_net"]["bm_net_down_count"].append(10)
      self._data["bm_net"]["bm_net_state"].append(10)
      self._data["bm_net"]["bm_net_mtu"].append(10)
      self._data["bm_net"]["bm_net_numa"].append(10)
      self._data["bm_net"]["bm_net_cpulist"].append(10)
      self._data["bm_net"]["bm_net_tx_queue"].append(10)
      self._data["bm_net"]["bm_net_gw_in_arp"].append(10)

   def _update_kpis_linux_vm_cpu(self):
      """Update KPIs for linux VM cpu subservice

      """
      pass
   def _update_kpis_linux_vm_mem(self):
      """Update KPIs for linux VM mem subservice

      """
      pass
   def _update_kpis_linux_vm_net(self):
      """Update KPIs for linux VM net subservice

      """
      pass
   def _update_kpis_linux_kb_proc(self):
      """Update KPIs for linux KB proc subservice

      """
      pass
   def _update_kpis_linux_kb_mem(self):
      """Update KPIs for linux KB mem subservice

      """
      pass
   def _update_kpis_linux_kb_net(self):
      """Update KPIs for linux KB net subservice

      """
      pass
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
      self.name = self.sysinfo.node
      self.dependencies = [Baremetal(self.name, self.engine, parent=self)]

   def add_vm(self, name):
      self.dependencies.append(VM(name, self.engine, parent=self))
   def add_kbnet(self, name):
      self.dependencies.append(KBNet(name, self.engine, parent=self))
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

      XXX: meta-kpis like active count ?
      """
      pass

class Baremetal(Subservice):
   """Baremetal subservice assurance
   
   """
   def __init__(self, name, engine, parent=None):
      super(Baremetal, self).__init__(name, engine, parent=parent)
      
      deps = ["cpu", "sensors", "disk", "mem", "proc", "net"]
      self.dependencies = [Subservice(dep, self.engine, parent=self) for dep in deps]
      # init KPIs for non-list RBs
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
   def __init__(self, name, engine, parent=None):
      super(VM, self).__init__(name, engine, parent=parent)

      deps = ["cpu", "mem", "net"]
      self.dependencies = [Subservice(dep, self.engine, parent=self) for dep in deps]
      # init KPIs for non-list RBs
      self._data["vm_mem"] = self._init_kpis_rb("vm", "mem")
      self._data["vm_cpu"] = self._init_kpis_rb("vm", "cpu")

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      pass
   def _del_kpis(self):
      """
      remove this VM KPIs ringbuffers
      """
      pass
      
class KBNet(Subservice):
   """Kernel Bypassing Networks subservice assurance
   
   """
   def __init__(self, name, engine, parent=None):
      super(KBNet, self).__init__(name, engine, parent=parent)

      deps = ["proc", "mem", "net"]
      self.dependencies = [Subservice(dep, self.engine, parent=self) for dep in deps]
      # init KPIs for non-list RBs
      self._data["kb_mem"] = self._init_kpis_rb("kb", "mem")
      self._data["kb_proc"] = self._init_kpis_rb("kb", "proc")

   def _update_kpis(self):
      """
      update KPIs for this subservice 

      """
      pass

   def _del_kpis(self):
      """
      remove this VM KPIs ringbuffers
      """
      pass


