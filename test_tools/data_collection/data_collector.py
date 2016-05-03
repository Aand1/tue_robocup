#!/usr/bin/python

"""Data collector

Usage:
  data_collector.py <name> <start_time> <end_time> [--go]
  data_collector.py (-h | --help)
  data_collector.py --version

Examples:
  data_collector.py reo2016_challenge_navigation 15:30 15:40
  data_collector.py rwc_2016_challenge_restaurant 15:30 now
  data_collector.py rwc_2016_challenge_speech_recognition 15:30 2015-03-02 17:40 2015-04-08

Options:
  -h --help     Show this screen.

"""
from docopt import docopt
from datetime import datetime
import sys
import os
from glob import glob
import shutil
from util import parse_start_end, get_modification_date

GLOBS = {
    "faces": ["/tmp/faces/*.jpg"],
    "speech": ["/tmp/*.wav"],
    "mapping_data_and_plans": ["/tmp/*.bag"],
    "objects" : [os.path.expanduser("~/ed/kinect/*/*.*"), os.path.expanduser("~/ed/kinect/*/*/*.*")]
}

if __name__ == '__main__':
    now = datetime.now()

    arguments = docopt(__doc__, version='Data Collector 1.0')

    start, end = parse_start_end(arguments, now)
    name = arguments["<name>"]

    print "I am going to collect data for '%s'" % name
    print "Datetime: [%s <--> %s]" % (start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"))

    if not arguments["--go"]:
        raw_input("Press Enter to continue...")

    # Create dir if exist
    if not os.path.exists(name):
        os.makedirs(name)

    # Copy files
    for cat_name, glob_entries in GLOBS.iteritems():
        dir_name = name + "/" + cat_name
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)

        for glob_entry in glob_entries:
            for file_name in glob(glob_entry):
                # Check if modification date is between bounds (or unknown)
                mod_date = get_modification_date(file_name)
                if not mod_date or start < mod_date < end:
                    print "Writing file '%s' to '%s'" % (file_name, dir_name)
                    shutil.copy(file_name, dir_name)
