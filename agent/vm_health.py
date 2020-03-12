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

      self._data["virtualbox/system"] = [
         ("version", self._vbox.version_normalized)
      ]
      self._data["virtualbox/vms"] = []
      
      for m in self._vbox.machines:

         # check if machine is online/offline
         state = m.state
         if not (state >= MachineState.first_online
               and state <= MachineState.last_online):
            continue
         state = _virtualbox_states[int(state)]

         #sc=m.storage_controllers # IStorageController
         vm_attrs = [
            ("name", m.name), ("cpu", str(m.cpu_count)),
            ("state", state), ("accessible", str(int(m.accessible))),
            ("id", m.id_p), ("os_type_id",m.os_type_id),
            ("cpu_cap", str(m.cpu_execution_cap)), 
            ("mem_size", str(m.memory_size), "MB"), 
            ("vram_size", str(m.vram_size), "MB"),
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
         vm_attrs.append(("net_count", net_count))

         guest_attrs=[]
         for net in range(int(net_count)):
            attrs_suffix = ["Name", "MAC", "V4/IP", "V4/Broadcast",
                             "V4/Netmask", "Status"]
            guest_attrs.append([(attr, str(m.get_guest_property("{}{}/{}".format(guestinfo_prefix, net, attr))[0])) 
                                 for attr in attrs_suffix])
         vm_attrs.append(guest_attrs)

         # probe for guest metrics
         val, metric_attrs, _, units, scales, _, _, _ = self.vbox_perf.query_metrics_data([], [m])
         vm_attrs.extend([(attr, str(val[i]/scales[i]), units[i]) for i,attr in enumerate(metric_attrs)])

         self._data["virtualbox/vms"].append(vm_attrs)

      # renew registration for new vms XXX
      self.vbox_perf.setup_metrics([], self._vbox.machines, _virtualbox_metrics_sampling_period, 
                                  _virtualbox_metrics_sampling_count)
      

