"""
symptoms.py

   symptom rules

@author: K.Edeline

"""

import ast
import operator

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
      if "vm" in path:
         self.prefix="vm"
      if "kb" in path:
         self.prefix="kb"
      self._compile_rule()
      
   def _safe_rule(self, variables):
       """
       
       Returns True if rule is safe for eval()
       """
       variables += ['access', '_1min', '_5min']
       _safe_names = {'None': None, 'True': True, 'False': False}
       _safe_nodes = [
           'Add', 'And', 'BinOp', 'BitAnd', 'BitOr', 'BitXor', 'BoolOp',
           'Compare', 'Dict', 'Eq', 'Expr', 'Expression', 'Call',
           'Gt', 'GtE', 'Is', 'In', 'IsNot', 'LShift', 'List',
           'Load', 'Lt', 'LtE', 'Mod', 'Name', 'Not', 'NotEq', 'NotIn',
           'Num', 'Or', 'RShift', 'Set', 'Slice', 'Str', 'Sub', 'Constant',
           'Tuple', 'UAdd', 'USub', 'UnaryOp', 'boolop', 'cmpop',
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
            return ast.Call(func=ast.Name(id="access", ctx=node.ctx),
                            args=[ast.Constant(value=node.id)],
                            keywords=[])
                            
      # 1. string-level replacement
      self._raw_rule = self.rule
      alias=[("1min","_1min"), ("5min","_5min")]
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
      
      class Comparator():
         def __init__(self, rb):
            self.islist=isinstance(rb,list)
            self.rb=rb
            # how many samples are considered
            self.count=1
            
         def indexes(self):
            return [index for (index,_) in self.rb]
            
         def compare(self, other, _operator):
            """
            compare a Comparator with a constant or another Comparator
            """
            if not self.islist:
               # not enough samples, skip
               if len(self.rb) < self.count:
                  return False
               return all(_operator(v,other) for v in self.rb._tops(self.count))
            ret=[]
            for index, rb in self.rb:
               if len(rb) < self.count:
                  continue
               if all(_operator(v,other) for v in rb._tops(self.count)):
                  ret.append((index,rb))
            # return a comparator if it matched
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
            
         def __and__(self, other):
            if (not self.islist 
                 or not isinstance(other,Comparator) 
                 or not other.islist):
               return self and other
            intersection=list(set(self.indexes()) & set(other.indexes()))
            self.rb = filter(lambda e: e[0] in intersection, self.rb)
            if not self.rb:
               return False
            return self
            
         def __or__(self, other):
            if (not self.islist 
                 or not isinstance(other,Comparator) 
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
               return Comparator([(dev, b[path][var]) for dev,b in data[prefix2].items()])
            # double list
            ret=[]
            for dev,b in data[prefix2].items():
               ret += [(dev+":"+dev2,rb[var]) for dev2,rb in b[path].items()]
            return Comparator(ret)
         
         if not metric.islist:
            return Comparator(data[path][var])
         return Comparator([(dev, b[var]) for dev,b in data[path].items()])
         
      def _1min(rb):
         rb.count = engine.sample_per_min
         return rb
      def _5min(rb):
         rb.count = engine.sample_per_min*5
         return rb
         
      ret=eval(self._o, globals(), locals())
      try:
         self.args = []
         if ret:
            if isinstance(ret, Comparator):
               # XXX
               if self.path.endswith("if"):
                  self.args = ["{}/if[name={}]".format(self.node.fullname,index) for index in ret.indexes()]
               else:
                  self.args = ["{}[name={}]".format(self.node.fullname,index) for index in ret.indexes()]
            else:
               self.args = [self.node.fullname]
            return True
         return False
      except Exception as e:
         self.engine.info("Evaluating rule {} raised error ".format(self.rule, e))
         return False
      
   def __str__(self):
      return "{} {} {}".format(self.name, self.severity, self.rule)
      
