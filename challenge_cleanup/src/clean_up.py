#! /usr/bin/env python
import roslib; roslib.load_manifest('challenge_cleanup')
import rospy

import smach

from robot_skills.amigo import Amigo
import robot_smach_states as states

from robot_skills.reasoner  import Conjunction, Compound
from robot_skills.arms import State as ArmState
from robot_smach_states.util.startup import startup

from speech_interpreter.srv import AskUser

grasp_arm = "left"
#grasp_arm = "right"

##########################################
############## What to run: ##############
##########################################
# CHECK the README!

# niet op bed pakken
#

class Ask_cleanup(smach.State):
    def __init__(self, robot, tracking=True, rate=2):
        smach.State.__init__(self, outcomes=["done"])

        self.robot = robot
        self.ask_user_service_get_cleanup = rospy.ServiceProxy('interpreter/ask_user', AskUser)

    def execute(self, userdata):
        self.robot.head.look_up()
                
        room = "living_room"
        try:
            self.response = self.ask_user_service_get_cleanup("room_cleanup", 4 , rospy.Duration(60))  # This means that within 4 tries and within 60 seconds an answer is received. 
            
            for x in range(0,len(self.response.keys)):
                if self.response.keys[x] == "answer":
                    response_answer = self.response.values[x]

            if response_answer == "no_answer" or response_answer == "wrong_answer":
                self.robot.speech.speak("I was not able to understand you but I'll clean the living room, humans always tend to make a mess of that.")
                 # ToDo: don't hardcode this!                
                room = "living_room"
            else:

                room_string = str(response_answer).replace("clean_up_the_", "")
                room = room_string
                rospy.loginfo("Room to clean is '{0}'".format(room))

        except Exception, e:
            rospy.logerr("Could not get_cleanup_service: {0}. Defaulting to {1}".format(e, room))
            self.robot.speech.speak("There is something wrong with my ears, I will cleanup the {1}, humans always tend to make a mess of that".format(e, room))

        self.robot.reasoner.query(Compound("assertz", Compound("goal", Compound("clean_up", room))))
            
        return "done"

class StupidHumanDropoff(smach.StateMachine):
    def __init__(self, arm, robot, dropoff_query):
        smach.StateMachine.__init__(self, outcomes=['succeeded','failed', 'target_lost'])

        with self:
            smach.StateMachine.add( "DROPOFF_OBJECT",
                                    states.PrepareOrientation(arm, robot, dropoff_query),
                                    transitions={   'orientation_succeeded':'ASK_TAKE_FROM_HAND',
                                                    'orientation_failed':'ASK_TAKE_FROM_HAND',
                                                    'abort':'failed',
                                                    'target_lost':'target_lost'})

            smach.StateMachine.add("ASK_TAKE_FROM_HAND", 
                                    states.Say(robot, ["Please take this from my hand, I'm not confident that I can place to object safely"]),
                                    transitions={   'spoken':'HANDOVER_TO_HUMAN_1'})

            smach.StateMachine.add("HANDOVER_TO_HUMAN_1", 
                                    states.Say(robot, [ "Be careful, I will open my gripper now"]),
                                    transitions={   'spoken':'OPEN_GRIPPER_HANDOVER'})

            smach.StateMachine.add('OPEN_GRIPPER_HANDOVER', 
                                    states.SetGripper(robot, arm, gripperstate=ArmState.OPEN),
                                    transitions={'succeeded'    :   'SAY_PLACE_INSTRUCTION',
                                                 'failed'       :   'SAY_PLACE_INSTRUCTION'})

            def generate_object_sentence(*args,**kwargs):
                try:
                    answers = robot.reasoner.query(dropoff_query)
                    _type = answers[0]["ObjectType"]
                    dropoff = answers[0]["Disposal_type"]
                    return "Please put the {0} on the {1}".format(_type, dropoff).replace("_", " ")
                except Exception, e:
                    rospy.logerr(e)
                    return "Please put the object on the surface in front of me"
            smach.StateMachine.add("SAY_PLACE_INSTRUCTION", 
                                    states.Say_generated(robot, generate_object_sentence),
                                    transitions={   'spoken':'CLOSE_GRIPPER_HANDOVER'})

            smach.StateMachine.add('CLOSE_GRIPPER_HANDOVER', 
                                    states.SetGripper(robot, arm, gripperstate=ArmState.CLOSE),
                                    transitions={'succeeded'    :   'RESET_ARM',
                                                 'failed'       :   'RESET_ARM'})

            smach.StateMachine.add('RESET_ARM', 
                                    states.ArmToJointPos(robot, arm, (-0.0830 , -0.2178 , 0.0000 , 0.5900 , 0.3250 , 0.0838 , 0.0800)), #Copied from demo_executioner NORMAL
                                    transitions={   'done'      :'RESET_TORSO',
                                                  'failed'      :'RESET_TORSO'    })

            smach.StateMachine.add('RESET_TORSO',
                                    states.ResetTorso(robot),
                                    transitions={'succeeded'    :'succeeded',
                                                 'failed'       :'failed'})

class Cleanup(smach.StateMachine):

    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=['Done','Aborted'])

        if grasp_arm == "right": 
            arm = robot.rightArm
        else:            
            arm = robot.leftArm

        #retract old facts
        robot.reasoner.query(Compound("retractall", Compound("challenge", "X")))
        robot.reasoner.query(Compound("retractall", Compound("goal", "X")))
        robot.reasoner.query(Compound("retractall", Compound("explored", "X")))
        robot.reasoner.query(Compound("retractall", Compound("unreachable", "X")))
        robot.reasoner.query(Compound("retractall", Compound("state", "X", "Y")))
        robot.reasoner.query(Compound("retractall", Compound("current_exploration_target", "X")))
        robot.reasoner.query(Compound("retractall", Compound("current_object", "X")))
        robot.reasoner.query(Compound("retractall", Compound("disposed", "X")))
        
        robot.reasoner.query(Compound("load_database", "tue_knowledge", 'prolog/locations.pl'))
        robot.reasoner.query(Compound("load_database", "tue_knowledge", 'prolog/objects.pl'))
	
	    #robot.reasoner.query(Compound("load_database", "tue_knowledge", 'prolog/cleanup_test.pl'))
        #Assert the current challenge.
        robot.reasoner.assertz(Compound("challenge", "clean_up"))

        query_meeting_point = Compound("waypoint", 
                                Compound("meeting_point", "Waypoint"), 
                                Compound("pose_2d", "X", "Y", "Phi"))

        query_exploration_target_in_room = Conjunction( Compound("goal", Compound("clean_up", "Room")),
                                                        Compound("exploration_target", "Room", "Target"),
                                                        Compound("not", Compound("explored", "Target")),
                                                        Compound("waypoint", "Target", Compound("pose_2d", "X", "Y", "Phi"))
                                                       )
        query_room = Conjunction(   Compound("goal", Compound("clean_up", "Room")), 
                                    Compound("waypoint", "Room", Compound("pose_2d", "X", "Y", "Phi"))) 

        query_exploration_target = Conjunction( Compound("current_exploration_target", "Target"),
                                                Compound("waypoint", "Target", Compound("pose_2d", "X", "Y", "Phi")))

        query_lookat = Conjunction( Compound("current_exploration_target", "Target"),
                                    Compound("point_of_interest", "Target", Compound("point_3d", "X", "Y", "Z")))

        #Make sure the object we're dealing with isn't already disposed (i.e. handled for cleanup)
        #After cleaning the object up/disposing it, 
        #MARK_DISPOSED asserts disposed(current_objectID)
        query_object = Conjunction(
                            Compound("position", "ObjectID", Compound("point", "X", "Y", "Z")),
                            Compound("not", Compound("disposed", "ObjectID")))

        query_grabpoint = Conjunction(  Compound("current_object", "ObjectID"),
                                        Compound("position", "ObjectID", Compound("point", "X", "Y", "Z")))

        query_current_object_class = Conjunction(
                                Compound("current_object",      "Obj_to_Dispose"), #Of the current object
                                Compound("instance_of",         "Obj_to_Dispose",   Compound("exact", "ObjectType")))

        query_dropoff_loc = Conjunction(
                                Compound("current_object", "Obj_to_Dispose"), #Of the current object
                                Compound("instance_of",    "Obj_to_Dispose",   Compound("exact", "ObjectType")), #Gets its type
                                Compound("storage_class",  "ObjectType",       "Disposal_type"), #Find AT what sort of thing it should be disposed, e.g. a trash_bin
                                Compound("dropoff_point",  "Disposal_type", Compound("point_3d", "X", "Y", "Z")))

        query_dropoff_loc_backup = Compound("dropoff_point", Compound("trash_bin","Loc"), Compound("point_3d", "X", "Y", "Z"))

        meeting_point = Conjunction(    Compound("waypoint", Compound("meeting_point", "Waypoint"), Compound("pose_2d", "X", "Y", "Phi")),
                                        Compound("not", Compound("unreachable", Compound("meeting_point", "Waypoint"))))

        with self:

            smach.StateMachine.add( "START_CHALLENGE",
                                    states.StartChallengeRobust(robot, "initial"), 
                                    transitions={   "Done":"GOTO_MEETING_POINT", 
                                                    "Aborted":"Aborted", 
                                                    "Failed":"CANNOT_GOTO_MEETINGPOINT"})

            smach.StateMachine.add('GOTO_MEETING_POINT',
                                    states.GotoMeetingPoint(robot),
                                    transitions={   "found":"ASK_CLEANUP", 
                                                    "not_found":"ASK_CLEANUP", 
                                                    "no_goal":"ASK_CLEANUP",  # We are in the arena, so the current location is fine
                                                    "all_unreachable":"ASK_CLEANUP"})    # We are in the arena, so the current location is fine

            smach.StateMachine.add("CANNOT_GOTO_MEETINGPOINT", 
                                    states.Say(robot, [ "I can't find a way to the meeting point. Please teach me the correct position and clear the path to it", 
                                                        "I couldn't even get to my first waypoint. May I try again?", 
                                                        "This ended before I could get started, because my first waypoint is unreachable."]),
                                    transitions={   'spoken':'ASK_CLEANUP'})

            smach.StateMachine.add("ASK_CLEANUP",
                                Ask_cleanup(robot),
                                transitions={'done':'DETERMINE_EXPLORATION_TARGET'})
            
            ################################################################
            #                  DETERMINE_EXPLORATION_TARGET
            # TODO: What if there are multiple objects at the same exploration_target? 
            ################################################################

            @smach.cb_interface(outcomes=['found_exploration_target', 'done'], 
                                input_keys=[], 
                                output_keys=[])
            def determine_exploration_target(userdata):            
                # Ask the reaoner for an exploration target that is:
                #  - in the room that needs cleaning up
                #  - not yet explored
                answers = robot.reasoner.query(query_exploration_target_in_room)
                rospy.loginfo("Answers for {0}: {1}".format(query_exploration_target_in_room, answers))
                # First time: 
                # [   {'Y': 1.351, 'X': 4.952, 'Phi': 1.57, 'Room': living_room, 'Target': cabinet_expedit_1}, 
                #     {'Y': -1.598, 'X': 6.058, 'Phi': 3.113, 'Room': living_room, 'Target': bed_1}]
                # ----
                # 2nd:
                # [{'Y': -1.598, 'X': 6.058, 'Phi': 3.113, 'Room': living_room, 'Target': bed_1}]
                #
                #import ipdb; ipdb.set_trace()
                if not answers:
                    # no more exporation targets found
                    return 'done'
                else:         
                    # TODO: pick target based on some metric
                    def calc_dist((xA,yA), (xB,yB)):
                        import math
                        dist = math.sqrt(abs(xA-xB)**2 + abs(yA-yB)**2)
                        return dist
                    
                    loc = robot.base.location.pose.position
                    robot_xy = (loc.x, loc.y)
                    closest_QA = min(answers, key=lambda ans: calc_dist(robot_xy, (float(ans["X"]), float(ans["Y"]))))
                    target = closest_QA["Target"]
                    rospy.loginfo("Available targets: {0}".format(answers))
                    rospy.loginfo("Selected target: {0}".format(target))
                    #target = answers[0]["Target"]

                    # remove current target
                    robot.reasoner.query(Compound("retractall", Compound("current_exploration_target", "X")))

                    # add new target
                    robot.reasoner.assertz(Compound("current_exploration_target", target))

                    # Not so nice, but works for now: (TODO: add the fact if the target is actually explored)
                    robot.reasoner.assertz(Compound("explored", target))

                    string_target = str(target)
                    target_index = str(string_target).index("(")

                    speak_target = string_target[0:target_index]

                    robot.speech.speak("Lets go look at the {0}".format(speak_target).replace("_", " "), block=False)

                    return 'found_exploration_target'
            
            smach.StateMachine.add('DETERMINE_EXPLORATION_TARGET', smach.CBState(determine_exploration_target),
                                    transitions={   'found_exploration_target':'DRIVE_TO_EXPLORATION_TARGET',
                                                    'done':'SAY_ALL_EXPLORED'})

            ################################################################
            smach.StateMachine.add( 'DRIVE_TO_EXPLORATION_TARGET',
                                    states.NavigateGeneric(robot, goal_query=query_exploration_target),
                                    transitions={   "arrived":"SAY_LOOK_FOR_OBJECTS",
                                                    "unreachable":'SAY_GOAL_UNREACHABLE',
                                                    "preempted":'Aborted',
                                                    "goal_not_defined":'DETERMINE_EXPLORATION_TARGET'})

            def generate_unreachable_sentence(*args,**kwargs):
                try:
                    answers = robot.reasoner.query(query_exploration_target)
                    name = answers[0]["Target"] #Should only have 1 answer
                    return "{0} is unreachable, where else can I go?".format(name).replace("_", " ")
                except Exception, e:
                    rospy.logerr(e)
                    return "Something went terribly wrong, I don't know where to go and it's unreachable too"
            smach.StateMachine.add('SAY_GOAL_UNREACHABLE',
                                    states.Say_generated(robot, sentence_creator=generate_unreachable_sentence),
                                    transitions={ 'spoken':'DETERMINE_EXPLORATION_TARGET' })

            smach.StateMachine.add("SAY_LOOK_FOR_OBJECTS", 
                                    states.Say(robot, ["Lets see what I can find here."], block=False),
                                    transitions={   'spoken':'LOOK'})

            #query_dropoff_loc = Compound("point_of_interest", "trash_bin_1", Compound("point_3d", "X", "Y", "Z"))
            # 
            # Test this by: 
            # console 1: $ rosrun tue_reasoner_core reasoner
            # console 2: $ roslaunch wire_core start.launch
            # console 3: $ amigo-console
            # r.query(Compound("consult", '~/ros/fuerte/tue/trunk/tue_reasoner/tue_knowledge/prolog/cleanup_test.pl'))
            # r.query(Compound("consult", '~/ros/fuerte/tue/trunk/tue_reasoner/tue_knowledge/prolog/locations.pl'))
            # r.query(Compound("consult", '~/ros/fuerte/tue/trunk/tue_reasoner/tue_knowledge/prolog/objects.pl'))
            # r.assertz(Compound("challenge", "clean_up"))
            # r.assertz(Compound("environment", "tue_test_lab"))
            # r.query(r.dispose("X", "Y", "Z"))
            # This finally returns a list of (all the same) XYZ-coords.
            # If you enter query_dropoff_loc below into the amigo-console, 
            #   you can verify that it returns the same coords, but with more variables of course.

            smach.StateMachine.add('LOOK',
                                    states.LookForObjectsAtROI(robot, query_lookat, query_object),
                                    transitions={   'looking':'LOOK',
                                                    'object_found':'SAY_FOUND_SOMETHING',
                                                    'no_object_found':'SAY_FOUND_NOTHING',
                                                    'abort':'Aborted'})

            smach.StateMachine.add('SAY_FOUND_NOTHING',
                                    states.Say(robot, ["I didn't find anything to clean up here", "No objects to clean here", "There are no objects to clean here"]),
                                    transitions={ 'spoken':'DETERMINE_EXPLORATION_TARGET' })

            def generate_object_sentence(*args,**kwargs):
                try:
                    answers = robot.reasoner.query(query_dropoff_loc)
                    _type = answers[0]["ObjectType"]
                    dropoff = answers[0]["Disposal_type"]
                    return "I have found a {0}. I'll' bring it to the {1}".format(_type, dropoff).replace("_", " ")
                except Exception, e:
                    rospy.logerr(e)
                    try:
                        type_only = robot.reasoner.query(query_current_object_class)[0]["ObjectType"]
                        return "I found something called {0}.".format(type_only).replace("_", " ")
                    except Exception, e:
                        rospy.logerr(e)
                        pass
                    return "I have found something, but I'm not sure what it is."
            smach.StateMachine.add('SAY_FOUND_SOMETHING',
                                    states.Say_generated(robot, sentence_creator=generate_object_sentence, block=False),
                                    transitions={ 'spoken':'GRAB' })

            smach.StateMachine.add('GRAB',
                                    states.GrabMachine(arm, robot, query_grabpoint),
                                    transitions={   'succeeded':'DROPOFF_OBJECT',
                                                    'failed':'HUMAN_HANDOVER' })
            
            smach.StateMachine.add('HUMAN_HANDOVER',
                                    states.Human_handover(arm,robot),
                                    transitions={   'succeeded':'RESET_HEAD',
                                                    'failed':'DETERMINE_EXPLORATION_TARGET'})
        
            @smach.cb_interface(outcomes=["done"])
            def reset_head(*args, **kwargs):
                robot.head.reset_position()
                return "done"   
            smach.StateMachine.add( "RESET_HEAD", 
                        smach.CBState(reset_head),
                        transitions={"done":"DROPOFF_OBJECT"})

            # smach.StateMachine.add("DROPOFF_OBJECT",
            #                         states.DropObject(arm, robot, query_dropoff_loc),
            #                         transitions={   'succeeded':'MARK_DISPOSED',
            #                                         'failed':'MARK_DISPOSED',
            #                                         'target_lost':'DONT_KNOW_DROP'})

            smach.StateMachine.add("DROPOFF_OBJECT",
                                    StupidHumanDropoff(arm, robot, query_dropoff_loc),
                                    transitions={   'succeeded':'MARK_DISPOSED',
                                                    'failed':'MARK_DISPOSED',
                                                    'target_lost':'DONT_KNOW_DROP'})
            
            smach.StateMachine.add("DONT_KNOW_DROP", 
                                    states.Say(robot, "Now that I fetched this, I'm not sure where to put it. i'll just toss in in a trash bin.", block=False),
                                    transitions={   'spoken':'DROPOFF_OBJECT_BACKUP'})

            smach.StateMachine.add("DROPOFF_OBJECT_BACKUP",
                                    states.DropObject(arm, robot, query_dropoff_loc_backup),
                                    transitions={   'succeeded':'MARK_DISPOSED',
                                                    'failed':'MARK_DISPOSED',
                                                    'target_lost':'DONT_KNOW_DROP_BACKUP'})
                                    #states.Gripper_to_query_position(robot, robot.leftArm, query_dropoff_loc_backup),
                                    #transitions={   'succeeded':'MARK_DISPOSED',
                                    #                'failed':'MARK_DISPOSED',
                                    #                'target_lost':'DONT_KNOW_DROP_BACKUP'})

            smach.StateMachine.add("DONT_KNOW_DROP_BACKUP", 
                                    states.Say(robot, "I can't even find the trash bin! Then I'll just give it to a human. They'll know what to do.", mood="sad"),
                                    transitions={   'spoken':'GOTO_HUMAN_DROPOFF'})

            smach.StateMachine.add( 'GOTO_HUMAN_DROPOFF', states.NavigateGeneric(robot, goal_query=meeting_point),
                                    transitions={   "arrived":"SAY_PLEASE_TAKE",
                                                    "unreachable":'SAY_PLEASE_TAKE', #Maybe this should not be "FINISHED?"
                                                    "preempted":'SAY_PLEASE_TAKE',
                                                    "goal_not_defined":'SAY_PLEASE_TAKE'})

            smach.StateMachine.add("SAY_PLEASE_TAKE", 
                                    states.Say(robot, "Please take this thing from my hand. I don't know where to put it"),
                                    transitions={   'spoken':'HANDOVER_TO_HUMAN'})

            smach.StateMachine.add("HANDOVER_TO_HUMAN",
                                    states.HandoverToHuman(arm, robot),
                                    transitions={   'succeeded':'MARK_DISPOSED',
                                                    'failed':'MARK_DISPOSED'})

            #Mark the current_object as disposed
            @smach.cb_interface(outcomes=['done'])
            def deactivate_current_object(userdata):
                try:
                    #robot.speech.speak("I need some debugging in cleanup, please think with me here.")
                    #import ipdb; ipdb.set_trace()
                    objectID = robot.reasoner.query(Compound("current_object", "Disposed_ObjectID"))[0]["Disposed_ObjectID"]
                    disposed = Compound("disposed", objectID)
                    robot.reasoner.assertz(disposed)
                except:
                    pass #Just continue
                return 'done'
            smach.StateMachine.add('MARK_DISPOSED', smach.CBState(deactivate_current_object),
                                    transitions={'done':'DETERMINE_EXPLORATION_TARGET'})

            smach.StateMachine.add("SAY_ALL_EXPLORED", 
                                    states.Say(robot, [ "I searched at all locations I know of, so cleaning is done.", 
                                                        "All locations I know of are explored, there is nothing I can find anymore", 
                                                        "All locations I know of are explored, there are no locations to search anymore"]),
                                    transitions={   'spoken':'RETURN'})
                    
            smach.StateMachine.add( 'RETURN', states.NavigateGeneric(robot, goal_name="exitB"),
                                    transitions={   "arrived":"SAY_DONE",
                                                    "unreachable":'SAY_DONE', #Maybe this should not be "FINISHED?"
                                                    "preempted":'Aborted',
                                                    "goal_not_defined":'Aborted'})

            smach.StateMachine.add("SAY_DONE", 
                                    states.Say(robot, ["I cleaned up everything I could find, so my work here is done. Have a nice day!", "I'm done, everything I could find is cleaned up."]),
                                    transitions={   'spoken':'FINISH'})

            smach.StateMachine.add( 'FINISH', states.Finish(robot),
                                    transitions={'stop':'Done'})

if __name__ == "__main__":
    rospy.init_node('clean_up_exec')
    
    startup(Cleanup)
