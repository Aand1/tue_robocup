#! /usr/bin/env python

from robot_smach_states.navigation import NavigateTo

from cb_planner_msgs_srvs.srv import *
from cb_planner_msgs_srvs.msg import *
from geometry_msgs.msg import *

import rospy


# ----------------------------------------------------------------------------------------------------
class NavigateToObserve(NavigateTo):
    def __init__(self, robot, designator, radius = .7):
        super(NavigateToObserve, self).__init__(robot)

        self.robot    = robot
        self.designator = designator
        self.radius   = radius

    def generateConstraint(self):
        entity_id = self.designator.resolve()
        e = self.robot.ed.get_entity(entity_id)

        if not e:
            rospy.logerr("No such entity")
            return None

        ch = e.convex_hull

        if len(ch) == 0:
            rospy.logerr("{0} has no convex hull so cannot NavigateToObserve there".format(entity_id))
            return None

        x = e.pose.position.x
        y = e.pose.position.y      

        ch.append(ch[0])

        pci = ""

        for i in xrange(len(ch) - 1):
            dx = ch[i+1].x - ch[i].x
            dy = ch[i+1].y - ch[i].y

            length = (dx * dx + dy * dy)**.5

            xs = ch[i].x + (dy/length)*self.radius
            ys = ch[i].y - (dx/length)*self.radius
            
            if i != 0:
                pci = pci + ' and '

            pci = pci + "-(x-%f)*%f+(y-%f)*%f > 0.0 "%(xs, dy, ys, dx)

        pc = PositionConstraint(constraint=pci, frame="/map")
        oc = OrientationConstraint(look_at=Point(x, y, 0.0), frame="/map")

        return pc, oc