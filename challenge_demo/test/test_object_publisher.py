#! /usr/bin/env python

from std_msgs.msg import String
import rospy
import rosnode
import random

pub = rospy.Publisher('/detected_objects', String)

rospy.init_node('node_alive_server')

objects = ['coke','sprite','fanta','peanut_butter','milk','yoghurt','dr_pepper','pills','chewing_gum','noodles','bla','rofl']

while not rospy.is_shutdown():
    msg = String()
    sample_size = random.randint(1,len(objects))
    msg.data = "|".join(random.sample(objects,sample_size))
    pub.publish(msg)
    rospy.sleep(0.2)

