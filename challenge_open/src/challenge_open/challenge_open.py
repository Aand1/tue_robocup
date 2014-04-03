#! /usr/bin/env python
import roslib; roslib.load_manifest('challenge_open')
import rospy, sys

import smach

from robot_skills.reasoner  import Conjunction, Compound

from math import cos, sin
from geometry_msgs.msg import *

from robot_skills.amigo import Amigo
import robot_smach_states as states

from speech_interpreter.srv import AskUser

class TurnAround(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["Done", "Aborted", "Failed"])
        self.robot = robot

    def execute(self, userdata=None):
        b = self.robot.base
        #b.force_drive(0.25, 0, 0, 3)
        b.force_drive(0, 0, 0.5, 6.28) #turn yourself around, 0.5*2PI rads = 1 pi rads = 180 degrees
        #b.force_drive(-0.25, 0, 0, 3)
        return "Done"

class AskOpenChallenge(smach.State):

    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["location_selected", "all_visited"])
        self.robot = robot
        self.ask_user_service = rospy.ServiceProxy('interpreter/ask_user', AskUser)

        self.locations = ["bar","kitchen_block","table"]

    def execute(self, userdata=None):

        self.robot.head.look_up()
        
        try:
            self.response = self.ask_user_service("challenge_open_2014", 4 , rospy.Duration(18))  # This means that within 4 tries and within 60 seconds an answer is received. 
            
            for x in range(0,len(self.response.keys)):
                if self.response.keys[x] == "answer":
                    response_answer = self.response.values[x]

            if response_answer == "no_answer" or response_answer == "wrong_answer" or response_answer == "":
                if self.locations:
                    target = self.locations.pop(0) #Get the first item from the list
                    self.robot.speech.speak("I was not able to understand you but I'll drive to %s."%target)
                else:
                    return "all_visited"
            else:
                target = response_answer

        except Exception, e:
            rospy.logerr(e)
            target = "table"
            self.robot.speech.speak("There is something wrong with my ears, I will go to %s"%target)

        self.robot.base2.pc.constraint = 'x^2 + y^2 < 1.2^2'
        self.robot.base2.pc.frame      = target

        self.robot.base2.oc.look_at    = Point()
        self.robot.base2.oc.frame      = target

        return "location_selected"


#######################################################################################################################################################################################################

class OpenChallenge2014(smach.StateMachine):

    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=['success','aborted'])

        with self:

            smach.StateMachine.add( "TURN_AROUND",
                                    TurnAround(robot),
                                    transitions={   "Done"      :"ASK_OPENCHALLENGE", 
                                                    "Aborted"   :"ASK_OPENCHALLENGE", 
                                                    "Failed"    :"ASK_OPENCHALLENGE"})

            smach.StateMachine.add("ASK_OPENCHALLENGE",
                                AskOpenChallenge(robot),
                                transitions={'location_selected':   'INITIALIZE',
                                             'all_visited':         'success'})

            smach.StateMachine.add("INITIALIZE",
                                states.ResetArmsSpindleHead(robot),
                                transitions={'done'             :   'NAVIGATE_TO_TARGET'})

            smach.StateMachine.add("NAVIGATE_TO_TARGET",
                                states.NavigateWithConstraints(robot),
                                transitions={'arrived'          :   'SAY_ARRIVED',
                                             'unreachable'      :   'SAY_UNREACHABLE',
                                             'goal_not_defined' :   'SAY_UNDEFINED'})              

            smach.StateMachine.add( "SAY_ARRIVED",
                                    states.Say(robot, ["Hey, I reached my goal."]),
                                    transitions={"spoken":"TURN_AROUND"})          
          
            smach.StateMachine.add( "SAY_UNREACHABLE",
                                    states.Say(robot, ["I can't reach the goal you asked me to go to"]),
                                    transitions={"spoken":"TURN_AROUND"})          

            smach.StateMachine.add( "SAY_UNDEFINED",
                                    states.Say(robot, ["I can't reach the location you asked me to go to."]),
                                    transitions={"spoken":"TURN_AROUND"})


if __name__ == "__main__":
    rospy.init_node('open_challenge_2014')
    states.util.startup(OpenChallenge2014)
