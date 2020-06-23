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

from agent.rbuffer import MDict

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
      supModel = gnmi_pb2.ModelData(name="my_model",
                  organization="My Company Inc", version="1.0")
      response.supported_models.extend([supModel])
      response.supported_encodings.extend(gnmi_pb2.PROTO)
      response.gNMI_version = "GNMI Version 1.0"
       
      return response
    
   def _getResponse(self, paths):
      response = gnmi_pb2.GetResponse()
      return response
      
   def _subscribeResponse(self, requests):
      """
      build SubscribeResponse
      
      only allows for subscription to root
      """
      for request in requests:
         #print(request.subscribe.subscription[0].path)
         #print(request.subscribe.prefix)
         # build reponse
         response = gnmi_pb2.SubscribeResponse()
         response.update.timestamp = int(time.time())
         response.sync_response = True
         
         for path_string, val, _type in self.exporter._iterate_data():
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
         yield response
      
   # gNMI Services Capabilities Routine
   def Capabilities(self, request, context):
      return self._capabilitiesResponse()
      
   # gNMI Services Get Routine
   def Get(self, request, context):
      return self._getResponse(request)
      
   # gNMI Services Subscribe Routine
   def Subscribe(self, request, context):
      return self._subscribeResponse(request)
        
        
class DXAgentExporter():
   def __init__(self, data, info, engine,
                target_url="0.0.0.0:50051",
                tls_enabled=True):
      self.data = data
      self.info = info
      self.engine = engine
      self.target_url = target_url
      
      pkeypath = self.engine.args.certs_dir+"/device.key"
      certpath = self.engine.args.certs_dir+"/device.crt"
      
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
      _before_indexed = ["vm", "kb", "cpu", "if", "sensors", "disk"]
      if node in _before_indexed:
         return True
      for before_indexed in _before_indexed:
         if node.endswith(before_indexed):
            return True
      return False
      
   def build_path_string(self, nodes):
      path_string = ""
      indexed = False
      
      for node in nodes:
         if indexed:
            path_string += "[name={}]".format(node)
            indexed = False
         else:
            path_string += "/{}".format(node)
            indexed = self._node_before_indexed(node)
            
      return path_string.replace('.', '/')

   def _iterate_data(self, skip=[]):
      """
      write dict to ShareableMemory

      only write fields that changed
           if total datafield changed, rewrite all
            otherwise skip all if not has_changed()

      """
      skip.append("symptoms")
      skip.append("stats")
      skip.append("health_scores")
      for k,d in self.data.items():
         if k in skip:
            continue
         #self.info(k)
         yield from self._iterate_data_rec(d, k)
      # special entry: symptom
      for s in self.data["symptoms"]:
         for path in s.args:
            yield "{}/symptoms[name={}]/".format(path,s.name), "", None
            yield "{}/symptoms[name={}]/severity".format(path,s.name), s.severity.value, int
      for path,score in self.data["health_scores"].items():
         yield path+"/health", score, int   
      
#def test():
#   exporter = DXAgentExporter(None, print, None)
#   exporter.run()

