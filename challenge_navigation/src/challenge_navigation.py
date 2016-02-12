#!/usr/bin/python
import roslib;
import rospy
import smach
import sys
import time

from cb_planner_msgs_srvs.msg import PositionConstraint

from robot_smach_states.util.designators import EdEntityDesignator, EntityByIdDesignator, analyse_designators
import robot_smach_states as states

from robocup_knowledge import load_knowledge
challenge_knowledge = load_knowledge('challenge_navigation')

print "=============================================="
print "==           CHALLENGE NAVIGATION           =="
print "=============================================="

class Turn(smach.State):
    def __init__(self, robot, radians):
        smach.State.__init__(self, outcomes=["turned"])
        self.robot = robot
        self.radians = radians

    def execute(self, userdata):
        self.robot.head.close()

        vth = 1.0
        print "Turning %f radians with force drive" % self.radians
        self.robot.base.force_drive(0, 0, vth, self.radians / vth)

        return "turned"

class DetermineObject(smach.State):
    def __init__(self, robot, entity_id):
        smach.State.__init__(self, outcomes=["done", "timeout"])
        self.robot = robot

        try:
            pose = robot.ed.get_entity(id=entity_id).pose
        except Exception as e:
            rospy.logerr(e)
            sys.exit(1)

        self.pc = PositionConstraint(frame="/map", constraint="(x-%f)^2+(y-%f)^2 < 0.05" % (pose.position.x, pose.position.y))

    def execute(self, userdata):

        self.robot.speech.speak("Waypoint 2 is occupied, what do we have here", block=False)

        # Make sure you look where you would expect the person to stand
        self.robot.head.look_at_standing_person()
        self.robot.head.wait_for_motion_done()

        res_segm = self.robot.ed.update_kinect(background_padding = 0.3)
        ids = res_segm.new_ids + res_segm.updated_ids

        # Try to determine the types of the entities just segmented
        res_classify = self.robot.ed.classify(ids)

	rospy.loginfo("Classification result: %s" % res_classify)

        # Get the ids of all humans
        human_ids = [e.id for e in res_classify if e.type == "human"]

        # Stop looking at person
        self.robot.head.cancel_goal()

        if human_ids:
            self.robot.speech.speak("Hi there Human, please step aside")
        else:
            self.robot.speech.speak("Can somebody please remove the object that is blocking waypoint 2?")

        self.robot.ed.reset()

        start_time = time.time()
        while not self.robot.base.global_planner.getPlan(self.pc):
            if time.time() - start_time > 30:
                return "timeout"
            time.sleep(1)

        self.robot.speech.speak("Thank you")

        time.sleep(3)

        return "done"

def setup_statemachine(robot):

    sm = smach.StateMachine(outcomes=['Done','Aborted'])

    with sm:

        # Start challenge via StartChallengeRobust
        smach.StateMachine.add( "START_CHALLENGE_ROBUST",
                                states.StartChallengeRobust(robot, challenge_knowledge.starting_point, use_entry_points = True),
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
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target1), challenge_knowledge.target1_radius1),
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
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target1), challenge_knowledge.target1_radius2),
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
                                transitions={   'spoken'            :   'GOTO_TARGET2_PRE'})

        smach.StateMachine.add('GOTO_TARGET2_PRE',
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target2), challenge_knowledge.target2_radius1),
                                transitions={   'arrived'           :   'GOTO_TARGET2',
                                                'unreachable'       :   'GOTO_TARGET2',
                                                'goal_not_defined'  :   'GOTO_TARGET2'})

        smach.StateMachine.add('GOTO_TARGET2',
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target2), challenge_knowledge.target2_radius2),
                                transitions={   'arrived'           :   'SAY_TARGET2_REACHED',
                                                'unreachable'       :   'DETERMINE_OBJECT',
                                                'goal_not_defined'  :   'DETERMINE_OBJECT'})

        smach.StateMachine.add('DETERMINE_OBJECT',
                                DetermineObject(robot, challenge_knowledge.target2),
                                transitions={   'done'           :   'GOTO_TARGET2_AGAIN',
                                                'timeout'        :   'GOTO_TARGET2_AGAIN'})

        smach.StateMachine.add('GOTO_TARGET2_AGAIN',
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target2), challenge_knowledge.target2_radius2),
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
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target2), challenge_knowledge.target2_radius3),
                                transitions={   'arrived'           :   'SAY_TARGET2_REACHED',
                                                'unreachable'       :   'SAY_TARGET2_FAILED',
                                                'goal_not_defined'  :   'SAY_TARGET2_FAILED'})

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
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target3), challenge_knowledge.target3_radius1),
                                transitions={   'arrived'           :   'SAY_TARGET3_REACHED',
                                                'unreachable'       :   'RESET_ED_TARGET3',
                                                'goal_not_defined'  :   'RESET_ED_TARGET3'})

        smach.StateMachine.add( 'SAY_TARGET3_REACHED',
                                states.Say(robot, ["Reached target 3",
                                                    "I have arrived at target 3",
                                                    "I am now at target 3"], block=True),
                                transitions={   'spoken'            :   'TURN'})

        smach.StateMachine.add('RESET_ED_TARGET3',
                                states.ResetED(robot),
                                transitions={   'done'              :   'GOTO_TARGET3_BACKUP'})

        smach.StateMachine.add('GOTO_TARGET3_BACKUP',
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target3), challenge_knowledge.target3_radius2),
                                transitions={   'arrived'           :   'SAY_TARGET3_REACHED',
                                                'unreachable'       :   'SAY_TARGET3_FAILED',
                                                'goal_not_defined'  :   'SAY_TARGET3_FAILED'})

        # Should we mention that we failed???
        smach.StateMachine.add( 'SAY_TARGET3_FAILED',
                                states.Say(robot, ["I am unable to reach target 3",
                                                    "I cannot reach target 3",
                                                    "Target 3 is unreachable"], block=True),
                                transitions={   'spoken'            :   'TURN'})

        ######################################################################################################################################################
        #
        #                                                       Follow waiter
        #
        ######################################################################################################################################################


        smach.StateMachine.add( 'TURN', Turn(robot, challenge_knowledge.rotation), transitions={ 'turned'   :   'SAY_STAND_IN_FRONT'})
        smach.StateMachine.add( 'SAY_STAND_IN_FRONT', states.Say(robot, "Please stand in front of me!", block=True), transitions={ 'spoken' : 'FOLLOW_OPERATOR'})

        smach.StateMachine.add( 'FOLLOW_OPERATOR', states.FollowOperator(robot), transitions={ 'no_operator':'SAY_SHOULD_I_RETURN', 'stopped' : 'SAY_SHOULD_I_RETURN', 'lost_operator' : 'SAY_SHOULD_I_RETURN'})
        smach.StateMachine.add( 'SAY_SHOULD_I_RETURN', states.Say(robot, "Should I return to target 3?"), transitions={ 'spoken' : 'HEAR_SHOULD_I_RETURN'})
        smach.StateMachine.add( 'HEAR_SHOULD_I_RETURN', states.HearOptions(robot, ["yes", "no"]), transitions={ 'no_result' : 'SAY_STAND_IN_FRONT', "yes" : "SAY_RETURN_TARGET3", "no" : "SAY_STAND_IN_FRONT"})

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
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target4), challenge_knowledge.target4_radius1),
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
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.target4), challenge_knowledge.target4_radius2),
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
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.exit1), radius = 0.6),
                                transitions={   'arrived'           :   'AT_END',
                                                'unreachable'       :   'RESET_ED_EXIT',
                                                'goal_not_defined'  :   'RESET_ED_EXIT'})

        smach.StateMachine.add('RESET_ED_EXIT',
                                states.ResetED(robot),
                                transitions={   'done'              :   'GO_TO_EXIT_BACKUP'})

        smach.StateMachine.add('GO_TO_EXIT_BACKUP',
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.exit2), radius = 0.6),
                                transitions={   'arrived'           :   'AT_END',
                                                'unreachable'       :   'RESET_ED_EXIT2',
                                                'goal_not_defined'  :   'RESET_ED_EXIT2'})

        smach.StateMachine.add('RESET_ED_EXIT2',
                                states.ResetED(robot),
                                transitions={   'done'              :   'GO_TO_EXIT_BACKUP2'})

        smach.StateMachine.add('GO_TO_EXIT_BACKUP2',
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.exit3), radius = 0.6),
                                transitions={   'arrived'           :   'GO_TO_EXIT_BACKUP3',
                                                'unreachable'       :   'RESET_ED_EXIT3',
                                                'goal_not_defined'  :   'RESET_ED_EXIT3'})

        smach.StateMachine.add('RESET_ED_EXIT3',
                                states.ResetED(robot),
                                transitions={   'done'              :   'GO_TO_EXIT_BACKUP3'})

        smach.StateMachine.add('GO_TO_EXIT_BACKUP3',
                                states.NavigateToWaypoint(robot, EntityByIdDesignator(robot, id=challenge_knowledge.exit4), radius = 0.6),
                                transitions={   'arrived'           :   'AT_END',
                                                'unreachable'       :   'AT_END',
                                                'goal_not_defined'  :   'AT_END'})

        smach.StateMachine.add('AT_END',
                                states.Say(robot, "Goodbye"),
                                transitions={   'spoken'            :   'Done'})



    analyse_designators(sm, "navigation")
    return sm


############################## initializing program ##############################
if __name__ == '__main__':
    rospy.init_node('navigation_exec')

    states.util.startup(setup_statemachine, challenge_name="navigation")
