"""
ios.py

   Handle arguments, configuration file 

@author: K.Edeline
"""

import sys
import argparse, configparser, logging


class IOManager():
   """

   extend me

   """
   def __init__(self, child):
   
      self.child    = child

      self.args   = None
      self.config = None
      self.logger = None

   def load_ios(self):
      """
      load_ios
      
      Load all ios
      """
      self.arguments()
      self.configuration()
      self.log()

   ########################################################
   # ARGPARSE
   ########################################################

   def arguments(self):
      """
      Parse arguments

         Used mostly to provide the location of the config file.
      """

      parser = argparse.ArgumentParser(description='Diagnostic Agent')

      parser.add_argument('-l' , '--log-file', type=str, default="dxagent.log",
                         help='log file location (default: dxagent.log)')

      parser.add_argument('-c' , '--config', type=str, default="./dxagent.ini",
                         help='configuration file location')
      parser.add_argument('-d' , '--debug', action='store_true',
                         help='increase output level') 
      parser.add_argument('-v' , '--verbose', action='store_true',
                         help='increase output level') 

      self.args = parser.parse_args()

      return self.args

   ########################################################
   # CONFIGPARSER
   ########################################################

   def configuration(self):
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
      if self.config == None:
         raise IOManagerException("Configuration not found")

      # create logger
      self.logger = logging.getLogger(self.child.__class__.__name__)
      self.logger.setLevel(logging.DEBUG)

      # log file handler
      fh = logging.FileHandler(self.config["core"]["logging_dir"]+"/"+self.args.log_file)
      fh.setLevel(logging.DEBUG if self.args.debug else logging.INFO)

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



      
