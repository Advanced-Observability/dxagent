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
      self.col_sizes=[36,24,0]

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
      self.scheduler.enter(1,0,self.process)

   def _format_attrs(self, category, pad_index):
      """
      format a list of tuples into a curses pad
 
      """
      self.pads[pad_index].addstr(category+"\n", curses.A_BOLD)
      for e in self._data[category]:
         self.pads[pad_index].addstr(e[0]+": ")
         self.pads[pad_index].addstr(" ".join(e[1:])+" ")
      self.pads[pad_index].addstr("\n\n")

   def _format_attrs_rb(self, category, pad_index):
      """
      format a dict of ringbuffers into a curses pad
 
      """
      self._center_text(category+"\n", pad_index, curses.A_BOLD)
      self._draw_hline_top(pad_index)

      for k,d in self._data[category].items():
         if d.is_empty():
            continue

         self.pads[pad_index].addnstr((" {}"+" "*self.col_sizes[0]).format(k), 
            self.col_sizes[0])
         self.pads[pad_index].addch(curses.ACS_VLINE)

         value, severity = d.top()
         if d.unit():
            self.pads[pad_index].addnstr(("{} {}"+" "*self.col_sizes[1]).format(
               value, d.unit()), self.col_sizes[1], curses.color_pair(severity.value))  
         else:
            self.pads[pad_index].addnstr(("{}"+" "*self.col_sizes[1]).format(value), 
               self.col_sizes[1], curses.color_pair(severity.value))  

         self.pads[pad_index].addch(curses.ACS_VLINE)

         value, severity = d.dynamicity()
         self.pads[pad_index].addstr("{}\n".format(value),
            curses.color_pair(severity.value))
            
      self._draw_hline_bottom(pad_index)

   def _format_attrs_list(self, category, pad_index):
      """
      format a list of list (opt:of list) of tuples into a curses pad
 
      """

      self._center_text(category+"\n", pad_index, curses.A_BOLD)
      self._draw_hline_top(pad_index)

      for l in self._data[category]:
         for e in l:
            if type(e) is list:
               for t in e:
                  if type(t) is list:
                     for tt in t:
                        self.pads[pad_index].addstr(" "+tt[0]+": ")
                        self.pads[pad_index].addstr(" ".join(tt[1:])+"\n")
                  else:
                     self.pads[pad_index].addstr(" "+t[0]+": ")
                     self.pads[pad_index].addstr(" ".join(t[1:])+"\n")
            else:
               self.pads[pad_index].addstr(" "+e[0]+": ")
               self.pads[pad_index].addstr(" ".join(e[1:])+"\n")
         self._draw_hline(pad_index)

   def _format_attrs_list_rb(self, category, pad_index):
      """
      format a dict of dict of ringbuffers into a curses pad
 
      """
      self._center_text(category+"\n", pad_index, curses.A_BOLD)
      self._draw_hline_top(pad_index)

      for i,(k,d) in enumerate(self._data[category].items()):

         self.pads[pad_index].addstr(" "*self.col_sizes[0])
         self.pads[pad_index].addch(curses.ACS_VLINE)
         self.pads[pad_index].addnstr(k+" "*self.col_sizes[1], self.col_sizes[1])
         self.pads[pad_index].addch(curses.ACS_VLINE)
         self.pads[pad_index].addch('\n')

         for kk,dd in d.items():
            if dd.is_empty():
               continue

            self.pads[pad_index].addnstr((" {}"+" "*self.col_sizes[0]).format(kk), 
               self.col_sizes[0])
            self.pads[pad_index].addch(curses.ACS_VLINE)
      
            value, severity = dd.top()
            if dd.unit():
               self.pads[pad_index].addnstr(("{} {}"+" "*self.col_sizes[1]).format(
                  value, dd.unit()), self.col_sizes[1], 
                     curses.color_pair(severity.value))  
            else:
               self.pads[pad_index].addnstr(("{}"+" "*self.col_sizes[1]).format(
                  value), self.col_sizes[1], curses.color_pair(severity.value))  

            self.pads[pad_index].addch(curses.ACS_VLINE)

            value, severity = dd.dynamicity()
            self.pads[pad_index].addstr("{}\n".format(value),
               curses.color_pair(severity.value))

         if i == len(self._data[category])-1:
            self._draw_hline_bottom(pad_index)
         else:
            self._draw_hline(pad_index)

   def _center_text(self, text, pad_index, *args):
      padding = int((self.width-len(text))/2)
      self.pads[pad_index].addstr(padding*" ")
      self.pads[pad_index].addstr(text, *args)

   def _draw_hline(self, pad_index):
      for _ in range(self.col_sizes[0]):
         self.pads[pad_index].addch(curses.ACS_HLINE)

      self.pads[pad_index].addch(curses.ACS_PLUS)

      for _ in range(self.col_sizes[1]):
         self.pads[pad_index].addch(curses.ACS_HLINE)

      self.pads[pad_index].addch(curses.ACS_PLUS)
      for _ in range(self.width-self.col_sizes[0]-self.col_sizes[1]-2):
         self.pads[pad_index].addch(curses.ACS_HLINE)

   def _draw_hline_bottom(self, pad_index):
      for _ in range(self.col_sizes[0]):
         self.pads[pad_index].addch(curses.ACS_HLINE)

      self.pads[pad_index].addch(curses.ACS_BTEE)
      for _ in range(self.col_sizes[1]):
         self.pads[pad_index].addch(curses.ACS_HLINE)

      self.pads[pad_index].addch(curses.ACS_BTEE)
      for _ in range(self.width-self.col_sizes[0]-self.col_sizes[1]-2):
         self.pads[pad_index].addch(curses.ACS_HLINE)

   def _draw_hline_top(self, pad_index):
      for _ in range(self.col_sizes[0]):
         self.pads[pad_index].addch(curses.ACS_HLINE)

      self.pads[pad_index].addch(curses.ACS_TTEE)
      for _ in range(self.col_sizes[1]):
         self.pads[pad_index].addch(curses.ACS_HLINE)

      self.pads[pad_index].addch(curses.ACS_TTEE)
      for _ in range(self.width-self.col_sizes[0]-self.col_sizes[1]-2):
         self.pads[pad_index].addch(curses.ACS_HLINE)

   def _format_header(self, pad_index):
      """

      """

      full_str="Baremetal | Virtual Machines | VPP | Health"
      padding = int((self.width-len(full_str))/2)
      self.pads[pad_index].addstr(padding*" ")
      
      self.pads[pad_index].addstr("Baremetal", 
         curses.A_BOLD | curses.color_pair(10) if pad_index == 0 else 0)
      self.pads[pad_index].addstr(" | ")
      self.pads[pad_index].addstr("Virtual Machines", 
         curses.A_BOLD | curses.color_pair(10) if pad_index == 1 else 0)
      self.pads[pad_index].addstr(" | ")
      self.pads[pad_index].addstr("VPP", 
         curses.A_BOLD | curses.color_pair(10) if pad_index == 2 else 0)
      self.pads[pad_index].addstr(" | ")
      self.pads[pad_index].addstr("Health", 
         curses.A_BOLD | curses.color_pair(10) if pad_index == 3 else 0)
      self.pads[pad_index].addstr(" | ")
      
      self.pads[pad_index].addstr("\n\n\n")

   def _format(self):
      """
      format data for displaying

      """

      self.height, self.width = self.window.getmaxyx()
      self.pads = [curses.newpad(self.max_lines, self.width) 
                     for _ in range(self.max_screens)]

      # Raw input Pad
      self._format_header(0)
                 
      # baremetal   
      self.pads[0].addstr("System:\n\n", curses.A_BOLD)
      self.pads[0].addstr(str(self.sysinfo)+"\n\n")

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
      self._format_attrs_list_rb("stat/cpu", 0)
      self._format_attrs_rb("stat", 0)
      self._format_attrs_list_rb("rt-cache", 0)
      self._format_attrs_list_rb("arp-cache", 0)
      self._format_attrs_list_rb("ndisc-cache", 0)
      self._format_attrs_list("net/route", 0)

      # XXX: very verbose at the end, also very greedy
      if self.args.verbose:
         self._format_attrs_list_rb("stats", 0)

      # VM
      self._format_header(1)

      if "virtualbox" in agent.vm_health.vm_libs:
         self._format_attrs_rb("virtualbox/system", 1)
         self._format_attrs_list_rb("virtualbox/vms", 1)

      # VPP
      self._format_header(2)

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
      self._format_header(3)

      self.pads[3].addstr("Metrics\n\n", curses.A_BOLD)
      self.pads[3].addstr("Symptoms\n\n", curses.A_BOLD)

   def _display(self):
      """
      refresh the display and reschedule itself

      """

      self.height, self.width = self.window.getmaxyx()
      self.pads[self.screen].refresh(self.top, 0, 0, 0, 
                                     self.height-1, self.width-1)
      self.scheduler.enter(0.1,1,self._display)

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

      self.height, self.width = self.window.getmaxyx()
      self.pads = [curses.newpad(self.max_lines, self.width) 
                     for _ in range(self.max_screens)]

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
            time.sleep(0.1)

      except KeyboardInterrupt:
         pass
      finally:
         self.exit()
      

if __name__ == '__main__':
   dxa = DXAgent()
   dxa.run()

