"""
dxagent.py

   This file contains the core of dxagent

@author: K.Edeline

"""

import sched
import time
import signal

import agent
from agent.ios import IOManager
from agent.daemon import Daemon
from agent.sysinfo import SysInfo
from agent.bm_health import BMWatcher
from agent.vm_health import VMWatcher
from agent.vpp_health import VPPWatcher

# input processing delay
INPUT_RATE=3.0

class DXAgent(Daemon, IOManager):

   """
   DXAgent

   
   """

   def __init__(self):
      super(DXAgent, self).__init__(
                      pidfile='/var/run/dxagent.pid',
                      stdout='/var/log/dxagent.log', 
                      stderr='/var/log/dxagent.log',
                      name='dxagent')

      self.load_ios()
      self.sysinfo = SysInfo()
      if "start" not in self.args.cmd:
         return

      self.scheduler = sched.scheduler()
      self._data = {}

      # watchers
      self.bm_watcher = BMWatcher(self._data, self.info)
      self.vm_watcher = VMWatcher(self._data, self.info)
      self.vpp_watcher = VPPWatcher(self._data, self.info)
      signal.signal(signal.SIGTERM, self.exit)
      #signal.signal(signal.SIGKILL, self.exit)

      self.running = True

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
      self.scheduler.enter(INPUT_RATE,0,self.process)

   def exit(self, signum=None, stackframe=None):
      """
      cleanup before exiting

      """
      self.running = False
      time.sleep(INPUT_RATE)

      self.vm_watcher.exit()
      self.vpp_watcher.exit()

   def run(self):
      """
      main function

      """
      self.info(self.sysinfo)
      self.process()

      while self.running:
         self.scheduler.run(blocking=False)
         time.sleep(INPUT_RATE)

