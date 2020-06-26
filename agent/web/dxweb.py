"""
dxweb.py

   This file contains a DxAgent web interface

@author: K.Edeline

"""

from agent.ios import IOManager
from agent.gnmi_client import DXAgentGNMIClient

from flask import Flask
from flask import render_template
import json


class DXWeb(IOManager):
   def __init__(self):
      super(DXWeb, self).__init__(self)
      self.load_ios()
      
      self.gnmi_client = DXAgentGNMIClient(self.gnmi_target, self)
      self.app = Flask(__name__)
      self.app.add_url_rule('/', 'index', self.index)
      
   def index(self):
      # format data
      
      json_nodes = []
      unique_edges=set()
      for fullpath,health in self.health_scores.items():
         node=fullpath.split('/')[-1]
         self.info(node)
         json_nodes.append({"data":
            { "id": node,
              "red":int((100-health)/10),
              "green":int(health/10)
            }
         })         
         
         prev=None
         for node in fullpath.lstrip("/").split('/'):
            if prev:
               unique_edges.add((prev,node))
            prev=node

      json_edges=[]
      for i,edge in enumerate(unique_edges):
         json_edges.append({"data":
            { "id": edge[0]+edge[1],
              "weight":i+1,
              "source":edge[0],
              "target":edge[1],
            }
         })
      self.info(json_edges)

#      { data: { id: 'ab', red: 3, green: 7 } },
#      { data: { id: 'b', red: 6, green: 4} },
#      { data: { id: 'c', red: 2, green: 8 } },
#      { data: { id: 'd', red: 7, green: 3} },
#      { data: { id: michel, red: 2, green: 8} }
      return render_template('index.html', health_scores=self.health_scores,
                                           symptoms=self.symptoms,
                                           actives=self.actives,
                                           dxnodes=json_nodes,
                                           dxedges=json_edges)
      
   def parse_subscribe_response(self, response):
      msg = json.loads(response)
      if "update" not in msg or "update" not in msg["update"]:
         return
      
      self.health_scores = {}
      self.symptoms = {}
      self.actives = {}

      
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
         elif "active" in path_str:
            self.actives[path_str.replace("/active","")] = val
          
   def run(self):
      for response in self.gnmi_client.subscribe():
         self.parse_subscribe_response(response)
      self.info(self.health_scores)
      self.info(self.symptoms)
      self.info(self.actives)
      
      self.app.run(host="0.0.0.0")
      
   
      
