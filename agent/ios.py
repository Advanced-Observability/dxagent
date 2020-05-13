"""
ios.py

   Handle arguments, configuration file 

@author: K.Edeline
"""

import sys
import argparse
import configparser
import logging
import os

class IOManager():
   """

   extend me

   """
   def __init__(self, child=None, parse_args=True):
      #super(IOManager, self).__init__()

      self.child  = child
      self.parse_args = parse_args

      self.args   = None
      self.config = None
      self.logger = None

   def load_ios(self, module="dxagent"):
      """
      Load all ios

      """
      if not self.parse_args:
         return

      if module == "dxtop":
         self.arguments_dxtop()
         self.log()

      if module == "dxagent":
         self.arguments_dxagent()
         if "start" in self.args.cmd:
            self.configuration_dxagent()
            self.log()
      
   ########################################################
   # ARGPARSE
   ########################################################
   def arguments_dxtop(self):
      """
      Parse dxtop arguments

         Used mostly to provide the location of the config file.
      """

      parser = argparse.ArgumentParser(description='Diagnostic Agent console app')

      # XXX: remove
      parser.add_argument('-l' , '--log-file', type=str, default="dxtop.log",
                         help='log file location (default: dxtop.log)')
      parser.add_argument('-v' , '--verbose', action='store_true',
                         help='increase output level') 

      self.args = parser.parse_args()

      return self.args

   def arguments_dxagent(self):
      """
      Parse dxagent arguments

      """

      parser = argparse.ArgumentParser(description='Diagnostic Agent')
      parser.add_argument('cmd', type=str,
                           choices=["start", "stop", "restart", "status"],
                          )
      parser.add_argument('-l' , '--log-file', type=str,
                         default="/var/log/dxagent.log",
                         help='log file location (default: dxagent.log)')
      parser.add_argument('-c' , '--config', type=str, default="./dxagent.ini",
                         help='configuration file location')
      parser.add_argument('-r' , '--ressources-dir', type=str,
                         default="./res/",
                         help='configuration file location')  
      parser.add_argument('-s' , '--disable-shm', action='store_true',
                         help='disable shared memory segment '
                              '(cannot use dxtop)')      
      parser.add_argument('-v' , '--verbose', action='store_true',
                         help='increase output level') 

      self.args = parser.parse_args()

      # retreive absolute paths
      self.args.config = os.path.abspath(self.args.config)
      self.args.ressources_dir = os.path.abspath(self.args.ressources_dir)

      return self.args

   ########################################################
   # CONFIGPARSER
   ########################################################

   def configuration_dxagent(self):
      """
      Parse configuration file
      """

      if self.args == None or self.args.config == None:
         raise IOSException("Arguments not found")

      self.config = configparser.ConfigParser()
      parsed      = self.config.read(self.args.config)
      if not parsed:
         print("Configuration file not found:", self.args.config)
         sys.exit(1)

      # set default configuration directory
      if "config_directory" not in self.config["virtualbox"]:
         default_config_dir = "/home/{}/.config".format(
                     self.config["virtualbox"]["vbox_user"])
         self.config["virtualbox"]["config_directory"] = default_config_dir

      # parse gNMI nodes
      self.gnmi_nodes = []
      gnmi_nodes = self.config["vpp"].get("gnmi_nodes")
      if gnmi_nodes:
         self.gnmi_nodes = [node.rstrip().lstrip() for node in gnmi_nodes.split(",")]
      
      return self.config

   ########################################################
   # LOGGING
   ########################################################

   def log(self):
      """
      load logging facility
      """
      if self.args == None:
         raise IOManagerException("Arguments not found")

      # create logger
      self.logger = logging.getLogger(self.child.__class__.__name__)
      self.logger.setLevel(logging.DEBUG)

      # log file handler
      fh = logging.FileHandler(self.args.log_file if self.args.log_file.startswith("/") else "./"+self.args.log_file)
      fh.setLevel(logging.DEBUG if self.args.verbose else logging.INFO)

      # add formatter to handlers
      formatter = logging.Formatter("%(asctime)s %(message)s",
                                    "%m-%d %H:%M:%S")
      fh.setFormatter(formatter)
      self.logger.addHandler(fh)

      # log functions
      self.debug    = self.logger.debug
      self.info     = self.logger.info
      self.warn     = self.logger.warn
      self.error    = self.logger.error
      self.critical = self.logger.critical

      return self.logger

class IOManagerException(Exception):
   """
   IOManagerException(Exception)
   """

   def __init__(self, value):
      self.value = value

   def __str__(self):
      return repr(self.value)



      
