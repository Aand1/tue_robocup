#! /usr/bin/env python
import roslib; roslib.load_manifest('challenge_open_2014')
import rospy

import smach

from robot_skills.amigo import Amigo
import robot_smach_states as states

class FollowPerson(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["Success"])
        self.robot = robot

    def execute(self, userdata=None):
        return True

class OpenChallenge2014(smach.StateMachine):

    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=['We did it :)'])

        with self:

            smach.StateMachine.add('FOLLOW_PERSON',
                                    FollowPerson(robot),
                                    transitions={ "succes":"FOLLOW_PERSON" })

if __name__ == "__main__":
    rospy.init_node('open_challenge_2014')
    states.util.startup(OpenChallenge2014)
