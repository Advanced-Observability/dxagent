"""
   gnmi-client.py
   
   basic gnmi client
   
   K.Edeline
"""

import grpc
from cisco_gnmi import ClientBuilder
from google.protobuf import json_format
from cisco_gnmi.proto import gnmi_pb2, gnmi_pb2_grpc

class DXAgentGNMIClient:

   def __init__(self, node, parent, certs=None):
      self.node = node
      self.parent = parent
      
      builder = ClientBuilder(self.node)
      #builder.set_secure_from_target()
      if self.parent:
         cert_path = self.parent.args.certs_dir
      elif certs:
         cert_path = certs
      else:
         cert_path = "../../certs/"
      builder.set_secure_from_file(cert_path+"/rootCA.pem",
                                   cert_path+"/client.key",
                                   cert_path+"/client.crt")
      self.client = builder.construct()
      
   def capabilities(self):
      response = self.client.capabilities()
      return response
   def get(self, paths):
      response = self.client.get_xpaths(paths)
      return response
   def subscribe(self, xpath=["/"]):
      responses = []
      return [json_format.MessageToJson(response) 
               for response in self.client.subscribe_xpaths(xpath)]
     
import json
import base64

if __name__ == "__main__":
   cli = DXAgentGNMIClient("0.0.0.0:50051", None)
   print(cli.capabilities())
   responses = cli.subscribe(xpath=["/subservices"])
   for response in responses:
      response_json = json.loads(response)
      print(response_json)
      for i in response_json["update"]["update"]:
         print(base64.b64decode(i["val"]["jsonVal"]))
      print(base64.b64decode(response_json["update"]["update"][0]["val"]["jsonVal"]))
      
      
      

