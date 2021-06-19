"""
dxweb.py

   DxAgent web interface

@author: K.Edeline

"""

from ..constants import DXWEB_EMIT_PERIOD
from ..core.utils import remove_suffix
from ..core.ios import IOManager
from ..gnmi.client import DXAgentGNMIClient

import threading
import time
import json
from flask import Flask
from flask import render_template
from flask_socketio import SocketIO
from google.protobuf import json_format

class DXWeb(IOManager):
   def __init__(self):
      super(DXWeb, self).__init__(self)
      self.load_ios()
      
      self.gnmi_client = DXAgentGNMIClient(self.gnmi_target, self)
      self.app = Flask(__name__)
      self.app.add_url_rule('/', 'index', self.index)
      self.socketio = SocketIO(self.app)
      
   def index(self):
      self.format_data()
      return render_template('index.html', health_scores=self.health_scores,
                                           symptoms=self.symptoms,
                                           actives=self.actives,
                                           dxnodes=self.json_nodes,
                                           dxedges=self.json_edges)
   def format_data(self):
      """
      format dxagent data for web display
      
      """
       # format data
      self.json_nodes,self.json_edges = [],[]
      nodes={}
      compound_nodes=set()
      
      def insert_node(fullpath, node_list, tree):
         """
         insert node in graph
         """
         prev=None
         path = []
         for node in node_list:
            if node in tree:
               tree = tree[node]
            else: 
               tree[node] = {}
               tree = tree[node]
               if prev: # insert edge
                  src, dst = "/".join(path), "/".join(path+[node])
                  self.json_edges.append({"data":
                     { "id": src+dst,
                       "weight":len(self.json_edges)+1,
                       "source":src,
                       "target":dst,
                       #
                     },
                     "group":"edges",
                     #"position":{},
                     #"edgeType" : "type1",
                  })
            prev=node
            path.append(node)
            
         # insert node 
         node_data = {"data":
            { "id": "/".join(path), "name": node,
              "red":0,
              "green":0,
              "grey":0,
              #"selected":False,
              "symptoms": self.symptoms.get("/"+"/".join(path), ""),
              "parent": "/".join(path[:-1])+"parent" if len(path)>3 else "",
              "depth":len(path)-1,
            },  "classes": 'l1',
            "group":"nodes",
         }
         compound_nodes.add("/".join(path[:-1])+"parent" if len(path)>3 else "")
#         
#         self.info("id: {} parent: {}".format(node_data["data"]["id"],
#                                             node_data["data"]["parent"]))
         is_active = self.is_active(fullpath)
         if is_active:
            health = self.health_scores.get(fullpath,100)
            node_data["data"]["name"] += " \nhealth: {}%".format(health)
            node_data["data"]["red"] = 100-health#int((100-health)/10)
            node_data["data"]["green"] = health#int(health/10)
         else:
            node_data["data"]["grey"] = 100
         self.json_nodes.append(node_data)    

      for fullpath in self.health_scores:
         path = fullpath.lstrip("/").split('/')
         insert_node(fullpath, path, nodes)   
      for fullpath in self.nodes:
         path = self.path_to_nodes(fullpath.lstrip("/"))
         fullpath = "/"+"/".join(path)
         insert_node(fullpath, path, nodes)     
      #compound nodes
      for cnode in compound_nodes:
         if not cnode:
            continue
         self.json_nodes.append({"data":
                                    { "id": cnode,"name":"",
                                    "red":0,
                                   "green":0,
                                   "grey":0,
                                    }})
                                    
   def is_active(self, fullpath):
      """
      a node is active if itself and all its parents/ancestors are active
      """
      elements = fullpath.lstrip("/").split('/')
      for i in range(len(elements)):
         subpath = "/".join(elements[:i+1])
         if not self.actives.get("/"+subpath, True):
            return False
      return True
          
   def path_to_nodes(self, path):
   
      nodes = []
      node = ""
      
      parsing_name=False
      for c in path:
         if c == '/':
            if parsing_name:
               node += c
            else:
               nodes.append(node)
               node=""
         elif c == "[":
            parsing_name=True
            node += c
         elif c == "]":
            parsing_name=False
            node += c
         else:
            node += c
      # XXX
      if '[' in node and "if" not in node:
         nodes.append(node.split('[')[0])
      nodes.append(node)
      return nodes
      
   def parse_subscribe_response(self, response):
      msg = json.loads(json_format.MessageToJson(response))
      if "update" not in msg or "update" not in msg["update"]:
         return
      
      self.health_scores = {}
      self.symptoms = {}
      self.actives = {}
      self.nodes = set()
      
      for e in msg["update"]["update"]:
         path_json = e["path"]["elem"]
         path_str = ""
         for path_elem in path_json:
            if "key" in path_elem:
               key = path_elem["key"]["name"].replace("/","\\")
               path_str = path_str + "/{}[name={}]".format(
                    path_elem["name"], key)
            else:
               path_str = path_str + "/{}".format(path_elem["name"])
               
         val = None
         if "val" in e:
            if "intVal" in e["val"]:
               val = int(e["val"]["intVal"])
            elif "stringVal" in e["val"]:
               val = e["val"]["stringVal"]
            
         if "health" in path_str:
            self.health_scores[path_str.replace("/health","")] = val
         elif "symptoms" in path_str:
            split = path_str.split("/symptoms[name=")
            path_str = split[0]
            name = remove_suffix(split[1], "]/severity")
            symptoms = self.symptoms.get(path_str, "") +"<br>{} ({})".format(name, val)
            self.symptoms[path_str] = symptoms
         elif "active" in path_str and "/bm/mem" not in path_str:
            self.actives[path_str.replace("/active","")] = val
         #else:
         #   self.nodes.add("/".join(path_str.split('/')[:-1]))
            
   def fetch_data(self):
      """
      Fetch data from dxagent through gNMI
      """
      for response in self.gnmi_client.subscribe(xpath=["/health", "/symptoms", "/metrics"]):
         self.parse_subscribe_response(response)
         
   def gnmi_read_loop(self):
      """
      Push data to dxweb socketio
      """
      while True:
         self.fetch_data()
         self.format_data()
         self.socketio.emit("dxgraph", {"nodes":self.json_nodes, "edges":self.json_edges})
         time.sleep(DXWEB_EMIT_PERIOD)
         
   def run(self):
      thread = threading.Thread(target=self.gnmi_read_loop)
      thread.start()
      self.socketio.run(self.app, host="localhost")  
   
      
