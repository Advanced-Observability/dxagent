"""
vm_health.py

   Input parsing for virtual machines health monitoring

@author: K.Edeline
"""

import virtualbox
from virtualbox.library import MachineState
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
      self._vbox = virtualbox.VirtualBox()

      # setup performance metric collection for all vms
      self.vbox_perf = self._vbox.performance_collector # IPerformanceCollecto
      self.vbox_perf.setup_metrics([], self._vbox.machines, _virtualbox_metrics_sampling_period, 
                                  _virtualbox_metrics_sampling_count)

      attr_list = ["version"]
      self._data["virtualbox/system"] = init_rb_dict(attr_list, type=str)
      self._data["virtualbox/vms"] = {}

   def input(self):
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
         "io_cache_enabled",  "io_cache_size", "/VirtualBox/GuestInfo/Net/Count",
         'CPU/Load/User', 'CPU/Load/User:avg', 'CPU/Load/User:min', 'CPU/Load/User:max',
         'CPU/Load/Kernel', 'CPU/Load/Kernel:avg', 'CPU/Load/Kernel:min',
         'CPU/Load/Kernel:max', 'RAM/Usage/Used', 'RAM/Usage/Used:avg',
         'RAM/Usage/Used:min', 'RAM/Usage/Used:max', 'Disk/Usage/Used',
         'Disk/Usage/Used:avg', 'Disk/Usage/Used:min', 'Disk/Usage/Used:max',
         'Net/Rate/Rx', 'Net/Rate/Rx:avg', 'Net/Rate/Rx:min', 'Net/Rate/Rx:max',
         'Net/Rate/Tx', 'Net/Rate/Tx:avg', 'Net/Rate/Tx:min', 'Net/Rate/Tx:max',
         'Guest/CPU/Load/User', 'Guest/CPU/Load/User:avg', 'Guest/CPU/Load/User:min',
         'Guest/CPU/Load/User:max', 'Guest/CPU/Load/Kernel', 'Guest/CPU/Load/Kernel:avg',
         'Guest/CPU/Load/Kernel:min', 'Guest/CPU/Load/Kernel:max', 'Guest/CPU/Load/Idle',
         'Guest/CPU/Load/Idle:avg', 'Guest/CPU/Load/Idle:min', 'Guest/CPU/Load/Idle:max',
         'Guest/RAM/Usage/Total', 'Guest/RAM/Usage/Total:avg', 'Guest/RAM/Usage/Total:min',
         'Guest/RAM/Usage/Total:max', 'Guest/RAM/Usage/Free', 'Guest/RAM/Usage/Free:avg',
         'Guest/RAM/Usage/Free:min', 'Guest/RAM/Usage/Free:max', 'Guest/RAM/Usage/Balloon',
         'Guest/RAM/Usage/Balloon:avg', 'Guest/RAM/Usage/Balloon:min',
         'Guest/RAM/Usage/Balloon:max', 'Guest/RAM/Usage/Shared',
         'Guest/RAM/Usage/Shared:avg', 'Guest/RAM/Usage/Shared:min',
         'Guest/RAM/Usage/Shared:max', 'Guest/RAM/Usage/Cache', 'Guest/RAM/Usage/Cache:avg',
         'Guest/RAM/Usage/Cache:min', 'Guest/RAM/Usage/Cache:max',
         'Guest/Pagefile/Usage/Total', 'Guest/Pagefile/Usage/Total:avg',
         'Guest/Pagefile/Usage/Total:min', 'Guest/Pagefile/Usage/Total:max'
      ]
      unit_list = [ '','','','','MB','MB','','','','','','','','','','','','',
         '%', '%', '%', '%', '%', '%', '%', '%', 'kB', 'kB', 'kB', 'kB', 'mB',
         'mB', 'mB', 'mB', 'B/s', 'B/s', 'B/s', 'B/s', 'B/s', 'B/s', 'B/s',
         'B/s', '%', '%', '%', '%', '%', '%', '%', '%', '%', '%', '%', '%',
         'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB',
         'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 'kB',
         'kB','kB'
      ]
      type_list = [ str, str, str, str, str, str, str, str, str, str, str,
         str, str, str, str, str, str, int, float, float, float, float, float, float,
         float, float, float, float, float, float, float, float, float, float, float,
         float, float, float, float, float, float, float, float, float, float, float,
         float, float, float, float, float, float, float, float, float, float, float,
         float, float, float, float, float, float, float, float, float, float, float,
         float, float, float, float, float, float, float, float, float, float, 
      ]

      self._data["virtualbox/system"]["version"].append(self._vbox.version_normalized)
      
      for m in self._vbox.machines:

         # check if machine is online/offline
         state = m.state
         if not (state >= MachineState.first_online
               and state <= MachineState.last_online):
            continue
         state = _virtualbox_states[int(state)]
         name = m.name

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
         val, metric_attrs, _, _, scales, _, _, _ = self.vbox_perf.query_metrics_data([], [m])
         vm_attrs.extend([(attr, str(val[i]/scales[i])) for i,attr in enumerate(metric_attrs)])
         
         for k,d in vm_attrs:
            self._data["virtualbox/vms"][name][k].append(d)

         # add rest of probed input (the variable bit)
         attrs_suffix = ["Name", "MAC", "V4/IP", "V4/Broadcast",
                             "V4/Netmask", "Status"]
         for net in range(int(net_count)):
            attrs_list = ["{}{}/{}".format(guestinfo_prefix, net, attr) for attr in attrs_suffix]

            # add entry if needed
            if attrs_list[0] not in self._data["virtualbox/vms"]:
               self._data["virtualbox/vms"][name].update(init_rb_dict(attrs_list, type=str))

            for attr in attrs_list:
               d = str(m.get_guest_property(attr)[0])
               self._data["virtualbox/vms"][name][attr].append(d)

         # 

      # renew registration for new vms XXX
      self.vbox_perf.setup_metrics([], self._vbox.machines, _virtualbox_metrics_sampling_period, 
                                  _virtualbox_metrics_sampling_count)
      

