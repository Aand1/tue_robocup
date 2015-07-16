#!/usr/bin/python
import roslib;
import rospy
import smach
import sys

from robot_smach_states.util.designators import EdEntityDesignator
import robot_smach_states as states

from robocup_knowledge import load_knowledge
challenge_knowledge = load_knowledge('challenge_navigation')

TIME = 0
DURATION = 0

class TurnAndStoreTime(smach.State):
    def __init__(self, robot, radians):
        smach.State.__init__(self, outcomes=["turned"])
        self.robot = robot
        self.radians = radians

    def execute(self, userdata):

        vth = 1.0
        print "Turning %f radians with force drive" % radians
        self.robot.base.force_drive(0, 0, vth, radians / vth)

        TIME = rospy.Time.now()
        DURATION = self.duration

        return "turned"

def setup_statemachine(robot):

    sm = smach.StateMachine(outcomes=['Done','Aborted'])

    with sm:

        # Start challenge via StartChallengeRobust
        smach.StateMachine.add( "START_CHALLENGE_ROBUST",
                                states.StartChallengeRobust(robot, "initial_pose", use_entry_points = True),
                                transitions={   "Done"              :   "SAY_GOTO_TARGET1",
                                                "Aborted"           :   "SAY_GOTO_TARGET1",
                                                "Failed"            :   "SAY_GOTO_TARGET1"})

        smach.StateMachine.add( 'SAY_GOTO_TARGET1',
                                states.Say(robot, ["I will go to my first target now",
                                                    "I will now go to my first target",
                                                    "Lets go to my first target",
                                                    "Going to target 1"], block=False),
                                transitions={   'spoken'            :   'GOTO_TARGET1'})

        ######################################################################################################################################################
        #
        #                                                       TARGET 1
        #
        ######################################################################################################################################################

        smach.StateMachine.add('GOTO_TARGET1',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=challenge_knowledge.target1['near']) : "near", 
                                                           EdEntityDesignator(robot, id=challenge_knowledge.target1['in']) : "in" }, 
                                                          EdEntityDesignator(robot, id=challenge_knowledge.target1['lookat'])),
                                transitions={   'arrived'           :   'SAY_TARGET1_REACHED',
                                                'unreachable'       :   'RESET_ED_TARGET1',
                                                'goal_not_defined'  :   'RESET_ED_TARGET1'})

        smach.StateMachine.add( 'SAY_TARGET1_REACHED',
                                states.Say(robot, ["Reached target 1",
                                                    "I have arrived at target 1",
                                                    "I am now at target 1"], block=True),
                                transitions={   'spoken'            :   'SAY_GOTO_TARGET2'})

        smach.StateMachine.add('RESET_ED_TARGET1', 
                                states.ResetED(robot),
                                transitions={   'done'              :   'GOTO_TARGET1_BACKUP'})

        smach.StateMachine.add('GOTO_TARGET1_BACKUP',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=challenge_knowledge.target1['near']) : "near", 
                                                           EdEntityDesignator(robot, id=challenge_knowledge.target1['in']) : "in" }, 
                                                          EdEntityDesignator(robot, id=challenge_knowledge.target1['lookat'])),
                                transitions={   'arrived'           :   'SAY_TARGET1_REACHED',
                                                'unreachable'       :   'SAY_TARGET1_FAILED',
                                                'goal_not_defined'  :   'SAY_TARGET1_FAILED'})

        # Should we mention that we failed???
        smach.StateMachine.add( 'SAY_TARGET1_FAILED',
                                states.Say(robot, ["I am not able to reach target 1",
                                                    "I cannot reach target 1",
                                                    "Target 1 is unreachable"], block=True),
                                transitions={   'spoken'            :   'SAY_GOTO_TARGET2'})

        ######################################################################################################################################################
        #
        #                                                       TARGET 2
        #
        ######################################################################################################################################################

        smach.StateMachine.add( 'SAY_GOTO_TARGET2',
                                states.Say(robot, ["I will go to target 2 now",
                                                    "I will now go to target 2",
                                                    "Lets go to target 2",
                                                    "Going to target 2"], block=False),
                                transitions={   'spoken'            :   'GOTO_TARGET2'})

        smach.StateMachine.add('GOTO_TARGET2',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=challenge_knowledge.target2['near']) : "near", 
                                                           EdEntityDesignator(robot, id=challenge_knowledge.target2['in']) : "in" },
                                                          EdEntityDesignator(robot, id=challenge_knowledge.target2['lookat'])),
                                transitions={   'arrived'           :   'SAY_TARGET2_REACHED',
                                                'unreachable'       :   'RESET_ED_TARGET2',
                                                'goal_not_defined'  :   'RESET_ED_TARGET2'})

        smach.StateMachine.add( 'SAY_TARGET2_REACHED',
                                states.Say(robot, ["Reached target 2",
                                                    "I have arrived at target 2",
                                                    "I am now at target 2"], block=True),
                                transitions={   'spoken'            :   'SAY_GOTO_TARGET3'})

        smach.StateMachine.add('RESET_ED_TARGET2', 
                                states.ResetED(robot),
                                transitions={   'done'              :   'GOTO_TARGET2_BACKUP'})

        smach.StateMachine.add('GOTO_TARGET2_BACKUP',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=challenge_knowledge.target2['near']) : "near", 
                                                           EdEntityDesignator(robot, id=challenge_knowledge.target2['in']) : "in" },
                                                          EdEntityDesignator(robot, id=challenge_knowledge.target2['lookat'])),
                                transitions={   'arrived'           :   'SAY_TARGET2_REACHED',
                                                'unreachable'       :   'SAY_TARGET2_FAILED',
                                                'goal_not_defined'  :   'SAY_TARGET2_FAILED'})

        # Should we mention that we failed???
        smach.StateMachine.add( 'SAY_TARGET2_FAILED',
                                states.Say(robot, ["I am unable to reach target 2",
                                                    "I cannot reach target 2",
                                                    "Target 2 is unreachable"], block=True),
                                transitions={   'spoken'            :   'SAY_GOTO_TARGET3'})

        ######################################################################################################################################################
        #
        #                                                       TARGET 3
        #
        ######################################################################################################################################################


        smach.StateMachine.add( 'SAY_GOTO_TARGET3',
                                states.Say(robot, ["I will go to target 3 now",
                                                    "I will now go to target 3",
                                                    "Lets go to target 3",
                                                    "Going to target 3"], block=False),
                                transitions={   'spoken'            :   'GOTO_TARGET3'})

        smach.StateMachine.add('GOTO_TARGET3',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=challenge_knowledge.target3['near']) : "near", 
                                                           EdEntityDesignator(robot, id=challenge_knowledge.target3['in']) : "in" },
                                                          EdEntityDesignator(robot, id=challenge_knowledge.target3['lookat'])),
                                transitions={   'arrived'           :   'SAY_TARGET3_REACHED',
                                                'unreachable'       :   'RESET_ED_TARGET3',
                                                'goal_not_defined'  :   'RESET_ED_TARGET3'})

        smach.StateMachine.add( 'SAY_TARGET3_REACHED',
                                states.Say(robot, ["Reached target 3",
                                                    "I have arrived at target 3",
                                                    "I am now at target 3"], block=True),
                                transitions={   'spoken'            :   'TURN_AND_STORE_TIME'})

        smach.StateMachine.add('RESET_ED_TARGET3', 
                                states.ResetED(robot),
                                transitions={   'done'              :   'GOTO_TARGET3_BACKUP'})

        smach.StateMachine.add('GOTO_TARGET3_BACKUP',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=challenge_knowledge.target3['near']) : "near", 
                                                           EdEntityDesignator(robot, id=challenge_knowledge.target3['in']) : "in" },
                                                          EdEntityDesignator(robot, id=challenge_knowledge.target3['lookat'])),
                                transitions={   'arrived'           :   'SAY_TARGET3_REACHED',
                                                'unreachable'       :   'SAY_TARGET3_FAILED',
                                                'goal_not_defined'  :   'SAY_TARGET3_FAILED'})

        # Should we mention that we failed???
        smach.StateMachine.add( 'SAY_TARGET3_FAILED',
                                states.Say(robot, ["I am unable to reach target 3",
                                                    "I cannot reach target 3",
                                                    "Target 3 is unreachable"], block=True),
                                transitions={   'spoken'            :   'TURN_AND_STORE_TIME'})

        ######################################################################################################################################################
        #
        #                                                       Follow waiter
        #
        ######################################################################################################################################################

        smach.StateMachine.add( 'TURN_AND_STORE_TIME', TurnAndStoreTime(robot, 3.1415), transitions={ 'turned'   :   'CHECK_TIME'})

        smach.StateMachine.add( 'CHECK_TIME', checkTime(robot, 60), transitions={ 'ok' : 'FOLLOW_OPERATOR', 'time_passed' : 'SAY_RETURN_TARGET3'})

        # TODO :  (Make sure that we toggle the torso laser and disable the kinect)
        smach.StateMachine.add( 'FOLLOW_OPERATOR', states.FollowOperator(robot), transitions={ 'stopped' : 'CHECK_TIME', 'lost_operator' : 'CHECK_TIME'})

        ######################################################################################################################################################
        #
        #                                                       RETURN TARGET 3
        #
        ######################################################################################################################################################


        smach.StateMachine.add( 'SAY_RETURN_TARGET3',
                                states.Say(robot, ["I will go back to target 3 now",
                                                    "I will return to target 3",
                                                    "Lets go to target 3 again",
                                                    "Going to target 3, again"], block=False),
                                transitions={   'spoken'            :   'RETURN_TARGET3'})

        smach.StateMachine.add('RETURN_TARGET3',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=challenge_knowledge.target3['near']) : "near", 
                                                           EdEntityDesignator(robot, id=challenge_knowledge.target3['in']) : "in" },
                                                          EdEntityDesignator(robot, id=challenge_knowledge.target3['lookat'])),
                                transitions={   'arrived'           :   'SAY_TARGET3_RETURN_REACHED',
                                                'unreachable'       :   'RESET_ED_RETURN_TARGET3',
                                                'goal_not_defined'  :   'RESET_ED_RETURN_TARGET3'})

        smach.StateMachine.add( 'SAY_TARGET3_RETURN_REACHED',
                                states.Say(robot, ["Reached target 3 again",
                                                    "I have arrived at target 3 again",
                                                    "I am now at target 3 again"], block=True),
                                transitions={   'spoken'            :   'SAY_GOTO_EXIT'})

        smach.StateMachine.add('RESET_ED_RETURN_TARGET3', 
                                states.ResetED(robot),
                                transitions={   'done'              :   'GOTO_RETURN_TARGET3_BACKUP'})

        smach.StateMachine.add('GOTO_RETURN_TARGET3_BACKUP',
                                states.NavigateToSymbolic(robot, 
                                                          {EdEntityDesignator(robot, id=challenge_knowledge.target3['near']) : "near", 
                                                           EdEntityDesignator(robot, id=challenge_knowledge.target3['in']) : "in" },
                                                          EdEntityDesignator(robot, id=challenge_knowledge.target3['lookat'])),
                                transitions={   'arrived'           :   'SAY_TARGET3_RETURN_REACHED',
                                                'unreachable'       :   'SAY_RETURN_TARGET3_FAILED',
                                                'goal_not_defined'  :   'SAY_RETURN_TARGET3_FAILED'})

        # Should we mention that we failed???
        smach.StateMachine.add( 'SAY_RETURN_TARGET3_FAILED',
                                states.Say(robot, ["I am unable to reach target 3 again",
                                                    "I cannot reach target 3 again",
                                                    "Target 3 is unreachable"], block=True),
                                transitions={   'spoken'            :   'SAY_GOTO_EXIT'})

        ######################################################################################################################################################
        #
        #                                                       TARGET EXIT
        #
        ######################################################################################################################################################

        smach.StateMachine.add( 'SAY_GOTO_EXIT',
                                states.Say(robot, ["I will move to the exit now. See you guys later!",
                                                    "I am done with this challenge. Going to the exit"], block=False),
                                transitions={   'spoken'            :   'GO_TO_EXIT'})

        # Amigo goes to the exit (waypoint stated in knowledge base)
        smach.StateMachine.add('GO_TO_EXIT',
                                states.NavigateToWaypoint(robot, EdEntityDesignator(robot, id="exit_1_rips"), radius = 1.2),
                                transitions={   'arrived'           :   'AT_END',
                                                'unreachable'       :   'RESET_ED_EXIT',
                                                'goal_not_defined'  :   'RESET_ED_EXIT'})

        smach.StateMachine.add('RESET_ED_EXIT', 
                                states.ResetED(robot),
                                transitions={   'done'              :   'GO_TO_EXIT_BACKUP'})

        smach.StateMachine.add('GO_TO_EXIT_BACKUP',
                                states.NavigateToWaypoint(robot, EdEntityDesignator(robot, id="exit_1_rips"), radius = 1.2),
                                transitions={   'arrived'           :   'AT_END',
                                                'unreachable'       :   'RESET_ED_EXIT2',
                                                'goal_not_defined'  :   'RESET_ED_EXIT2'})

        smach.StateMachine.add('RESET_ED_EXIT2', 
                                states.ResetED(robot),
                                transitions={   'done'              :   'GO_TO_EXIT_BACKUP2'})

        smach.StateMachine.add('GO_TO_EXIT_BACKUP2',
                                states.NavigateToWaypoint(robot, EdEntityDesignator(robot, id="exit_2_rips"), radius = 0.5),
                                transitions={   'arrived'           :   'GO_TO_EXIT_BACKUP3',
                                                'unreachable'       :   'RESET_ED_EXIT3',
                                                'goal_not_defined'  :   'RESET_ED_EXIT3'})

        smach.StateMachine.add('RESET_ED_EXIT3', 
                                states.ResetED(robot),
                                transitions={   'done'              :   'GO_TO_EXIT_BACKUP3'})

        smach.StateMachine.add('GO_TO_EXIT_BACKUP3',
                                states.NavigateToWaypoint(robot, EdEntityDesignator(robot, id="exit_1_rips"), radius = 1.2),
                                transitions={   'arrived'           :   'AT_END',
                                                'unreachable'       :   'AT_END',
                                                'goal_not_defined'  :   'AT_END'})

        # Finally amigo will stop and says 'goodbye' to show that he's done.
        smach.StateMachine.add('AT_END',
                                states.Say(robot, "Goodbye"),
                                transitions={   'spoken'            :   'Done'})
    return sm


############################## initializing program ##############################
if __name__ == '__main__':
    rospy.init_node('navigation_exec')

    if len(sys.argv) > 1:
        robot_name = sys.argv[1]
    else:
        print "[CHALLENGE NAVIGATION] Please provide robot name as argument."
        exit(1)

    states.util.startup(setup_statemachine, robot_name=robot_name)
