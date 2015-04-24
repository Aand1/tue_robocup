#!/usr/bin/python
import rospy
import smach
import sys
import random
import math

import robot_smach_states as states
from robot_smach_states.util.designators import *
from robot_smach_states.util.startup import startup
from robot_skills.util import msg_constructors as msgs
from robot_smach_states.util.geometry_helpers import *

from robocup_knowledge import load_knowledge
challenge_knowledge = load_knowledge('challenge_open')
CABINET = challenge_knowledge.cabinet
TABLE1 = challenge_knowledge.table1
TABLE2 = challenge_knowledge.table2
OBJECT_SHELVES = challenge_knowledge.object_shelves


class AskItems(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=['succeeded','failed'])
        self.robot = robot

    def execute(self, userdata):
        self.robot.head.look_at_standing_person()

        self.robot.speech.speak("What can you tell me?")

        res = self.robot.ears.recognize(spec=challenge_knowledge.spec, choices=challenge_knowledge.choices, time_out = rospy.Duration(30))
        self.robot.head.cancel_goal()
        if not res:
            self.robot.speech.speak("My ears are not working properly, can i get a restart?.")
            return "failed"
        try:
            if res.result:
                # ToDo: make nice
                location = res.choices['location']
                if 'object3' in res.choices:
                    object1  = res.choices['object1']
                    object2  = res.choices['object2']
                    object3  = res.choices['object3']
                    self.robot.speech.speak("All right, so I can find {0}, {1} and {2} on the {3}".format(object1, object2, object3, location))
                elif 'object2' in res.choices:
                    object1  = res.choices['object1']
                    object2  = res.choices['object2']
                    self.robot.speech.speak("All right, so I can find {0} and {1} on the {2}".format(object1, object2, location))
                else:
                    object1  = res.choices['object1']
                    self.robot.speech.speak("All right, so I can find {0} on the {1}".format(object1, location))
            else:
                self.robot.speech.speak("Sorry, could you please repeat?")
                return "failed"
        except KeyError:
            print "[what_did_you_say] Received question is not in map. THIS SHOULD NEVER HAPPEN!"
            return "failed"

        return "succeeded"


class CiteItems(smach.State):
    """ Cite all items that have been found """
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=['succeeded','failed'])
        self.robot = robot

    def execute(self, userdata):

        entities = self.robot.ed.get_entities()
        if len(entities) == 0:
            rospy.logerr("Something went terribly wrong, I have not found any entities")
            self.robot.speech.speak("I must be blind")
            return 'failed'

        self.robot.speech.speak("I have found some items that I don't know")

        surface = self.robot.ed.get_entity(id=TABLE1)
        if surface:
            count = 0
            for entity in entities:
                if (onTopOff(entity, surface)):
                    count += 1
            self.robot.speech.speak("I have found {0} items on the {1}".format(count, TABLE1))

        count = 0
        for shelf in OBJECT_SHELVES:
            surface = self.robot.ed.get_entity(id=shelf)
            if surface:
                for entity in entities:
                    if (onTopOff(entity, surface)):
                        count += 1
        self.robot.speech.speak("I have found {0} items in the bookcase".format(count))

        surface = self.robot.ed.get_entity(id=TABLE2)
        if surface:
            count = 0
            for entity in entities:
                if (onTopOff(entity, surface)):
                    count += 1
        self.robot.speech.speak("I have found {0} items on the {1}".format(count, TABLE2))

        return 'succeeded'

class InspectShelves(smach.State):
    """ Inspect all object shelves """

    def __init__(self, robot, object_shelves):
        smach.State.__init__(self, outcomes=['succeeded','failed'])
        self.robot = robot
        self.object_shelves = object_shelves

    def execute(self, userdata):

        ''' Loop over shelves '''
        for shelf in self.object_shelves:

            rospy.loginfo("Shelf: {0}".format(shelf))

            ''' Get entities '''
            entity = self.robot.ed.get_entity(id=shelf, parse=False)

            if entity:

                ''' Extract center point '''
                cp = entity.center_point

                ''' Look at target '''
                self.robot.head.look_at_point(msgs.PointStamped(cp.x,cp.y,cp.z,"/map"))

                ''' Move spindle
                    Implemented only for AMIGO (hence the hardcoding)
                    Assume table height of 0.8 corresponds with spindle reset = 0.35 '''
                # def _send_goal(self, torso_pos, timeout=0.0, tolerance = []):
                height = min(0.4, max(0.1, cp.z-0.55))
                self.robot.torso._send_goal([height], timeout=5.0)

                ''' Sleep for 1 second '''
                rospy.sleep(1.0)

        return 'succeeded'

############################## explore state machine #####################
class ExporeScenario(smach.StateMachine):
    
    def __init__(self, robot):

        smach.StateMachine.__init__(self, outcomes=['done'])

        with self:
            smach.StateMachine.add('GOTO_TABLE1',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=TABLE1):"in_front_of"}, 
                                                          EdEntityDesignator(robot, id=TABLE1)),
                                transitions={   'arrived'           :   'LOOKAT_TABLE1',
                                                'unreachable'       :   'LOOKAT_TABLE1',
                                                'goal_not_defined'  :   'LOOKAT_TABLE1'})

            smach.StateMachine.add("LOOKAT_TABLE1",
                                     states.LookAtEntity(robot, EdEntityDesignator(robot, id=TABLE1), keep_following=True),
                                     transitions={  'succeeded'         :'RESET_HEAD_TABLE1'})

            smach.StateMachine.add( "RESET_HEAD_TABLE1",
                                    states.CancelHead(robot),
                                    transitions={   'done'              :'GOTO_CABINET'})

            smach.StateMachine.add('GOTO_CABINET',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=CABINET):"in_front_of"}, 
                                                          EdEntityDesignator(robot, id=CABINET)),
                                transitions={   'arrived'           :   'LOOKAT_CABINET',
                                                'unreachable'       :   'LOOKAT_CABINET',
                                                'goal_not_defined'  :   'LOOKAT_CABINET'})

            smach.StateMachine.add("LOOKAT_CABINET",
                                InspectShelves(robot, OBJECT_SHELVES),
                                transitions={'succeeded'                :'RESET_HEAD_CABINET',
                                             'failed'                   :'RESET_HEAD_CABINET'})

            smach.StateMachine.add( "RESET_HEAD_CABINET",
                                    states.CancelHead(robot),
                                    transitions={   'done'              :'GOTO_TABLE2'})

            smach.StateMachine.add('GOTO_TABLE2',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=TABLE2):"in_front_of"}, 
                                                          EdEntityDesignator(robot, id=TABLE2)),
                                transitions={   'arrived'           :   'LOOKAT_TABLE2',
                                                'unreachable'       :   'LOOKAT_TABLE2',
                                                'goal_not_defined'  :   'LOOKAT_TABLE2'})

            smach.StateMachine.add("LOOKAT_TABLE2",
                                     states.LookAtEntity(robot, EdEntityDesignator(robot, id=TABLE2), keep_following=True),
                                     transitions={  'succeeded'         :'RESET_HEAD_TABLE2'})

            smach.StateMachine.add( "RESET_HEAD_TABLE2",
                                    states.CancelHead(robot),
                                    transitions={   'done'              :'done'})

############################## state machine #############################
def setup_statemachine(robot):

    sm = smach.StateMachine(outcomes=['Done', 'Aborted'])

    with sm:
        
        # smach.StateMachine.add('SET_INITIAL_POSE',
        #                         states.SetInitialPose(robot, "open_challenge_start"),
        #                         transitions={   'done'          :'INITIALIZE',
        #                                         'preempted'     :'Aborted',
        #                                         'error'         :'Aborted'})

        # smach.StateMachine.add('INITIALIZE',
        #                         states.Initialize(robot),
        #                         transitions={   'initialized'   :'SAY_EXPLORE',
        #                                         'abort'         :'Aborted'})

        # smach.StateMachine.add('SAY_EXPLORE',
        #                         states.Say(robot, ["I do not have much knowledge about this room, I better go and explore it"], block=False),
        #                         transitions={   'spoken'        :'EXPLORE'})

        # smach.StateMachine.add('EXPLORE',
        #                         ExporeScenario(robot),
        #                         transitions={   'done'        :'GOTO_OPERATOR'})

        # smach.StateMachine.add('GOTO_OPERATOR',
        #                         states.NavigateToWaypoint(robot, EdEntityDesignator(robot, id="open_challenge_start"), radius = 0.75),
        #                         transitions={   'arrived'           :   'CITE_UNKNOWN_ITEMS',
        #                                         'unreachable'       :   'CITE_UNKNOWN_ITEMS',
        #                                         'goal_not_defined'  :   'CITE_UNKNOWN_ITEMS'})

        # smach.StateMachine.add('CITE_UNKNOWN_ITEMS',
        #                         CiteItems(robot),
        #                         transitions={   'succeeded'         :   'ASK_ITEMS1',
        #                                         'failed'            :   'ASK_ITEMS1'} )

        smach.StateMachine.add('ASK_ITEMS1',
                                AskItems(robot),
                                transitions={   'succeeded'         :   'Done',
                                                'failed'            :   'Done'} )

    return sm

############################## initializing program ######################
if __name__ == '__main__':
    rospy.init_node('open_challenge_exec')

    ''' Now, we will use AMIGO, but in the future we might change that '''
    robot_name = 'amigo'

    startup(setup_statemachine, robot_name=robot_name)