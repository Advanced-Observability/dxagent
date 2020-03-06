"""
bm_health.py

   Input parsing for baremetal health monitoring

@author: K.Edeline
"""

import os
import netifaces
import time

class BMWatcher():

   def __init__(self, data, info):
      self.msec_per_jiffy = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
      self._data = data
      self.info = info
   
   def input(self):
      """
      baremetal health: Linux

      """

      """
      parse input from

      /proc/<PID>/stat k
      /proc/stat + stat/cpu k
      /proc/meminfo k
      /proc/loadavg       k
      /proc/swaps      k
      /proc/uptime k
      /proc/diskstats
      /proc/net/netstat k
      /proc/net/snmp k
      /proc/net/stat/arp_cache k
      /proc/net/stat/ndisc_cache k
      /proc/net/stat/rt_cache k
      /proc/net/dev (interfaces listed in /sys/class/net/*) k
      /sys/class/net/enp4s0/

      /proc/net/arp
      /proc/net/tcp
      /proc/net/udp
      /proc/net/unix

      /proc/net/arp
      /proc/net/route
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
      self._process_proc_net_dev()
      self._process_proc_net_arp()
      self._process_proc_net_route()
      self._process_net_settings()

      # non-standards
      self._process_interfaces()

   def _process_proc_meminfo(self):
      with open("/proc/meminfo", 'r') as f:
         self._data["meminfo"] = [tuple(e.rstrip(':') for e in l.rstrip().split()) for l in f.readlines()]

   def _process_proc_stats(self):
      attr_names = [ "pid", "comm", "state", "ppid", "pgrp", "sid",
                     "tty_nr", "tty_pgrp", "flags", "min_flt", "cmin_flt",
                     "maj_flt", "cmaj_flt", "utime", "stime", "cutime",
                     "cstime", "priority", "nice", "num_threads", "itrealvalue",
                     "starttime", "vsize", "rss", "rsslim", "startcode",
                     "endcode", "startstack", "kstk_esp", "kstk_eip", "signal",
                     "blocked", "sigignore", "sigcatch", "wchan", "nswap",
                     "cnswap", "exit_signal", "processor", "rt_priority",
                     "policy", "delayacct_blkio_ticks", "gtime", 
                     "cgtime"]
      self._data["stats"] = []
      root_dir = "/proc/"
      proc_state = {"R":0, "S":0, "D":0, "T":0, "t":0, "X":0, "Z":0,
                    "P":0,"I": 0, }
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
               
               self._data["stats"].append([(attr_names[i], e) for i,e in enumerate(([pid,comm]+split[-1].split())[:len(attr_names)])])
            proc_state[self._data["stats"][-1][2][1]] += 1
         except FileNotFoundError:
            pass

      # count procs
      self._data["stats_global"] = [("proc_count",str(len(self._data["stats"])))]
      # count proc states
      proc_state_names = {"R":"run_count", "S":"sleep_count", "D":"wait_count", 
         "T":"stopped_count", "t":"ts_count",   "X":"dead_count",
         "Z":"zombie_count", "P":"parked_count", "I":"idle_count",
      }
      self._data["stats_global"].extend([(proc_state_names[d],str(v)) for d,v in proc_state.items()])
      

   def _process_proc_stat(self):
      attr_names = ["cpu", "user", "nice", "system", "idle", "iowait",
                    "irq", "softirq", "steal", "guest", "guest_nice"]

      self._data["stat/cpu"] = []
      self._data["stat"] = []

      with open("/proc/stat", 'r') as f:
         for l in f.readlines():
            if l.startswith("cpu"):
               self._data["stat/cpu"].append([(attr_names[i], e) for i,e in enumerate(l.rstrip().split())])
            elif l.startswith("intr") or l.startswith("softirq"):
               self._data["stat"].append(tuple(l.rstrip().split()[:2]))
            else:
               self._data["stat"].append(tuple(l.rstrip().split()))

   def _process_proc_loadavg(self):
      attr_names = ["1min", "5min", "15min", "runnable", "total"]
      self._data["loadavg"] = []

      with open("/proc/loadavg", 'r') as f:
         for i, e in enumerate(f.readline().rstrip().split()):
            if i == 3:
               vals = e.split('/')
               self._data["loadavg"].append((attr_names[i], vals[0]))
               self._data["loadavg"].append((attr_names[i+1], vals[1]))
               break
            else:
               self._data["loadavg"].append((attr_names[i], e))

   def _process_proc_swaps(self):
      """
      [
         [(attr[0], e), (attr[1], e), ..], # a single swap
         [(attr[0], e), (attr[1], e), ..]
      ]
      """

      attr_names = ["filename", "type", "size", "used", "priority"]
      self._data["swaps"] = []     
      with open("/proc/swaps", 'r') as f:
         self._data["swaps"] = [[(attr_names[i],e) for i,e in enumerate(l.rstrip().split())] for l in f.readlines()[1:]]

   def _process_proc_uptime(self):
      attr_names = ["up", "idle"]
      self._data["uptime"] = []

      with open("/proc/uptime", 'r') as f:
         self._data["uptime"] = [(attr_names[i], e) for i,e in enumerate(f.readline().rstrip().split())]

   def _process_proc_diskstats(self):
      attr_names = []
      with open("/proc/diskstats", 'r') as f:
         self._data["diskstats"] = [l.rstrip().split() for l in f.readlines()]

   def _process_proc_net_netstat(self):

      self._data["netstat"] = []
      with open("/proc/net/netstat", 'r') as f:
         while True:
            attrs = f.readline().split()
            vals = f.readline().split()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')

            self._data["netstat"] += [(prefix+attr, val) for attr,val in zip(attrs[1:], vals[1:])]

   def _process_proc_net_snmp(self):

      self._data["snmp"] = []
      with open("/proc/net/snmp", 'r') as f:
         while True:
            attrs = f.readline().split()
            vals = f.readline().split()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')

            self._data["snmp"] += [(prefix+attr, val) for attr,val in zip(attrs[1:], vals[1:])]

   def _process_proc_net_stat_arp_cache(self):
      with open("/proc/net/stat/arp_cache", 'r') as f:
         attr_names = f.readline().split()
         self._data["arp-cache"] = [[(attr_names[i], str(int(e,16))) for i,e in enumerate(l.rstrip().split())] for l in f.readlines()]

   def _process_proc_net_stat_ndisc_cache(self):
      with open("/proc/net/stat/ndisc_cache", 'r') as f:
         attr_names = f.readline().split()
         self._data["ndisc-cache"] = [[(attr_names[i],str(int(e,16))) for i,e in enumerate(l.rstrip().split())] for l in f.readlines()]

   def _process_proc_net_stat_rt_cache(self):
      with open("/proc/net/stat/rt_cache", 'r') as f:
         attr_names = f.readline().split()
         self._data["rt-cache"] = [[(attr_names[i],str(int(e,16))) for i,e in enumerate(l.rstrip().split())] for l in f.readlines()]

   def _process_proc_net_dev(self):
      attr_names = ["if_name", 
                    "rx_bytes", "rx_packets", "rx_errs", "rx_drop", "rx_fifo",
                    "rx_frame", "rx_compressed", "rx_multicast", 
                    "tx_bytes", "tx_packets", "tx_errs", "tx_drop", "tx_fifo",
                    "tx_cols", "tx_carrier", "tx_compressed"]
      with open("/proc/net/dev", 'r') as f:
          self._data["net/dev"] = [[(attr_names[i],e.rstrip(':')) for i,e in enumerate(l.rstrip().split())] for l in f.readlines()[2:]]

   def _process_proc_net_arp(self):
      with open("/proc/net/arp", 'r') as f:
         #attr_names = f.readline().split()
         
         self._data["net/arp"] = [(l.rstrip().split()) for l in f.readlines()[1:]]

   def _process_proc_net_route(self):
      with open("/proc/net/route", 'r') as f:
         self._data["net/route"] = [tuple(l.rstrip().split()) for l in f.readlines()[1:]]

   def _process_interfaces(self):
      """
      list interfaces and get their addresses

      [ 
         ["if_name": 'lo', 
          [("link_addr", "00:00:00:00:00"),
           ("link_broadcast", "ff:ff:ff:ff:ff"),
           ("link_peer" , "00:00:01:00:00")],

          [("ip4_addr", "127.0.0.1"),
           ("ip4_broadcast", "127.0.0.255"),
           ("ip4_netmask" , "255.255.255.254")],

          [("ip6_addr", "::dead:beef"),
           ("ip6_broadcastr", "::ffff")
          ],
         ],

         ["if_name": 'enp4s0',  
            ...
         ],
      ]

      """

      self._data["bm_ifs"] = []
      gws = netifaces.gateways()
      for if_name in netifaces.interfaces(): #os.listdir("/sys/class/net")
         addrs = netifaces.ifaddresses(if_name)
         if_attrs = [("if_name",if_name)]

         # eth
         if netifaces.AF_LINK in addrs:
            link_attrs = []

            # addresses
            for item in addrs[netifaces.AF_LINK]:
               if "addr" in item:
                  link_attrs.append(("link_addr", item["addr"]))
               if "broadcast" in item:
                  link_attrs.append(("link_broadcast", item["broadcast"]))
               if "peer" in item:
                  link_attrs.append(("link_peer", item["peer"]))

            # gateways
            if netifaces.AF_LINK in gws:
               for item in gws[netifaces.AF_LINK]:

                  if item[1] != if_name:
                     continue
                  link_attrs.append(("gateway_addr", item[0]))
                  link_attrs.append(("gateway_if", item[1]))
                  link_attrs.append(("gateway_default", str(int(item[2]))))

            if_attrs.append(link_attrs)

         # ip4
         if netifaces.AF_INET in addrs:
            inet_attrs = []

            # addr
            for item in addrs[netifaces.AF_INET]:
               if "addr" in item:
                  inet_attrs.append(("ip4_addr", item["addr"]))
               if "broadcast" in item:
                  inet_attrs.append(("ip4_broadcast", item["broadcast"]))
               if "netmask" in item:
                  inet_attrs.append(("ip4_netmask", item["netmask"]))
               if "peer" in item:
                  inet_attrs.append(("ip4_peer", item["peer"]))

            # gateways
            if netifaces.AF_INET in gws:
               for item in gws[netifaces.AF_INET]:

                  if item[1] != if_name:
                     continue
                  link_attrs.append(("gateway_addr", item[0]))
                  link_attrs.append(("gateway_if", item[1]))
                  link_attrs.append(("gateway_default", str(int(item[2]))))

            if_attrs.append(inet_attrs)

         # ip6 addr
         if netifaces.AF_INET6 in addrs:
            inet6_attrs = []

            # addr
            for item in addrs[netifaces.AF_INET6]:
               if "addr" in item:
                  inet6_attrs.append(("ip6_addr", item["addr"]))
               if "broadcast" in item:
                  inet6_attrs.append(("ip6_broadcast", item["broadcast"]))
               if "netmask" in item:
                  inet6_attrs.append(("ip6_netmask", item["netmask"]))
               if "peer" in item:
                  inet6_attrs.append(("ip6_peer", item["peer"]))

            # gateways
            if netifaces.AF_INET6 in gws:
               for item in gws[netifaces.AF_INET6]:

                  if item[1] != if_name:
                     continue
                  link_attrs.append(("gateway_addr", item[0]))
                  link_attrs.append(("gateway_if", item[1]))
                  link_attrs.append(("gateway_default", str(int(item[2]))))

            if_attrs.append(inet6_attrs)

         self._data["bm_ifs"].append(if_attrs)



   def _process_net_settings(self):
      """
      parse network kernel parameters from /pros/sys/
      normally read through sysctl calls

      """
      self._data["proc/sys"] = []

      with open("/proc/sys/net/core/rmem_default") as f:
         self._data["proc/sys"].append(("net.core.rmem_default", f.read().rstrip(), "B"))
      with open("/proc/sys/net/core/rmem_max") as f:
         self._data["proc/sys"].append(("net.core.rmem_max", f.read().rstrip(), "B"))
      with open("/proc/sys/net/core/wmem_default") as f:
         self._data["proc/sys"].append(("net.core.wmem_default", f.read().rstrip(), "B"))
      with open("/proc/sys/net/core/wmem_max") as f:
         self._data["proc/sys"].append(("net.core.wmem_max", f.read().rstrip(), "B"))
      with open("/proc/sys/net/core/default_qdisc") as f:
         self._data["proc/sys"].append(("net.core.default_qdisc", f.read().rstrip()))
      with open("/proc/sys/net/core/netdev_max_backlog") as f:
         self._data["proc/sys"].append(("net.core.netdev_max_backlog", f.read().rstrip()))

      attr_suffixes=["_min","_pressure", "_max"]
      page_to_bytes=4096
      with open("/proc/sys/net/ipv4/tcp_mem") as f:
         self._data["proc/sys"].extend([("net.ipv4.tcp_mem"+attr_suffixes[i],
            str(int(e)*page_to_bytes), "B") for i,e in 
                  enumerate(f.read().rstrip().split())])

      attr_suffixes=["_min","_default", "_max"]
      with open("/proc/sys/net/ipv4/tcp_rmem") as f:
         self._data["proc/sys"].extend([("net.ipv4.tcp_rmem"+attr_suffixes[i], e, "B")
                        for i,e in enumerate(f.read().rstrip().split())])
      with open("/proc/sys/net/ipv4/tcp_wmem") as f:
         self._data["proc/sys"].extend([("net.ipv4.tcp_wmem"+attr_suffixes[i], e, "B")
                        for i,e in enumerate(f.read().rstrip().split())])

      with open("/proc/sys/net/ipv4/tcp_congestion_control") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_congestion_control", 
                                        f.read().rstrip()))

      with open("/proc/sys/net/ipv4/tcp_sack") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_sack", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_dsack") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_dsack", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_fack") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_fack", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_syn_retries") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_syn_retries", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_slow_start_after_idle") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_slow_start_after_idle", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_retries1") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_retries1", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_retries2") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_retries2", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_mtu_probing") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_mtu_probing", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_max_syn_backlog") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_max_syn_backlog", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_base_mss") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_base_mss", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_min_snd_mss") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_min_snd_mss", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_ecn_fallback") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_ecn_fallback", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_ecn") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_ecn", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_adv_win_scale") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_adv_win_scale", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_window_scaling") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_window_scaling", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_tw_reuse") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_tw_reuse", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_syncookies") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_syncookies", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_timestamps") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_timestamps", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/tcp_no_metrics_save") as f:
         self._data["proc/sys"].append(("net.ipv4.tcp_no_metrics_save", f.read().rstrip()))

      with open("/proc/sys/net/ipv4/ip_forward") as f:
         self._data["proc/sys"].append(("net.ipv4.ip_forward", f.read().rstrip()))
      with open("/proc/sys/net/ipv4/ip_no_pmtu_disc") as f:
         self._data["proc/sys"].append(("net.ipv4.ip_no_pmtu_disc", f.read().rstrip()))
