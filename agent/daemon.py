"""
daemon.py

    Daemon

@author: K.Edeline
"""

import sys
import os
import pwd
import time
from contextlib import contextmanager

from signal import SIGTERM

class Daemon():
   """
   Spawn a double-forked daemon
   Subclass Daemon class and override the run() method.

   """
   def __init__(self, pidfile='/var/run/dxagent.pid', stdin='/dev/null', 
                     stdout='/var/log/dxagent.log', 
                     stderr='/var/log/dxagent.log',
                     name='dxagent',
                     input_rate=1):
      self.stdin      = stdin
      self.stdout     = stdout
      self.stderr     = stderr
      self.pidfile    = pidfile
      self.input_rate = input_rate
      self.name       = name
      self.puid       = 0
      self.cwd        = os.getcwd()
      self.username   = os.getlogin()
      self._dropped   = False

   def _fork(self):
      """
      Fork, exit parent and returns pid
      """
      try:
         pid = os.fork()
         if pid > 0:
            # Exit first parent.
            sys.exit(0)
      except OSError as e:
         message = "fork failed: {}\n".format(e)
         sys.stderr.write(message)
         sys.exit(1)

      return pid
 
   def daemonize(self):
      """
      Daemonize, do double-fork magic.
      """
      pid = self._fork()

      # Decouple from parent environment.
      os.chdir("/")
      os.setsid()
      os.umask(0)

      # Do the double fork, do the, do the double fork
      pid = self._fork()

      # Write pidfile.
      pid = str(os.getpid())
      with open(self.pidfile,'w+') as f:
         f.write("{}\n".format(pid))

      # Redirects stdio
      self.redirect_fds()   

   def delpid(self):
      """
      don't call this

      """
      self.root()
      os.remove(self.pidfile)

   @contextmanager
   def drop(self, user=None):
      """
      context manager that drops privileges to user's

      """
      if not user:
         user = self.username
      try: 
         self.drop_privileges(user)
         yield self
      finally:
         self.root()

   @contextmanager
   def switch_config_home(self, dir):
      saved = None
      try:
         if "XDG_CONFIG_HOME" in os.environ:
            saved = os.environ["XDG_CONFIG_HOME"]
         os.environ["XDG_CONFIG_HOME"]=dir
         yield self
      finally:
         if saved:
            os.environ["XDG_CONFIG_HOME"]=saved

   def drop_privileges(self, user):
       """
       drop effective uid to user's

       """
       uid = os.getuid()
       if uid != 0:
           # We're not root so, osef
           return
       self.puid = uid

       # Get the uid/gid from the name
       pw = pwd.getpwnam(user)

       # Remove group privileges
       #os.setgroups([])

       # Try setting the new uid
       os.setresuid(pw.pw_uid, pw.pw_uid, uid)

       # Ensure a reasonable umask
       old_umask = os.umask(0o022)
       self._dropped=True

   def root(self):
      """
      Grant root rights, if possible.
      """
      if self._dropped:
         os.setresuid(self.puid, self.puid, self.puid)
         self._dropped=False
 
   def start(self):
      """
      Start daemon.
      """
      # Check pidfile to see if the daemon already runs.
      pid = self._open_pid()
      if pid and not self.status(): # catch nopid exception
         message = "{} already running\n".format(self.name)
         sys.stderr.write(message)
         return 1
 
      # Start daemon.
      self.daemonize()
      self.run()

      return 0
 
   def redirect_fds(self):
      """
      Redirect standard file descriptors.
      """
      sys.stdout.flush()
      sys.stderr.flush()
      si = open(self.stdin, 'r')
      so = open(self.stdout, 'a+')
      se = open(self.stderr, 'a+')
      os.dup2(si.fileno(), sys.stdin.fileno())
      os.dup2(so.fileno(), sys.stdout.fileno())
      os.dup2(se.fileno(), sys.stderr.fileno())

   def _open_pid(self, exit_on_error=False):
      """
      open the pid file and return the pid number
      @return:
         pid the pid number
      """
      try:
         with open(self.pidfile,'r') as pf:
            pid = int(pf.read().strip())
      except IOError as e:
         if exit_on_error:
            message = "{} is not running\n".format(self.name)
            sys.stderr.write(message)
            sys.exit(1)      
         else:
            pid = None  

      return pid

   def print_status(self):
      """
      get status of daemon and print it to stderr

      """
      status = self.status()
      if status == 0:
         message = "{} is running\n".format(self.name)
         sys.stderr.write(message)
      elif status == 1:
         message = "{} is not running\n".format(self.name)
         sys.stderr.write(message)
      return 0

   def status(self):
      """
      Get status of daemon.

      @return 0 if running
              1 if not running

      """
      pid = self._open_pid(exit_on_error=True)

      try:
         with open("/proc/{}/status".format(pid), 'r') as procfile:
            pass
         return 0
      except IOError:
         pass

      return 1 

   def stop(self):
      """
      Stop the daemon.
      """
      pid = self._open_pid(exit_on_error=True)

      # Try killing daemon process.
      try:
         os.kill(pid, SIGTERM)
         time.sleep(1)
      except OSError as e:
         sys.stdout.write(str(e)+"\n")
         return 1

      return 0
 
   def restart(self):
      """
      Restart daemon.
      """
      if self.stop() > 0:
         return 1
      # gently wait for process to exit
      time.sleep(self.input_rate)
      if self.start() > 0:
         return 1
 
   def run(self):
      """
      Example:

      class MyDaemon(Daemon):
         def run(self):
             while True:
                 time.sleep(1)
      """
      pass

class DaemonException(Exception):
   """
   DaemonException(Exception)
   """

   def __init__(self, value):
      self.value = value

   def __str__(self):
      return repr(self.value)

