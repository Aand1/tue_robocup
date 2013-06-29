#! /usr/bin/env python
import roslib; roslib.load_manifest('challenge_final')
import rospy

import smach
from robot_skills.amigo import Amigo
import robot_smach_states as states

from robot_skills.reasoner  import Conjunction, Compound, Sequence
from robot_skills.arms import State as ArmState
from robot_smach_states.util.startup import startup
from speech_interpreter.srv import GetYesNo
from speech_interpreter.srv import GetInfo

import geometry_msgs.msg

from psi import *

grasp_arm = "left"
#grasp_arm = "right"

##########################################
############## What to run: ##############
##########################################
# CHECK the README!

class Ask_drink(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["done" , "failed"])
        self.robot = robot
        self.get_drink_service = rospy.ServiceProxy('interpreter/get_info_user', GetInfo)
        self.person_learn_failed = 0
        self.drink_learn_failed = 0

    def execute(self, userdata=None):
        self.response = self.get_drink_service("drink_final", 3 , 120)  # This means that within 4 tries and within 60 seconds an answer is received. 
        # Check available options from rulebook!
        
        #import ipdb; ipdb.set_trace()
        self.robot.reasoner.query(Compound("assert", Compound("goal", Compound("serve", "coke"))))
        return "done"

class Ask_yes_no(smach.State):
    def __init__(self, robot, tracking=True):
        smach.State.__init__(self, outcomes=["yes", "preempted", "no"])

        self.robot = robot
        self.preempted = False
        self.get_yes_no_service = rospy.ServiceProxy('interpreter/get_yes_no', GetYesNo)

    def execute(self, userdata=None):

        self.response = self.get_yes_no_service(2 , 8) # 3 tries, each max 10 seconds

        if self.response.answer == "true":
            return "yes"
        else:
            return "yes" # THIS WAS "no", in this case bring sevenup to trashbin, so yes.

        

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

class ScanTables(smach.State):
    def __init__(self, robot, timeout_duration):
        smach.State.__init__(self, outcomes=['succeeded'])
        self.robot = robot
        self.timeout_duration = timeout_duration

    def execute(self, gl):

        rospy.loginfo("Trying to detect objects on tables")

        answers = self.robot.reasoner.query(Compound('region_of_interest', 
            'large_table_1', Compound('point_3d', 'X', 'Y', 'Z'), Compound('point_3d', 'Length_x', 'Length_y', 'Length_z')))
        
        ''' Remember current spindle position '''      
        spindle_pos = self.robot.spindle.get_position()


        if answers:
            answer = answers[0] #TODO Loy/Sjoerd: sort answers by distance to gripper/base? 
            target_point = geometry_msgs.msg.PointStamped()
            target_point.header.frame_id = "/map"
            target_point.header.stamp = rospy.Time()
            target_point.point.x = float(answer["X"])
            target_point.point.y = float(answer["Y"])
            target_point.point.z = float(answer["Z"])

            ''' If height is feasible for LRF, use this. Else: use head and tabletop/clustering '''
            if self.robot.spindle.send_laser_goal(float(answer["Z"]), timeout=self.timeout_duration):
                #self.robot.speech.speak("I will scan the tables for objects", block=False)
                self.robot.perception.toggle_perception_2d(target_point, answer["Length_x"], answer["Length_y"], answer["Length_z"])
                rospy.logwarn("Here we should keep track of the uncertainty, how can we do that? Now we simply use a sleep")
                rospy.logwarn("Waiting for 2.0 seconds for laser update")
                rospy.sleep(rospy.Duration(2.0))
            else:
                rospy.logerr("Can't scan on spindle height, either the spindle timeout exceeded or ROI too low. Will have to move to prior location")
            
            ''' Reset head and stop all perception stuff '''
            self.robot.perception.toggle([])
            self.robot.spindle.send_goal(spindle_pos, waittime=self.timeout_duration)
        else:
            rospy.logerr("No table location found...")

        return 'succeeded'

class ScanTablePosition(smach.State):
    def __init__(self, robot, timeout_duration):
        smach.State.__init__(self, outcomes=['succeeded'])
        self.robot = robot
        self.timeout_duration = timeout_duration

    def execute(self, gl):

        rospy.loginfo("Trying to detect tables")

        answers = self.robot.reasoner.query(Compound('region_of_interest', 
            'large_table_position', Compound('point_3d', 'X', 'Y', 'Z'), Compound('point_3d', 'Length_x', 'Length_y', 'Length_z')))
        
        ''' Remember current spindle position '''      
        spindle_pos = self.robot.spindle.get_position()


        if answers:
            answer = answers[0] #TODO Loy/Sjoerd: sort answers by distance to gripper/base? 
            target_point = geometry_msgs.msg.PointStamped()
            target_point.header.frame_id = "/map"
            target_point.header.stamp = rospy.Time()
            target_point.point.x = float(answer["X"])
            target_point.point.y = float(answer["Y"])
            target_point.point.z = float(answer["Z"])

            ''' If height is feasible for LRF, use this. Else: use head and tabletop/clustering '''
            if self.robot.spindle.send_laser_goal(float(answer["Z"]), timeout=self.timeout_duration):
                self.robot.perception.toggle_perception_2d(target_point, answer["Length_x"], answer["Length_y"], answer["Length_z"])
                #rospy.logwarn("Here we should keep track of the uncertainty, how can we do that? Now we simply use a sleep")
                rospy.loginfo("Tracking table for {0}".format(self.timeout_duration))
                self.robot.speech.speak("Hey guys, can I do anything for you.")
                rospy.sleep(rospy.Duration(self.timeout_duration))
            else:
                rospy.logerr("Can't scan on spindle height, either the spindle timeout exceeded or ROI too low. Will have to move to prior location")
            
            ''' Reset head and stop all perception stuff '''
            self.robot.perception.toggle([])
            self.robot.spindle.send_goal(spindle_pos, waittime=self.timeout_duration)
        else:
            rospy.logerr("No table location found...")

        return 'succeeded'

class LookForServeObject(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["found", "not_found"])
        self.robot = robot
        self.preempted = False
        self.side = robot.leftArm

    def execute(self, userdata=None):
        look_at_query = Compound("base_grasp_point", "ObjectID", Compound("point_3d", "X", "Y", "Z"))
        answers = self.robot.reasoner.query(look_at_query)

        lookat_point = geometry_msgs.msg.Point()
        if answers:
            lookat_point.x = float(answers[0]["X"])
            lookat_point.y = float(answers[0]["Y"])
            lookat_point.z = float(answers[0]["Z"])
        else:
            rospy.logerr("World model is empty, while at grasp location")
            return 'not_found'

        spindle_target = max(0.15, min(lookat_point.z - 0.41, self.robot.spindle.upper_limit))
        rospy.loginfo("Target height: {0}, spindle_target: {1}".format(lookat_point.z, spindle_target))

        self.robot.head.send_goal(lookat_point, keep_tracking=True)
        self.robot.spindle.send_goal(spindle_target,waittime=5.0)

        rospy.loginfo("Start object recognition")
        self.robot.perception.toggle_recognition(objects=True)
        rospy.sleep(2.5)
        rospy.loginfo("Stop object recognition")

        self.robot.perception.toggle_recognition(objects=False)

        #Select object we are looking for
        serve_object = Compound("goal", Compound("serve", "Counter", "Object"))
        answers = self.robot.reasoner.query(serve_object)
        print answers
        object_class = ""
        if answers:
            object_class = answers[0]["Object"]
            is_object_there = Conjunction(Compound("instance_of", "ObjectID", object_class),
                                        Compound("property_expected", "ObjectID", "position", Sequence("X", "Y", "Z")))
            object_query_answers = self.robot.reasoner.query(is_object_there)
            if object_query_answers:
                self.robot.speech.speak("I have found what I have been looking for, a " + str(object_class))
                self.robot.reasoner.query(Compound("retractall", Compound("base_grasp_point", "ObjectID", "A")))# ToDo: is this what you mean?
                self.robot.reasoner.assertz(Compound("base_grasp_point", object_query_answers[0]['ObjectID'], Compound("point_3d", object_query_answers[0]["X"], object_query_answers[0]["Y"], object_query_answers[0]["Z"])))
                return "found"
            else:
                self.robot.speech.speak("I have not yet found what I am looking for")
                return "not_found"

        else:
            rospy.logerr("I Forgot what I have been looking for")
            return 'not_found'

class MoveToTable(smach.StateMachine):
    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=["done", "failed_navigate", "no_tables_left"])
        self.robot = robot

        with self:
            smach.StateMachine.add("GET_LOCATION", 
                GetNextLocation(self.robot),
                transitions={'done':'NAVIGATE_TO', 'no_locations':'no_tables_left'})

            smach.StateMachine.add("NAVIGATE_TO", states.NavigateGeneric(robot, 
                lookat_query=Compound("base_grasp_point", "ObjectID", Compound("point_3d", "X", "Y", "Z"))), 
                transitions={'unreachable' : 'failed_navigate', 'preempted' : 'NAVIGATE_TO', 
                'arrived' : 'done', 'goal_not_defined' : 'failed_navigate'})

class MoveToGoal(smach.StateMachine):
    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=["succeeded_person" ,"succeeded_prior", "failed"])
        self.robot = robot
        with self:
            smach.StateMachine.add("PERSON_OR_PRIOR",
                PersonOrPrior(self.robot),
                transitions={'at_prior': 'NAVIGATE_TO_PRIOR', 'at_person' : 'NAVIGATE_TO_PERSON', 'failed': 'failed'})
            smach.StateMachine.add("NAVIGATE_TO_PERSON", states.NavigateGeneric(robot, 
                lookat_query=Compound("deliver_goal", Compound("point_3d", "X", "Y", "Z"))), 
                transitions={'unreachable' : 'failed', 'preempted' : 'NAVIGATE_TO_PRIOR', 
                'arrived' : 'succeeded_person', 'goal_not_defined' : 'failed'})
            smach.StateMachine.add("NAVIGATE_TO_PRIOR", states.NavigateGeneric(robot, 
                goal_query=Compound("waypoint", "prior",  Compound("pose_2d", "X", "Y", "Phi"))), 
                transitions={'unreachable' : 'failed', 'preempted' : 'NAVIGATE_TO_PERSON', 
                'arrived' : 'succeeded_prior', 'goal_not_defined' : 'failed'})

class Final(smach.StateMachine):
    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=['Done','Aborted'])
        self.robot = robot
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
        robot.reasoner.assertz(Compound("challenge", "final"))

        # query_unkown_object = Conjunction( Compound("goal", Compound("clean_up", "Room")),
        #                                                 Compound("exploration_target", "Room", "Target"),
        #                                                 Compound("not", Compound("explored", "Target")),
        #                                                 Compound("waypoint", "Target", Compound("pose_2d", "X", "Y", "Phi"))
                                                       # )
        query_living_room1 = Compound("waypoint", "living_room1", Compound("pose_2d", "X", "Y", "Phi"))
        query_living_room2 = Compound("waypoint", "living_room2", Compound("pose_2d", "X", "Y", "Phi"))
        query_living_room3 = Compound("waypoint", "living_room3", Compound("pose_2d", "X", "Y", "Phi"))

        query_unkown_object = Conjunction(
                 Compound( "property_expected", "ObjectID", "position", Sequence("X", "Y", "Z")), 
                 Compound( "not", Compound("property_expected", "ObjectID", "class_label", "Class")),
                 Compound( "not", Compound("explored", "ObjectID")))

        query_exploration_target = Conjunction( Compound("current_exploration_target", "ObjectID"), 
                                                Compound( "property_expected", "ObjectID", "position", Sequence("X", "Y", "Z")))

        query_lookat = Conjunction( Compound("current_exploration_target", "Target"),
                                    Compound( "property_expected", "ObjectID", "position", Sequence("X", "Y", "Z")))

        #Make sure the object we're dealing with isn't already disposed (i.e. handled for cleanup)
        #After cleaning the object up/disposing it, 
        #MARK_DISPOSED asserts disposed(current_objectID)
        query_object = Conjunction(
                            Compound( "property_expected", "ObjectID", "position", Sequence("X", "Y", "Z")),
                            Compound("not", Compound("disposed", "ObjectID")))

        query_grabpoint = Conjunction(  Compound("current_object", "ObjectID"),
                                        Compound("position", "ObjectID", Compound("point", "X", "Y", "Z")))

        query_current_object_class = Conjunction(
                                Compound("current_object",      "Obj_to_Dispose"), #Of the current object
                                Compound("instance_of",         "Obj_to_Dispose",   Compound("exact", "ObjectType")))

        query_dropoff_loc = Compound("dropoff_point",  "trash_bin", Compound("point_3d", "X", "Y", "Z"))        

        meeting_point = Conjunction(    Compound("waypoint", Compound("meeting_point", "Waypoint"), Compound("pose_2d", "X", "Y", "Phi")),
                                        Compound("not", Compound("unreachable", Compound("meeting_point", "Waypoint"))))

        with self:
            ######################################################
            ##################### ENTER ROOM #####################
            ######################################################
            # Start challenge via StartChallengeRobust
            smach.StateMachine.add( "START_CHALLENGE",
                                    states.StartChallengeRobust(robot, "initial"), 
                                    transitions={   "Done":"SAY_GOTO_LIVINGROOM", 
                                                    "Aborted":"SAY_GOTO_LIVINGROOM", 
                                                    "Failed":"SAY_GOTO_LIVINGROOM"}) 

            smach.StateMachine.add("SAY_GOTO_LIVINGROOM",
                                    states.Say(robot, "I will go to the living room, see if I can do something over there.", block=False),
                                    transitions={   "spoken":"GOTO_LIVING_ROOM1"})

            smach.StateMachine.add('GOTO_LIVING_ROOM1',
                                    states.NavigateGeneric(robot, goal_query = query_living_room1),
                                    transitions={   "arrived":"SCAN_TABLE_POSITION", 
                                                    "unreachable":"GOTO_LIVING_ROOM2", 
                                                    "preempted":"GOTO_LIVING_ROOM2", 
                                                    "goal_not_defined":"GOTO_LIVING_ROOM2"})

            smach.StateMachine.add('GOTO_LIVING_ROOM2',
                                    states.NavigateGeneric(robot, goal_query = query_living_room2),
                                    transitions={   "arrived":"SCAN_TABLE_POSITION", 
                                                    "unreachable":"GOTO_LIVING_ROOM3", 
                                                    "preempted":"GOTO_LIVING_ROOM3", 
                                                    "goal_not_defined":"GOTO_LIVING_ROOM3"})

            smach.StateMachine.add('GOTO_LIVING_ROOM3',
                                    states.NavigateGeneric(robot, goal_query = query_living_room3),
                                    transitions={   "arrived":"SCAN_TABLE_POSITION", 
                                                    "unreachable":"SCAN_TABLE_POSITION", 
                                                    "preempted":"SCAN_TABLE_POSITION", 
                                                    "goal_not_defined":"SCAN_TABLE_POSITION"})
            
            smach.StateMachine.add("SCAN_TABLE_POSITION", 
                                ScanTablePosition(robot, 20.0),
                                transitions={   'succeeded':'TAKE_ORDER'})

            smach.StateMachine.add( "TAKE_ORDER",
                                            Ask_drink(robot),
                                            transitions={   "done":"SCAN_TABLES",
                                                            "failed":"SCAN_TABLES"})

            # After this state: objects might be in the world model
            smach.StateMachine.add("SCAN_TABLES", 
                                ScanTables(robot, 10.0),
                                transitions={   'succeeded':'MOVE_TO_TABLE'})

            smach.StateMachine.add("MOVE_TO_TABLE", 
                MoveToTable(robot),
                transitions={   'done':'SAY_LOOK_FOR_OBJECTS', 'failed_navigate' : 'MOVE_TO_TABLE', 'no_tables_left' : 'EXIT'})

            def generate_no_targets_sentence(*args,**kwargs):
                try:
                    answers = robot.reasoner.query(query_unkown_object)
                    return "I have found {0} possible object locations".format(len(answers))
                except Exception, e:
                    rospy.logerr(e)
                    return "I found no objects"

            smach.StateMachine.add('SAY_NO_TARGETS',
                                    states.Say_generated(robot, sentence_creator=generate_no_targets_sentence),
                                    transitions={ 'spoken':'DETERMINE_EXPLORATION_TARGET' })

            ##### ADD ASK USER DRINK #####

            # Now find the closest object on the table
            @smach.cb_interface(outcomes=['found_exploration_target', 'done'], 
                                input_keys=[], 
                                output_keys=[])
            def determine_exploration_target(userdata):            
                # Ask the reaoner for an exploration target that is:
                #  - in the room that needs cleaning up
                #  - not yet explored
                answers = robot.reasoner.query(query_unkown_object)
                for answer in answers:
                    rospy.loginfo("Answers for {0}: {1} \n\n".format(query_unkown_object, answer))
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
                    
                    loc = self.robot.base.location[0]
                    
                    robot_xy = (loc.x, loc.y)
                    closest_QA = min(answers, key=lambda ans: calc_dist(robot_xy, (float(ans["X"]), float(ans["Y"]))))
                    target = closest_QA["ObjectID"]

                    rospy.loginfo("Minimum distance: {0}".format(closest_QA))

                    #rospy.loginfo("Available targets: {0}".format(answers))
                    rospy.loginfo("Selected target: {0}".format(target))

                    # remove current target
                    robot.reasoner.query(Compound("retractall", Compound("current_exploration_target", "X")))

                    # add new target
                    robot.reasoner.assertz(Compound("current_exploration_target", target))
                    answers = robot.reasoner.query(query_exploration_target)

                    # Not so nice, but works for now: (TODO: add the fact if the target is actually explored)
                    robot.reasoner.assertz(Compound("explored", target))
                    
                    #robot.speech.speak("Lets go look at the object with ID {0}".format(target))
                    robot.speech.speak("Let's go look at an object I found!".format(target), block=False)

                    return 'found_exploration_target'
            
            smach.StateMachine.add('DETERMINE_EXPLORATION_TARGET', smach.CBState(determine_exploration_target),
                                    transitions={   'found_exploration_target':'DRIVE_TO_EXPLORATION_TARGET',
                                                    'done':'SAY_ALL_EXPLORED'})

            ################################################################
            smach.StateMachine.add( 'DRIVE_TO_EXPLORATION_TARGET',
                                    states.PrepareOrientation(arm, robot, grabpoint_query=query_exploration_target),
                                    transitions={   "orientation_succeeded":"SAY_LOOK_FOR_OBJECTS",
                                                    "orientation_failed":'SAY_GOAL_UNREACHABLE',
                                                    "abort":'Aborted',
                                                    "target_lost":'DETERMINE_EXPLORATION_TARGET'})
          
            smach.StateMachine.add('SAY_GOAL_UNREACHABLE',
                                    states.Say(robot, ["The object is unreachable, where else can I go?"]),
                                    transitions={ 'spoken':'DETERMINE_EXPLORATION_TARGET' })

            smach.StateMachine.add("SAY_LOOK_FOR_OBJECTS", 
                                    states.Say(robot, ["Let's see what object I can find here."]),
                                    transitions={   'spoken':'RECOGNIZE_OBJECTS'})

            # smach.StateMachine.add('LOOK',
            #                         states.LookForObjectsAtROI(robot, query_lookat, query_object,waittime=3.0),
            #                         transitions={   'looking':'LOOK',
            #                                         'object_found':'SAY_FOUND_SOMETHING',
            #                                         'no_object_found':'SAY_FOUND_NOTHING',
            #                                         'abort':'DETERMINE_EXPLORATION_TARGET'})

            # smach.StateMachine.add('SAY_FOUND_NOTHING',
            #                         states.Say(robot, ["I didn't find anything."]),
            #                         transitions={ 'spoken':'DETERMINE_EXPLORATION_TARGET' })

            # def generate_object_sentence(*args,**kwargs):
            #     try:
            #         answers = robot.reasoner.query(query_dropoff_loc)
            #         _type = answers[0]["ObjectType"]
            #         return "I have found a {0}. I'll dump it in the trash bin".format(_type)
            #     except Exception, e:
            #         rospy.logerr(e)
            #         try:
            #             type_only = robot.reasoner.query(query_current_object_class)[0]["ObjectType"]
            #             return "I found a {0}.".format(type_only)
            #         except Exception, e:
            #             rospy.logerr(e)
            #             pass
            #         return "I have found something, but I'm not sure what it is. I'll toss in in the trash bin"

            # smach.StateMachine.add('SAY_FOUND_SOMETHING',
            #                         states.Say_generated(robot, sentence_creator=generate_object_sentence),
            #                         transitions={ 'spoken':'RECOGNIZE_OBJECTS' })

            smach.StateMachine.add("RECOGNIZE_OBJECTS", 
                LookForServeObject(robot), # En andere dingen
                transitions={  'not_found':'MOVE_TO_TABLE', 'found': 'GRAB'})

            smach.StateMachine.add('GRAB',
                                    states.GrabMachine(arm, robot, query_grabpoint),
                                    transitions={   'succeeded':'MOVE_TO_OPERATOR',
                                                    'failed':'HUMAN_HANDOVER' })
            
            smach.StateMachine.add('HUMAN_HANDOVER',
                                    states.Human_handover(arm,robot),
                                    transitions={   'succeeded':'MOVE_TO_OPERATOR',
                                                    'failed':'MOVE_TO_OPERATOR'})

            # ToDo: how do we move to operator?
            smach.StateMachine.add("MOVE_TO_OPERATOR", 
            MoveToGoal(robot), # En andere dingen
            transitions={   'succeeded_person':'HANDOVER', 
                            'succeeded_prior':'SCAN_FOR_PERSONS_AT_PRIOR', 'failed':'ASK_GET_OBJECT'})
        
            @smach.cb_interface(outcomes=["done"])
            def reset_head(*args, **kwargs):
                robot.head.reset_position()
                return "done"   
            smach.StateMachine.add( "RESET_HEAD", 
                        smach.CBState(reset_head),
                        transitions={"done":"DROPOFF_OBJECT"})

            smach.StateMachine.add("DROPOFF_OBJECT",
                                    states.DropObject(arm, robot, query_dropoff_loc),
                                    transitions={   'succeeded':'MARK_DISPOSED',
                                                    'failed':'MARK_DISPOSED',
                                                    'target_lost':'GOTO_HUMAN_DROPOFF'})

            # smach.StateMachine.add("DROPOFF_OBJECT",
            #                         StupidHumanDropoff(arm, robot, query_dropoff_loc),
            #                         transitions={   'succeeded':'MARK_DISPOSED',
            #                                         'failed':'MARK_DISPOSED',
            #                                         'target_lost':'GOTO_HUMAN_DROPOFF'})

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
                                    states.Say(robot, ["All object locations I found with my laser are explored, there are no locations to search anymore"],block=False),
                                    transitions={   'spoken':'RETURN_LIVING_ROOM'})

            # ToDo: replace by something more interesting
            smach.StateMachine.add('RETURN_LIVING_ROOM',
                                    states.NavigateGeneric(robot, goal_query = query_living_room1),
                                    transitions={   "arrived":"SAY_THANKS", 
                                                    "unreachable":"RETURN_LIVING_ROOM2", 
                                                    "preempted":"RETURN_LIVING_ROOM2", 
                                                    "goal_not_defined":"RETURN_LIVING_ROOM2"})

            smach.StateMachine.add('RETURN_LIVING_ROOM2',
                                    states.NavigateGeneric(robot, goal_query = query_living_room2),
                                    transitions={   "arrived":"SAY_THANKS", 
                                                    "unreachable":"RETURN_LIVING_ROOM3", 
                                                    "preempted":"RETURN_LIVING_ROOM3", 
                                                    "goal_not_defined":"RETURN_LIVING_ROOM3"})

            smach.StateMachine.add('RETURN_LIVING_ROOM3',
                                    states.NavigateGeneric(robot, goal_query = query_living_room3),
                                    transitions={   "arrived":"SAY_THANKS", 
                                                    "unreachable":"SAY_THANKS", 
                                                    "preempted":"SAY_THANKS", 
                                                    "goal_not_defined":"SAY_THANKS"})





            # TODO DRIVE TO AUDIENCE NEAR COUCH.



            smach.StateMachine.add('SAY_LASER_ERROR',
                                    states.Say(robot, "Something went terribly wrong, can I start again",mood="sad",block=False),
                                    transitions={'spoken':'EXIT'})

            smach.StateMachine.add('SAY_THANKS',
                                    states.Say(robot, "Thanks for your time, hope you enjoyed Robocup 2013."),
                                    transitions={'spoken':'EXIT'}) 

            smach.StateMachine.add('EXIT',
                                    states.NavigateGeneric(robot, goal_query = Compound("waypoint","exit_1",Compound("pose_2d","X","Y","Phi"))),
                                    transitions={   "arrived":"FINISH", 
                                                    "unreachable":"CLEAR_PATH_TO_EXIT", 
                                                    "preempted":"CLEAR_PATH_TO_EXIT", 
                                                    "goal_not_defined":"CLEAR_PATH_TO_EXIT"})

            smach.StateMachine.add('CLEAR_PATH_TO_EXIT',
                                    states.Say(robot, "I couldn't go to the exit. Please clear the path, I will give it another try."),
                                    transitions={'spoken':'GO_TO_EXIT_SECOND_TRY'}) 

            smach.StateMachine.add('GO_TO_EXIT_SECOND_TRY',
                                    states.NavigateGeneric(robot, goal_query = Compound("waypoint","exit_2",Compound("pose_2d","X","Y","Phi"))),
                                    transitions={   "arrived":"FINISH", 
                                                    "unreachable":"FINISH", 
                                                    "preempted":"FINISH", 
                                                    "goal_not_defined":"FINISH"})

            smach.StateMachine.add( 'FINISH', 
                                    states.Finish(robot),
                                    transitions={'stop':'Done'})






        # # Await anser of question 1
        # smach.StateMachine.add('ANSWER_YES_NO',
        #                             Ask_yes_no(robot),
        #                             transitions={   'yes':'ASK_IF_KNOWS_DIRECTION',
        #                                             'preempted':'SAY_REGISTER_NOT_OKAY',
        #                                             'no':'SAY_REGISTER_NOT_OKAY'})   


            

if __name__ == "__main__":
    rospy.init_node('final_exec')
    
    startup(Final)
