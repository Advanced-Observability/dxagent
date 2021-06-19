
"""
ping_scheduler.py
    Ping scheduler
@author: Thomas Carlisi
"""

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from .ping_wrapper import PingWrapper

class PingScheduler():
    """
    Scheduler for launching ping to all indicated addresses at a fixed frequency
    """

    def __init__(self, ping_config, output_dir):
        self.ping_config = ping_config                                      # ping configuration
        self.output_dir = output_dir                                        # output directory
        self.interval_scheduler = int(ping_config["interval_scheduler"])    # interval of ping scheduler
        self.scheduler = BackgroundScheduler()                              # scheduler

    def start_ping_scheduler(self):
        """
        Start the scheduling of pings
        """
        self.scheduler.start()
        pinger = PingWrapper(self.ping_config, self.output_dir)
        self.scheduler.add_job(pinger.ping, trigger="interval", 
            seconds=self.interval_scheduler, replace_existing=True,
            max_instances=2, 
            next_run_time=datetime.now())

    def shutdown_ping_scheduler(self):
        """
        Shutdown the scheduler
        """
        self.scheduler.shutdown(wait=True)
    