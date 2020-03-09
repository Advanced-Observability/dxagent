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
      self.top = 0 
      self.screen = 0
      self.max_screens = 2
      self.max_lines = 2**12  

      self._data = {}

      # watchers
      self.bm_watcher = BMWatcher(self._data, self.info)
      self.vm_watcher = VMWatcher(self._data, self.info)
      self.vpp_watcher = VPPWatcher(self._data, self.info)

   def _input(self):
     
      
      self.bm_watcher.input()
      self.vm_watcher.input()
      self.vpp_watcher.input()
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
      self.pad_raw_input.addstr(category+"\n", curses.A_BOLD)
      for e in self._data[category]:
         self.pad_raw_input.addstr(e[0]+": ")
         self.pad_raw_input.addstr(" ".join(e[1:])+" ")
      self.pad_raw_input.addstr("\n")
      self.pad_raw_input.addstr("\n")

   def _format_attrs_list(self, category):
      self.pad_raw_input.addstr(category+"\n", curses.A_BOLD)
      for l in self._data[category]:
         for e in l:
            if type(e) is list:
               for t in e:
                  if type(t) is list:
                     for tt in t:
                        self.pad_raw_input.addstr(tt[0]+": ")
                        self.pad_raw_input.addstr(" ".join(tt[1:])+" ")
                  else:
                     self.pad_raw_input.addstr(t[0]+": ")
                     self.pad_raw_input.addstr(" ".join(t[1:])+" ")
            else:
               self.pad_raw_input.addstr(e[0]+": ")
               self.pad_raw_input.addstr(" ".join(e[1:])+" ")
         self.pad_raw_input.addstr("\n")
      self.pad_raw_input.addstr("\n")

   def _center_text(self, pad, text, *args):
      padding = int((self.width-len(text))/2)
      pad.addstr(padding*" "+text, *args)

   def _format(self):
      """
      format data for displaying

      """

      self.height, self.width = self.window.getmaxyx()
      self.pad_raw_input = curses.newpad(self.max_lines, self.width)

      self._center_text(self.pad_raw_input, "RAW INPUT   \n",
                        curses.A_BOLD)
                         
      self.pad_raw_input.addstr("System:\n\n", curses.A_BOLD)
      self.pad_raw_input.addstr(str(self.sysinfo)+"\n")
      self.pad_raw_input.addstr("\nBareMetal:\n\n", curses.A_BOLD)

      self._format_attrs_list("bm_ifs")
      self._format_attrs("stats_global")
      self._format_attrs("uptime")
      self._format_attrs("loadavg")
      self._format_attrs_list("net/dev")
      self._format_attrs("meminfo")
      self._format_attrs_list("swaps")
      self._format_attrs("proc/sys")
      self._format_attrs("netstat")
      self._format_attrs("snmp")  
      self._format_attrs_list("net/arp")
      self._format_attrs_list("stat/cpu")
      self._format_attrs("stat")
      self._format_attrs_list("rt-cache")
      self._format_attrs_list("ndisc-cache")
      self._format_attrs_list("net/route")

      self.pad_raw_input.addstr("\nVirtual Machines:\n\n", curses.A_BOLD)   
      self._format_attrs("virtualbox/system")
      self._format_attrs_list("virtualbox/vms")

      self._format_attrs_list("stats")

      self.pad_health_metrics = curses.newpad(self.max_lines, self.width)
      self._center_text(self.pad_health_metrics, "HEALTH\n\n",
                        curses.A_BOLD) #, 

      self.pad_health_metrics.addstr("Metrics\n\n", curses.A_BOLD)
      self.pad_health_metrics.addstr("Symptoms\n\n", curses.A_BOLD)

   def _display(self):
      """
      refresh the display and reschedule itself

      """

      self.height, self.width = self.window.getmaxyx()

      if self.screen == 0:
         self.pad_raw_input.refresh(self.top, 0, 0, 0, self.height-1, self.width-1)
      elif self.screen == 1:
         self.pad_health_metrics.refresh(0, 0, 0, 0, self.height-1, self.width-1)
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
      
      self.window.refresh()

      self.height, self.width = self.window.getmaxyx()
      self.pad_raw_input = curses.newpad(self.max_lines, self.width)
      self.pad_health_metrics = curses.newpad(self.max_lines, self.width)

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
         self.stop_gui()
      

if __name__ == '__main__':
   dxa = DXAgent()
   dxa.run()

