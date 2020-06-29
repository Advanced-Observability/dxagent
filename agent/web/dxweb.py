"""
dxweb.py

   DxAgent web interface

@author: K.Edeline

"""

from agent.core.ios import IOManager
from agent.gnmi.gnmi_client import DXAgentGNMIClient

import threading
import time
import json
from flask import Flask
from flask import render_template
from flask_socketio import SocketIO


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
      
      def insert_node(fullpath, node_list, tree):
         """
         insert node in graph
         """
         #self.info(fullpath)
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
                     }
                  })
            prev=node
            path.append(node)
            
         # insert node 
         node_data = {"data":
            { "id": "/".join(path), "name": node,
              "red":0,
              "green":0,
              "grey":0,
            }
         }
         #self.info(self.actives)
         is_active = self.actives.get(fullpath, True)
         if is_active:
            health = self.health_scores.get(fullpath,100)
            node_data["data"]["name"] += " health: {}%".format(health)
            node_data["data"]["red"] = int((100-health)/10)
            node_data["data"]["green"] = int(health/10)
         else:
            node_data["data"]["grey"] = 10
         self.json_nodes.append(node_data)    
      
      for fullpath in self.health_scores:
         path = fullpath.lstrip("/").split('/')
         insert_node(fullpath, path, nodes)   
      for fullpath in self.nodes:
         path = self.path_to_nodes(fullpath.lstrip("/"))#fullpath.lstrip("/").split('/')
         fullpath = "/".join(path)
         insert_node(fullpath, path, nodes)     
                                           
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
      msg = json.loads(response)
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
               path_str = path_str + "/{}[name={}]".format(
                    path_elem["name"], path_elem["key"]["name"])
            else:
               path_str = path_str + "/{}".format(path_elem["name"])
               
         if "val" in e:
            if "intVal" in e["val"]:
               val = int(e["val"]["intVal"])
            elif "stringVal" in e["val"]:
               val = e["val"]["stringVal"]
         else:
            val = None
         if "health" in path_str:
            self.health_scores[path_str.replace("/health","")] = val
         elif "symptoms" in path_str:
            self.symptoms[path_str.replace("/symptoms","")] = val
         elif "active" in path_str and "/bm/mem" not in path_str:
            self.actives[path_str.replace("/active","")] = val
         else:
            self.nodes.add("/".join(path_str.split('/')[:-1]))
            
   def fetch_data(self):
      for response in self.gnmi_client.subscribe():
         self.parse_subscribe_response(response)
         
   def gnmi_read_loop(self):
      while True:
         self.fetch_data()
         self.format_data()
         #self.info(self.json_nodes)
         #self.socketio.emit("dxgraph", {"nodes":1, "edges":2})
         self.socketio.emit("dxgraph", {"nodes":self.json_nodes, "edges":self.json_edges})
         time.sleep(1)
         
   def run(self):
      thread = threading.Thread(target=self.gnmi_read_loop)
      thread.start()
      self.socketio.run(self.app, host="0.0.0.0")  
   
      
