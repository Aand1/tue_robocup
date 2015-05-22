#! /usr/bin/env python

from robot_smach_states.navigation import NavigateTo

from cb_planner_msgs_srvs.srv import *
from cb_planner_msgs_srvs.msg import *
from geometry_msgs.msg import *

from robot_smach_states.util.designators import check_resolve_type
import ed.msg
from robot_skills.util import transformations as tf

import rospy

# ----------------------------------------------------------------------------------------------------

class NavigateToWaypoint(NavigateTo):
    def __init__(self, robot, waypoint_designator, radius = 0.15):
        """@param waypoint_designator resolves to a waypoint stored in ED"""
        super(NavigateToWaypoint, self).__init__(robot)

        self.robot               = robot

        check_resolve_type(waypoint_designator, ed.msg.EntityInfo) #Check that the waypoint_designator resolves to an Entity
        self.waypoint_designator = waypoint_designator
        self.radius              = radius

    def generateConstraint(self):
        e = self.waypoint_designator.resolve()

        if not e:
            rospy.logerr("No such entity")
            return None

        try:
            pose = e.data["pose"]
            x = pose["x"]
            y = pose["y"]
            rz = e.data["pose"]["rz"]
        except:
            try:
                x = e.pose.position.x
                y = e.pose.position.y
                rz = tf.euler_z_from_quaternion(e.pose.orientation)
            except:
                return None

        pc = PositionConstraint(constraint="(x-%f)^2+(y-%f)^2 < %f^2"%(x, y, self.radius), frame="/map")
        oc = OrientationConstraint(look_at=Point(x+10, y, 0.0), angle_offset=rz, frame="/map")

        return pc, oc
