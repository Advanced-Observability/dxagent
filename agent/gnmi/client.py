"""
   gnmi-client.py
   
   basic gnmi client
   
   K.Edeline
"""

import threading
import time

import grpc
from cisco_gnmi import ClientBuilder
from google.protobuf import json_format
from cisco_gnmi.proto import gnmi_pb2, gnmi_pb2_grpc

#
# The rate at which gNMI sends updates
GNMI_SAMPLING_PERIOD=int(1e9)*10
#
# gNMI client max consecutive retries
MAX_RETRIES=3
#
# time for gNMI to wait before retry connecting
GNMI_RETRY_INTERVAL=30

class BaseGNMIClient(threading.Thread):
   def __init__(self, node, info, data, user='a', password='a'):
      super().__init__()
      self.node = node
      self.info = info
      self._data = data
      self.user = user
      self.password = password
      self.client = None
      self.connected = False
      self.last_attempt = None
      self.retry=0
      self._exit=False
      self.synced = False
         
   def disconnect(self):
      self._exit=True

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
      @return synced, fetching, connected, abandonned, connecting
      
      """
      if self.connected and self.is_alive():
         if self.synced:
            return "synced"    
         else: 
            return "fetching"
      if self.connected and not self.is_alive():
         return "connected"
      if not self.connected and self.retry > MAX_RETRIES:
         return "abandonned"
      if not self.connected and self.retry <= MAX_RETRIES:
         return "connecting"

   def run(self,xpath="/"):
      """
      
      """
      _synced = False

      try:
         for response in self.client.subscribe_xpaths(xpath,
                         sample_interval=GNMI_SAMPLING_PERIOD):
            if self._exit:
               break
            if response.sync_response:
               _synced = True
            elif _synced:
               self.parse_json(json_format.MessageToJson(response))
               self.synced = True
      except Exception as e:
         self.info(e)
      finally:
         self.connected = False

class DXAgentGNMIClient:

   def __init__(self, node, parent, certs=None):
      self.node = node
      self.parent = parent
      
      builder = ClientBuilder(self.node)
      builder.set_secure_from_target()
      if self.parent:
         cert_path = self.parent.args.certs_dir
      elif certs:
         cert_path = certs
      else:
         cert_path = "../../certs/"
      #builder.set_secure_from_file(cert_path+"/rootCA.pem",
      #                             cert_path+"/client.key",
      #                             cert_path+"/client.crt")
      self.client = builder.construct()
      
   def capabilities(self):
      response = self.client.capabilities()
      return response
   def get(self, paths):
      response = self.client.get_xpaths(paths)
      return response
   def subscribe(self, xpath=["/"], mode="SAMPLE"):
      return self.client.subscribe_xpaths(xpath_subscriptions=xpath,
                                          sub_mode=mode)
     
import json
import base64

if __name__ == "__main__":
   target = "0.0.0.0:50051"
   cli = DXAgentGNMIClient(target, None)
   print(cli.capabilities())
   responses = cli.subscribe(xpath=["/"], mode="ON_CHANGE")
   for response in responses:
      response_json = json.loads(json_format.MessageToJson(response))
      print(response_json)
      print(response.update.timestamp)
#      for i in response_json["update"]["update"]:
#         print(base64.b64decode(i["val"]["jsonVal"]))
#      print(base64.b64decode(response_json["update"]["update"][0]["val"]["jsonVal"]))
      
      
      

