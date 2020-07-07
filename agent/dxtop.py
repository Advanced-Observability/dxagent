"""
dxtop.py

   This file contains the GUI

@author: K.Edeline

"""

import curses
import sched
import time
import datetime
import os

from agent.constants import *
from agent.core.ios import IOManager
from agent.core.shareablebuffer import ShareableBuffer
from agent.core.shareablebuffer import ShareableBufferException
from agent.core.rbuffer import RingBuffer, Severity
from agent.input.sysinfo import SysInfo
from agent.input.vpp_input import vpp_support
from agent.input.vm_input import hypervisors_support

ESCAPE_CHAR=27
ENTER_CHAR=10
HLINE_CHAR=u'\u2500'
VLINE_CHAR=u'\u2502'
TTEE_CHAR=u'\u252c'
BTEE_CHAR=u'\u2534'
CROSS_CHAR=u'\u253c'

class DXTop(IOManager):

   """
   DXTop

   console app for DxAgent

   """

   UP = -1
   DOWN = 1

   def __init__(self):
      super(DXTop, self).__init__(self)

      self.load_ios()
      self.scheduler = sched.scheduler()
      self.sysinfo = SysInfo()
      
      # navigation vars  
      self.screen = 0
      self.max_screens = 7
      self.top = [0 for _ in range(self.max_screens)]
      self.current = [0 for _ in range(self.max_screens)]
      self.max_lines = 2**14
      self._data=None

      try:
         self.sbuffer = ShareableBuffer()
      except FileNotFoundError:
         raise ShareableBufferException("ShareableBuffer not found")

      self.vbox_supported = hypervisors_support()
      self.vpp_api_supported, self.vpp_stats_supported=vpp_support()
      
   def resize_columns(self):
      """
      find column sizes from screen width

      """
      # column sizes proportions
      self.col_sizes=[80,64,32]
      self.col_sizes_cpu=[30,12,12,12,12,12,12,12,12]
      # shrink factor until columns fit screen
      shrink_factor = 0.85

      while self.width <= sum(self.col_sizes)+len(self.col_sizes):
         self.col_sizes = [int(c*shrink_factor) for c in self.col_sizes]
      while self.width <= sum(self.col_sizes_cpu)+len(self.col_sizes_cpu):
         self.col_sizes_cpu = [int(c*shrink_factor) for c in self.col_sizes_cpu]

      self.col_sizes[-1] = 0
      self.col_sizes_cpu[-1] = 0

      self._format_header()
      self._format_colname_pad()
      if self._data:
         self._format_top_pad()
      
      self.info("resized {}".format(str(self.col_sizes)))
      self.info("width: {}".format(self.width))

   def _center_text(self, s, width=None):
      """
      return a pad-fitting string with s centered in blanks

      """
      if not width:
         width = self.pad_width
      lpad,rpad = self._center_padding(s, width=width)
      return (lpad+s+rpad)[:width]

   def _center_padding(self, s, width=None):
      """
      @return left and right padding for a self.pad_width-centered string

      """
      if not width:
         width = self.pad_width
      padding = int((width-len(s))/2)
      rest = (width-len(s)) % 2
      return padding*" ",(padding+rest)*" "

   def _fill_line(self, s):
      """
      fill string with blanks
      """
      padding = self.pad_width-len(s)
      return s+" "*padding

   def hline(self, col_sizes=[0]):
      return self._hline(col_sizes, HLINE_CHAR)

   def hline_x(self, col_sizes=[0]):
      return self._hline(col_sizes, CROSS_CHAR)

   def hline_bottom(self, col_sizes=[0]):
      return self._hline(col_sizes, BTEE_CHAR)

   def hline_top(self, col_sizes=[0]):
      return self._hline(col_sizes, TTEE_CHAR)

   def _hline(self, col_sizes, sep_char):
      """
      draw a horizontal line, add a sep_char between each
      column, last column has max size that fits pad.
      
      """
      s=""
      for i, col_size in enumerate(col_sizes):

         if i == len(col_sizes) - 1:
            col_size = self.pad_width-sum(col_sizes)-len(col_sizes)+1
         s += col_size*HLINE_CHAR

         if i < len(col_sizes) - 1:
            s += sep_char

      return s
      
   def _append_content(self, s, screen_index, flags=0, fill=False, 
                       buf=None):
      """
      content is a list of screen content
      each screen content is a list of (str, flags) tuples

      @param fill Fill rest of line with blanks
      @param buf The buffer related to this line
      """
      if fill:
         s = self._fill_line(s)
      self.content[screen_index].append((s,flags))

   def _format(self):
      """
      format data for displaying

      """

      # baremetal 
      self._format_attrs_list_rb_percpu("stat/cpu", 0)
      self._format_attrs_list_rb("sensors/thermal", 0)
      self._format_attrs_list_rb("sensors/fans", 0)
      self._format_attrs_list_rb("sensors/coretemp", 0)
      self._format_attrs_list_rb_percpu("rt-cache", 0)
      self._format_attrs_list_rb_percpu("arp-cache", 0)
      self._format_attrs_list_rb_percpu("ndisc-cache", 0)

      self._format_attrs_list_rb("diskstats", 1)
      self._format_attrs_list_rb("swaps", 1)
      self._format_attrs_rb("meminfo", 1)

      self._format_attrs_rb("stats_global", 2)
      self._format_attrs_rb("loadavg", 2)
      self._format_attrs_rb("stat", 2)

      # XXX: very verbose at the end, also very greedy
      if self.args.verbose:
         self._format_attrs_list_rb("stats", 2)

      self._format_attrs_list_rb("net/dev", 3)
      self._format_attrs_list_rb("routes4", 3)
      self._format_attrs_list_rb("routes6", 3)
      self._format_attrs_rb("proc/sys", 3)
      self._format_attrs_rb("netstat", 3)
      self._format_attrs_rb("snmp", 3)
      self._format_attrs_list_rb("net/arp", 3)

      # VM
      # virtualbox
      self._format_attrs_list_rb("virtualbox/vms", 4)

      # VPP
      #vpp_api
      self._format_attrs_rb("vpp/system", 5)
      self._format_attrs_list_rb("vpp/api/if", 5)

      #vpp_stats
      self._format_attrs_rb("vpp/stats/sys", 5) 
      self._format_attrs_list_rb("vpp/stats/buffer-pool", 5)
      self._format_attrs_list_rb("vpp/stats/workers", 5) 
      self._format_attrs_list_rb("vpp/stats/if", 5)
      self._format_attrs_list_rb("vpp/stats/err", 5)

      #vpp_gnmi
      if "vpp/gnmi" in self._data:
         self._append_content(self._center_text("vpp/gnmi"), 5, curses.A_BOLD)
         for kb_name in self._data["vpp/gnmi"]:
            self._append_content(self._center_text(kb_name), 5, curses.A_DIM)
            self._format_attrs_rb(kb_name, 5, subdict=self._data["vpp/gnmi"], title=False)
            self._format_attrs_list_rb("kb_net_if", 5, 
                                       subdict=self._data["vpp/gnmi"][kb_name],
                                       title=False)

      # Health metrics Pad
      self._append_content(self._center_text("Symptoms"), 6, curses.A_REVERSE)
      self._append_content(self._center_text(" "), 6)
      if "symptoms" in self._data:
         for name, severity, args in self._data["symptoms"]:
            if not args:
               s=name
               lpad,rpad=self._center_padding(s)
               flags = [(len(lpad),curses.color_pair(int(severity))),(len(s)+len(lpad),0)]
               self._append_content(self._center_text(s), 6, flags=flags)
            else:
               s="{}: {}".format(name,args)
               lpad,rpad=self._center_padding(s)
               flags = [(len(lpad),curses.color_pair(int(severity))),(len(s)+len(lpad),0)]
               self._append_content(self._center_text(s), 6, flags=flags)              
         self._append_content(self._center_text(" "), 6)
      
      self._append_content(self._center_text("Metrics"), 6, curses.A_REVERSE)
      self._format_attrs_list_rb_percpu("/node/bm/cpu", 6, health=True)
      self._format_attrs_list_rb("/node/bm/net/if", 6, health=True)
      self._format_attrs_list_rb("/node/bm/sensors", 6, health=True)
      self._format_attrs_rb("/node/bm/mem", 6, health=True)
      self._format_attrs_rb("/node/bm/proc", 6, health=True)
      self._format_attrs_list_rb("/node/bm/disks", 6, health=True)
      self._format_attrs_rb("/node/bm/net", 6, health=True)
      
      if "/node/vm" in self._data:
         for vm_name in self._data["/node/vm"]:
            vm_dict = self._data["/node/vm"][vm_name]
            skip = ["/node/vm/net/if", "/node/vm/cpu"]
            for subservice in vm_dict:
               if subservice in skip:
                  continue
               self._format_attrs_rb(subservice, 6, subdict=vm_dict,
                                     health=True, health_index=vm_name)
            self._format_attrs_list_rb("/node/vm/cpu", 6, subdict=vm_dict,
                                              health=True, health_index=vm_name)
            self._format_attrs_list_rb("/node/vm/net/if", 6, subdict=vm_dict,
                                        health=True, health_index=vm_name)
                                    
      if "/node/kb" in self._data:      
         for kb_name in self._data["/node/kb"]:
            kb_dict = self._data["/node/kb"][kb_name]
            skip = ["/node/kb/net/if"]
            for subservice in kb_dict:
               if subservice in skip:
                  continue
               self._format_attrs_rb(subservice, 6, subdict=kb_dict,
                                     health=True, health_index=kb_name)
            self._format_attrs_list_rb("/node/kb/net/if", 6, subdict=kb_dict,
                                      health=True, health_index=kb_name)
             
      self.resize_columns()
      
   def _indexed_path(self, path, index=""):
      path = path.replace("node","node[name={}]".format(self.sysinfo.node))
      path = path.replace("vm","vm[name={}]".format(index))
      path = path.replace("kb","kb[name={}]".format(index))
      return path      
      
   def _root_health_score(self, path):      
      # XXX: 
      path = path.replace("/if","")
      return self._data["health_scores"][path]

   def _format_attrs_rb(self, category, pad_index, extend_name=False,
                        subdict=None, title=True, health=False, health_index=""):
      """
      format a dict of ringbuffers into a curses pad
      
      @param extend_name if True, prepend attr name with subservice path
 
      """
      if subdict:
         data=subdict
      else:
         data=self._data
      if category not in data:
         return
      if title:
         title_str = category
         flags = curses.A_BOLD
         if health:
            title_str = self._indexed_path(category, index=health_index)
            score = self._root_health_score(title_str)
            title_str += " health:"
            category_len = len(title_str)
            title_str += str(score)
            lpad,rpad=self._center_padding(title_str)
            # flags to color health value only
            flags = [(len(lpad), curses.A_BOLD),
                     (len(lpad)+category_len, 
                       curses.A_BOLD|curses.color_pair(self.health_colors[score])),
                     (len(lpad)+len(title_str), curses.A_BOLD)]
                  
         self._append_content(self._center_text(title_str),
                              pad_index, flags)
      self._append_content(self.hline_top(self.col_sizes), pad_index)

      for k,d in data[category].items():
         if not isinstance(d, list):
            continue  
            
         s = (" {}"+" "*self.col_sizes[0]).format(k)[:self.col_sizes[0]]
         s += VLINE_CHAR
         flags = []

         value, severity = d[:2]
         if severity:
            flags.append((len(s),curses.color_pair(severity)))
         s += ("{}"+" "*self.col_sizes[1]).format(value)[:self.col_sizes[1]]

         if severity:
            flags.append((len(s),0))
         s += VLINE_CHAR

         value, severity = d[2:4]
         if severity:
            flags.append((len(s),curses.color_pair(severity)))
         s += "{}".format(value)
         if severity:
            flags.append((len(s),0))

         self._append_content(s, pad_index, flags, fill=True)      

      self._append_content(self.hline_bottom(self.col_sizes), pad_index)

   def _format_attrs_list_rb(self, category, pad_index, extend_name=False,
                             subdict=None, title=True, health=False,
                             health_index=""):
      """
      format a dict of dict of ringbuffers into a curses pad
      
      @param extend_name if True, prepend attr name with subservice path
 
      """
      if subdict:
         data=subdict
      else:
         data=self._data
      if category not in data:
         return
      if title:
         title_str = category
         flags = curses.A_BOLD
         if health:
            title_str = self._indexed_path(category, index=health_index)
            score = self._root_health_score(title_str)
            title_str += " health:"
            category_len = len(title_str)
            title_str += str(score)
            lpad,rpad=self._center_padding(title_str)
            # flags to color health value only
            flags = [(len(lpad), curses.A_BOLD),
                     (len(lpad)+category_len, 
                       curses.A_BOLD|curses.color_pair(self.health_colors[score])),
                     (len(lpad)+len(title_str), curses.A_BOLD)]
            
         self._append_content(self._center_text(title_str),
                              pad_index, flags)
      self._append_content(self.hline_top(self.col_sizes), pad_index)

      for i,(k,d) in enumerate(data[category].items()):

         s = " "*self.col_sizes[0]+VLINE_CHAR
         flags = [(len(s), curses.A_DIM)]
         substitle = k
         s +=  (substitle+" "*self.col_sizes[1])[:self.col_sizes[1]]
         flags.append((len(s), 0))
         s += VLINE_CHAR
         self._append_content(s, pad_index, fill=True, flags=flags)

         for kk,dd in d.items():
            if not isinstance(dd, list):
               continue
            s = (" {}"+" "*self.col_sizes[0]).format(kk)[:self.col_sizes[0]]
            s += VLINE_CHAR
            flags = []
      
            value, severity = dd[:2]
            if severity:
               flags = [(len(s),curses.color_pair(severity))]
            s += ("{}"+" "*self.col_sizes[1]).format(
               value)[:self.col_sizes[1]]
            if severity:
               flags.append((len(s),0))

            s += VLINE_CHAR
            value, severity = dd[2:4]
            if severity:
               flags.append((len(s),curses.color_pair(severity)))
            s += "{}".format(value)
            if severity:
               flags.append((len(s),0))

            self._append_content(s, pad_index, flags, fill=True, buf=dd)

         if i == len(data[category])-1:
            self._append_content(self.hline_bottom(self.col_sizes), pad_index)
         else:
            self._append_content(self.hline_x(self.col_sizes), pad_index)

   def _format_attrs_list_rb_percpu(self, category, pad_index, subdict=None,
                                    extend_name=False, health=False,
                                    health_index=""):
      """
      format a dict of dict of ringbuffers into a curses pad
 
      @param extend_name if True, prepend attr name with subservice path
      """
      if subdict:
         data=subdict
      else:
         data=self._data
      if category not in data:
         return
      cpu_slice = 8
      cpu_count = len(data[category])-1
      if "cpu" in data[category]:
         keys = data[category]["cpu"].keys()
      else:
         keys = data[category]["cpu0"].keys()
      
      title_str = category
      flags = curses.A_BOLD
      if health:
         title_str = self._indexed_path(category, index=health_index)
         score = self._root_health_score(title_str)
         title_str += " health:"
         category_len = len(title_str)
         title_str += str(score)
         lpad,rpad=self._center_padding(title_str)
         # flags to color health value only
         flags = [(len(lpad), curses.A_BOLD),
                  (len(lpad)+category_len, 
                    curses.A_BOLD|curses.color_pair(self.health_colors[score])),
                  (len(lpad)+len(title_str), curses.A_BOLD)]
         
      self._append_content(self._center_text(title_str),
                           pad_index, flags)
      self._append_content(self.hline(self.col_sizes), pad_index)

      for i in range(0,cpu_count,cpu_slice):
         self._append_content(
            self._center_text("cpu{}-cpu{}".format(i,i+cpu_slice-1)),
            pad_index, curses.A_DIM)
         self._append_content(self.hline_top(self.col_sizes_cpu), pad_index)

         for k in keys:
            s = (" {}"+" "*self.col_sizes_cpu[0]).format(k)[:self.col_sizes_cpu[0]]
            flags = [(0,0)]
            s += VLINE_CHAR

            for cpu_index in range(i,i+cpu_slice):

               cpu_label="cpu{}".format(cpu_index)
               d = data[category][cpu_label][k]
               value, severity = d[:2]
               if severity:
                  flags.append((len(s),curses.color_pair(severity)))
               s += ("{}"+" "*self.col_sizes_cpu[1]).format(
                     value)[:self.col_sizes_cpu[1]]

               if severity:
                  flags.append((len(s),0))
               if cpu_index < i+cpu_slice-1:
                  s += VLINE_CHAR

            self._append_content(s, pad_index, flags, fill=True)

         if cpu_count-i <= cpu_slice:
            self._append_content(self.hline_bottom(self.col_sizes_cpu), pad_index)
         else:
            self._append_content(self.hline_x(self.col_sizes_cpu), pad_index)

   def _format_colname_pad(self):
      self.colname_pad.clear()

      if self.screen == 0:
         pass
      elif self.screen in [1, 2, 3, 4, 5]:
         s= ("name"+" "*self.col_sizes[0])[:self.col_sizes[0]-1]
         self.colname_pad.addstr(" ")
         self.colname_pad.addstr(s, self.selection_color)
         s= ("value"+" "*self.col_sizes[1])[:self.col_sizes[1]]
         self.colname_pad.addstr(" ")
         self.colname_pad.addstr(s, self.selection_color)
         s= ("dynamicity"+" "*(self.pad_width-sum(self.col_sizes)))[:self.pad_width-sum(self.col_sizes)-3]
         self.colname_pad.addstr(" ")
         self.colname_pad.addstr(s, self.selection_color)
      elif self.screen == 6:
         pass

   def _format_header(self):
      """

      """
      self.header.clear()

      screen_names = ["CPU", "Memory", "Processes", "Networking",
                      "Virtual Machines", "VPP", "Health"]
      short_names = ["CPU", "Mem", "Proc", "Net",
                      "VMs", "VPP", "H"]
      this_name = [screen_names[self.screen]]
      
      full_str  = " | ".join(screen_names)
      short_str = " | ".join(short_names)
      min_str = screen_names[self.screen]
      
      names = [screen_names, short_names, this_name]   
      strs = [full_str, short_str, min_str]

      for names, s in zip(names, strs):

         if self.width > len(s):
            self._fill_header(names, s)
            break

   def _fill_header(self, names, s):
      """
      fill header pad with names

      """
      padding = int((self.width-len(s))/2)
      self.header.addstr(padding*" ")

      for i,name in enumerate(names):

         self.header.addstr(name, 
            curses.A_BOLD | curses.A_REVERSE if self.screen == i else 0)
         if i != len(names)-1:
            self.header.addstr(" | ")    

   def _format_top_pad(self):
      self.top_pad.clear()

      if self.screen in [0, 1, 2, 3]:
         # Line 1
         s=str(self.sysinfo)
         lpad,rpad=self._center_padding(s)
         self.top_pad.addstr(lpad+"node: ", curses.A_DIM)
         self.top_pad.addstr(self.sysinfo.node)
         self.top_pad.addstr(" system: ", curses.A_DIM)
         self.top_pad.addstr(self.sysinfo.system)
         self.top_pad.addstr(" release: ", curses.A_DIM)
         self.top_pad.addstr(self.sysinfo.release)
         self.top_pad.addstr(" arch: ", curses.A_DIM)
         self.top_pad.addstr(self.sysinfo.processor+rpad)
         # Line 2
         sec = self._data["uptime"]["up"][0]
         uptime=datetime.timedelta(seconds=int(float(sec)))
         k,d="uptime",str(uptime)
         s="{}: {}".format(k,d)
         lpad,rpad=self._center_padding(s)
         self.top_pad.addstr(lpad+"{}: ".format(k), curses.A_DIM)
         self.top_pad.addstr(d+rpad)
      
      elif self.screen == 4:
         if self.vbox_supported:
            # Line 1
            v=self._data["virtualbox/system"]["version"][0]
            s = "virtualbox: {}".format(v)
            lpad,rpad=self._center_padding(s)
            self.top_pad.addstr(lpad+"virtualbox: ", curses.A_DIM)
            self.top_pad.addstr(v+rpad)
            # Line 2
            v=self._data["virtualbox/system"]["vm_count"][0]
            s = "active-count: {}".format(v)
            lpad,rpad=self._center_padding(s)
            self.top_pad.addstr(lpad+"active-count: ", curses.A_DIM)
            self.top_pad.addstr(v+rpad)
            
      elif self.screen == 5:
         if self.vpp_api_supported:
            v = self._data["vpp/system"]["version"][0]
            v = "vpp: "+v
            self.top_pad.addstr(self._center_text(v))

      elif self.screen == 6:
         vm_count=len(self._data["/node/vm"]) if "/node/vm" in self._data else 0
         kb_count=len(self._data["/node/vm"]) if "/node/vm" in self._data else 0
         s = "vm-count: {} kb-count:{}".format(vm_count, kb_count)
         self.top_pad.addstr(self._center_text(s))         
         s = "symptoms-count: {}".format(len(self._data["symptoms"]))
         self.top_pad.addstr(self._center_text(s))

   def _fill_pad(self):
      """
      fill pad from visible content

      """
      top = self.top[self.screen]
      current = self.current[self.screen]-top
      visible_content = self.content[self.screen][top:top+self.pad_height]

      for i,(s,flags) in enumerate(visible_content):
         
         if type(flags) is list:

            # print substrings per flag combination
            poffset,pflag=0,0
            for (offset,flag) in flags:
               self.pad.addstr(i,poffset,s[poffset:offset],
                    pflag if i != current else pflag | self.selection_color)
               poffset,pflag=offset,flag
            self.pad.addstr(i,poffset,s[poffset:],
                 pflag if i != current else pflag | self.selection_color)

         else:
            self.pad.addstr(i,0,s,
               flags if i != current else flags | self.selection_color)

      # empty strings
      for i in range(len(visible_content), self.pad_height):
         self.pad.addstr(i,0,'\n')

   def _display(self):
      """
      refresh the display and reschedule itself

      """

      if (self.height, self.width) != self.window.getmaxyx():
         self._init_pads()
         self.resize_columns()

      try:
         self._fill_pad()

         self.header.refresh(0, 0, 0, 0, 0, self.width-1)
         self.top_pad.refresh(0, 0, 2, 1,
                              self.top_pad_height+2,
                              self.pad_width-2)
         self.colname_pad.refresh(0, 0, 5, 1, 
                                  5, self.pad_width-1)
         self.pad.refresh(0, 0, 3+self.top_pad_height, 1, 
                          self.height-2,
                          self.pad_width)
      except:
         pass

      self.scheduler.enter(SCREEN_REFRESH_PERIOD,1,self._display)

   def start_gui(self):

      self.window = curses.initscr()
      curses.noecho()
      curses.cbreak()
      self.window.keypad(1)
      os.environ.setdefault('ESCDELAY', '25')
      self.window.nodelay(1)
      curses.curs_set(0)
      
      curses.start_color()
      curses.use_default_colors()
      # 4: orange
      curses.init_color(4, 1000, 700, 0)
      # 1: orange on black
      curses.init_pair(1, 4, -1)
      # 2: red on black
      curses.init_pair(2, curses.COLOR_RED, -1)
      # 8: black on white
      curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_WHITE)
      # 9: orange on white
      curses.init_pair(9, 4, curses.COLOR_WHITE)
      # 10: red on white
      curses.init_pair(10, curses.COLOR_RED, curses.COLOR_WHITE)
      
      # health gradation color, 101 colors from green to red
      self.health_colors = [i for i in range(11,213) if not i & 8]
      for c,i in enumerate(self.health_colors):
         # reverse red and green
         c = 100-c
         # c
         # 0   => (1000,0,0)    red
         # 50  => (1000,700,0) orange
         # 100 => (0,1000,0)    green
         curses.init_color(i, min(2*c,100)*10, max(0,min(200-(2*c)-30,100))*10, 0)
         curses.init_pair(i, i, -1)
         curses.init_pair(i | 8, i, curses.COLOR_WHITE)
      
      # This color is combined to other colors using | (binary or)
      # to obtain the selection color (i.E., with white background)
      # Therefore, do not define a non-selection color with
      # bit '8' set
      self.selection_color = curses.color_pair(8)
      self.content = [[] for _ in range(self.max_screens)]
      self.window.refresh()
      self._init_pads()
      self.resize_columns()

   def stop_gui(self):
      self.window.keypad(False)
      curses.nocbreak()
      curses.echo()
      curses.endwin()

#   def _clear_pads(self):
#      """
#      if screen was not resized, clear pads
#      otherwise create new pads

#      """
#      if (self.height, self.width) == self.window.getmaxyx():
#         self.pad.clear()
#      else:
#         self._init_pads()

   def _init_pads(self):
      self.height, self.width = self.window.getmaxyx()
      self.pad_height, self.pad_width = self.height-6, self.width-2
      self.top_pad_height, self.top_pad_width = 3, self.pad_width

      self.header = curses.newpad(1, self.width)
      self.top_pad = curses.newpad(3, self.pad_width)
      self.colname_pad = curses.newpad(1, self.pad_width)
      self.pad = curses.newpad(self.pad_height+1, self.pad_width)

   def scroll(self, direction):
      if direction == self.UP and self.current[self.screen] > 0:

         self.current[self.screen] += direction
         if self.current[self.screen] < self.top[self.screen]:
            self.top[self.screen] += direction

      elif direction == self.DOWN and (self.current[self.screen] 
                             < len(self.content[self.screen])-1):

         self.current[self.screen] += direction
         if self.current[self.screen] >= self.top[self.screen]+self.pad_height-1:
            self.top[self.screen] += direction

   def paging(self, direction):
      if direction == self.UP and self.current[self.screen] > 0:

         self.current[self.screen] -= min(self.pad_height-1,self.current[self.screen])
         self.top[self.screen] -= min(self.pad_height-1,self.top[self.screen])

      elif direction == self.DOWN and (self.current[self.screen] 
                             < len(self.content[self.screen])):

         self.current[self.screen] += min(self.pad_height-1,
              len(self.content[self.screen])-self.current[self.screen]-1)         
         self.top[self.screen] += min(self.pad_height-1,
          max(0,len(self.content[self.screen])-self.top[self.screen]-self.pad_height+1))

   def switch_screen(self, direction):
      self.screen = (self.screen+direction) % self.max_screens
      self._format_header()
      self._format_top_pad()
      self._format_colname_pad()

   def exit(self):
      """
      cleanup before exiting

      """
      self.stop_gui()

   def process(self):
      """
      read data from shared memory

      """
      # this list contains formatted text
      self.content = [[] for _ in range(self.max_screens)]
      self._data = self.sbuffer.dict(info=self.info)
      self._format()
      self.scheduler.enter(TOP_INPUT_PERIOD,0,self.process)

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
               if c == ord('q') or c == ESCAPE_CHAR: 
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
                  self.switch_screen(self.UP)
               elif c == curses.KEY_RIGHT:
                  self.switch_screen(self.DOWN)
               elif c == curses.KEY_RESIZE:
                  self.info("KEY_RESIZE")
               c = self.window.getch()
            self.scheduler.run(blocking=False)
            time.sleep(KEYBOARD_INPUT_PERIOD)

      except KeyboardInterrupt:
         pass
      finally:
         self.exit()


