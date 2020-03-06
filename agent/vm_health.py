"""
vm_health.py

   Input parsing for virtual machines health monitoring

@author: K.Edeline
"""

class VMWatcher():

   def __init__(self, data):
      self._data = data

   def input(self):
      """
      VM (virtualbox)
         VBoxManage showvminfo
         VBoxManage bandwidthctl
         VBoxManage storagectl
         VBoxManage metrics

      """

      pass

