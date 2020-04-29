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
from agent.shareablebuffer import ShareableBuffer

# input processing delay
INPUT_RATE=3.0

class DXAgent(Daemon, IOManager):
   """
   DXAgent

   
   """

   def __init__(self, parse_args=True):
      Daemon.__init__(self, pidfile='/var/run/dxagent.pid',
                      stdout='/var/log/dxagent.log', 
                      stderr='/var/log/dxagent.log',
                      name='dxagent')
      IOManager.__init__(self, child=self, parse_args=parse_args)

      self.load_ios()
      if not parse_args:
         return
      if "start" not in self.args.cmd:
         return

      self.sysinfo = SysInfo()
      self.scheduler = sched.scheduler()

      # ringbuffers are stored here
      self._data = {}

      # SharedMemory with dxtop.
      # Drop privileges to avoid dxtop root requirements
      if not self.args.disable_shm:
         with self.drop():
            self.sbuffer = ShareableBuffer(create=True)

      # catch signal for cleanup
      signal.signal(signal.SIGTERM, self.exit)

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
      if not self.args.disable_shm:
         skip=["stats"] if not self.args.verbose else []
         self.sbuffer.write(self._data, skip=skip, info=self.info)
      self.scheduler.enter(INPUT_RATE,0,self.process)

   def exit(self, signum=None, stackframe=None):
      """
      cleanup before exiting

      """
      self.running = False
      time.sleep(INPUT_RATE)

      self.vm_watcher.exit()
      self.vpp_watcher.exit()

      self.sbuffer.unlink()
      del self.sbuffer

   def run(self):
      """
      main function

      """
      # watchers.
      self.bm_watcher = BMWatcher(self._data, self.info, self)
      self.vm_watcher = VMWatcher(self._data, self.info, self)
      self.vpp_watcher = VPPWatcher(self._data, self.info, self)

      self.running = True

      self.info(self.sysinfo)
      self.process()

      while self.running:
         self.scheduler.run(blocking=False)
         time.sleep(INPUT_RATE)

