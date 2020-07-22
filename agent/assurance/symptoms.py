"""
symptoms.py

   symptom rules

@author: K.Edeline

"""

import ast
import operator
import hashlib
import time
import sys

from ..core.rbuffer import RingBuffer

class RuleException(Exception):
   """
   RuleException(Exception)
   """
   def __init__(self, value):
      self.value = value
   def __str__(self):
      return repr(self.value)
      
class Symptom():
   def __init__(self, name, path, severity, rule, engine, node=None, weight=None):
      self.name = name
      self.path = path
      self.severity = severity
      self.rule = rule
      self.engine = engine
      self.prefix = None
      self.weight = weight if weight else severity.weight()
      self.node = node
      self.id = hashlib.sha1(self.name.encode('utf-8')).hexdigest()
      self.timestamp = "0"
      if "/node/vm" in path:
         self.prefix="/node/vm"
      if "/node/kb" in path:
         self.prefix="/node/kb"
      self._compile_rule()
      
   def _safe_rule(self, variables):
       """
       
       Returns True if rule is safe for eval()
       """
       variables += ['access', '_1min', '_5min', '_dynamicity']
       _safe_names = {'None': None, 'True': True, 'False': False}
       _safe_nodes = [
           'Add', 'And', 'BinOp', 'BitAnd', 'BitOr', 'BitXor', 'BoolOp',
           'Compare', 'Dict', 'Eq', 'Expr', 'Expression', 'Call',
           'Gt', 'GtE', 'Is', 'In', 'IsNot', 'LShift', 'List',
           'Load', 'Lt', 'LtE', 'Mod', 'Name', 'Not', 'NotEq', 'NotIn',
           'Num', 'Or', 'RShift', 'Set', 'Slice', 'Str', 'Sub', 'Constant',
           'Tuple', 'UAdd', 'USub', 'UnaryOp', 'boolop', 'cmpop', 'Div',
           'expr', 'expr_context', 'operator', 'slice', 'unaryop']
       for subnode in ast.walk(self.tree):
           subnode_name = type(subnode).__name__
           if isinstance(subnode, ast.Name):
               if subnode.id not in _safe_names and subnode.id not in variables:
                   raise RuleException("Unsafe rule {} contains {}".format(self._raw_rule, subnode.id))
           if subnode_name not in _safe_nodes:
               raise RuleException("Unsafe rule {} contains {}".format(self._raw_rule, subnode_name))
       return True     

   def _compile_rule(self):
      class RewriteName(ast.NodeTransformer):
         def visit_BoolOp(self, node):
            self.generic_visit(node)
            return ast.BinOp(left=node.values[0],
               op=ast.BitAnd(),
               right=node.values[1]
               )
         def visit_Name(self, node):
            # only if parent is not a func
            if node.id.startswith("_"):
               return node
            # backward-compatible with <3.8
            return ast.Call(func=ast.Name(id="access", ctx=node.ctx),
                            args=[ast.Str(s=node.id)],
                            keywords=[])
             

      # 1. string-level replacement
      self._raw_rule = self.rule
      alias=[("1min","_1min"), ("5min","_5min"), ("dynamicity","_dynamicity")]
      for old,new in alias:
         self.rule=self.rule.replace(old,new)
      # 2. ast-level replacement
      node = ast.parse(self.rule, mode='eval')
      self.tree = ast.fix_missing_locations(RewriteName().visit(node))
      # 3. check()
      self._o=compile(node, '<string>', 'eval')
         
   def check(self, data):
      """
      Check if the node exhibit this symptom
      
      """
      engine = self.engine
      metrics = self.engine.metrics
      info = self.engine.info
      class IndexedVariable():
         def __init__(self, rb):
            self.islist=isinstance(rb,list)
            self.rb=rb
            # how many samples are considered
            self.count=1
            # whether to compare value or dynamicty
            self.dynamicity=False
            
         def indexes(self):
            return [index for (index,_) in self.rb]
            
         def compare(self, other, _operator):
            """
            compare a IndexedVariable with a constant or another IndexedVariable
            """
            if not self.islist:
               # not enough samples, skip
               if len(self.rb) < self.count:
                  return False
               if not self.dynamicity:
                  return all(_operator(v,other) for v in self.rb._tops(self.count))
               else:
                  return _operator(self.rb._dynamicity(self.count),other)
                  
            if len(self.rb)>0 and not isinstance(self.rb[0][1], RingBuffer):
               ret = []
               if not isinstance(other,IndexedVariable):
                  ret = [(dev,True) for dev,val in self.rb if _operator(val,other)]        
               else:
                  ret = [(d1,True) for (d1,v1),(d2,v2) in zip(self.rb,other.rb) if _operator(v1,v2) and d1 == d2]
               #info("compare: {}".format(ret))
               if not ret:
                  return False
               self.rb = ret
               return self                  
                  
            ret=[]
            for index, rb in self.rb:
               if len(rb) < self.count:
                  continue
               if not self.dynamicity:
                  if all(_operator(v,other) for v in rb._tops(self.count)):
                     ret.append((index,rb))
               else:
                  if _operator(rb._dynamicity(self.count),other):
                     ret.append((index,rb))                  
            # return a IndexedVariable if it matched
            if not ret:
               return False
            self.rb = ret
            return self         
         
         def __lt__(self, other):
            return self.compare(other, operator.__lt__)
         def __le__(self, other):
            return self.compare(other, operator.__le__)
         def __eq__(self, other):
            return self.compare(other, operator.__eq__)
         def __ne__(self, other):
            return self.compare(other, operator.__ne__)
         def __gt__(self, other):
            return self.compare(other, operator.__gt__)
         def __ge__(self, other):
            return self.compare(other, operator.__ge__)
            
         def __add__(self, other):
            return self.rb._top() + other.rb._top()
         def __sub__(self, other):
            return self.rb._top() - other.rb._top()
         def __mul__(self, other):
            return self.rb._top() * other.rb._top()
         def __floordiv__(self, other):
            div = other.rb._top()
            if div == 0:
               return 0
            return self.rb._top() // div
         def __truediv__(self, other):
            ret = []
            for a,b in zip(self.rb,other.rb):
               if a[0] != b[0]:
                  continue
               div = b[1]._top()
               if div == 0:
                  ret.append((a[0], 0))
               else:
                  ret.append((a[0], a[1]._top()/div))
            if not ret:
               return False
            self.rb = ret
            return self
            
         def __and__(self, other):
            if (not self.islist 
                 or not isinstance(other,IndexedVariable) 
                 or not other.islist):
               return self and other
            intersection=list(set(self.indexes()) & set(other.indexes()))
            self.rb = list(filter(lambda e: e[0] in intersection, self.rb))
            if not self.rb:
               return False
            return self
            
         def __or__(self, other):
            if (not self.islist 
                 or not isinstance(other,IndexedVariable) 
                 or not other.islist):
               return self or other
            for e in other.rb:
               if e not in self.rb:
                  self.rb.append(e)
            if not self.rb:
               return False
            return self
      
      def access(var):
         metric = metrics[var]
         path = self.path
         
         if self.prefix:
            prefix2=self.prefix            
            if not metric.islist:
               ret = []
               for dev,b in data[prefix2].items():
                  # exception for double list in vm/kb
                  if var in b[path] and dev in self.node.fullname:
                     ret.append((dev, b[path][var]))
                  elif self.node.name in b[path]:
                     ret.append((dev, b[path][self.node.name][var]))
                  #info("node:{} dev:{}".format(self.node, dev))
               #info("node:{} access:{}".format(self.node, ret))
               return IndexedVariable(ret)
               
            # double list
            ret=[]
            for dev,b in data[prefix2].items():
               if path not in b:
                  continue
               ret += [(dev+":"+dev2,rb[var]) for dev2,rb in b[path].items()]
            return IndexedVariable(ret)
         
         if not metric.islist:
            # exception for net/if
            if self.node.name in data[path]:
               return IndexedVariable(data[path][self.node.name][var])
            return IndexedVariable(data[path][var])
         return IndexedVariable([(dev, b[var]) for dev,b in data[path].items()])
         
      def _dynamicity(indexed_var):
         indexed_var.dynamicity=True
         return indexed_var
      def _1min(indexed_var):
         indexed_var.count = engine.sample_per_min
         return indexed_var
      def _5min(indexed_var):
         indexed_var.count = engine.sample_per_min*5
         return indexed_var
      
      # skip symptoms for subservices of inactive vm/kb
      if not self.node.active or not (self.node.parent and self.node.parent.active):
         return False
         
      ret=eval(self._o, globals(), locals())
      try:
         
         self.args = []
         if ret:
            self.timestamp = str(time.time())
            if isinstance(ret, IndexedVariable):
               if ret.islist:
                  self.args = ["{}[name={}]".format(self.node.fullname,index) if index not in self.node.fullname else self.node.fullname for index in ret.indexes()]
               else:
                  self.args = ["{}{}".format(self.node.fullname,index) for index in ret.indexes()]
            else:
               self.args = [self.node.fullname]
            return True
         return False
      except Exception as e:
         self.engine.info("Evaluating rule {} raised error ".format(self.rule, e))
         return False
      
   def __str__(self):
      return "{} {} {}".format(self.name, self.severity, self.rule)
   def __repr__(self):
      return str(self)
      
