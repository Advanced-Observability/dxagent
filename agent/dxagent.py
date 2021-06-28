"""
dxagent.py

   This file contains the core of dxagent

@author: K.Edeline

"""

import sched
import time
import signal
import importlib
import os, shutil

from .constants import AGENT_INPUT_PERIOD
from .core.ios import IOManager
from .core.daemon import Daemon
from .input.sysinfo import SysInfo
from .input.bm_input import BMWatcher
from .input.vm_input import VMWatcher
from .input.vpp_input import VPPWatcher
from .assurance.health import HealthEngine
from .gnmi.exporter import DXAgentExporter

from ping.ping_scheduler import PingScheduler
from owamp.source.owamp_api import OwampApi, InputError

class DXAgent(Daemon, IOManager):
   """
   DXAgent

   
   """

   def __init__(self, parse_args=True):
      Daemon.__init__(self, pidfile='/var/run/dxagent.pid',
                      stdout='/var/log/dxagent.log', 
                      stderr='/var/log/dxagent.log',
                      name='dxagent',
                      input_rate=AGENT_INPUT_PERIOD)
      IOManager.__init__(self, child=self, parse_args=parse_args)

      self.agent_dir = self.load_ios()
      self.owamp_api = None
      self.ping_scheduler = None
      if not parse_args:
         return

   def _init(self):
      self.sysinfo = SysInfo()
      self.scheduler = sched.scheduler()

      # ringbuffers are stored here
      self._data = {}

      # owamp integration
      self.owamp_api = OwampApi()
      try:
         # Get info from config.ini and configure owamp
         self.owamp_api.configure(self.agent_dir + "/dxagent.ini")
         # Start owamp server
         if self._string_to_bool(self.config["owamp-server"]["start_server"]):
            self.owamp_api.start_server()

      except (InputError, KeyError, Exception) as err:
         print(str(err))
         exit()

      # icmp ping
      self.rm_directory("/ping/outputs/icmp_outputs")
      ping_config = self.config["ping"]
      if ping_config["address_list"]:
         self.ping_scheduler = PingScheduler(self.config["ping"], self.agent_dir + "/ping/outputs/icmp_outputs")
         self.ping_scheduler.start_ping_scheduler()

      # SharedMemory with dxtop.
      # Drop privileges to avoid dxtop root requirements
      if not self.args.disable_shm:
         mod = importlib.import_module("agent.core.shareablebuffer")     
         with self.drop():
            self.sbuffer = getattr(mod, "ShareableBuffer")(create=True)

      # watchers.
      self.bm_watcher = BMWatcher(self._data, self.info, self)
      self.vm_watcher = VMWatcher(self._data, self.info, self)
      self.vpp_watcher = VPPWatcher(self._data, self.info, self)

      # health engine
      self.engine = HealthEngine(self._data, self.info, self)

      # exporter
      if self.gnmi_target:
         self.exporter = DXAgentExporter(self._data, self.info, self,
                                         target_url=self.gnmi_target)
         self.exporter.run()

      # catch signal for cleanup
      signal.signal(signal.SIGTERM, self.exit)

   def _input(self):
      self.bm_watcher.input()
      self.vm_watcher.input()
      self.vpp_watcher.input()

   def process(self):
      """
      read input data, process and write it to shmem.
      re-schedule itself.

      """
      # fetch input
      self._input()
      # compute metrics&symptoms from input
      self.engine.update_health()
      # write to shmem
      if not self.args.disable_shm:
         skip=["stats"] if not self.args.verbose else []
         self.sbuffer.write(self._data, skip=skip, info=self.info)
      #self.info(list(self.exporter._iterate_data()))
      self.scheduler.enter(AGENT_INPUT_PERIOD,0,self.process)

   def exit(self, signum=None, stackframe=None):
      """
      cleanup before exiting

      """
      self.running = False
      time.sleep(AGENT_INPUT_PERIOD)

      self.bm_watcher.exit()
      self.vm_watcher.exit()
      self.vpp_watcher.exit()
      if self.owamp_api.server:
         self.owamp_api.stop_server()
      if self.owamp_api.scheduler:
         self.owamp_api.stop_owping_scheduler()
      self.rm_directory("/ping/outputs/owamp_outputs")
      if self.ping_scheduler:
         self.ping_scheduler.shutdown_ping_scheduler()
      self.rm_directory("/ping/outputs/icmp_outputs")
      if not self.args.disable_shm:
         self.sbuffer.unlink()
         del self.sbuffer

   def run(self):
      """
      main function

      """
      self._init()
      self.running = True

      self.info(self.sysinfo)
      self.process()

      while self.running:
         self.scheduler.run(blocking=False)
         time.sleep(AGENT_INPUT_PERIOD)

   
   def rm_directory(self, dir_path):
      """
      Remove the directory dxgent/dirpath
      """
      folder = self.agent_dir + dir_path
      for filename in os.listdir(folder):
         file_path = os.path.join(folder, filename)
         try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                  os.unlink(file_path)
            # should not be useful since no directories are supposed to be created
            elif os.path.isdir(file_path):
                  shutil.rmtree(file_path)
         except Exception as e:
            print('Failed to delete file %s because: %s' % (file_path, e))

   def _string_to_bool(self, value):
      """
      Return bool value from strings
      """
      return value.lower() in ("yes", "true", "1")

