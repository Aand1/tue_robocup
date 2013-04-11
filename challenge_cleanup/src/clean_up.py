#! /usr/bin/env python
import roslib; roslib.load_manifest('challenge_cleanup')
import rospy

import smach

from robot_skills.amigo import Amigo
import robot_smach_states as states

from robot_skills.reasoner  import Conjunction, Compound

class Cleanup(smach.StateMachine):

    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=['Done','Aborted'])

        #retract old facts
        robot.reasoner.query(Compound("retractall", Compound("challenge", "X")))
        robot.reasoner.query(Compound("retractall", Compound("goal", "X")))
        robot.reasoner.query(Compound("retractall", Compound("explored", "X")))
        robot.reasoner.query(Compound("retractall", Compound("state", "X", "Y")))
        robot.reasoner.query(Compound("retractall", Compound("current_exploration_target", "X")))
        robot.reasoner.query(Compound("retractall", Compound("current_object", "X")))
        robot.reasoner.query(Compound("retractall", Compound("disposed", "X")))
        
        robot.reasoner.query(Compound("load_database", "tue_knowledge", 'prolog/locations.pl'))
        robot.reasoner.query(Compound("load_database", "tue_knowledge", 'prolog/objects.pl'))
        #Assert the current challenge.
        robot.reasoner.assertz(Compound("challenge", "clean_up"))
        
        with self:
                                  
            smach.StateMachine.add('INITIALIZE',
                                    states.Initialize(robot),
                                    transitions={   'initialized':'ASK_OPEN_DOOR',
                                                    'abort':'Aborted'})

            smach.StateMachine.add("ASK_OPEN_DOOR", 
                                    states.Say(robot, ["Knock, Knock, please open the door.", "May I please come in?", "I'm ready to clean up, please let me in so that I can get started."]),
                                    transitions={   'spoken':'STATE_DOOR'})

            ### UNDERSTANDING STATES COME FROM REGISTRATION. WAIT FOR DOOR STATES didn't work while testing. Loy, maybe have a look at you WAIT_FOR_DOOR states.

            # Start laser sensor that may change the state of the door if the door is open:
            smach.StateMachine.add('STATE_DOOR', 
                                        states.Read_laser(robot, "entrance_door"),
                                        transitions={'laser_read':'WAIT_FOR_DOOR'})       
            
            # define query for the question wether the door is open in the state WAIT_FOR_DOOR
            dooropen_query = Compound("state", "entrance_door", "open")
            
            # Query if the door is open:
            smach.StateMachine.add('WAIT_FOR_DOOR', 
                                        states.Ask_query_true(robot, dooropen_query),
                                        transitions={   'query_false':'STATE_DOOR',
                                                        'query_true':'THROUGH_DOOR',
                                                        'waiting':'DOOR_CLOSED',
                                                        'preempted':'Aborted'})

            # If the door is still closed after certain number of iterations, defined in Ask_query_true 
            # in perception.py, amigo will speak and check again if the door is open
            smach.StateMachine.add('DOOR_CLOSED',
                                        states.Say(robot, 'Door is closed, please open the door'),
                                        transitions={'spoken':'STATE_DOOR'}) 

            # If the door is open, amigo will say that it goes to the meeting point
            smach.StateMachine.add('THROUGH_DOOR',
                                        states.Say(robot, "Thank you for letting me in, I'll see you at the meeting point"),
                                        transitions={'spoken':'INIT_POSE'})

            smach.StateMachine.add('INIT_POSE',
                                    states.Set_initial_pose(robot, "initial"),
                                    transitions={   'done':'ENTER_ROOM',
                                                    'preempted':'Aborted',
                                                    'error':'Aborted'})
           
            query_meeting_point = Compound("waypoint", "meeting_point", Compound("pose_2d", "X", "Y", "Phi"))
            smach.StateMachine.add('ENTER_ROOM',
                                    states.Navigate_to_queryoutcome(robot, query_meeting_point, X="X", Y="Y", Phi="Phi"),
                                    transitions={   "arrived":"QUESTION",
                                                    "unreachable":'CANNOT_GOTO_MEETINGPOINT',
                                                    "preempted":'CANNOT_GOTO_MEETINGPOINT',
                                                    "goal_not_defined":'CANNOT_GOTO_MEETINGPOINT'})

            smach.StateMachine.add("CANNOT_GOTO_MEETINGPOINT", 
                                    states.Say(robot, ["I can't find a way to the meeting point. Please teach me the correct position and clear the path to it"]),
                                    transitions={   'spoken':'Aborted'})


            smach.StateMachine.add('QUESTION', 
                                    states.Timedout_QuestionMachine(
                                            robot=robot,
                                            default_option = "cleanupthelivingroom", 
                                            sentence = "Where do you want me to go", 
                                            options = { "cleanupthelivingroom":Compound("goal", Compound("clean_up", "living_room")),
                                                        "cleanupthekitchen":Compound("goal", Compound("clean_up", "kitchen")),
                                                        "cleanupthelobby":Compound("goal", Compound("clean_up", "lobby")),
                                                        "cleanupthebedroom":Compound("goal", Compound("clean_up", "bedroom"))}),
                                    transitions={   'answered':'DRIVE_TO_ROOM',
                                                    'not_answered':'QUESTION'})

            query_room = Conjunction(Compound("goal", Compound("clean_up", "Room")), Compound("waypoint", "Room", Compound("pose_2d", "X", "Y", "Phi")))        
            smach.StateMachine.add( 'DRIVE_TO_ROOM',
                                    states.Navigate_to_queryoutcome(robot, query_room, X="X", Y="Y", Phi="Phi"),
                                    transitions={   "arrived":"SAY_ARRIVED_IN_ROOM",
                                                    "unreachable":'Aborted',
                                                    "preempted":'Aborted',
                                                    "goal_not_defined":'Aborted'})

            smach.StateMachine.add('SAY_ARRIVED_IN_ROOM',
                                    states.Say(robot, ["So, i have arrived, lets do some cleaning", "Allright, lets clean this mess up.", "Lets find some stuff to clean up here."]),
                                    transitions={ 'spoken':'DETERMINE_EXPLORATION_TARGET' })
            
            ################################################################
            #                  DETERMINE_EXPLORATION_TARGET
            ################################################################

            @smach.cb_interface(outcomes=['found_exploration_target', 'done'], 
                                input_keys=[], 
                                output_keys=[])
            def determine_exploration_target(userdata):            
                # Ask the reaoner for an exploration target that is:
                #  - in the room that needs cleaning up
                #  - not yet explored
                query_exploration_target = Conjunction( Compound("goal", Compound("clean_up", "Room")),
                                                        Compound("exploration_target", "Room", "Target"),
                                                        Compound("not", Compound("explored", "Target")),
                                                        Compound("base_pose", "Target", Compound("pose_2d", "X", "Y", "Phi"))
                                                       )    

                answers = robot.reasoner.query(query_exploration_target)
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
                    
                    loc = robot.base.location[0]
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

                    return 'found_exploration_target'
            
            smach.StateMachine.add('DETERMINE_EXPLORATION_TARGET', smach.CBState(determine_exploration_target),
                                    transitions={   'found_exploration_target':'DRIVE_TO_EXPLORATION_TARGET',
                                                    'done':'RETURN'})

            ################################################################

            query_exploration_target = Conjunction( Compound("current_exploration_target", "Target"),
                                                    Compound("base_pose", "Target", Compound("pose_2d", "X", "Y", "Phi")))

            smach.StateMachine.add( 'DRIVE_TO_EXPLORATION_TARGET',
                                    states.Navigate_to_queryoutcome(robot, query_exploration_target, X="X", Y="Y", Phi="Phi"),
                                    transitions={   "arrived":"SAY_LOOK_FOR_OBJECTS",
                                                    "unreachable":'DETERMINE_EXPLORATION_TARGET',
                                                    "preempted":'Aborted',
                                                    "goal_not_defined":'DETERMINE_EXPLORATION_TARGET'})

            smach.StateMachine.add("SAY_LOOK_FOR_OBJECTS", 
                                    states.Say(robot, ["Lets see what I can find here."]),
                                    transitions={   'spoken':'LOOK'})

            query_lookat = Conjunction( Compound("current_exploration_target", "Target"),
                                        Compound("region_of_interest", "Target", Compound("point_3d", "X", "Y", "Z")))

            query_object = Conjunction(
                            Compound("position", "ObjectID", Compound("point", "X", "Y", "Z")),
                            #Make sure the object we're dealing with isn't already disposed (i.e. handled for cleanup)
                            #After cleaning the object up/disposing it, 
                            #MARK_DISPOSED asserts disposed(current_objectID)
                            Compound("not", Compound("disposed", "ObjectID")))

            #query_dropoff_loc = Compound("region_of_interest", "trashbin1", Compound("point_3d", "X", "Y", "Z"))
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
            query_dropoff_loc = Conjunction(Compound("current_object",      "Obj_to_Dispose"), #Of the current object
                                            Compound("type",                "Obj_to_Dispose",   Compound("exact", "ObjectType")), #Gets its type
                                            Compound("disposal_type",       "ObjectType",       "Disposal_type"), #Find AT what sort of thing it should be disposed, e.g. a trashbin
                                            Compound("type",                "Dispose_to_object",  "Disposal_type"), #Find objects of that are of type trashbin
                                            Compound("region_of_interest",  "Dispose_to_object",  \
                                                        Compound("point_3d", "X", "Y", "Z"))) #Get locations of those things

            smach.StateMachine.add('LOOK',
                                    states.LookForObjectsAtROI(robot, query_lookat, query_object),
                                    transitions={   'looking':'LOOK',
                                                    'object_found':'SAY_FOUND_SOMETHING',
                                                    'no_object_found':'DETERMINE_EXPLORATION_TARGET',
                                                    'abort':'Aborted'})
            def generate_object_sentence(*args,**kwargs):
                try:
                    answers = robot.reasoner.query(query_dropoff_loc)
                    _type = answers[0]["ObjectType"]
                    dropoff = answers[0]["Disposal_type"]
                    return "I have found a {0}. I'll' dispose it to a {1}".format(_type, dropoff)
                except:
                    return "I have found something"
            smach.StateMachine.add('SAY_FOUND_SOMETHING',
                                    states.Say_generated(robot, sentence_creator=generate_object_sentence),
                                    transitions={ 'spoken':'GRAB' })

            query_grabpoint = Conjunction(  Compound("current_object", "ObjectID"),
                                            Compound("position", "ObjectID", Compound("point", "X", "Y", "Z")))
            smach.StateMachine.add('GRAB',
                                    states.GrabMachine(robot.leftArm, robot, query_grabpoint),
                                    transitions={   'succeeded':'DROPOFF_OBJECT',
                                                    'failed':'HUMAN_HANDOVER' })
            
            smach.StateMachine.add('HUMAN_HANDOVER',
                                    states.Human_handover(robot.leftArm,robot),
                                    transitions={   'succeeded':'RESET_HEAD',
                                                    'failed':'DETERMINE_EXPLORATION_TARGET'})
        
            @smach.cb_interface(outcomes=["done"])
            def reset_head(*args, **kwargs):
                robot.head.reset_position()
                return "done"   
            smach.StateMachine.add( "RESET_HEAD", 
                        smach.CBState(reset_head),
                        transitions={"done":"DROPOFF_OBJECT"})

            smach.StateMachine.add("DROPOFF_OBJECT",
                                    states.Gripper_to_query_position(robot, robot.leftArm, query_dropoff_loc),
                                    transitions={   'succeeded':'DROP_OBJECT',
                                                    'failed':'DROP_OBJECT',
                                                    'target_lost':'DONT_KNOW_DROP'})
            
            smach.StateMachine.add("DONT_KNOW_DROP", 
                                    states.Say(robot, "Now that I fetched this, I'm not sure where to put it. I'll just toss it in a trashbin. Lets hope its not fragile."),
                                    transitions={   'spoken':'DROPOFF_OBJECT_BACKUP'}) #TODO: Dont abort, do something smart!

            query_dropoff_loc_backup = Conjunction( Compound("type",                "Dispose_to_object",  "trashbin"), #Find objects of that are of type trashbin
                                                    Compound("region_of_interest",  "Dispose_to_object",  \
                                                        Compound("point_3d", "X", "Y", "Z"))) #Get locations of those things
            smach.StateMachine.add("DROPOFF_OBJECT_BACKUP",
                                    states.Gripper_to_query_position(robot, robot.leftArm, query_dropoff_loc_backup),
                                    transitions={   'succeeded':'DROP_OBJECT',
                                                    'failed':'DROP_OBJECT',
                                                    'target_lost':'DONT_KNOW_DROP_BACKUP'})

            smach.StateMachine.add("DONT_KNOW_DROP_BACKUP", 
                                    states.Say(robot, "Now that I fetched this, I don't know where to put it. Silly me!"),
                                    transitions={   'spoken':'Aborted'}) #TODO: Dont abort, do something smart!


            # smach.StateMachine.add( 'DRIVE_TO_DROPOFF',
            #                         states.Navigate_to_queryoutcome(robot, query_dropoff_loc, X="X", Y="Y", Phi="Phi"),
            #                         transitions={   "arrived":"PLACE_OBJECT",
            #                                         "unreachable":'RETURN',
            #                                         "preempted":'Aborted',
            #                                         "goal_not_defined":'Aborted'})                
            
            # smach.StateMachine.add( 'PLACE_OBJECT', states.Place_Object(robot.leftArm,robot),
            #                         transitions={   'object_placed':'CARR_POS2'})
            smach.StateMachine.add( 'DROP_OBJECT', states.SetGripper(robot, robot.leftArm, gripperstate=0, drop_from_frame="/grippoint_left"), #open
                                    transitions={   'state_set':'CLOSE_AFTER_DROP'})
            smach.StateMachine.add( 'CLOSE_AFTER_DROP', states.SetGripper(robot, robot.leftArm, gripperstate=1), #close
                                    transitions={   'state_set':'RESET_ARM'})
            smach.StateMachine.add('RESET_ARM', 
                                    states.ArmToPose(robot, robot.leftArm, (-0.0830 , -0.2178 , 0.0000 , 0.5900 , 0.3250 , 0.0838 , 0.0800)), #Copied from demo_executioner NORMAL
                                    transitions={   'done':'MARK_DISPOSED',
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
                    
            smach.StateMachine.add( 'RETURN', states.Navigate_exact(robot, 0,0,0),
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
    
    amigo = Amigo(wait_services=True)

    machine = Cleanup(amigo)

    machine.execute()
