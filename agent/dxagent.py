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
import string
import datetime

import agent
from agent.ios import IOManager
from agent.sysinfo import SysInfo
from agent.bm_health import BMWatcher
from agent.vm_health import VMWatcher
from agent.vpp_health import VPPWatcher

ESCAPE = 27
ENTER = 10

# keyboard input processing delay
KEYBOARD_INPUT_RATE=0.05

# screen refresh delay
SCREEN_REFRESH_RATE=0.05

# input processing delay
INPUT_RATE=3.0

HLINE_CHAR=u'\u2500'
VLINE_CHAR=u'\u2502'
TTEE_CHAR=u'\u252c'
BTEE_CHAR=u'\u2534'
CROSS_CHAR=u'\u253c'

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
      self.info(self.sysinfo)
      self.scheduler = sched.scheduler()
      
      # navigation vars  
      self.screen = 0
      self.max_screens = 7
      self.top = [0 for _ in range(self.max_screens)]
      self.current = [0 for _ in range(self.max_screens)]
      self.max_lines = 2**14

      self._data = {}

      # watchers
      self.bm_watcher = BMWatcher(self._data, self.info)
      self.vm_watcher = VMWatcher(self._data, self.info)
      self.vpp_watcher = VPPWatcher(self._data, self.info)

   def _input(self):

      self.bm_watcher.input()
      self.vm_watcher.input()
      self.vpp_watcher.input()
      # XXX: ioam

   def process(self):
      """
      read input data, process and format it for
      displaying. re-schedule itself.

      """

      self._input()
      self._format()
      self.scheduler.enter(INPUT_RATE,0,self.process)

   def resize_columns(self):
      """
      find column sizes from screen width

      """
      self.col_sizes=[36,32,32]
      self.col_sizes_cpu=[20,12,12,12,12,12,12,12,12]
      shrink_factor = 0.85

      while ((self.width <= sum(self.col_sizes)+len(self.col_sizes))
         or (self.width <= sum(self.col_sizes_cpu)+len(self.col_sizes_cpu))):

         self.col_sizes = [int(c*shrink_factor) for c in self.col_sizes]
         self.col_sizes_cpu = [int(c*shrink_factor) for c in self.col_sizes_cpu]

      self.col_sizes[-1] = 0
      self.col_sizes_cpu[-1] = 0

      self._format_header()
      self._format_top_pad()
      self._format_colname_pad()
      self._format_footer()

   def _format_attrs(self, category, pad_index):
      """
      format a list of tuples into a curses pad
 
      """
      self._append_content(self._center_text(category),
                           pad_index, curses.A_BOLD)
      for e in self._data[category]:
         self._append_content(e[0]+": "+" ".join(e[1:])+"\n", 
                              pad_index, buf=e)
      self._append_content("\n", pad_index)

   def _format_attrs_rb(self, category, pad_index):
      """
      format a dict of ringbuffers into a curses pad
 
      """
      self._append_content(self._center_text(category),
                           pad_index, curses.A_BOLD)
      self._append_content(self.hline_top(self.col_sizes), pad_index)

      for k,d in self._data[category].items():
         if d.is_empty():
            continue

         s = (" {}"+" "*self.col_sizes[0]).format(k)[:self.col_sizes[0]]
         s += VLINE_CHAR
         flags = 0

         value, severity = d.top()
         if severity:
            flags = [(len(s),curses.color_pair(severity.value))]
         if d.unit():
            s += ("{} {}"+" "*self.col_sizes[1]).format(value, 
                  d.unit())[:self.col_sizes[1]]
         else:
            s += ("{}"+" "*self.col_sizes[1]).format(value)[:self.col_sizes[1]]

         if severity:
            flags.append((len(s),0))
         s += VLINE_CHAR

         value, severity = d.dynamicity()
         if severity:
            flags.append((len(s),curses.color_pair(severity.value)))
         s += "{}".format(value)
         if severity:
            flags.append((len(s),0))

         self._append_content(s, pad_index, flags, fill=True, buf=d)      

      self._append_content(self.hline_bottom(self.col_sizes), pad_index)

   def _format_attrs_list(self, category, pad_index):
      """
      format a list of list (opt:of list) of tuples into a curses pad
 
      """

      self._append_content(self._center_text(category),
                           pad_index, curses.A_BOLD)
      self._append_content(self.hline_top(self.col_sizes), pad_index)

      for l in self._data[category]:
         for e in l:
            if type(e) is list:
               for t in e:
                  if type(t) is list:
                     for tt in t:
                        self._append_content(" "+tt[0]+": "+" ".join(tt[1:])+"\n", 
                                             pad_index)
                  else:
                     self._append_content(" "+t[0]+": "+" ".join(t[1:])+"\n",
                                          pad_index)
            else:
               self._append_content(" "+e[0]+": "+" ".join(e[1:])+"\n",
                                    pad_index)

         self._append_content(self.hline(self.col_sizes), pad_index)

   def _format_attrs_list_rb(self, category, pad_index):
      """
      format a dict of dict of ringbuffers into a curses pad
 
      """

      self._append_content(self._center_text(category),
                           pad_index, curses.A_BOLD)
      self._append_content(self.hline_top(self.col_sizes), pad_index)

      for i,(k,d) in enumerate(self._data[category].items()):

         s = " "*self.col_sizes[0]+VLINE_CHAR
         s +=  (k+" "*self.col_sizes[1])[:self.col_sizes[1]]
         s += VLINE_CHAR
         self._append_content(s, pad_index, fill=True)

         for kk,dd in d.items():
            if dd.is_empty():
               continue

            s = (" {}"+" "*self.col_sizes[0]).format(kk)[:self.col_sizes[0]]
            s += VLINE_CHAR
            flags = 0
      
            value, severity = dd.top()
            if severity:
               flags = [(len(s),curses.color_pair(severity.value))]
            if dd.unit():
               s += ("{} {}"+" "*self.col_sizes[1]).format(
                  value, dd.unit())[:self.col_sizes[1]]
            else:
               s += ("{}"+" "*self.col_sizes[1]).format(
                  value)[:self.col_sizes[1]]
            if severity:
               flags.append((len(s),0))

            s += VLINE_CHAR
            value, severity = dd.dynamicity()
            if severity:
               flags.append((len(s),curses.color_pair(severity.value)))
            s += "{}".format(value)
            if severity:
               flags.append((len(s),0))

            self._append_content(s, pad_index, flags, fill=True, buf=dd)

         if i == len(self._data[category])-1:
            self._append_content(self.hline_bottom(self.col_sizes), pad_index)
         else:
            self._append_content(self.hline_x(self.col_sizes), pad_index)

   def _format_attrs_list_rb_percpu(self, category, pad_index):
      """
      format a dict of dict of ringbuffers into a curses pad
 
      """
      cpu_slice = 8
      cpu_count = self.bm_watcher.cpu_count
      keys = self._data[category]["cpu0"].keys()

      self._append_content(self._center_text(category),
                           pad_index, curses.A_BOLD)
      self._append_content(self.hline(self.col_sizes), pad_index)

      for i in range(0,cpu_count,cpu_slice):

         self._append_content(
            self._center_text("cpu{}-cpu{}".format(i,i+cpu_slice-1)),
            pad_index)
         self._append_content(self.hline_top(self.col_sizes_cpu), pad_index)

         for k in keys:
            s = (" {}"+" "*self.col_sizes_cpu[0]).format(k)[:self.col_sizes_cpu[0]]
            flags = [(0,0)]
            s += VLINE_CHAR
            buffers = []

            for cpu_index in range(i,i+cpu_slice):

               cpu_label="cpu{}".format(cpu_index)
               d = self._data[category][cpu_label][k]
               value, severity = d.top()
               if severity:
                  flags.append((len(s),curses.color_pair(severity.value)))
               if d.unit():
                  s += ("{} {}"+" "*self.col_sizes_cpu[1]).format(
                        value, d.unit())[:self.col_sizes_cpu[1]]
               else:
                  s += ("{}"+" "*self.col_sizes_cpu[1]).format(
                        value)[:self.col_sizes_cpu[1]]

               if severity:
                  flags.append((len(s),0))
               if cpu_index < i+cpu_slice-1:
                  s += VLINE_CHAR

               buffers.append(d)

            self._append_content(s, pad_index, flags, fill=True, buf=buffers)

         if cpu_count-i <= cpu_slice:
            self._append_content(self.hline_bottom(self.col_sizes_cpu), pad_index)
         else:
            self._append_content(self.hline_x(self.col_sizes_cpu), pad_index)

   def _center_text(self, s, width=None):
      """
      return a pad-fitting string with s centered in blanks

      """
      if not width:
         width = self.pad_width

      padding = int((width-len(s))/2)
      rest = (width-len(s)) % 2
      return (padding*" "+s+padding*" "+ rest*" ")[:self.pad_width]

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

   def _fill_header(self, names, s):
      """
      fill header pad with names

      """
      padding = int((self.width-len(s))/2)
      self.header.addstr(padding*" ")

      for i,name in enumerate(names):

         self.header.addstr(name, 
            curses.A_BOLD | self.selection_color if self.screen == i else 0)
         if i != len(names)-1:
            self.header.addstr(" | ")

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

   def _format_top_pad(self):
      self.top_pad.clear()

      if self.screen in [0, 1, 2, 3]:
         self.top_pad.addstr(self._center_text(str(self.sysinfo)))
         sec,_ = self._data["uptime"]["up"].top()
         if sec:
            uptime=datetime.timedelta(seconds=int(float(sec)))
            self.top_pad.addstr(self._center_text("uptime: {}".format(str(uptime))))
      
      elif self.screen == 4:
         if "virtualbox" in agent.vm_health.vm_libs:
            v,_=self._data["virtualbox/system"]["version"].top()
            s = "virtualbox: {}".format(v)
            self.top_pad.addstr(self._center_text(s))
            s = "active-count: {}".format(self.vm_watcher.vbox_vm_count)
            self.top_pad.addstr(self._center_text(s))
            
      elif self.screen == 5:
         if self.vpp_watcher.use_api:
            v,_ = self._data["vpp/system"]["version"].top()
            v = "vpp: "+v
            self.top_pad.addstr(self._center_text(v))

      elif self.screen == 6:
         pass
      
   def _format_colname_pad(self):
      self.colname_pad.clear()

      s=""
      s += (self._center_text("name",
                             width=self.col_sizes[0])
        + " " +  self._center_text("value",
                             width=self.col_sizes[1]))
      s += self._center_text("dynamicity",
                             width=self.pad_width-len(s)-1)
      
      if self.screen == 0:
         pass
      elif self.screen in [1, 2, 3, 4, 5]:
         self.colname_pad.addstr(s)
      elif self.screen == 6:
         pass

   def _append_content(self, s, screen_index, flags=0, fill=False, 
                       buf=None):
      """
      content is a list of screen content
      each screen content is a list of (str, flags) tuples

      @param fill Fill line with blanks
      @param buf The buffer related to this line
      """
      if fill:
         s = self._fill_line(s)
      self.content[screen_index].append((s,flags))
      self.buffers[screen_index].append(buf)

   def _format(self):
      """
      format data for displaying

      """

      self._init_pads()

      # baremetal 
      self._format_attrs_list_rb_percpu("stat/cpu", 0)
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

      self._format_attrs_list_rb("bm_ifs", 3)
      self._format_attrs_list_rb("net/dev", 3)
      self._format_attrs_rb("proc/sys", 3)
      self._format_attrs_rb("netstat", 3)
      self._format_attrs_rb("snmp", 3)
      self._format_attrs_list_rb("net/arp", 3)
      self._format_attrs_list("net/route", 3)

      # VM
      if ("virtualbox" in agent.vm_health.vm_libs
         and self.vm_watcher.vbox_vm_count):
         self._format_attrs_list_rb("virtualbox/vms", 4)

      # VPP
      if "vpp" in agent.vpp_health.kbnets_libs:
         if self.vpp_watcher.use_api:
            self._format_attrs_rb("vpp/system", 5)
            self._format_attrs_list_rb("vpp/api/if", 5)

         if self.vpp_watcher.use_stats:
            self._format_attrs_rb("vpp/stats/sys", 5) 
            self._format_attrs_list_rb("vpp/stats/buffer-pool", 5)
            self._format_attrs_list_rb("vpp/stats/workers", 5) 
            self._format_attrs_list_rb("vpp/stats/if", 5)
            self._format_attrs_list_rb("vpp/stats/err", 5)

      # Health metrics Pad
      self._append_content("Metrics", 6, curses.A_BOLD, fill=True)
      self._append_content("Symptoms", 6, curses.A_BOLD, fill=True)

      self.resize_columns()

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
            self.pad.addstr(i,0,s,flags if i != current else flags | self.selection_color)

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
         self.footer.refresh(0, 0, 
                             self.height-1, 1,
                             self.height-1, self.width-2)
      except:
         pass

      self.scheduler.enter(SCREEN_REFRESH_RATE,1,self._display)

   def start_gui(self):

      self.window = curses.initscr()
      curses.noecho()
      curses.cbreak()
      self.window.keypad(True)
      os.environ.setdefault('ESCDELAY', '25')
      self.window.nodelay(True)
      curses.curs_set(0)
      
      curses.start_color()
      curses.init_color(4, 1000, 700, 0)
      curses.init_pair(1, 4, curses.COLOR_BLACK)
      curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
      
      curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_WHITE)
      curses.init_pair(9, 4, curses.COLOR_WHITE)  
      curses.init_pair(10, curses.COLOR_RED, curses.COLOR_WHITE)

      self.selection_color = curses.color_pair(8)

      self.window.refresh()
      self._init_pads()
      self.resize_columns()

   def _clear_pads(self):
      """
      if screen was not resized, clear pads
      otherwise create new pads

      """
      if (self.height, self.width) == self.window.getmaxyx():
         self.pad.clear()
      else:
         self._init_pads()

   def _init_pads(self):
      self.height, self.width = self.window.getmaxyx()
      self.pad_height, self.pad_width = self.height-6, self.width-2
      self.top_pad_height, self.top_pad_width = 3, self.pad_width
      # this list contains formatted text
      self.content = [[] for _ in range(self.max_screens)]
      # this list is aligned to content and contains buffers
      # it is used to display extra details on demand
      self.buffers = [[] for _ in range(self.max_screens)]

      self.header = curses.newpad(1, self.width)
      self.top_pad = curses.newpad(3, self.pad_width)
      self.colname_pad = curses.newpad(1, self.pad_width)
      self.pad = curses.newpad(self.pad_height+1, self.pad_width)
      self.footer = curses.newpad(1, self.width)

   def exit(self):
      """
      cleanup before exiting

      """
      self.stop_gui()

      self.vm_watcher.exit()
      self.vpp_watcher.exit()

   def stop_gui(self):
      self.window.keypad(False)
      curses.nocbreak()
      curses.echo()
      curses.endwin()

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

      self._format_footer()

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

      self._format_footer()

   def switch_screen(self, direction):
      self.screen = (self.screen+direction) % self.max_screens
      self._format_header()
      self._format_top_pad()
      self._format_colname_pad()
      self._format_footer()

   def _format_footer(self):
      self.footer.clear()
      if not self.buffers[self.screen]:
         return      

      buffer = self.buffers[self.screen][self.current[self.screen]]
      if not buffer:
         return

      if type(buffer) is list:
         name = buffer[0].name()
         s = "{}".format(name)
      elif buffer.type is str:
         name = buffer.name()
         s = "{}".format(name)        
      else:
         name = buffer.name()
         s = "{} min:{} max:{} severity:{}".format(name,
               buffer.min(), buffer.max(), buffer._top_severity())

      self.footer.addstr(self._center_text(s))

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
                   self.switch_screen(self.UP)
               elif c == curses.KEY_RIGHT:
                   self.switch_screen(self.DOWN)
               c = self.window.getch()
 
            self.scheduler.run(blocking=False)
            time.sleep(KEYBOARD_INPUT_RATE)

      except KeyboardInterrupt:
         pass
      finally:
         self.exit()
      

if __name__ == '__main__':
   dxa = DXAgent()
   dxa.run()

