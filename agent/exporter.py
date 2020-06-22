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
            self._iterate_data_rec(dd, *args, kk)
            if isinstance(dd, MDict):
               dd.release()
         else:
            if dd.is_empty():
               continue
            # write a line to ShareableMemory
            value, severity = dd.top()
            path_string = self.build_path_string(
                        "".join(["/"+key for key in list(args)+[kk]]))
            yield path_string, value, dd.type

   def build_path_string(self, path_string):
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
      for k,d in self.data.items():
         if k in skip:
            continue
         yield from self._iterate_data_rec(d, k)
      # special entry: symptom
      for s in self.data["symptoms"]:
         yield "/symptoms/"+s.name, str(s.args), str
         yield "/symptoms/"+s.name+"/severity", s.severity.value, int
      
#def test():
#   exporter = DXAgentExporter(None, print, None)
#   exporter.run()

