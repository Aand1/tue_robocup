#! /usr/bin/env python
"""Scenario:
amigo in kamer
WM vind unknown blobs (servicecall: ed.srv.SimpleQuery.srv) op /ed/simple_query. query.type should be left empty.
blobs queryen via WM, krijgen IDs.
Vraag TF van ID op (= frame /<ID>), en beweeg naar punt in TF van blob. 
    Of use inverse reachability om in de buurt te komen
    Define a point 0,0,1 in the /<ID> frame, then transform that to /map-coordinates and call NavigateGeneric with lookat_point_3d=(that point in /map)

Als geen unknown objecten in WM, stukje draaien en weer checken of er unknowns zijn.

"""
import roslib; roslib.load_manifest('challenge_final')
import rospy, sys

import smach

from robot_skills.reasoner  import Conjunction, Compound, Sequence
from wire_fitter.srv import *
from ed.srv import SimpleQuery, SimpleQueryRequest
from tf import TransformListener
import robot_skills.util.msg_constructors as msgs

import robot_smach_states as states

class NavigateToUnknownBlob(smach.State):
    """Ask Ed (Environment Description) what the IDs of unkown blobs are. """
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=['arrived', 'unreachable', 'preempted', 'goal_not_defined'])
        self.robot = robot

        self.ed = rospy.ServiceProxy('/ed/simple_query', SimpleQuery)

        self.tf = TransformListener()

        self.visited_ids = []

    def execute(self, userdata=None):
        query = SimpleQueryRequest()

        unknown_ids = self.ed(query).ids

        import ipdb; ipdb.set_trace()
        #DEBUG (also run rosrun tf static_transform_publisher 5 0 0 0 0 0 /map /unknown_1 100)
        if not unknown_ids: unknown_ids = ["unknown_1"]
        #END DEBUG

        if unknown_ids:
            selected_id = unknown_ids[0]

            self.visited_ids += [selected_id]

            point_in_unknown_blob_tf = msgs.PointStamped(0,0,1, frame_id="/"+selected_id)
            map_pointstamped = self.tf.transformPoint("/map", point_in_unknown_blob_tf)
            map_point_tuple = (map_pointstamped.point.x, map_pointstamped.point.y, map_pointstamped.point.z)

            nav = states.NavigateGeneric(self.robot, lookat_point_3d=map_point_tuple, xy_dist_to_goal_tuple=(1.5, 0)) #Look from 1.5m distance to the unknown ubject
            return nav.execute()
        else:
            return "goal_not_defined"

class TurnDegrees(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, degrees, outcomes=["Done", "Aborted", "Failed"])
        self.robot = robot

    def execute(self, userdata=None):
        b = self.robot.base
        #b.force_drive(0.25, 0, 0, 3)
        b.force_drive(0, 0, 0.5, 6.28) #turn yourself around, 0.5*2PI rads = 1 pi rads = 180 degrees
        #b.force_drive(-0.25, 0, 0, 3)
        return "Done"

class FinalChallenge2014(smach.StateMachine):

    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=['Done','Failed', "Aborted"])
        self.robot = robot

        with self:
            smach.StateMachine.add('INITIALIZE',
                                states.Initialize(robot),
                                transitions={   'initialized':'DRIVE_TO_UNKNOWN_1',    ###### IN CASE NEXT STATE IS NOT "GO_TO_DOOR" SOMETHING IS SKIPPED
                                                'abort':'Aborted'})

            smach.StateMachine.add('DRIVE_TO_UNKNOWN_1',
                                    NavigateToUnknownBlob(robot),
                                    transitions={   'arrived':'WAIT_1', 
                                                    'preempted':'Failed', 
                                                    'unreachable':'Failed', 
                                                    'goal_not_defined':'Failed'})

            smach.StateMachine.add('WAIT_1', 
                                    states.Wait_time(robot, 3),
                                    transitions={   'waited':'DRIVE_TO_WAYPOINT_2', 
                                                    'preempted':'Aborted'})

            smach.StateMachine.add('DRIVE_TO_WAYPOINT_2',
                                    states.NavigateGeneric(robot, goal_name="final_waypoint_2"),
                                    transitions={   'arrived':'WAIT_2', 
                                                    'preempted':'Failed', 
                                                    'unreachable':'Failed', 
                                                    'goal_not_defined':'Failed'})

            smach.StateMachine.add('WAIT_2', 
                                    states.Wait_time(robot, 3),
                                    transitions={   'waited':'DRIVE_TO_WAYPOINT_3', 
                                                    'preempted':'Aborted'})

            smach.StateMachine.add('DRIVE_TO_WAYPOINT_3', 
                                    states.NavigateGeneric(robot, goal_name="final_waypoint_3"),
                                    transitions={   'arrived':'WAIT_3', 
                                                    'preempted':'Failed', 
                                                    'unreachable':'Failed', 
                                                    'goal_not_defined':'Failed'})

            smach.StateMachine.add('WAIT_3', 
                                    states.Wait_time(robot, 3),
                                    transitions={   'waited':'Done', 
                                                    'preempted':'Aborted'})


if __name__ == "__main__":
    rospy.init_node('exec_challenge_final_2014')

    states.util.startup(FinalChallenge2014)
