"""
dxagent.py

   This file contains the core of dxagent

@author: K.Edeline
"""

import sys
import os
import sched
import curses
import time

from ios import IOManager
from sysinfo import SysInfo

ESCAPE = 27

class DXAgent(IOManager):

   """
   DXAgent

   
   """

   UP = -1
   DOWN = 1

   def __init__(self):
      super(DXAgent, self).__init__(self)
      self.load_ios()
      self.sysinfo = SysInfo()

      self.msec_per_jiffy = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
      self.info(self.sysinfo)
      self.scheduler = sched.scheduler()
      
      self.top = 0 
      self.page = 0
      self.max_lines = 2**10      

      self._data = {}

   def _process_proc_meminfo(self):
      with open("/proc/meminfo", 'r') as f:
         self._data["meminfo"] = [tuple(e.rstrip(':') for e in l.rstrip().split()) for l in f.readlines()]

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

   def _process_sys_class_net(self):
      self._data["bm_ifs"] = os.listdir("/sys/class/net")

   def _input(self):
      """
      parse input from

      /proc/<PID>/stat
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
      
      
   fd = socket(PF_INET, SOCK_DGRAM, IPPROTO_IP)
   ioctl(fd, SIOCGIFCONF, ...)
   gets
   ioctl(4, SIOCGIFCONF, {120, {{"lo", {AF_INET, inet_addr("127.0.0.1")}}, {"eth0", {AF_INET, inet_addr("10.6.23.69")}}, {"tun0", {AF_INET, inet_addr("10.253.10.151")}}}})
      https://stackoverflow.com/questions/5281341/get-local-network-interface-addresses-using-only-proc

      /proc/net/arp
      /proc/net/route
      """
      

      """
      baremetal health: Linux

      """
      self._process_proc_meminfo()
      self._process_proc_stat()
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

      # non-standards linux locations 
      self._process_sys_class_net()

      """
      VPP

      """

      """
      ioam 

      """

   def process(self):
      """
      read input data, process and format it for
      displaying. re-schedule itself.

      """

      self._input()
      self._format()
      self.scheduler.enter(1,0,self.process)

   def _format_attrs(self, category):
      self.pad.addstr(category+"\n", curses.A_BOLD)
      for e in self._data[category]:
         self.pad.addstr(e[0]+": ")
         self.pad.addstr(" ".join(e[1:])+" ")
      self.pad.addstr("\n")
      self.pad.addstr("\n")

   def _format_attrs_list(self, category):
      self.pad.addstr(category+"\n", curses.A_BOLD)
      for l in self._data[category]:
         for e in l:
            self.pad.addstr(e[0]+": ")
            self.pad.addstr(" ".join(e[1:])+" ")
         self.pad.addstr("\n")
      self.pad.addstr("\n")

   def _format(self):
      """
      format data for displaying

      """

      self.height, self.width = self.window.getmaxyx()
      self.pad = curses.newpad(self.max_lines, self.width)

      self.pad.addstr("RAW INPUT\n")
   
      self.pad.addstr("System:\n\n")
      self.pad.addstr(str(self.sysinfo)+"\n")

      self.pad.addstr("\nBareMetal:\n\n")
      self.pad.addstr("bm_ifs: "+" ".join(self._data["bm_ifs"])+"\n\n")

      self._format_attrs("uptime")
      self._format_attrs("loadavg")
      self._format_attrs("meminfo")
      self._format_attrs_list("swaps")
      self._format_attrs("netstat")
      self._format_attrs("snmp")
      self._format_attrs_list("net/dev")
      self._format_attrs_list("stat/cpu")
      self._format_attrs("stat")
      self._format_attrs_list("arp-cache")
      self._format_attrs_list("rt-cache")
      self._format_attrs_list("ndisc-cache")

   def _display(self):
      """
      refresh the display and reschedule itself

      """

      self.height, self.width = self.window.getmaxyx()
      self.pad.refresh(self.top, 0, 0, 0, self.height-1, self.width-1)
      self.scheduler.enter(0.1,1,self._display)

   def start_gui(self):

      self.window = curses.initscr()
      curses.noecho()
      curses.cbreak()
      self.window.keypad(True)
      os.environ.setdefault('ESCDELAY', '25')
      self.window.nodelay(True)
      
      curses.start_color()
      curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
      curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
      self.window.refresh()

      self.height, self.width = self.window.getmaxyx()
      self.pad = curses.newpad(2**10, self.width)

   def stop_gui(self):
      self.window.keypad(False)
      curses.nocbreak()
      curses.echo()
      curses.endwin()

   def scroll(self, direction):
      if direction == self.UP and self.top > 0:
         self.top += direction
      elif direction == self.DOWN and (self.top < self.max_lines-self.height):
         self.top += direction

   def paging(self, direction):
      if direction == self.UP and self.top > 0:
         self.top -= min(self.height-1,self.top)
      elif direction == self.DOWN and (self.top < self.max_lines-self.height-1):
         self.top += min(self.height-1,self.max_lines-self.top-self.height)

   def run(self):
      """
      main function
      """
      try:
         self.start_gui()
         self.process()
         self._display()

         while True:

            # user input
            c = self.window.getch()
            while c != -1:
               if c == ord('q') or c == ESCAPE: 
                  raise KeyboardInterrupt()
               elif c == curses.KEY_UP:
                   self.scroll(self.UP)
               elif c == curses.KEY_DOWN:
                   self.scroll(self.DOWN)
               elif c == curses.KEY_PPAGE:
                   self.paging(self.UP)
               elif c == curses.KEY_NPAGE:
                   self.paging(self.DOWN)
               elif c == curses.KEY_LEFT:
                   pass
               elif c == curses.KEY_RIGHT:
                   pass
               c = self.window.getch()
 
            self.scheduler.run(blocking=False)
            time.sleep(0.1)

      except KeyboardInterrupt:
         pass
      finally:
         self.stop_gui()
      

if __name__ == '__main__':
   dxa = DXAgent()
   dxa.run()

