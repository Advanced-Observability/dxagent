"""
vm_health.py

   Input parsing for virtual machines health monitoring

@author: K.Edeline
"""

# list of supported vm api libs
vm_libs=[]

try:
   import virtualbox
   from virtualbox.library import MachineState
   import vboxapi
   vm_libs.append("virtualbox")
except:
   pass

from agent.buffer import init_rb_dict

# vbox states without pseudo-states
_virtualbox_states = [
      'Null','PoweredOff','Saved','Teleported','Aborted','Running','Paused', 
      'Stuck','Teleporting','LiveSnapshotting','Starting', 'Stopping', 
      'Saving','Restoring', 'TeleportingPausedVM', 'TeleportingIn', 
      'FaultTolerantSyncing', 'DeletingSnapshotOnline','DeletingSnapshotPaused',
      'OnlineSnapshotting','RestoringSnapshot', 'DeletingSnapshot','SettingUp',
      'Snapshotting'
   ]

"""
   Time interval in seconds between two consecutive samples of
   performance data.
"""
_virtualbox_metrics_sampling_period = 1

"""
   Number of samples to retain in performance data history. Older
   samples get discarded.
"""
_virtualbox_metrics_sampling_count = 1

class VMWatcher():

   def __init__(self, data, info):
      self._data = data
      self.info = info

      if "virtualbox" in vm_libs:
         self._vbox = virtualbox.VirtualBox()

         # setup performance metric collection for all vms
         self.vbox_perf = self._vbox.performance_collector # IPerformanceCollecto
         self.vbox_perf.setup_metrics(['*:'], # all metrics without aggregates
                self._vbox.machines, _virtualbox_metrics_sampling_period, 
                                     _virtualbox_metrics_sampling_count)

         attr_list = ["version"]
         self._data["virtualbox/system"] = init_rb_dict(attr_list, type=str)
         self._data["virtualbox/vms"] = {}
         self.vbox_vm_count = 0

         # create guest sessions for each active machine
         self._vbox_sessions       = []
         self._vbox_guest_sessions = []
         for m in self._vbox.machines:
            if not self.virtualbox_vm_is_active(m):
               continue

            s=m.create_session()
            self._vbox_sessions.append(s)
            gs=s.console.guest.create_session("root","vagrant")
            self._vbox_guest_sessions.append(gs)

   def exit(self):
      """
      exit vmwatcher gracefuly

      """
      if "virtualbox" in vm_libs:

         # close sessions         
         for gs in self._vbox_guest_sessions:
            gs.close()
#         for s in self._vbox_sessions:
#            s.unlock_machine()
         
   def virtualbox_vm_is_active(self, machine):
         state = machine.state
         return (state >= MachineState.first_online
               and state <= MachineState.last_online)

   def input(self):

      if "virtualbox" in vm_libs:
         self._input_virtualbox()
#         try: # unstable if a vm is started during monitoring
#            self._input_virtualbox()
#         except:
#            pass

   def _input_virtualbox(self):
      """
      VM (virtualbox)
         VBoxManage showvminfo
         VBoxManage bandwidthctl
         VBoxManage storagectl
         VBoxManage metrics
      #sys = self._vbox.system_properties#ISystemProperties 
      #hds = self._vbox.hard_disks#IMedium 

      """

      attr_list = ["cpu", "state", "accessible", "id", "os_type_id", "cpu_cap", 
         "mem_size", "vram_size", "firmware", "chipset", "session_state", 
         "session_name", "session_pid",  "last_state_change",  "snapshot_count",
         "io_cache_enabled",  "io_cache_size", "/VirtualBox/GuestInfo/Net/Count"
      ] + [ 
         'CPU/Load/User', 'CPU/Load/Kernel', 'RAM/Usage/Used',
         'Disk/Usage/Used', 'Net/Rate/Rx', 'Net/Rate/Tx',
         'Guest/CPU/Load/User','Guest/CPU/Load/Kernel', 'Guest/CPU/Load/Idle',
         'Guest/RAM/Usage/Total', 'Guest/RAM/Usage/Free',
         'Guest/RAM/Usage/Balloon', 'Guest/RAM/Usage/Shared',
         'Guest/RAM/Usage/Cache', 'Guest/Pagefile/Usage/Total',
      ]
      unit_list = [ '','','','','MB','MB','','','','','','','','','','','','',
         '%', '%', 'kB', 'mB', 'B/s',
         'B/s', '%', '%', '%',
         'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 
      ]
      type_list = [ str, str, str, str, str, str, str, str, str, str, str,
         str, str, str, str, str, str, int, float, float, float,
         float, float, float, float, float, float, float, float,
         float, float, float, float,
      ]

      self._data["virtualbox/system"]["version"].append(self._vbox.version_normalized)
      self.vbox_vm_count = 0

      for m in self._vbox.machines:

         # check if machine is online/offline
         if not self.virtualbox_vm_is_active(m):
            continue

         state = _virtualbox_states[int(m.state)]
         name = m.name
         self.vbox_vm_count += 1

         # add entry if needed
         if name not in self._data["virtualbox/vms"]:
            self._data["virtualbox/vms"][name] = init_rb_dict(attr_list, 
                  types=type_list, units=unit_list)

         #sc=m.storage_controllers # IStorageController
         
         vm_attrs = [
            ("cpu", str(m.cpu_count)),
            ("state", state), ("accessible", str(int(m.accessible))),
            ("id", m.id_p), ("os_type_id",m.os_type_id),
            ("cpu_cap", str(m.cpu_execution_cap)), 
            ("mem_size", str(m.memory_size)), 
            ("vram_size", str(m.vram_size)),
            ("firmware", str(m.firmware_type)), 
            ("chipset", str(m.chipset_type)),
            ("session_state", str(m.session_state)), 
            ("session_name", m.session_name), 
            ("session_pid", str(m.session_pid)), 
            ("last_state_change", str(m.last_state_change)), 
            ("snapshot_count", str(m.snapshot_count)), 
            ("io_cache_enabled", str(int(m.io_cache_enabled))),
            ("io_cache_size", str(m.io_cache_size)) 
         ]

         # probe for guest networks
         guestinfo_prefix="/VirtualBox/GuestInfo/Net/"
         net_count =  m.get_guest_property(guestinfo_prefix+"Count")[0]
         vm_attrs.append(("/VirtualBox/GuestInfo/Net/Count", net_count))

         # probe for guest metrics
         val, metric_attrs, _, _, scales, _, _, _ = self.vbox_perf.query_metrics_data(
               ['*:'], [m])
         vm_attrs.extend([(attr, str(val[i]/scales[i])) 
                  for i,attr in enumerate(metric_attrs)])
         
         for k,d in vm_attrs:
            self._data["virtualbox/vms"][name][k].append(d)

         # add rest of probed input (the variable bit)
         attrs_suffix = ["Name", "MAC", "V4/IP", "V4/Broadcast",
                             "V4/Netmask", "Status"]
         for net in range(int(net_count)):
            attrs_list = ["{}{}/{}".format(guestinfo_prefix, net, attr) 
                           for attr in attrs_suffix]

            # add entry if needed
            if attrs_list[0] not in self._data["virtualbox/vms"]:
               self._data["virtualbox/vms"][name].update(init_rb_dict(
                  attrs_list, type=str))

            for attr in attrs_list:
               d = str(m.get_guest_property(attr)[0])
               self._data["virtualbox/vms"][name][attr].append(d)

      # look for vpp-in-vm through guest sessions
      for gs in self._vbox_guest_sessions:
         pass
         #s=gs.execute("/vagrant/dxagent/dump-vpp")[1]
         #for k,d in eval(s):
         #   if k not in self._data:
         #      self._data
         #a=eval(s)

      # renew registration for new vms XXX
      self.vbox_perf.setup_metrics(['*:'], self._vbox.machines, 
            _virtualbox_metrics_sampling_period, 
            _virtualbox_metrics_sampling_count)
      

