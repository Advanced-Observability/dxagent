"""
vpp_health.py

   Input parsing for VPP health monitoring

@author: K.Edeline
"""

import os
import fnmatch
import json
import threading
import time
from cisco_gnmi import ClientBuilder
from google.protobuf import json_format
 
kbnets_libs=[]
try:
   from vpp_papi import VPP
   from vpp_papi.vpp_stats import VPPStats
   kbnets_libs.append("vpp")
except:
   pass

from agent.buffer import init_rb_dict
from agent.buffer import RingBuffer
#
# The rate at which gNMI sends updates
GNMI_SAMPLING_RATE=int(1e9)*10
#
# gNMI max consecutive connection fails
MAX_RETRIES=3
#
# time for gNMI to wait before retry connecting
GNMI_RETRY_INTERVAL=60

def vpp_support(api_sock='/run/vpp/api.sock',
                stats_sock='/run/vpp/stats.sock'):
   """
   indicates local support for VPP api&stats   

   @return (vpp_api_supported, vpp_stats_supported)
   """
   return ("vpp" in kbnets_libs and os.path.exists(api_sock),
           "vpp" in kbnets_libs and os.path.exists(stats_sock))


class VPPGNMIClient(threading.Thread):
   def __init__(self, node, info, user='a', password='a'):
      super().__init__()
      self.node = node
      self.info = info
      self.user = user
      self.password = password
      self.client = None
      self.connected = False
      self.last_attempt = None
      self.retry=0

   def parse_json(self, response):
      self.info(json.loads(response))

   def connect(self):
      """
      connect
      
      If more than MAX_RETRIES, do not connect. Wait at least 
      GNMI_RETRY_INTERVAL before re-connecting.
      """
      # too much retries
      if self.retry > MAX_RETRIES:
         return False
      # Less than GNMI_RETRY_INTERVAL since last attempt
      if (self.last_attempt != None and
         time.time()-self.last_attempt < GNMI_RETRY_INTERVAL):
         return False
      self.last_attempt = time.time()

      self.info("connecting to gNMI node {}".format(self.node))
      try:
         builder = ClientBuilder(self.node)
         builder.set_secure_from_target()
         builder.set_call_authentication(self.user, self.password)
         self.client = builder.construct()
         self.connected=True
         self.retry = 0
         return True
      except Exception as e:
         self.info(e)
         self.retry += 1
         return False

   def is_connected(self):
      return self.connected and self.is_alive()

   def status(self):
      """
      @return running, connected, abandonned, connecting
      
      """
      if self.connected and self.is_alive():
         return "running"
      if self.connected and not self.is_alive():
         return "connected"
      if not self.connected and self.retry > MAX_RETRIES:
         return "abandonned"
      if not self.connected and self.retry <= MAX_RETRIES:
         return "connecting"

   def run(self,xpath="/"):
      """
      
      """
      synced  = False

      try:
         for response in self.client.subscribe_xpaths(xpath,
                         sample_interval=GNMI_SAMPLING_RATE):
            if response.sync_response:
               synced = True
            elif synced:
               #self.parse_json(json_format.MessageToJson(response))
               pass
      except Exception as e:
         self.info(e)
      finally:
         pass

class VPPWatcher():

   def __init__(self, data={}, info=None, parent=None,
                      use_api=True, use_stats=True,
                api_sock='/run/vpp/api.sock',
                stats_sock='/run/vpp/stats.sock'): 
      self._data=data
      self.info=info
      self.parent=parent
      self.gnmi_nodes = self.parent.gnmi_nodes
      self.gnmi_timer = time.time()
      self.gnmi_clients = []
      self.use_api=(use_api and os.path.exists(api_sock)
                    and "vpp" in kbnets_libs)
      self.use_stats=(use_stats and os.path.exists(stats_sock)
                      and "vpp" in kbnets_libs)
      self.use_gnmi=(not not self.gnmi_nodes)

      # connect to VPP process (baremetal)
      if self.use_api:
         self._init_stats()
      if self.use_stats:
         self._init_stats()
      if self.use_gnmi:
         self._init_gnmi_client()

   def _init_gnmi_client(self):
      """
      instantiate gNMI clients and try connecting nodes

      """
      self._data["vpp/gnmi"] = {}

      attr_names = ["status"]
      for node in self.gnmi_nodes:
         self.gnmi_clients.append(VPPGNMIClient(node, self.info))
         self._data["vpp/gnmi"][node] = init_rb_dict(attr_names, type=str)
      self._connect_gnmi_clients()

   def _connect_gnmi_clients(self):
      """
      connect gNMI clients
      """
      for gnmi_client in self.gnmi_clients:
         if gnmi_client.is_alive():
            continue
         
         if gnmi_client.connect():
            gnmi_client.start()
      
   def _init_api(self,vpp_json_dir = "/usr/share/vpp/api/core/"):
      """
      init VPP api classes and rbuffers

      """
      # connect to API socket
      jsonfiles = []
      for root, dirnames, filenames in os.walk(vpp_json_dir):
          for filename in fnmatch.filter(filenames, '*.api.json'):
              jsonfiles.append(os.path.join(vpp_json_dir, filename))

      self.vpp = VPP(jsonfiles)
      self.vpp.connect("dxagent")

      # init api fields
      self._data["vpp/api/if"] = {}
      attr_list = ["version"]
      self._data["vpp/system"] = init_rb_dict(attr_list, type=str)
    
   def _init_stats(self):
      """
      init VPP stats classes and rbuffers

      """
      # connect to stats socket
      self.stats = VPPStats('/run/vpp/stats.sock')
      self.stats.connect()  

      # init system stats
      attr_names = [
         '/sys/vector_rate', '/sys/num_worker_threads', '/sys/input_rate',
         '/mem/statseg/total', '/mem/statseg/used', 
         
      ]
      attr_types = [float, int, float, float, float]
      self._data["vpp/stats/sys"] = init_rb_dict(attr_names, types=attr_types)
      attr_names[0] += '$' # XXX
      self._dir_sys = self.stats.ls(attr_names)

      # numa stats (per numa node ?)
      self._dir_buffer_pool = self.stats.ls(['/buffer-pool'])
      self._data["vpp/stats/buffer-pool"] = {}

      # workers stats (per worker)
      attr_names = [
         '/sys/vector_rate_per_worker', '/sys/node/clocks', '/sys/node/vectors',
         '/sys/node/calls', '/sys/node/suspends', '/sys/node/names'
         
      ]
      self._dir_workers = self.stats.ls(attr_names)
      self._data["vpp/stats/workers"] = {}

      # if stats (per if)
      self._dir_if_names = self.stats.ls(['/if/names'])
      attr_names = [
         '/if/drops', '/if/punt', '/if/ip4', '/if/ip6',
         '/if/rx-no-buf', '/if/rx-miss', '/if/rx-error', '/if/tx-error',
         '/if/mpls', 'if/rx', '/if/rx-unicast', '/if/rx-multicast',
         '/if/rx-broadcast', '/if/tx', '/if/tx-unicast', '/if/tx-multicast',
         '/if/tx-broadcast'
      ]
      self._dir_if = self.stats.ls(attr_names)
      self._data["vpp/stats/if"] = {}

      # node stats (per node)
      attr_names = [
         '/err/'
      ]
      self._dir_err = self.stats.ls(attr_names)
      self._data["vpp/stats/err"] = {}  

   def input(self):
      if self.use_api:
         self._input_api()
      if self.use_stats:
         self._input_stats()
      if self.use_gnmi:
         self._input_gnmi()

   def _input_gnmi(self):
      """
      input from gNMI client

      NOTE: actual input is done in VPPGNMIClient instances
      Here we only connect/reconnect if needed
      """
      self._connect_gnmi_clients()

      # update status
      for client in self.gnmi_clients:
         node = client.node
         status = client.status()
         self._data["vpp/gnmi"][node]["status"].append(status)
            
   def _input_api(self):
      """
      input from api socket

      """

      self._data["vpp/system"]["version"].append(self.vpp.api.show_version().version)

      attr_names=[
         "link_addr", "sw_if_index", "type",  "link_duplex", "link_speed", "link_mtu",
         "interface_dev_type",
      ]
      attr_types=[
         str, int, str, str, int, int, str,
      ]

      for intf in self.vpp.api.sw_interface_dump():

         # add entry if needed
         sw_if_name = intf.interface_name
         if sw_if_name not in self._data["vpp/api/if"]:
            self._data["vpp/api/if"][sw_if_name] = init_rb_dict(attr_names, types=attr_types)

         self._data["vpp/api/if"][sw_if_name]["link_addr"].append(intf.l2_address)
         self._data["vpp/api/if"][sw_if_name]["sw_if_index"].append(intf.sw_if_index)
         self._data["vpp/api/if"][sw_if_name]["type"].append(intf.type)
         self._data["vpp/api/if"][sw_if_name]["link_duplex"].append(intf.link_duplex)
         self._data["vpp/api/if"][sw_if_name]["link_speed"].append(intf.link_speed)
         self._data["vpp/api/if"][sw_if_name]["link_mtu"].append(intf.link_mtu)
         self._data["vpp/api/if"][sw_if_name]["interface_dev_type"].append(intf.interface_dev_type)

      # vpp.api.sw_interface_rx_placement_dump()
      # vpp.api.ip_table_dump()
      # vpp.api.ip_route_dump()

   def _input_stats(self):
      """
      input from stats socket

      """  

      attr_names = ['cached', 'used', 'available']

      # init system stats
      for k,d in self.stats.dump(self._dir_sys).items():         
         self._data["vpp/stats/sys"][k].append(d)

      # numa stats (per numa node ?)
      attr_names = ['cached', 'used', 'available']
      for k,d in self.stats.dump(self._dir_buffer_pool).items():

         # create entry if needed
         numa_node = k.split('/')[2]
         if numa_node not in self._data["vpp/stats/buffer-pool"]:
            self._data["vpp/stats/buffer-pool"][numa_node] = init_rb_dict(attr_names, counter=True)
         
         field_name = k.split('/')[3]
         self._data["vpp/stats/buffer-pool"][numa_node][field_name].append(d)
         
      # workers stats (per worker)
      attr_names = [
         '/sys/vector_rate_per_worker', '/sys/node/clocks', '/sys/node/vectors',
         '/sys/node/calls', '/sys/node/suspends', '/sys/node/names'
      ]
      attr_types = [ int, int, int, int, int, str ]

      worker_count, _ = self._data["vpp/stats/sys"]["/sys/num_worker_threads"].top()
      for i in range(worker_count):

         # create entry if needed
         if i not in self._data["vpp/stats/workers"]:
            self._data["vpp/stats/workers"][i] = init_rb_dict(attr_names, types=attr_types)

         for k,d in self.stats.dump(self._dir_workers).items():
            self._data["vpp/stats/workers"][i][k].append(d)

      # if stats (per if)
      attr_names = [
         '/if/drops', '/if/punt', '/if/ip4', '/if/ip6',
         '/if/rx-no-buf', '/if/rx-miss', '/if/rx-error', '/if/tx-error',
         '/if/mpls', '/if/rx-packets',  '/if/rx-bytes', 
         '/if/rx-unicast-packets', '/if/rx-unicast-bytes', 
         '/if/rx-multicast-packets', '/if/rx-multicast-bytes',
         '/if/rx-broadcast-packets',  '/if/rx-broadcast-bytes', 
         '/if/tx-packets', '/if/tx-bytes', 
         '/if/tx-unicast-packets', '/if/tx-unicast-bytes', 
         '/if/tx-multicast-packets', '/if/tx-multicast-bytes',
         '/if/tx-broadcast-packets', '/if/tx-broadcast-bytes'
      ]

      dump = self.stats.dump(self._dir_if)
      for i, if_name in enumerate(self.stats.dump(self._dir_if_names)['/if/names']):
         
         # add interface when needed
         if if_name not in self._data["vpp/stats/if"]:
            self._data["vpp/stats/if"][if_name] = init_rb_dict(attr_names, counter=True)
 
         for k,d in dump.items():
            
            if type(d[i][0]) is dict:
               bytes = sum([e['bytes'] for e in d[i]])
               packets = sum([e['packets'] for e in d[i]])

               self._data["vpp/stats/if"][if_name][k+'-bytes'].append(bytes)
               self._data["vpp/stats/if"][if_name][k+'-packets'].append(packets)

            else:
               self._data["vpp/stats/if"][if_name][k].append(sum(d[i]))

      # node stats (per node)
      for k,d in self.stats.dump(self._dir_err).items():
         
         node_name = k.split('/')[2]
         # skip ip6 nodes because nobody uses ip6
         if "6" in node_name:
            continue

         # add node entry if needed
         if node_name not in self._data["vpp/stats/err"]:
            self._data["vpp/stats/err"][node_name] = {}
         # add field entry if needed XXX: fix this
         err_name = k.split('/')[3]
         if err_name not in self._data["vpp/stats/err"][node_name]:
            self._data["vpp/stats/err"][node_name][err_name] = RingBuffer(err_name, counter=True)

         self._data["vpp/stats/err"][node_name][err_name].append(sum(d))

   def dump(self):
      print(self._data)

   def exit(self):
      if self.use_api:
         self.vpp.disconnect()
      if self.use_stats:
         self.stats.disconnect()
  

