#! /usr/bin/env python

from robot_smach_states.navigation import NavigateTo

from cb_planner_msgs_srvs.srv import *
from cb_planner_msgs_srvs.msg import *
from geometry_msgs.msg import *
import ed.msg

import rospy

# ----------------------------------------------------------------------------------------------------

class NavigateToSymbolic(NavigateTo):
    def __init__(self, robot, entity_designator_area_name_map, entity_lookat_designator):
        super(NavigateToSymbolic, self).__init__(robot)

        self.robot                 = robot
        
        #Check that the entity_designator_area_name_map's keys all resolve to EntityInfo's
        assert(all(entity_desig.resolve_type == ed.msg.EntityInfo for entity_desig in entity_designator_area_name_map.keys()))
        self.entity_designator_area_name_map     = entity_designator_area_name_map

        assert(entity_lookat_designator.resolve_type == ed.msg.EntityInfo) #Check that the entity_designator resolves to an Entity
        self.entity_lookat_designator = entity_lookat_designator

    def generateConstraint(self):
        ''' PositionConstraint '''
        entity_id_area_name_map = { k.resolve().id: v for k,v in self.entity_designator_area_name_map.iteritems() }
        pc = self.robot.ed.navigation.get_position_constraint(entity_id_area_name_map)

        ''' Orientation constraint is the entity itself...'''
        entity_lookat_id = self.entity_lookat_designator.resolve().id
        oc = OrientationConstraint(frame=entity_lookat_id)

        return pc, oc
