"""
ping.py
    Ping Wrapper
@author: Thomas Carlisi
"""

import shlex
import threading
from atomicwrites import atomic_write
from subprocess import Popen, PIPE
from datetime import datetime

class PingWrapper():
    """
    Wrap the system ping program
    """

    def __init__(self, ping_config, output_dir):
        self.address_list = ping_config["address_list"]  
        self.count = ping_config["count"]
        self.interval = ping_config["ping_interval"]
        self.data_size = ping_config["data_size"]
        self.timeout = ping_config["timeout"]
        self.exit_code = 0
        self.output_dir = output_dir
        self.param_list = []
        self._init_params()
    
    def _init_params(self):
        
        # count
        if not self.count:
            self.count = "1"
        self.param_list.append("-c" + self.count)

        #data size
        if self.data_size:
            self.param_list.append("-b" + self.data_size)
        
        #timeout
        if self.timeout:
            self.param_list.append("-t" + self.timeout)

        #ping interval
        if self.interval:
            self.param_list.append("-p" + self.interval)

        # addresses to ping
        self.address_list = self.address_list.split(",")


    def ping(self):
        """
        start a ping using the config (dxagent.ini) options
        """

        cmd = ["fping"] + self.param_list + self.address_list

        # Execution of ping
        process = Popen(cmd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        new_exit_code = process.wait() # success -> 0 / no reply -> 1 / other error -> 2

        # Analalyze output
        stdout = stdout.decode("utf-8")
        stderr = stderr.decode("utf-8")

        # new error
        if(self.exit_code != 2 and new_exit_code == 2):
            for line in stderr.splitlines():
                if not line:
                    break
                print("error icmp ping : ", line)
                # remove problematic addresses
                self.address_list.remove(line.split(":")[0].strip())
        
        self.exit_code = new_exit_code

        self._print_output_dir(stdout, stderr)
    
    def _print_output_dir(self, stdout, stderr):

        with atomic_write(self.output_dir + "/" + "ping_output.txt", overwrite=True) as f:
            f.write(datetime.now().strftime("%m/%d/%Y-%H:%M:%S\n"))
            f.write(stderr)
