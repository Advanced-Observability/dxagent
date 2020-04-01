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

import agent
from agent.ios import IOManager
from agent.sysinfo import SysInfo
from agent.bm_health import BMWatcher
from agent.vm_health import VMWatcher
from agent.vpp_health import VPPWatcher

ESCAPE = 27

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
      
      # 
      self.col_sizes=[36,32,0]

      # navigation vars  
      self.top = 0 
      self.screen = 0
      self.max_screens = 4
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

   def _format_attrs(self, category, pad_index):
      """
      format a list of tuples into a curses pad
 
      """
      self._append_content(self._center_text(category+"\n"),
                           pad_index, curses.A_BOLD)
      for e in self._data[category]:
         self._append_content(e[0]+": "+" ".join(e[1:])+"\n", pad_index)
      self._append_content("\n", pad_index)

   def _format_attrs_rb(self, category, pad_index):
      """
      format a dict of ringbuffers into a curses pad
 
      """
      self._append_content(self._center_text(category+"\n"),
                           pad_index, curses.A_BOLD)
      self._append_content(self.hline_top(self.col_sizes), pad_index)

      for k,d in self._data[category].items():
         if d.is_empty():
            continue

         s = (" {}"+" "*self.col_sizes[0]).format(k)[:self.col_sizes[0]]
         s += VLINE_CHAR

         value, severity = d.top()
         if d.unit():
            s += ("{} {}"+" "*self.col_sizes[1]).format(value, 
                  d.unit())[:self.col_sizes[1]]
         else:
            s += ("{}"+" "*self.col_sizes[1]).format(value)[:self.col_sizes[1]]
         #curses.color_pair(severity.value))  
         s += VLINE_CHAR

         value, severity = d.dynamicity()
         s += "{}\n".format(value)

         self._append_content(s, pad_index)         

      self._append_content(self.hline_bottom(self.col_sizes), pad_index)

   def _format_attrs_list(self, category, pad_index):
      """
      format a list of list (opt:of list) of tuples into a curses pad
 
      """

      self._append_content(self._center_text(category+"\n"),
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
               self._append_content(" "+e[0]+": "+" ".join(e[1:])+"\n", pad_index)

         self._append_content(self.hline(self.col_sizes), pad_index)

   def _format_attrs_list_rb(self, category, pad_index):
      """
      format a dict of dict of ringbuffers into a curses pad
 
      """

      self._append_content(self._center_text(category+"\n"),
                           pad_index, curses.A_BOLD)
      self._append_content(self.hline_top(self.col_sizes), pad_index)

      for i,(k,d) in enumerate(self._data[category].items()):

         s = " "*self.col_sizes[0]+VLINE_CHAR
         s +=  (k+" "*self.col_sizes[1])[:self.col_sizes[1]]
         s += VLINE_CHAR+'\n'
         self._append_content(s, pad_index)

         for kk,dd in d.items():
            if dd.is_empty():
               continue

            s = (" {}"+" "*self.col_sizes[0]).format(kk)[:self.col_sizes[0]]
            s += VLINE_CHAR
      
            value, severity = dd.top()
            if dd.unit():
               s += ("{} {}"+" "*self.col_sizes[1]).format(
                  value, dd.unit())[:self.col_sizes[1]]
            else:
               s += ("{}"+" "*self.col_sizes[1]).format(
                  value)[:self.col_sizes[1]]

            s += VLINE_CHAR
            value, severity = dd.dynamicity()
            s += "{}\n".format(value)

            self._append_content(s, pad_index)

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
      col_sizes=[20,8,8,8,8,8,8,8,0]
      keys = self._data[category]["cpu0"].keys()

      self._append_content(self._center_text(category+"\n"),
                           pad_index, curses.A_BOLD)
      self._append_content(self.hline(self.col_sizes), pad_index)

      for i in range(0,cpu_count,cpu_slice):

         self._append_content(
            self._center_text("cpu{}-cpu{}".format(i,i+cpu_slice-1)+"\n"),
            pad_index)
         self._append_content(self.hline_top(col_sizes), pad_index)

         for k in keys:
            s = (" {}"+" "*col_sizes[0]).format(k)[:col_sizes[0]]
            s += VLINE_CHAR

            for cpu_index in range(i,i+cpu_slice):

               cpu_label="cpu{}".format(i)
               d = self._data[category][cpu_label][k]
               value, severity = d.top()
               s += ("{}"+" "*8).format(value)[:col_sizes[1]]
               if cpu_index < i+cpu_slice-1:
                  s += VLINE_CHAR

            s += '\n'
            self._append_content(s, pad_index)

         if cpu_count-i <= cpu_slice:
            self._append_content(self.hline_bottom(col_sizes), pad_index)
         else:
            self._append_content(self.hline_x(col_sizes), pad_index)

   def _center_text(self, text):
      padding = int((self.pad_width-len(text))/2)
      return padding*" "+text

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

   def _format_header(self, pad_index):
      """

      """
      self.header.clear()

      full_str="Baremetal | Virtual Machines | VPP | Health"
      padding = int((self.width-len(full_str))/2)
      self.header.addstr(padding*" ")
      
      self.header.addstr("Baremetal", 
         curses.A_BOLD | curses.color_pair(10) if pad_index == 0 else 0)
      self.header.addstr(" | ")
      self.header.addstr("Virtual Machines", 
         curses.A_BOLD | curses.color_pair(10) if pad_index == 1 else 0)
      self.header.addstr(" | ")
      self.header.addstr("VPP", 
         curses.A_BOLD | curses.color_pair(10) if pad_index == 2 else 0)
      self.header.addstr(" | ")
      self.header.addstr("Health", 
         curses.A_BOLD | curses.color_pair(10) if pad_index == 3 else 0)
      #self.header.addstr(" | ")
      
   def _append_content(self, s, screen_index, flags=None):
      """
      content is a list of screen content
      each screen content is a list of (str, flags) tuples

      """
      self.content[screen_index].append((s,flags))

   def _format(self):
      """
      format data for displaying

      """

      self._init_pads()

      # baremetal 
      self._append_content("System:\n", 0, curses.A_BOLD)
      self._append_content("\n", 0)
      self._append_content(str(self.sysinfo)+"\n", 0)
      self._append_content("\n", 0)

      self._format_attrs_list_rb("bm_ifs", 0)
      self._format_attrs_rb("stats_global", 0)
      self._format_attrs_rb("uptime", 0)
      self._format_attrs_rb("loadavg", 0)
      self._format_attrs_list_rb("net/dev", 0)
      self._format_attrs_rb("meminfo", 0)
      self._format_attrs_list_rb("swaps", 0)
      self._format_attrs_rb("proc/sys", 0)
      self._format_attrs_rb("netstat", 0)
      self._format_attrs_rb("snmp", 0)
      self._format_attrs_list_rb("net/arp", 0)
      self._format_attrs_list_rb_percpu("stat/cpu", 0)
      self._format_attrs_rb("stat", 0)
      self._format_attrs_list_rb_percpu("rt-cache", 0)
      self._format_attrs_list_rb_percpu("arp-cache", 0)
      self._format_attrs_list_rb_percpu("ndisc-cache", 0)
      self._format_attrs_list("net/route", 0)

      # XXX: very verbose at the end, also very greedy
      if self.args.verbose:
         self._format_attrs_list_rb("stats", 0)

      # VM
      if "virtualbox" in agent.vm_health.vm_libs:
         self._format_attrs_rb("virtualbox/system", 1)
         self._format_attrs_list_rb("virtualbox/vms", 1)

      # VPP
      if "vpp" in agent.vpp_health.kbnets_libs:
         if self.vpp_watcher.use_api:
            self._format_attrs_rb("vpp/system", 2)
            self._format_attrs_list_rb("vpp/api/if", 2)

         if self.vpp_watcher.use_stats:
            self._format_attrs_rb("vpp/stats/sys", 2) 
            self._format_attrs_list_rb("vpp/stats/buffer-pool", 2)
            self._format_attrs_list_rb("vpp/stats/workers", 2) 
            self._format_attrs_list_rb("vpp/stats/if", 2)
            self._format_attrs_list_rb("vpp/stats/err", 2)

      # Health metrics Pad
      self._append_content("Metrics\n", 3, curses.A_BOLD)
      self._append_content("Symptoms\n", 3, curses.A_BOLD)

   def _fill_pad(self):
      """
      fill pad from visible content
      """
      visible_content = self.content[self.screen][self.top:self.top+self.pad_height]

      for i,(s,flags) in enumerate(visible_content):
         if not flags:
            self.pad.addstr(i,0,s)
         elif type(flags) is list:
            pass
         else:
            self.pad.addstr(i,0,s,flags)
      # empty strings
      for i in range(len(visible_content), self.pad_height):
         self.pad.addstr(i,0,'\n')

   def _display(self):
      """
      refresh the display and reschedule itself

      """

      self.height, self.width = self.window.getmaxyx()
      self._fill_pad()
      try:
         self.header.refresh(0, 0, 0, 0, 1, self.width)
         self.pad.refresh(0, 0, 2, 1, 
                          self.pad_height, self.pad_width)
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
      curses.init_color(10, 1000, 700, 0)
      curses.init_pair(1, 10, curses.COLOR_BLACK)
      curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
      
      curses.init_pair(10, curses.COLOR_BLACK, curses.COLOR_WHITE)      

      self.window.refresh()
      self._init_pads()

      self.header = curses.newpad(1, self.width)
      self._format_header(0)

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
      self.pad_height, self.pad_width = self.height-2, self.width-2

      self.content = [[] for _ in range(self.max_screens)]
      self.pad = curses.newpad(self.pad_height+1, self.pad_width)  

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
      if direction == self.UP and self.top > 0:
         self.top += direction
      elif direction == self.DOWN and (self.top < self.max_lines-self.height):
         self.top += direction

   def paging(self, direction):
      if direction == self.UP and self.top > 0:
         self.top -= min(self.height-1,self.top)
      elif direction == self.DOWN and (self.top < self.max_lines-self.height-1):
         self.top += min(self.height-1,self.max_lines-self.top-self.height)

   def switch_screen(self, direction):
      self.screen = (self.screen+direction) % self.max_screens
      self._format_header(self.screen)
      self.pad.clear()

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

