"""
exporter.py

   gNMI exporter for dxagent data

@author: K.Edeline
"""

import re
import time
from concurrent import futures
import grpc
from cisco_gnmi import ClientBuilder
from google.protobuf import json_format
from cisco_gnmi.proto import gnmi_pb2, gnmi_pb2_grpc
from cisco_gnmi.proto.gnmi_pb2_grpc import gNMIServicer 
import json

from ..core.rbuffer import MDict

def list_from_path(path='/'):
   if path:
      if path[0]=='/':
         if path[-1]=='/':
            return re.split('''/(?=(?:[^\[\]]|\[[^\[\]]+\])*$)''', path)[1:-1]
         else:
            return re.split('''/(?=(?:[^\[\]]|\[[^\[\]]+\])*$)''', path)[1:]
      else:
         if path[-1]=='/':
            return re.split('''/(?=(?:[^\[\]]|\[[^\[\]]+\])*$)''', path)[:-1]
         else:
            return re.split('''/(?=(?:[^\[\]]|\[[^\[\]]+\])*$)''', path)
   return []

def path_from_string(path='/'):
   mypath = []
   for e in list_from_path(path):
      eName = e.split("[", 1)[0]
      eKeys = re.findall('\[(.*?)\]', e)
      dKeys = dict(x.split('=', 1) for x in eKeys)
      mypath.append(gnmi_pb2.PathElem(name=eName, key=dKeys))
   return gnmi_pb2.Path(elem=mypath)

class DXAgentServicer(gNMIServicer):

   def __init__(self, exporter):
      super(DXAgentServicer, self).__init__()
      self.exporter = exporter

   def _capabilitiesResponse(self):
      response = gnmi_pb2.CapabilityResponse()
      supModel = gnmi_pb2.ModelData(name="ietf-service-assurance",
                  organization="IETF", version="1.0")
      supModel2 = gnmi_pb2.ModelData(name="dxagent-internal",
                  organization="uliege", version="1.0")
      response.supported_models.extend([supModel, supModel2])
      response.gNMI_version = "0.7.0"
       
      return response
    
   def _getResponse(self, paths):
      response = gnmi_pb2.GetResponse()
      return response
      
   def _validate_subscriptions(self, request):
      """
      validate and return string-converted paths
      
      
      """
      paths = []
      if "subscribe" not in request or "subscription" not in request["subscribe"]:
         return paths
      subscriptions = request["subscribe"]["subscription"]
      for subscription in subscriptions:
         path_str = ""
         path_elements = subscription["path"]["elem"]
         for name in path_elements:
            if "name" in name:
               path_str += "/{}".format(name["name"])
            else:
               path_str += "/"
         paths.append(path_str)
      return paths
      
   def _subscribeResponse(self, request):
      """
      build SubscribeResponse
      
      only allows for subscription to root
      """
      request_json = json.loads(json_format.MessageToJson(request))
      paths=self._validate_subscriptions(request_json)
      
      while True:

         #self.exporter.info(request.subscribe.prefix)
         
         # build reponse
         response = gnmi_pb2.SubscribeResponse()
         response.update.timestamp = int(time.time())
         response.sync_response = True
         
         for path_string, val, _type in self.exporter._iterate_data(paths):
            #self.exporter.engine.info(path_string)
            path = path_from_string(path_string)
            # add an update message for path
            added = response.update.update.add()
            added.path.CopyFrom(path)
            if _type == int:
               added.val.int_val = val
            elif _type == str:
               added.val.string_val = val
            elif _type == float:
               added.val.float_val = val
            elif _type == "json": # grpc will base64 encode
               added.val.json_val = val.encode("utf-8")
         yield response
         time.sleep(10)
      
   # gNMI Services Capabilities Routine
   def Capabilities(self, request, context):
      return self._capabilitiesResponse()
      
   # gNMI Services Get Routine
   def Get(self, request, context):
      return self._getResponse(request)
      
   # gNMI Services Subscribe Routine
   def Subscribe(self, requests, context):

      for request in requests:
         self.exporter.info(request)
         self.exporter.info(type(request)) 
         #yield from self._subscribeResponse(request)
         request_json = json.loads(json_format.MessageToJson(request))
         paths=self._validate_subscriptions(request_json)
         
         while True:

            #self.exporter.info(request.subscribe.prefix)
            
            # build reponse
            response = gnmi_pb2.SubscribeResponse()
            response.update.timestamp = int(time.time())
            response.sync_response = True
            
            for path_string, val, _type in self.exporter._iterate_data(paths):
               #self.exporter.engine.info(path_string)
               path = path_from_string(path_string)
               # add an update message for path
               added = response.update.update.add()
               added.path.CopyFrom(path)
               if _type == int:
                  added.val.int_val = val
               elif _type == str:
                  added.val.string_val = val
               elif _type == float:
                  added.val.float_val = val
               elif _type == "json": # grpc will base64 encode
                  added.val.json_val = val.encode("utf-8")
            yield response
            self.exporter.info("yield once")
            time.sleep(10)
         
      self.exporter.info("after")
        
        
class DXAgentExporter():
   def __init__(self, data, info, agent,
                target_url="0.0.0.0:50051",
                tls_enabled=True):
      self.data = data
      self.info = info
      self.agent = agent
      self.target_url = target_url
      
      pkeypath = self.agent.args.certs_dir+"/device.key"
      certpath = self.agent.args.certs_dir+"/device.crt"
      
      self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
      gnmi_pb2_grpc.add_gNMIServicer_to_server(
           DXAgentServicer(self), self._server)
      if tls_enabled:
         with open(pkeypath, 'rb') as f:
            privateKey = f.read()
         with open(certpath, 'rb') as f:
            certChain = f.read()
         credentials = grpc.ssl_server_credentials(((privateKey, certChain, ), ))
         self._server.add_secure_port(self.target_url, credentials)         
      else:
         self._server.add_insecure_port(self.target_url)
       
   def run(self, wait=False):
      if not self.target_url:
         return
      self._server.start()
      if wait:
         self._server.wait_for_termination()      

   def _iterate_data_rec(self, d, *args):
      """
      recursively write dictionnary to shareableMemory
      
      @param d the dictionary
      @param args parent keys to be written aswell 
      """
      for kk, dd in d.items():
         if isinstance(dd, dict):
            # avoid race condition with threads writing in dicts
            if isinstance(dd, MDict):
               dd.acquire()
            yield from self._iterate_data_rec(dd, *args, kk)
            if isinstance(dd, MDict):
               dd.release()
         else:
            if dd.is_empty() or not dd.is_metric():
               continue
            value, severity = dd.top()
            path_string = self.build_path_string(list(args)+[kk])
            yield path_string, value, dd.type
               
   def _node_before_indexed(self, node):
      """
      
      @return True if node comes before an indexed node
      
      """
      _before_indexed = ["vm", "kb", "cpus", "if", "sensors", "disks"]
      if node in _before_indexed:
         return True
      for before_indexed in _before_indexed:
         if node.endswith(before_indexed):
            return True
      return False
      
   def build_path_string(self, nodes):
      path_string = ""
      indexed = False
      # XXX:
      if nodes[0] == "/node/vm" or nodes[0] == "/node/kb":
         nodes[2]=nodes[2].replace("/node/vm","")
         nodes[2]=nodes[2].replace("/node/kb","")
      nodes[0]=nodes[0].replace("/node",
                                "/node[name={}]".format(self.agent.sysinfo.node))
      for node in nodes:
         if not node:
            continue
         if indexed and node != "active":
            path_string += "[name={}]".format(node)
            indexed = False
         else:
            if not node.startswith("/"):
                path_string += "/"
            path_string += node
            indexed = self._node_before_indexed(node)
            
      return path_string

   def _iterate_data(self, subscribed, skip=[]):
      """
      write dict to ShareableMemory

      only write fields that changed
           if total datafield changed, rewrite all
            otherwise skip all if not has_changed()
            
      @param subscribed the list of subscribed paths
             /subservices
             /subservices/subservice
             /metrics 
             /symptoms
             /health
             / 

      """
      skip.append("symptoms")
      skip.append("stats")
      skip.append("health_scores")
      if "/" in subscribed or "/metrics" in subscribed:
         for k,d in self.data.items():
            if k in skip:
               continue
            yield from self._iterate_data_rec(d, k)
      # special entry: symptom
      if "/" in subscribed or "/symptoms" in subscribed:
         for s in self.data["symptoms"]:
            for path in s.args:
               #yield "{}/symptoms[name={}]/".format(path,s.name), "", None
               yield "{}/symptoms[name={}]/severity".format(path,s.name), s.severity.weight(), int
            
      if "/" in subscribed or "/health" in subscribed:
         for path,score in self.data["health_scores"].items():
            yield path+"/health", score, int 
            
      if "/" in subscribed or "/subservices/subservice" in subscribed:
         for subservice in self.agent.engine:
            yield subservice.fullname, subservice.json_bag(), "json"
            
      if "/" in subscribed or "/subservices" in subscribed:
            yield "/subservices", self.agent.engine.json_bag(), "json" 
            
      
