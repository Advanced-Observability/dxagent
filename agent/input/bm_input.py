"""
bm_input.py

   Input parsing for baremetal health monitoring

@author: K.Edeline
"""

import os
import netifaces
import ipaddress
import time
import subprocess
import socket

import ethtool
import logging
import pyroute2

from pyroute2.netlink.rtnl import rt_type
from pyroute2.netlink.rtnl import rt_scope
from pyroute2.netlink.rtnl import rt_proto

from agent.core.rbuffer import init_rb_dict

# linux/include/linux/if_arp.h
_linux_if_types = { "0":"netrom", "1":"ether", "2":"eether", "3":"ax25",
   "4":"pronet","5":"chaos", "6":"ieee802", "7":"arcnet", "8":"appletlk", 
   "15":"dlci", "19":"atm","23":"metricom", "24":"ieee1394", "27":"eui64", 
   "32":"infiniband", "256":"slip", "257":"cslip", "258":"slip6",
   "259":"cslip6", "260":"rsrvd","264":"adapt", "270":"rose", "271":"x25",
   "272":"hwx25", "280":"can", "512":"ppp", "513":"hdlc", "516":"lapb",
   "517":"ddcmp", "518":"rawhdlc", "768":"tunnel", "769":"tunnel6", "770":"frad",
   "771":"skip", "772":"loopback", "773":"localtlk", "774":"fddi", "775":"bif",
   "776":"sit", "777":"ipddp", "778":"ipgre", "779":"pimreg", "780":"hippi",
   "781":"ash", "782":"econet", "783":"irda", "784":"fcpp",
   "785":"fcal", "786":"fcpl", "787":"fcfabric", "800":"ieee802_tr",
   "801":"ieee80211", "802":"ieee802_prism", "803":"ieee80211_radiotap",
   "804":"ieee802154", "820":"phonet", "821":"phonet_pipe", "822":"caif"
}

def ratio(v, total):
   try:
      return round(v/total*100.0)
   except:
      return 0

class BMWatcher():

   def __init__(self, data, info, parent):
      self.msec_per_jiffy = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
      self._data=data
      self.info=info
      self.parent=parent
      self._init_dicts()
      self.diskstats_timestamp=None
      self._ethtool = pyroute2.Ethtool()
      self._route = pyroute2.IPRoute()

   def _init_dicts(self):

      # init categories whose input count are prone to change during execution
      # e.g., interfaces , processes
      self._data["net/dev"] = {}
      self._data["routes4"] = {}
      self._data["routes6"] = {}
      self._data["swaps"] = {}
      self._data["net/arp"] = {}
      self._data["stats"] = {}
      self._data["diskstats"] = {}
      self._data["sensors/thermal"] = {}
      self._data["sensors/fans"] = {}
      self._data["sensors/coretemp"] = {}

      # uptime
      attr_list = ["up", "idle"]
      self._data["uptime"] = init_rb_dict(attr_list, type=str)

      # stats_global
      attr_list = ["proc_count", "run_count", "sleep_count", "wait_count", 
         "stopped_count", "ts_count", "dead_count",
         "zombie_count", "parked_count", "idle_count"]
      self._data["stats_global"] = init_rb_dict(attr_list)

      # loadavg
      attr_list = ["1min", "5min", "15min", "runnable", "total"]
      self._data["loadavg"] = init_rb_dict(attr_list,type=float)

      # meminfo
      attr_list, unit_list = [], []
      with open("/proc/meminfo", 'r') as f:
         for l in f.readlines():
            elements=l.rstrip().split()
            attr_list.append(elements[0].rstrip(':'))
            unit_list.append(elements[2] if len(elements)>2 else None)
      self._data["meminfo"] = init_rb_dict(attr_list, units=unit_list)

      # netstat
      attr_list = []
      with open("/proc/net/netstat", 'r') as f:
         while True:
            attrs = f.readline().split()
            _ = f.readline()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')
            attr_list.extend([prefix+attr for attr in attrs])
      self._data["netstat"] = init_rb_dict(attr_list, counter=True)

      # snmp
      attr_list = []
      with open("/proc/net/snmp", 'r') as f:
         while True:
            attrs = f.readline().split()
            _ = f.readline()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')
            attr_list.extend([prefix+attr for attr in attrs[1:]])
      self._data["snmp"] = init_rb_dict(attr_list, counter=True)

      # stat and stat/cpu
      attr_list = []
      attr_list_cpu = [
         "user_time", "nice_time", "system_time", "idle_time", 
         "iowait_time", "irq_time", "softirq_time", "steal_time", 
         "guest_time", "guest_nice_time", "system_all_time",
         "idle_all_time", "guest_all_time", "total_time",

         "user_period", "nice_period", "system_period", "idle_period", 
         "iowait_period", "irq_period", "softirq_period", "steal_period", 
         "guest_period", "guest_nice_period", "system_all_period",
         "idle_all_period", "guest_all_period", "total_period",

         "user_perc", "nice_perc", "system_perc", "idle_perc", 
         "iowait_perc", "irq_perc", "softirq_perc", "steal_perc", 
         "guest_perc", "guest_nice_perc", "system_all_perc",
         "idle_all_perc", "guest_all_perc",
       ]
      attr_units = ["ms"] * 28 + ["%"] * 13
      attr_types = [int] * 28 + [float] * 13

      self._data["stat/cpu"] = {}
      with open("/proc/stat", 'r') as f:
         for l in f.readlines():
            label = l.split()[0]

            if label.startswith("cpu"):
               self._data["stat/cpu"][label] = init_rb_dict(attr_list_cpu,
                                                            units=attr_units)
            else:
               attr_list.append(label)

      is_counter = [True, True, True, False, False, False, True]
      self._data["stat"] = init_rb_dict(attr_list, counters=is_counter)

      # proc/stat
      attr_list = [
         "net.core.rmem_default", "net.core.rmem_max", "net.core.wmem_default",
         "net.core.wmem_max", "net.ipv4.tcp_mem_min", "net.ipv4.tcp_mem_pressure",
         "net.ipv4.tcp_mem_max", "net.ipv4.tcp_rmem_min", "net.ipv4.tcp_rmem_default",
         "net.ipv4.tcp_rmem_max", "net.ipv4.tcp_wmem_min", "net.ipv4.tcp_wmem_default",
         "net.ipv4.tcp_wmem_max", "net.core.default_qdisc", "net.core.netdev_max_backlog", 
         "net.ipv4.tcp_congestion_control", "net.ipv4.tcp_sack", "net.ipv4.tcp_dsack", 
         "net.ipv4.tcp_fack", "net.ipv4.tcp_syn_retries", 
         "net.ipv4.tcp_slow_start_after_idle", "net.ipv4.tcp_retries1", 
         "net.ipv4.tcp_retries2", "net.ipv4.tcp_mtu_probing", 
         "net.ipv4.tcp_max_syn_backlog", "net.ipv4.tcp_base_mss", 
         "net.ipv4.tcp_min_snd_mss", "net.ipv4.tcp_ecn_fallback", "net.ipv4.tcp_ecn", 
         "net.ipv4.tcp_adv_win_scale", "net.ipv4.tcp_window_scaling", 
         "net.ipv4.tcp_tw_reuse", "net.ipv4.tcp_syncookies", "net.ipv4.tcp_timestamps", 
         "net.ipv4.tcp_no_metrics_save", "net.ipv4.ip_forward", "net.ipv4.ip_no_pmtu_disc", 
      ]
      unit_list = [
         "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", 
         "B", "B", "B", "", "", "", "", "", "", "", "", "", "", "", "", 
         "", "", "", "", "", "", "", "", "", "", "", ""
      ]
      self._data["proc/sys"] =  init_rb_dict(attr_list, units=unit_list, type=str)

      # rt-cache read attrs
      self._data["rt-cache"] = {}
      with open("/proc/net/stat/rt_cache", 'r') as f:
         attr_list_rt_cache = f.readline().split()
         self.cpu_count = len(f.readlines())

      # arp-cache read attrs
      self._data["arp-cache"] = {}
      with open("/proc/net/stat/arp_cache", 'r') as f:
         attr_list_arp_cache = f.readline().split()

      # ndisc-cache read attrs
      self._data["ndisc-cache"] = {}
      with open("/proc/net/stat/ndisc_cache", 'r') as f:
         attr_list_ndisc_cache = f.readline().split()

      # generate dict for each cpu
      for i in range(self.cpu_count):
         cpu_label="cpu{}".format(i)

         self._data["rt-cache"][cpu_label] = init_rb_dict(attr_list_rt_cache, type=int)
         self._data["arp-cache"][cpu_label] = init_rb_dict(attr_list_arp_cache, type=int)
         self._data["ndisc-cache"][cpu_label] = init_rb_dict(attr_list_ndisc_cache, type=int)
      
   def input(self):
      """
      baremetal health: Linux

      """
      
      self._process_proc_meminfo()
      self._process_proc_stat()
      self._process_proc_stats()
      self._process_proc_loadavg()
      self._process_proc_swaps()
      self._process_proc_uptime()
      self._process_proc_diskstats()
      self._process_proc_net_netstat()
      self._process_proc_net_snmp()
      self._process_proc_net_stat_arp_cache()
      self._process_proc_net_stat_ndisc_cache()
      self._process_proc_net_stat_rt_cache()
      self._process_proc_net_arp()
      self._process_net_settings()
      self._process_sensors()
      self._process_interfaces()
      self._process_routes()

   def _process_sensors(self):
      dev_cooling_path = "/sys/class/thermal/"
      attr_names = ["type", "temperature"]
      attr_types = [str, float]
      attr_units = ["", "C°"]
      category = "sensors/thermal"

      for d in next(os.walk(dev_cooling_path))[1]:
         if "thermal" not in d:
            continue

         path = dev_cooling_path+d+"/"
         self._data[category].setdefault(d, init_rb_dict(
                    attr_names, types=attr_types, units=attr_units))  

         with open(path+"type", 'r') as f:
            type = f.readlines()[0].rstrip()
            self._data[category][d]["type"].append(type)
         with open(path+"temp", 'r') as f:
            temp = f.readlines()[0].rstrip()
            self._data[category][d]["temperature"].append(int(temp)/1000)
      
      cpu_sensor_path="/sys/devices/platform/coretemp.0/hwmon/"
      attr_names = ["label", "input", "max", "critical"]
      attr_types = [str, float, float, float]
      attr_units = ["", "C°", "C°", "C°"]
      category = "sensors/coretemp"

      for d in next(os.walk(cpu_sensor_path))[1]:
         if "hwmon" not in d:
            continue
         
         path = cpu_sensor_path+d+"/"
         for n in range(1,512):
            name = "temp{}".format(n)
            if not os.path.exists(path+name+"_label"):
               break

            self._data[category].setdefault(name, init_rb_dict(
                 attr_names, types=attr_types, units=attr_units))

            with open(path+name+"_label") as f:
               label = f.readlines()[0].rstrip()
               self._data[category][name]["label"].append(label)
            with open(path+name+"_input") as f:
               input = f.readlines()[0].rstrip()
               self._data[category][name]["input"].append(int(input)/1000.0)
            with open(path+name+"_max") as f:
               max = f.readlines()[0].rstrip()
               self._data[category][name]["max"].append(int(max)/1000.0)
            with open(path+name+"_crit") as f:
               crit = f.readlines()[0].rstrip()
               self._data[category][name]["critical"].append(int(crit)/1000.0)

      fan_sensor_path="/sys/devices/platform/"
      attr_names = ["label", "input", "temperature"]
      attr_types = [str, int, float]
      attr_units = ["", "RPM", "C°"]
      category = "sensors/fans"

      # find directories that monitor fans
      fan_directories=[]
      for d in next(os.walk(fan_sensor_path))[1]:
         path=fan_sensor_path+d+"/hwmon/"
         if os.path.exists(path) and "coretemp" not in d:
            fan_directories.append(path)

      for p in fan_directories:
         for d in next(os.walk(p))[1]:
            if "hwmon" not in d:
               continue
            
            path = p+d+"/"
            with open(path+"name") as f:
               name = f.readlines()[0].rstrip()

            for n in range(1,512):
               
               prefix = "fan{}".format(n)
               if not os.path.exists(path+prefix+"_label"):
                  break

               # create entry if needed
               name += "-"+prefix
               self._data[category].setdefault(name, init_rb_dict(
                       attr_names, types=attr_types, units=attr_units))

               with open(path+prefix+"_label") as f:
                  label = f.readlines()[0].rstrip()
                  self._data[category][name]["label"].append(label)
               with open(path+prefix+"_input") as f:
                  input = f.readlines()[0].rstrip()
                  self._data[category][name]["input"].append(int(input))

               prefix = "temp{}".format(n)
               if os.path.exists(path+prefix+"_input"):
                  with open(path+prefix+"_input") as f:
                     temp = f.readlines()[0].rstrip()
                     self._data[category][name]["temperature"].append(int(temp)/1000.0)                 


   def _process_proc_meminfo(self):
      with open("/proc/meminfo", 'r') as f:
         for l in f.readlines():
            elements = l.rstrip().split()
            self._data["meminfo"][elements[0].rstrip(':')].append(elements[1])

   def _process_proc_stats(self):
      attr_names = [ "comm", "state", "ppid", "pgrp", "sid",
                     "tty_nr", "tty_pgrp", "flags", "min_flt", "cmin_flt",
                     "maj_flt", "cmaj_flt", "utime", "stime", "cutime",
                     "cstime", "priority", "nice", "num_threads", "itrealvalue",
                     "starttime", "vsize", "rss", "rsslim", "startcode",
                     "endcode", "startstack", "kstk_esp", "kstk_eip", "signal",
                     "blocked", "sigignore", "sigcatch", "wchan", "nswap",
                     "cnswap", "exit_signal", "processor", "rt_priority",
                     "policy", "delayacct_blkio_ticks", "gtime", 
                     "cgtime"]
      attr_types = 2*[str] + 41*[int]

      root_dir = "/proc/"
      proc_state = {"R":0, "S":0, "D":0, "T":0, "t":0, "X":0, "Z":0,
                    "P":0,"I": 0, }
      active_procs = []
      for d in next(os.walk(root_dir))[1]:

         # not a proc
         if not d.isdigit():
            continue

         path = root_dir+d+"/stat"
         try:
            with open(path, 'r') as f:
               line = f.readline().rstrip()
               split = line.split('(')
               pid = split[0].rstrip()
               split = split[-1].split(')')
               comm = split[0]

               # create new rb if needed
               self._data["stats"].setdefault(pid, 
                  init_rb_dict(attr_names, types=attr_types))
               # READ 
               for i,e in enumerate( ([comm]+split[-1].split())[:len(attr_names)] ):
                  self._data["stats"][pid][attr_names[i]].append(e)
            
            active_procs.append(pid)
            proc_state[self._data["stats"][pid]["state"]._top()] += 1
         except:
            pass

      # cleanup expired procs
      for monitored_pid in list(self._data["stats"].keys()):
         if monitored_pid not in active_procs:
            del self._data["stats"][monitored_pid]

      # count procs
      self._data["stats_global"]["proc_count"].append(len(self._data["stats"]))
      # count proc states
      proc_state_names = {"R":"run_count", "S":"sleep_count", "D":"wait_count", 
         "T":"stopped_count", "t":"ts_count",   "X":"dead_count",
         "Z":"zombie_count", "P":"parked_count", "I":"idle_count",
      }
      for d,v in proc_state.items():
         self._data["stats_global"][proc_state_names[d]].append(v)

   def _process_proc_stat(self):
      time_names = [
         "user_time", "nice_time", "system_time", "idle_time", 
         "iowait_time", "irq_time", "softirq_time", "steal_time", 
         "guest_time", "guest_nice_time", "system_all_time",
         "idle_all_time", "guest_all_time", "total_time",
      ]
      period_names = [
         "user_period", "nice_period", "system_period", "idle_period", 
         "iowait_period", "irq_period", "softirq_period", "steal_period", 
         "guest_period", "guest_nice_period", "system_all_period",
         "idle_all_period", "guest_all_period",
       ]
      perc_names = [
         "user_perc", "nice_perc", "system_perc", "idle_perc", 
         "iowait_perc", "irq_perc", "softirq_perc", "steal_perc", 
         "guest_perc", "guest_nice_perc", "system_all_perc",
         "idle_all_perc", "guest_all_perc",
      ]

      with open("/proc/stat", 'r') as f:
         for l in f.readlines():
            if l.startswith("cpu"):
               split = l.rstrip().split()
               cpu_label = split[0]

               split = [int(s) for s in split[1:]]
               # compute more metrics
               #
               # Guest time is already in usertime
               usertime = split[0] - split[8]
               nicetime = split[1] - split[9]
               #  kernels >= 2.6
               idlealltime = split[3] + split[4]
               systemalltime = split[2] + split[5] + split[6]
               virtalltime = split[8] + split[9]
               totaltime = (usertime + nicetime + systemalltime + idlealltime
                           + split[7] + virtalltime)

               attr_val = [ 
                  usertime, nicetime, split[2], split[3], split[4],
                  split[5], split[6], split[7], split[8], split[9], 
                  systemalltime, idlealltime, virtalltime, totaltime
               ]
               # append time attrs 
               for k,v in zip(time_names, attr_val):
                  v *= self.msec_per_jiffy
                  self._data["stat/cpu"][cpu_label][k].append(v)

               # compute total period first
               totalperiod = self._data["stat/cpu"][cpu_label]["total_time"].delta(
                                                                   count=1)
               self._data["stat/cpu"][cpu_label]["total_period"].append(
                                                                totalperiod)
               # compute&append period attrs
               for tname,pname,percname in zip(time_names, 
                                               period_names, 
                                               perc_names):

                  v = self._data["stat/cpu"][cpu_label][tname].delta(count=1)
                  #self.info("{}:{}: {} / {} = {}".format(cpu_label, percname, v,totalperiod, ratio(v,totalperiod)))
                  self._data["stat/cpu"][cpu_label][pname].append(v)
                  self._data["stat/cpu"][cpu_label][percname].append(
                                                   ratio(v,totalperiod))
            else:
               k, d = l.rstrip().split()[:2]
               self._data["stat"][k].append(d)

   def _process_proc_loadavg(self):
      attr_names = ["1min", "5min", "15min", "runnable", "total"]

      with open("/proc/loadavg", 'r') as f:
         for i, e in enumerate(f.readline().rstrip().split()):
            if i == 3:
               vals = e.split('/')
               self._data["loadavg"][attr_names[i]].append(vals[0])
               self._data["loadavg"][attr_names[i+1]].append(vals[1])
               break
            else:
               self._data["loadavg"][attr_names[i]].append(e)

   def _process_proc_swaps(self):
      """
      index is swap filename
      """

      attr_names = ["type", "size", "used", "priority"]
      attr_types = [str, int, int, int]
      active_swaps = []
      with open("/proc/swaps", 'r') as f:
         for l in f.readlines()[1:]:
            split = l.rstrip().split()

            # create swap if needed
            swap_label = split[0]
            active_swaps.append(swap_label)
            self._data["swaps"].setdefault(swap_label, init_rb_dict(attr_names, types=attr_types))

            for i,e in enumerate(split[1:]):
               self._data["swaps"][swap_label][attr_names[i]].append(e)

      # cleanup unmounted/deleted swaps
      for monitored_swaps in list(self._data["swaps"].keys()):
         if monitored_swaps not in active_swaps:
            del self._data["swaps"][monitored_swaps]

   def _process_proc_uptime(self):
      attr_names = ["up", "idle"]

      with open("/proc/uptime", 'r') as f:
         for i,e in enumerate(f.readline().rstrip().split()):
            self._data["uptime"][attr_names[i]].append(e)

   def _process_proc_diskstats(self):

      mount_names = ["fs_spec", "fs_file", "fs_vfstype", 
         "fs_mntops"]#, "fs_freq", "fs_passno"]
      mount_counters = [False]*4
      mount_units = [ "" ]*4
      mount_types = [str]*4

      time_names = [ "period_writting", "period_reading", "period_io",
                     "period_discarding",
                    "perc_writting", "perc_reading", "perc_io", 
                    "perc_discarding"]
      time_counters = [False]*8
      time_units = ["ms"]*4 + ["%"]*4
      time_types = [int]*8

      attr_names = [
         "device_major", "device_minor", "device_name",
         "reads_completed", "reads_merged", "sectors_read",
         "time_reading", "writes_completed", "writes_merged",
         "sectors_written", "time_writting", "current_io",
         "time_io", "time_io_weighted", "discards_completed",
         "discards_merged", "sectors_discarded", "time_discarding",
         "size", "total", "free_root", "free_user", 
         "used", "total_user", "usage_user"
      ] + mount_names + time_names
      attr_units = [  "", "", "", "", "", "", "ms", "",
         "", "", "ms", "", "ms", "ms", "", "", "", "ms", "KB",
         "KB","KB","KB","KB","KB","%",
         
      ] + mount_units + time_units
      attr_counters = [ False, False, False, True, True, True,
         False, True, True, True, False, False, False, False, # ??
         True, True, True, False, False, False, False, False, 
         False,  False, False,
      ] + mount_counters + time_counters
      attr_types = [ int ] * 25 + mount_types + time_types

      mounted_devs = []
      with open("/proc/mounts") as f:

         for l in f.readlines():
            attr_val = l.rstrip().split()[:-2]
            dev_name = attr_val[0].split("/")[-1]

            if not dev_name[-1].isdigit():
               continue

            # add disk if not tracked
            self._data["diskstats"].setdefault(dev_name, init_rb_dict(
                 attr_names, counters=attr_counters, units=attr_units,
                  types=attr_types))
            mounted_devs.append(dev_name)

            for i,attr in enumerate(attr_val):
               (self._data["diskstats"][dev_name]
                              [mount_names[i]].append(attr))       

      with open("/proc/partitions") as f:

         for l in f.readlines()[2:]:
            attr_val = l.rstrip().split()
            dev_name = attr_val[-1]

            if not dev_name[-1].isdigit():
               continue

            # skip disk if not present in /proc/mounts
            if dev_name not in self._data["diskstats"]:
               continue
            self._data["diskstats"][dev_name]["size"].append(attr_val[2])

      with open("/proc/diskstats", 'r') as f:
         tstamp = time.time()
         for disk in f.readlines():

            attr_val = disk.rstrip().split()
            dev_name = attr_val[2]
            if not dev_name[-1].isdigit():
               continue

            # skip disk if not present in /proc/mounts
            if dev_name not in self._data["diskstats"]:
               continue
            for i,v in enumerate(attr_val):
               if i == 2:
                  continue
               self._data["diskstats"][dev_name][attr_names[i]].append(v)
            # compute periods and percentages
            if self.diskstats_timestamp != None:
               totalperiod=(tstamp-self.diskstats_timestamp)*1000
               # compute&append period attrs
               time_names = ["time_writting", "time_reading", "time_io",
                             "time_discarding"]
               period_names = ["period_writting", "period_reading", "period_io",
                              "period_discarding"]
               perc_names = ["perc_writting", "perc_reading", "perc_io",
                             "perc_discarding"]
               for tname,pname,percname in zip(time_names, 
                                               period_names, 
                                               perc_names):
                  v = self._data["diskstats"][dev_name][tname].delta(count=1)
                  # periods are sums of per-CPU counters, compute avg.
                  self._data["diskstats"][dev_name][pname].append(v)
                  self._data["diskstats"][dev_name][percname].append(
                                                   ratio(v,totalperiod))
         self.diskstats_timestamp=tstamp

      for monitored_dev in list(self._data["diskstats"].keys()):
          # cleanup unmounted dev
         if monitored_dev not in mounted_devs:
            del self._data["diskstats"][monitored_dev]
            continue
         
         path,_ = self._data["diskstats"][monitored_dev]["fs_file"].top()
         try:
            st = os.statvfs(path)
         except:
            continue
         # Total space (only available to root)
         total = (st.f_blocks * st.f_frsize) / 1024
         # Remaining free space usable by root.
         avail_to_root = (st.f_bfree * st.f_frsize)  / 1024
         # Remaining free space usable by user.
         avail_to_user = (st.f_bavail * st.f_frsize)  / 1024
         # Total space being used in general.
         used = (total - avail_to_root)
         # Total space which is available to user (same as 'total' but
         # for the user).
         total_user = used + avail_to_user
         # User usage percent compared to the total amount of space
         # the user can use. This number would be higher if compared
         # to root's because the user has less space (usually -5%).
         try:
            usage_percent_user = (float(used) / total_user) * 100
         except:
            usage_percent_user=0
   
         self._data["diskstats"][monitored_dev]["total"].append(total)
         self._data["diskstats"][monitored_dev]["free_root"].append(avail_to_root)
         self._data["diskstats"][monitored_dev]["free_user"].append(avail_to_user)
         self._data["diskstats"][monitored_dev]["used"].append(used)
         self._data["diskstats"][monitored_dev]["total_user"].append(total_user)
         self._data["diskstats"][monitored_dev]["usage_user"].append(usage_percent_user)

   def _process_proc_net_netstat(self):

      with open("/proc/net/netstat", 'r') as f:
         while True:
            attrs = f.readline().split()
            vals = f.readline().split()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')
            for attr,val in zip(attrs[1:], vals[1:]):
               self._data["netstat"][prefix+attr].append(val)

   def _process_proc_net_snmp(self):

      with open("/proc/net/snmp", 'r') as f:
         while True:
            attrs = f.readline().split()
            vals = f.readline().split()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')
            for attr,val in zip(attrs[1:], vals[1:]):
               self._data["snmp"][prefix+attr].append(val)

   def _process_proc_net_stat_arp_cache(self):
      with open("/proc/net/stat/arp_cache", 'r') as f:
         attr_names = f.readline().split()

         for i,l in enumerate(f.readlines()):

            cpu_label="cpu{}".format(i)
            for i,e in enumerate(l.rstrip().split()):
               self._data["arp-cache"][cpu_label][attr_names[i]].append(int(e,16))

   def _process_proc_net_stat_ndisc_cache(self):
      with open("/proc/net/stat/ndisc_cache", 'r') as f:
         attr_names = f.readline().split()

         for i,l in enumerate(f.readlines()):

            cpu_label="cpu{}".format(i)
            for i,e in enumerate(l.rstrip().split()):
               self._data["ndisc-cache"][cpu_label][attr_names[i]].append(int(e,16))

   def _process_proc_net_stat_rt_cache(self):
      """

      index is cpu label
      """
      with open("/proc/net/stat/rt_cache", 'r') as f:
         attr_names = f.readline().split()
         for i,l in enumerate(f.readlines()):

            cpu_label="cpu{}".format(i)
            for i,e in enumerate(l.rstrip().split()):
               self._data["rt-cache"][cpu_label][attr_names[i]].append(int(e,16))

   def _inet_ntoa(self, addr):
      """
      addr is a hex network-ordered ip address

      return numbers-and-dots string 
      """
      return str(ipaddress.ip_address(bytes(reversed(bytearray.fromhex(addr)))))

   def _process_proc_net_arp(self):
      """
      list index is ip address
      """
      attr_names = ["type", "flags", "link_addr", "mask", "dev"]

      active_entry=[]
      with open("/proc/net/arp", 'r') as f:
         for l in f.readlines()[1:]:
            split = l.rstrip().split()

            # create entry if needed
            ip_addr = split[0]
            active_entry.append(ip_addr)
            self._data["net/arp"].setdefault(ip_addr, init_rb_dict(attr_names,type=str))

            for i,e in enumerate(split[1:]):
               self._data["net/arp"][ip_addr][attr_names[i]].append(e)

      # cleanup old entries
      for monitored_entry in list(self._data["net/arp"].keys()):
         if monitored_entry not in active_entry:
            del self._data["net/arp"][monitored_entry]

   def _process_proc_net_route(self):
      attr_names = ["if_name", "dst", "gateway", "flags", "ref_cnt", "use",
                    "metric", "mask", "mtu", "win", "irtt"]
      self._data["net/route"] = []

      with open("/proc/net/route", 'r') as f:
         for line in f.readlines()[1:]:
            entry = []
            for i,e in  enumerate(line.rstrip().split()):
               if i in [1,2,7]: # indexes of addrs
                  e=self._inet_ntoa(e)
                  
               entry.append((attr_names[i],e))
            self._data["net/route"].append(entry)

   def _open_read_append(self, path, obj):
      """
      append content of file at path to an object, if file exists

      """
      try:
         with open(path) as f:
            obj.append(f.read().rstrip())
      except:
         pass
         
   def _open_read(self, path):
      """
      return content of file if file exists

      """
      
      try:
         with open(path) as f:
            return f.read().rstrip()
      except:
         return None

   def _process_interfaces(self):
      """
      list interfaces and get their addresses

      index is if_name

      """
      attr_list_netdev = [ 
         "rx_bytes", "rx_packets", "rx_errs", "rx_drop", "rx_fifo",
         "rx_frame", "rx_compressed", "rx_multicast", 
         "tx_bytes", "tx_packets", "tx_errs", "tx_drop", "tx_fifo",
         "tx_cols", "tx_carrier", "tx_compressed",
         # ring params
         "rx_max_pending",
         "rx_mini_max_pending","rx_jumbo_max_pending","tx_max_pending",
         "rx_pending", "rx_mini_pending", "rx_jumbo_pending", "tx_pending",
      ]
      attr_list = [
         "link_addr", "link_broadcast", "link_peer",  
         "link_gw_addr", "link_gw_if", "link_gw_default",  
         "ip4_addr", "ip4_broadcast", "ip4_netmask", "ip4_peer",
         "ip4_gw_addr", "ip4_gw_if", "ip4_gw_default",  
         "ip6_addr", "ip6_broadcast", "ip6_netmask", "ip6_peer",  
         "ip6_gw_addr", "ip6_gw_if", "ip6_gw_default",  
         "dns_server", "dhcp_server",
         "wireless",
         "numa_node", "local_cpulist", "local_cpu",
         "enable", "current_link_speed", "current_link_width",
         "driver", "bus_info", 
         "bus_info", "wireless_protocol",
         "duplex", "carrier",
         "operstate", "type",
          
          
         "mtu", "tx_queue_len", 
         "ufo",
         "broadcast", "debug","loopback",
         "point_to_point","notrailers","running","noarp","promisc",
         "allmulticast","lb_master","lb_slave","multicast_support",
         "portselect","automedia","dynamic",
         
         "tx-scatter-gather","tx-checksum-ipv4",
         "tx-checksum-ip-generic","tx-checksum-ipv6",
         "highdma","tx-scatter-gather-fraglist","tx-vlan-hw-insert",
         "rx-vlan-hw-parse","rx-vlan-filter","vlan-challenged",
         "tx-generic-segmentation","tx-lockless","netns-local",
         "rx-gro","rx-lro","tx-tcp-segmentation","tx-gso-robust",
         "tx-tcp-ecn-segmentation","tx-tcp-mangleid-segmentation",
         "tx-tcp6-segmentation","tx-fcoe-segmentation","tx-gre-segmentation",
         "tx-gre-csum-segmentation","tx-ipxip4-segmentation",
         "tx-ipxip6-segmentation","tx-udp_tnl-segmentation",
         "tx-udp_tnl-csum-segmentation","tx-gso-partial",
         "tx-sctp-segmentation","tx-esp-segmentation","tx-udp-segmentation",
         "tx-checksum-fcoe-crc","tx-checksum-sctp","fcoe-mtu",
         "rx-ntuple-filter","rx-hashing","rx-checksum","tx-nocache-copy",
         "rx-fcs","rx-all","tx-vlan-stag-hw-insert","rx-vlan-stag-hw-parse",
         "rx-vlan-stag-filter","l2-fwd-offload","hw-tc-offload",
         "esp-hw-offload","esp-tx-csum-hw-offload","rx-udp_tunnel-port-offload",
         "tls-hw-tx-offload","tls-hw-rx-offload","rx-gro-hw","tls-hw-record",
         
         # counters
         "carrier_down_count", "carrier_up_count", "carrier_changes",
      ] + attr_list_netdev
      type_list = 37*[str] + 70*[int] + 27*[int]
      counter_list = 107*[False] + 27*[True]

      gws = netifaces.gateways()
      active_ifs = []
      
      # DNS
      # before ~2018 dns are stored in /etc/resolv.conf
      nameserver=""
      nameservers={}
      with open('/etc/resolv.conf') as f:
         for l in f.readlines():
            if l.startswith("nameserver"):
               nameserver = l.split()[-1]
               break
      # post-2018 systems use systemd based resolution
      # 127.0.0.53 indicates such behavior
      if not nameserver or nameserver == "127.0.0.53":
         res=subprocess.run(["systemd-resolve","--no-pager","--status"],
                        capture_output=True)
         this_if = "global"
         for l in res.stdout.split(b'\n'):
            if b"Link" in l:
               this_if=l.split()[-1][1:-1].decode()
            elif b"Current DNS Server" in l:
               nameservers[this_if]=l.split()[-1].decode()
      
      # DHCP
      # parse dhcp lease files
      dhcp_servers={}
      prefix='/var/lib/dhcp/'
      for suffix in os.listdir(prefix):
         if not suffix.endswith("leases"):
            continue
         with open(prefix+suffix) as f:
            for l in f.readlines():
               if "interface" in l:
                  this_if = l.split()[-1][1:-2]
               elif "dhcp-server-identifier" in l:
                  dhcp_servers[this_if] = l.split()[-1][:-1]
      
      for if_name in netifaces.interfaces(): #os.listdir("/sys/class/net")
         
         # create dict if interface was never observed
         active_ifs.append(if_name)
         self._data["net/dev"].setdefault(if_name, init_rb_dict(attr_list, 
                                          types=type_list, counters=counter_list))
         if_dict = self._data["net/dev"][if_name]
         # link
         addrs = netifaces.ifaddresses(if_name)
         if netifaces.AF_LINK in addrs:
            # addresses
            for item in addrs[netifaces.AF_LINK]:
               if "addr" in item:
                  if_dict["link_addr"].append(item["addr"])
               if "broadcast" in item:
                  if_dict["link_broadcast"].append(item["broadcast"])
               if "peer" in item:
                  if_dict["link_peer"].append(item["peer"])
            # gateways
            if netifaces.AF_LINK in gws:
               for item in gws[netifaces.AF_LINK]:
                  if item[1] != if_name:
                     continue
                  if_dict["link_gw_addr"].append(item[0])
                  if_dict["link_gw_if"].append(item[1])
                  if_dict["link_gw_default"].append(item[2])

         # ip4
         if netifaces.AF_INET in addrs:
            # addr
            for item in addrs[netifaces.AF_INET]:
               if "addr" in item:
                  if_dict["ip4_addr"].append(item["addr"])
               if "broadcast" in item:
                  if_dict["ip4_broadcast"].append(item["broadcast"])
               if "netmask" in item:
                  if_dict["ip4_netmask"].append(item["netmask"])
               if "peer" in item:
                  if_dict["ip4_peer"].append(item["peer"])
            # gateways
            if netifaces.AF_INET in gws:
               for item in gws[netifaces.AF_INET]:
                  if item[1] != if_name:
                     continue
                  if_dict["ip4_gw_addr"].append(item[0])
                  if_dict["ip4_gw_if"].append(item[1])
                  if_dict["ip4_gw_default"].append(item[2])

         # ip6 addr
         if netifaces.AF_INET6 in addrs:
            # addr
            for item in addrs[netifaces.AF_INET6]:
               if "addr" in item:
                  if_dict["ip6_addr"].append(item["addr"])
               if "broadcast" in item:
                  if_dict["ip6_broadcast"].append(item["broadcast"])
               if "netmask" in item:
                  if_dict["ip6_netmask"].append(item["netmask"])
               if "peer" in item:
                  if_dict["ip6_peer"].append(item["peer"])
            # gateways
            if netifaces.AF_INET6 in gws:
               for item in gws[netifaces.AF_INET6]:
                  if item[1] != if_name:
                     continue
                  if_dict["ip6_gw_addr"].append(item[0])
                  if_dict["ip6_gw_if"].append(item[1])
                  if_dict["ip6_gw_default"].append(tem[2])
                  
         self.read_ethtool_info(if_name, if_dict)
                  
         #
         # non-standard if attributes
         # https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-class-net
         #
         path_prefix="/sys/class/net/{}/".format(if_name)
         self._open_read_append(path_prefix+"carrier_down_count",
             if_dict["carrier_down_count"])
         self._open_read_append(path_prefix+"carrier_up_count",
             if_dict["carrier_up_count"])
         self._open_read_append(path_prefix+"carrier_changes",
             if_dict["carrier_changes"])             
         self._open_read_append(path_prefix+"device/numa_node",
             if_dict["numa_node"])
         self._open_read_append(path_prefix+"device/local_cpulist",
             if_dict["local_cpulist"])
         self._open_read_append(path_prefix+"device/local_cpu",
             if_dict["local_cpu"])
         self._open_read_append(path_prefix+"device/enable",
             if_dict["enable"])
         self._open_read_append(path_prefix+"device/current_link_speed",
             if_dict["current_link_speed"])
         self._open_read_append(path_prefix+"device/current_link_width",
             if_dict["current_link_width"])
         self._open_read_append(path_prefix+"mtu",
             if_dict["mtu"])
         self._open_read_append(path_prefix+"tx_queue_len",
             if_dict["tx_queue_len"])
         self._open_read_append(path_prefix+"duplex",
             if_dict["duplex"])
         self._open_read_append(path_prefix+"carrier",
             if_dict["carrier"])
         self._open_read_append(path_prefix+"operstate",
             if_dict["operstate"])
         if_type = _linux_if_types.get(self._open_read(path_prefix+"type"),
                                       "unknown")
         if_dict["type"].append(if_type)
         if_dict["wireless"].append(
               int(os.path.exists(path_prefix+"wireless")))
         if_dict["dns_server"].append(
               nameservers.get(if_name, nameserver))
         if_dict["dhcp_server"].append(
               dhcp_servers.get(if_name, ""))               
               
      with open("/proc/net/dev", 'r') as f:
         for l in f.readlines()[2:]:
            attr_val = [e.rstrip(':') for e in l.rstrip().split()]
            index = attr_val[0] 
            self._data["net/dev"].setdefault(index, init_rb_dict(attr_list, 
                                    types=type_list, counters=counter_list))
            for i,e in enumerate(attr_val[1:]):
               self._data["net/dev"][index][attr_list_netdev[i]].append(e)
            active_ifs.append(index)

      # cleanup expired ifs
      for monitored_ifs in list(self._data["net/dev"].keys()):
         if monitored_ifs not in active_ifs:
            del self._data["net/dev"][monitored_ifs]
            
   def _process_routes(self):
   
      # https://man7.org/linux/man-pages/man7/rtnetlink.7.html
      #
      extra_attrs = ['RTA_PRIORITY', 'RTA_GATEWAY', 'RTA_OIF', 'RTA_DST',
         'RTA_SRC', 'RTA_IIF', 'RTA_PREFSRC',]
      base_attrs = [ 'dst_len', 'src_len', 'tos', 'proto', 'scope',
         'type',  
      ] 
      attrs = base_attrs+ extra_attrs

      # atm, we only consider main table
      for route in self._route.get_routes(table=254):
         if route['event'] != 'RTM_NEWROUTE':
            self.info("Unexpected route event: {}".format(route['event']))
         route['proto'] = rt_proto[route['proto']]
         route['scope'] = rt_scope[route['scope']]
         route['type'] = rt_type[route['type']]
         route_attrs = dict(route["attrs"])
         if route["family"] == socket.AF_INET:
            route_dict = self._data["routes4"]
         elif route["family"] == socket.AF_INET6:
            route_dict = self._data["routes6"]
            
         if 'RTA_DST' in route_attrs:
            key = "{}/{}".format(route_attrs["RTA_DST"], route['dst_len'])
         else:
            key = "default"
         
         route_dict.setdefault(key, init_rb_dict(attrs, type=str))
         for attr in base_attrs:
            route_dict[key][attr].append(route[attr])
         for attr in extra_attrs:
            if attr in route_attrs:
               route_dict[key][attr].append(route_attrs[attr])
      

   def read_ethtool_info(self, if_name, if_dict):
      """

      @see ethtool.c from python3-ethtool
      """
      #self._ethtool = pyroute2.Ethtool()
      getters = [("driver", ethtool.get_module), 
                 ("bus_info", ethtool.get_businfo),
                # ("ufo", ethtool.get_ufo),
                ("wireless_protocol", ethtool.get_wireless_protocol),
               ]
      for attr, getter in getters:
         try:
            if_dict[attr].append(getter(if_name))
         except:
            pass
            
      for feature in self._ethtool.get_features(if_name)[0].values():
         if not feature.name or not feature.available:
            continue
         #self.info("if: {} feature: {}".format(if_name,feature.name))
         if_dict[feature.name].append(int(feature.enable))
         #self.info("inserted {} type {}".format(if_dict[attr]._top(),
         #                                       if_dict[attr].type))
         
      #try:
      #   coalesce_settings = ethtool.get_coalesce(if_name)
      #except:
      #   pass
      
      # 'rx_max_pending': 0, 'rx_mini_max_pending': 0,
      # 'rx_jumbo_max_pending': 0, 'tx_max_pending': 0,
      # 'rx_pending': 0, 'rx_mini_pending': 0, 'rx_jumbo_pending': 0,
      # 'tx_pending': 0
      try:
         for attr,val in ethtool.get_ringparam(if_name).items():
            if_dict[attr].append(val)
      except:
         pass
         
      try:
         flags = ethtool.get_flags(if_name)
      except:
         return
      if_dict["broadcast"].append((flags & ethtool.IFF_BROADCAST) != 0)
      if_dict["debug"].append((flags & ethtool.IFF_DEBUG) != 0)
      #if_dict["loopback"].append((flags & ethtool.IFF_LOOPBACK) != 0)
      if_dict["point_to_point"].append((flags & ethtool.IFF_POINTOPOINT) != 0)
      if_dict["notrailers"].append((flags & ethtool.IFF_NOTRAILERS) != 0)
      if_dict["running"].append((flags & ethtool.IFF_RUNNING) != 0)
      if_dict["noarp"].append((flags & ethtool.IFF_NOARP) != 0)
      if_dict["promisc"].append((flags & ethtool.IFF_PROMISC) != 0)
      if_dict["allmulticast"].append((flags & ethtool.IFF_ALLMULTI) != 0)
      if_dict["lb_master"].append((flags & ethtool.IFF_MASTER) != 0)
      if_dict["lb_slave"].append((flags & ethtool.IFF_SLAVE) != 0)
      if_dict["multicast_support"].append((flags & ethtool.IFF_MULTICAST) != 0)
      if_dict["portselect"].append((flags & ethtool.IFF_PORTSEL) != 0)
      if_dict["automedia"].append((flags & ethtool.IFF_AUTOMEDIA) != 0)
      if_dict["dynamic"].append((flags & ethtool.IFF_DYNAMIC) != 0)
      
      #self._ethtool.close()

   def _process_net_settings(self):
      """
      parse network kernel parameters from /pros/sys/
      normally read through sysctl calls

      """
      category="proc/sys"
      with open("/proc/sys/net/core/rmem_default") as f:
         self._data[category]["net.core.rmem_default"].append(f.read().rstrip())
      with open("/proc/sys/net/core/rmem_max") as f:
         self._data[category]["net.core.rmem_max"].append(f.read().rstrip())
      with open("/proc/sys/net/core/wmem_default") as f:
         self._data[category]["net.core.wmem_default"].append(f.read().rstrip())
      with open("/proc/sys/net/core/wmem_max") as f:
         self._data[category]["net.core.wmem_max"].append(f.read().rstrip())
      with open("/proc/sys/net/core/default_qdisc") as f:
         self._data[category]["net.core.default_qdisc"].append(f.read().rstrip())
      with open("/proc/sys/net/core/netdev_max_backlog") as f:
         self._data[category]["net.core.netdev_max_backlog"].append(f.read().rstrip())

      attr_suffixes=["_min","_pressure", "_max"]
      page_to_bytes=4096
      with open("/proc/sys/net/ipv4/tcp_mem") as f:
         for i,e in enumerate(f.read().rstrip().split()):
            self._data[category]["net.ipv4.tcp_mem"+attr_suffixes[i]].append(
                  int(e)*page_to_bytes)

      attr_suffixes=["_min","_default", "_max"]
      with open("/proc/sys/net/ipv4/tcp_rmem") as f:
         for i,e in enumerate(f.read().rstrip().split()):
            self._data[category]["net.ipv4.tcp_rmem"+attr_suffixes[i]].append(e)
      with open("/proc/sys/net/ipv4/tcp_wmem") as f:
         for i,e in enumerate(f.read().rstrip().split()):
            self._data[category]["net.ipv4.tcp_wmem"+attr_suffixes[i]].append(e)

      with open("/proc/sys/net/ipv4/tcp_congestion_control") as f:
         self._data[category]["net.ipv4.tcp_congestion_control"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_sack") as f:
         self._data[category]["net.ipv4.tcp_sack"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_dsack") as f:
         self._data[category]["net.ipv4.tcp_dsack"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_fack") as f:
         self._data[category]["net.ipv4.tcp_fack"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_syn_retries") as f:
         self._data[category]["net.ipv4.tcp_syn_retries"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_slow_start_after_idle") as f:
         self._data[category]["net.ipv4.tcp_slow_start_after_idle"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_retries1") as f:
         self._data[category]["net.ipv4.tcp_retries1"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_retries2") as f:
         self._data[category]["net.ipv4.tcp_retries2"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_mtu_probing") as f:
         self._data[category]["net.ipv4.tcp_mtu_probing"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_max_syn_backlog") as f:
         self._data[category]["net.ipv4.tcp_max_syn_backlog"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_base_mss") as f:
         self._data[category]["net.ipv4.tcp_base_mss"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_min_snd_mss") as f:
         self._data[category]["net.ipv4.tcp_min_snd_mss"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_ecn_fallback") as f:
         self._data[category]["net.ipv4.tcp_ecn_fallback"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_ecn") as f:
         self._data[category]["net.ipv4.tcp_ecn"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_adv_win_scale") as f:
         self._data[category]["net.ipv4.tcp_adv_win_scale"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_window_scaling") as f:
         self._data[category]["net.ipv4.tcp_window_scaling"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_tw_reuse") as f:
         self._data[category]["net.ipv4.tcp_tw_reuse"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_syncookies") as f:
         self._data[category]["net.ipv4.tcp_syncookies"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_timestamps") as f:
         self._data[category]["net.ipv4.tcp_timestamps"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_no_metrics_save") as f:
         self._data[category]["net.ipv4.tcp_no_metrics_save"].append(f.read().rstrip())

      with open("/proc/sys/net/ipv4/ip_forward") as f:
         self._data[category]["net.ipv4.ip_forward"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/ip_no_pmtu_disc") as f:
         self._data[category]["net.ipv4.ip_no_pmtu_disc"].append(f.read().rstrip())
