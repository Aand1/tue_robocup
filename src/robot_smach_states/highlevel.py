#! /usr/bin/env python
import roslib; 
import rospy
import smach

from state import State

import utility_states
import human_interaction
import perception
import navigation
import manipulation
import reasoning

from psi import Conjunction, Compound, Sequence
import robot_skills.util.msg_constructors as msgs
from designators.designator import Designator, VariableDesignator, PointStampedOfEntityDesignator

class StartChallengeRobust(smach.StateMachine):
    """Initialize, wait for the door to be opened and drive inside"""

    def __init__(self, robot, initial_pose, use_entry_points = False):
        smach.StateMachine.__init__(self, outcomes=["Done", "Aborted", "Failed"]) 
        assert hasattr(robot, "base")
        assert hasattr(robot, "reasoner")
        assert hasattr(robot, "speech")

        with self:
            smach.StateMachine.add( "INITIALIZE", 
                                    utility_states.Initialize(robot), 
                                    transitions={   "initialized"   :"INSTRUCT_WAIT_FOR_DOOR",
                                                    "abort"         :"Aborted"})

            smach.StateMachine.add("INSTRUCT_WAIT_FOR_DOOR",
                                    human_interaction.Say(robot, [  "Hi there, I will now wait until the door is opened"], block=False),
                                    transitions={   "spoken":"ASSESS_DOOR"})


             # Start laser sensor that may change the state of the door if the door is open:
            smach.StateMachine.add( "ASSESS_DOOR", 
                                    perception.Read_laser(robot, "entrance_door"),
                                    transitions={   "laser_read":"WAIT_FOR_DOOR"})       
            
            # define query for the question wether the door is open in the state WAIT_FOR_DOOR
            dooropen_query = robot.reasoner.state("entrance_door","open")
        
            # Query if the door is open:
            smach.StateMachine.add( "WAIT_FOR_DOOR", 
                                    reasoning.Ask_query_true(robot, dooropen_query),
                                    transitions={   "query_false":"ASSESS_DOOR",
                                                    "query_true":"DOOR_OPEN",
                                                    "waiting":"DOOR_CLOSED",
                                                    "preempted":"Aborted"})

            # If the door is still closed after certain number of iterations, defined in Ask_query_true 
            # in perception.py, amigo will speak and check again if the door is open
            smach.StateMachine.add( "DOOR_CLOSED",
                                    human_interaction.Say(robot, "Door is closed, please open the door"),
                                    transitions={   "spoken":"ASSESS_DOOR"}) 

            smach.StateMachine.add( "DOOR_OPEN",
                                    human_interaction.Say(robot, "Door is open!", block=False),
                                    transitions={   "spoken":"INIT_POSE"}) 

            # Initial pose is set after opening door, otherwise snapmap will fail if door is still closed and initial pose is set,
            # since it is thinks amigo is standing in front of a wall if door is closed and localization can(/will) be messed up.
            smach.StateMachine.add('INIT_POSE',
                                utility_states.SetInitialPose(robot, initial_pose),
                                transitions={   'done':'ENTER_ROOM',
                                                'preempted':'Aborted',  # This transition will never happen at the moment.
                                                'error':'ENTER_ROOM'})  # It should never go to aborted.

            # Enter the arena with force drive as back-up
            smach.StateMachine.add('ENTER_ROOM',
                                    EnterArena(robot, initial_pose, use_entry_points),
                                    transitions={   "done":"Done" })
            

# Enter the arena with force drive as back-up
class EnterArena(smach.StateMachine):

    class GotoEntryPoint(State):
        def __init__(self, robot, initial_pose, use_entry_points = False):
            State.__init__(self, locals(), outcomes=["no_goal" , "found", "not_found", "all_unreachable"])

        def run(self, robot, initial_pose, use_entry_points):
            print "TODO: IMPLEMENT THIS STATE"
            return "no_goal"

    class ForceDrive(State):
        def __init__(self, robot):
            State.__init__(self, locals(), outcomes=["done"])

        def execute(self, robot):            
            #self.robot.speech.speak("As a back-up scenario I will now drive through the door with my eyes closed.", block=False)  # Amigo should not say that it uses force drive, looks stupid.
            rospy.loginfo("AMIGO uses force drive as a back-up scenario!")
            robot.base.force_drive(0.25, 0, 0, 5.0)    # x, y, z, time in seconds
            return "done"

    def __init__(self, robot, initial_pose, use_entry_points = False):
        smach.StateMachine.__init__(self,outcomes=['done'])
        self.robot = robot

        with self:
            # If the door is open, amigo will say that it goes to the registration table
            smach.StateMachine.add( "THROUGH_DOOR",
                                    human_interaction.Say(robot, "I will start my task now", block=False),
                                    transitions={   "spoken":"FORCE_DRIVE_THROUGH_DOOR"}) 

            smach.StateMachine.add('FORCE_DRIVE_THROUGH_DOOR',
                                    self.ForceDrive(robot),
                                    transitions={   "done":"GO_TO_ENTRY_POINT"})

            smach.StateMachine.add('GO_TO_ENTRY_POINT',
                                    self.GotoEntryPoint(robot, initial_pose, use_entry_points),
                                    transitions={   "found":"done", 
                                                    "not_found":"GO_TO_ENTRY_POINT", 
                                                    "no_goal":"done",
                                                    "all_unreachable":"done"})

                        
class GotoMeetingPoint(State):
    def __init__(self, robot):
        State.__init__(self, locals(), outcomes=["no_goal" , "found", "not_found", "all_unreachable"])

    def run(self, robot):
        print "TODO: IMPLEMENT THIS STATE!"
        return "no_goal"


class VisitQueryPoi(smach.StateMachine):
    #TODO 3-12-2014: We don't have to keep track of what is visited and unreachable anymore using the reasoner, we can use a VariableDesignator for that now.
    #                The will reduce the complexity of this beast quite a lot.  
    """Go to the outcome of a point_of_interest-query and mark that identifier as visited or unreachable.
    When all matches are visited, the outcome is all_matches_tried"""
    def __init__(self, robot, poi_designator):
        """Go to the point that poi_designator resolves to. 
        If that poi is unreachable, this state machine will try to go to a different point, after calling poi_designator.next()
        @param poi_designator resolves to a point to visit. 
        """
        smach.StateMachine.__init__(self, outcomes=["arrived", "unreachable", "preempted", "goal_not_defined", "all_matches_tried"]) #visit_query_outcome also defines 'all_matches_tried'

        self.robot = robot
        visited = VariableDesignator([])
        unreachable = VariableDesignator([])

        with self:
            smach.StateMachine.add( 'SELECT_OBJECT_TO_VISIT',
                                    reasoning.Select_object(robot, decorated_query,     #Find an answer to this query
                                                            visit_label,                #And set it as the currently_visiting
                                                            object_variable=self.identifier),        
                                    transitions={'selected':'VISIT_OBJECT',
                                                 'no_answers':'CHECK_UNDECORATED_MATCHES'})

            #If we can find a match for the undecorated query, that means there are objects, but that we all tried them
            smach.StateMachine.add( 'CHECK_UNDECORATED_MATCHES',
                                    reasoning.Ask_query_true(robot, poi_query),
                                    transitions={'query_false':'goal_not_defined',
                                                 'query_true':'all_matches_tried',
                                                 'waiting':'goal_not_defined',          #this transition should no occur
                                                 'preempted':'preempted'})
            
            smach.StateMachine.add("VISIT_OBJECT",
                                    navigation.NavigateGeneric(self.robot, 
                                                               lookat_query=current_goal_query),
                                    transitions={   'arrived'         :'ASSERT_VISITED',
                                                    'unreachable'     :'ASSERT_UNREACHABLE',
                                                    'preempted'       :'preempted',
                                                    'goal_not_defined':'goal_not_defined'})

            smach.StateMachine.add( 'ASSERT_VISITED',
                                    reasoning.Select_object(robot, current_goal_query,  #Find the object we just went to
                                                            "visited",                  #And set it as being visited
                                                            retract_previous=False,     #And keep them visited, don't try to go there again
					                    object_variable=self.identifier),
                                    transitions={'selected':'arrived',
                                                 'no_answers':'goal_not_defined'})      #This should never occur

            smach.StateMachine.add( 'ASSERT_UNREACHABLE',
                                    reasoning.Select_object(robot, current_goal_query,  #Find the object we just tried to go to
                                                            "unreachable",              #And set it as being unreachable
                                                            retract_previous=False,     #And keep them unreachable, don't try to go there again
					                    object_variable=self.identifier),
                                    transitions={'selected':'unreachable',
                                                 'no_answers':'goal_not_defined'})      #This should never occur


class GetObject(smach.StateMachine):
    def __init__(self, robot, side, lookat_designator, 
                                    type_designator=Designator(""), 
                                    max_duration=rospy.Duration(3600)):
        """
        @param type_designator a designator resolving to the class/type of the object we want to grab. By default, we take any type.
        @param lookat_designator resolves to a PointStamped to look at.
            When looking at that entity, we hope to see the actual object we want to grab.
            Defaults to something in base_link"""
        smach.StateMachine.__init__(self, outcomes=["Done", "Aborted", "Failed", "Timeout"])

        self.robot = robot
        self.side = side
        self.type_designator = type_designator

        self.lookat_designator = lookat_designator
        # lookatquery = Conjunction(
        #                         Compound("currently_visiting","ID"),
        #                         Compound("point_of_interest", "ID", Compound("point_3d", "X", "Y", "Z")))

        self.entity_designator = VariableDesignator("dummy_entity") #Variable because LookForObjectsAtROI writes an antity

        assert hasattr(robot, "base")
        assert hasattr(robot, "reasoner")
        assert hasattr(robot, "perception")

        with self:

            smach.StateMachine.add('SET_TIME_MARKER',
                                    utility_states.SetTimeMarker(robot, "get_object_start"),
                                    transitions={   'done':'DRIVE_TO_SEARCHPOS' })            
                                                    
            smach.StateMachine.add("DRIVE_TO_SEARCHPOS",
                                    # human_interaction.Say(robot, ["I should visit the next region of interest, \
                                    #                                but that is not yet implemented with designators"], block=False),
                                    # transitions={ 'spoken':'SAY_LOOK_FOR_OBJECTS' })
                                    VisitQueryPoi(self.robot, poi_query=self.roi_query, identifier=self.roi_identifier, visit_label="currently_visiting"),
                                    transitions={   'arrived'         :'SAY_LOOK_FOR_OBJECTS',
                                                    'unreachable'     :'DRIVE_TO_SEARCHPOS',
                                                    'preempted'       :'RESET_HEAD_AND_SPINDLE_UPON_ABORTED',
                                                    'goal_not_defined':'RESET_HEAD_AND_SPINDLE_UPON_FAILURE',
                                                    'all_matches_tried':'RESET_HEAD_AND_SPINDLE_UPON_FAILURE'})    # End State

            smach.StateMachine.add("SAY_LOOK_FOR_OBJECTS", 
                                    human_interaction.Say(robot, ["Lets see what I can find here."],block=False),
                                    transitions={   'spoken':'LOOK'})

            smach.StateMachine.add('LOOK',
                                    perception.LookForObjectsAtROI(robot, self.lookat_designator, self.type_designator, self.entity_designator),
                                    transitions={   'looking':'LOOK',
                                                    'object_found':'SAY_FOUND_SOMETHING',
                                                    'no_object_found':'RESET_HEAD_AND_SPINDLE',
                                                    'abort':'RESET_HEAD_AND_SPINDLE_UPON_ABORTED'})      # End State

            #smach.StateMachine.add('RESET_HEAD_AND_SPINDLE',
            #                        utility_states.ResetHeadSpindle(robot),
            #                        transitions={   'done':'CHECK_TIME'})   # End State
            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'DRIVE_TO_SEARCHPOS'})   # End State

            smach.StateMachine.add('CHECK_TIME',
                                    utility_states.CheckTime(robot, "get_object_start", max_duration),
                                    transitions={   'ok':'DRIVE_TO_SEARCHPOS',
                                                    'timeout':'RESET_HEAD_AND_SPINDLE_UPON_TIMEOUT' })   # End State
                                                    
            smach.StateMachine.add('SAY_FOUND_SOMETHING',
                                    human_interaction.Say(robot, ["I have found something"],block=False),
                                    transitions={ 'spoken':'GRAB' })

            # smach.StateMachine.add('SAY_FOUND_SOMETHING_BEFORE',
            #                         human_interaction.Say(robot, ["I have seen the desired object before!"],block=False),
            #                         transitions={ 'spoken':'GRAB' })

            smach.StateMachine.add('GRAB',
                                    manipulation.GrabMachine(self.side, robot, self.entity_designator),
                                    transitions={   'succeeded':'RESET_HEAD_AND_SPINDLE_UPON_SUCCES',
                                                    'failed':'SAY_FAILED_GRABBING' })  

            smach.StateMachine.add('SAY_FAILED_GRABBING',
                                    human_interaction.Say(robot, ["Although I was not able to grab the object, you should be able to find it in \
                                                                   front of me! I will continue to grab another one for as long as I have the time."], block=False),
                                    transitions={ 'spoken':'MARK_DISPOSED' })

            #Mark the current_object as disposed
            @smach.cb_interface(outcomes=['done'])
            def deactivate_current_object(userdata):
                try:
                    #robot.speech.speak("I need some debugging in cleanup, please think with me here.")
                    #import ipdb; ipdb.set_trace()
                    entityID = self.entity_designator.resolve()
                    robot.reasoner.query(Compound("assertz", Compound("disposed", entityID)))
                    rospy.loginfo("objectID = {0} is DISPOSED".format(entityID))

                    try:
                        robot.reasoner.detach_all_from_gripper("/amigo/grippoint_left")
                    except KeyError, ke:
                        rospy.loginfo("Could not detach object from gripper, do not know which ID: {0}".format(ke))
                    rospy.loginfo("object should be detached from gripper!")

                except:
                    pass #Just continue
                return 'done'
            smach.StateMachine.add('MARK_DISPOSED', smach.CBState(deactivate_current_object),
                                    transitions={'done':'CHECK_TIME_AFTER_FAILED_GRAB'}) 

            smach.StateMachine.add('CHECK_TIME_AFTER_FAILED_GRAB',
                                    utility_states.CheckTime(robot, "get_object_start", max_duration),
                                    transitions={   'ok':'DRIVE_TO_SEARCHPOS',
                                                    'timeout':'RESET_HEAD_AND_SPINDLE_UPON_TIMEOUT' })   # End State

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE_UPON_ABORTED',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'Aborted'})   # End State

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE_UPON_FAILURE',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'Failed'})   # End State

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE_UPON_TIMEOUT',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'Timeout'})   # End State            

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE_UPON_SUCCES',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'Done'})   # End State

class Say_and_Navigate(smach.StateMachine):
    ## This class gives the ability to say something and at the same time start to navigate to the desired location.
    ## This makes the robot faster and 'look' smarter.
    ##
    ## The input_keys should be defined as follows:
    ## input_keys = ['navigate_named','location_in_database'] 
    ## or
    ## input_keys = ['navigate_goal_location',*3 choices: loc_from, loc_to or object_action*] 
    ## or
    ## input_keys = ['navigate_to_queryoutcome','query'] 
    ## or
    ## input_keys = ['navigate_exact',2.1,0.1,0.2]

    def __init__(self, 
                 sentence, input_keys, robot):
        smach.StateMachine.__init__(self, 
                                    outcomes=["succeeded", "not_at_loc"])
        self.robot = robot
        self.say_sentence = sentence
        
        self.navigate_option = input_keys[0]

        if self.navigate_option == 'navigate_named' or self.navigate_option == 'navigate_goal_location':
            self.navigate_named_location = input_keys[1]
        elif self.navigate_option == 'navigate_exact':
            self.navigate_x = input_keys[1]
            self.navigate_y = input_keys[2]
            self.navigate_phi = input_keys[3]
        elif self.navigate_option == 'navigate_to_queryoutcome':     
            self.nav_query = input_keys[1]

        with self:
            cc = smach.Concurrence(outcomes = ['succeeded', 'not_at_loc'],
                                   default_outcome = 'not_at_loc',
                                   outcome_map = {'succeeded':{'EXECUTE_SAY':'spoken',
                                                                'GO_TO_LOCATION':'arrived'},
                                                  'not_at_loc':{'EXECUTE_SAY':'spoken',
                                                                'GO_TO_LOCATION':'preempted'},
                                                  'not_at_loc':{'EXECUTE_SAY':'spoken',
                                                                'GO_TO_LOCATION':'unreachable'},
                                                  'not_at_loc':{'EXECUTE_SAY':'spoken',
                                                                'GO_TO_LOCATION':'goal_not_defined'}})

            with cc:
                smach.Concurrence.add("EXECUTE_SAY",
                                       human_interaction.Say(robot, self.say_sentence))
                if self.navigate_option == 'navigate_named':
                    smach.Concurrence.add('GO_TO_LOCATION', 
                                                navigation.Navigate_named(robot, self.navigate_named_location))
                elif self.navigate_option == 'navigate_exact':
                    smach.Concurrence.add('GO_TO_LOCATION', 
                                                navigation.Navigate_exact(robot,self.navigate_x,self.navigate_y,self.navigate_phi))
                elif self.navigate_option == 'navigate_goal_location':
                    smach.Concurrence.add('GO_TO_LOCATION', 
                                                navigation.Navigate_goal_location(robot, self.navigate_named_location))
                elif self.navigate_option == 'navigate_to_queryoutcome':
                    smach.Concurrence.add('GO_TO_LOCATION', 
                                                navigation.Navigate_to_queryoutcome(robot, self.nav_query, X="X", Y="Y", Phi="Phi"))
                
            smach.StateMachine.add('SUB_CONT_SAY_GO',
                                    cc)

class PointObject(smach.StateMachine):
    def __init__(self, robot, side, roi_query, roi_identifier="Poi", object_query=None, object_identifier="Object", max_duration=rospy.Duration(3600)):
        smach.StateMachine.__init__(self, outcomes=["Done", "Aborted", "Failed", "Timeout"])

        self.robot = robot
        self.side = side
        self.roi_query = roi_query
        self.object_query = object_query
        self.roi_identifier =roi_identifier

        rospy.logwarn("roi_query = {0}".format(roi_query))

        lookatquery = Conjunction(
                                Compound("currently_visiting","ID"),
                                Compound("point_of_interest", "ID", Compound("point_3d", "X", "Y", "Z")))

        assert hasattr(robot, "base")
        assert hasattr(robot, "reasoner")
        assert hasattr(robot, "perception")

        with self:
            #import ipdb; ipdb.set_trace()
            smach.StateMachine.add('SET_TIME_MARKER',
                                    utility_states.SetTimeMarker(robot, "get_object_start"),
                                    transitions={   'done':'DRIVE_TO_SEARCHPOS' })

            # smach.StateMachine.add('CHECK_OBJECT_QUERY',                                            
            #                         Check_object_found_before(robot, self.object_query),
            #                         transitions={   'object_found':'SAY_FOUND_SOMETHING_BEFORE',
            #                                         'no_object_found':'RESET_HEAD_AND_SPINDLE_UPON_FAILURE' })

            # smach.StateMachine.add("DRIVE_TO_SEARCHPOS",
            #                         navigation.Visit_query_outcome_3d(self.robot, 
            #                                                           self.roi_query, 
            #                                                           x_offset=0.7, y_offset=0.0001,
            #                                                           identifier=object_identifier),  #TODO Bas: when this is 0.0, amingo_inverse_reachability returns a 0,0,0,0,0,0,0 pose
            #                         transitions={   'arrived':'SAY_LOOK_FOR_OBJECTS',
            #                                         'unreachable':'DRIVE_TO_SEARCHPOS',
            #                                         'preempted':'RESET_HEAD_AND_SPINDLE_UPON_ABORTED',
            #                                         'goal_not_defined':'RESET_HEAD_AND_SPINDLE_UPON_FAILURE',
            #                                         'all_matches_tried':'RESET_HEAD_AND_SPINDLE_UPON_FAILURE'})


            smach.StateMachine.add("DRIVE_TO_SEARCHPOS",
                                    VisitQueryPoi(self.robot, poi_query=self.roi_query, identifier=self.roi_identifier, visit_label="currently_visiting"),
                                    transitions={   'arrived'         :'SAY_LOOK_FOR_OBJECTS',
                                                    'unreachable'     :'DRIVE_TO_SEARCHPOS',
                                                    'preempted'       :'RESET_HEAD_AND_SPINDLE_UPON_ABORTED',
                                                    'goal_not_defined':'RESET_HEAD_AND_SPINDLE_UPON_FAILURE',
                                                    'all_matches_tried':'RESET_HEAD_AND_SPINDLE_UPON_FAILURE'})    # End State


            smach.StateMachine.add("SAY_LOOK_FOR_OBJECTS", 
                                    human_interaction.Say(robot, ["Lets see if I can find the object."],block=False),
                                    transitions={   'spoken':'LOOK'})

            smach.StateMachine.add('LOOK',
                                    perception.LookForObjectsAtROI(robot, lookatquery, self.object_query),
                                    transitions={   'looking':'LOOK',
                                                    'object_found':'SAY_FOUND_SOMETHING',
                                                    'no_object_found':'RESET_HEAD_AND_SPINDLE',
                                                    'abort':'RESET_HEAD_AND_SPINDLE_UPON_ABORTED'})

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'CHECK_TIME'})   # End State

            smach.StateMachine.add('CHECK_TIME',
                                    utility_states.CheckTime(robot, "get_object_start", max_duration),
                                    transitions={   'ok':'DRIVE_TO_SEARCHPOS',
                                                    'timeout':'RESET_HEAD_AND_SPINDLE_UPON_TIMEOUT' })   # End State
                                                    
            smach.StateMachine.add('SAY_FOUND_SOMETHING',
                                    human_interaction.Say(robot, ["I have found what you are looking for and I will try to point at it!"],block=False),
                                    transitions={ 'spoken':'POINT' })

            # smach.StateMachine.add('SAY_FOUND_SOMETHING_BEFORE',
            #                         human_interaction.Say(robot, ["I have seen the desired object before!"],block=False),
            #                         transitions={ 'spoken':'POINT' })

            query_point = Conjunction(  Compound("current_object", "ObjectID"),
                                            Compound("position", "ObjectID", Compound("point", "X", "Y", "Z")))

            smach.StateMachine.add('POINT',
                                    manipulation.PointMachine(self.side, robot, query_point),
                                    transitions={   'succeeded':'RESET_HEAD_AND_SPINDLE_UPON_SUCCES',
                                                    'failed':'SAY_FAILED_POINTING' }) 

            smach.StateMachine.add('SAY_FAILED_POINTING',
                                    human_interaction.Say(robot, ["Although I was not able to point at the object, you should be able to find it in \
                                                                   front of me! I will continue to find another one for as long as I have the time."], block=False),
                                    transitions={ 'spoken':'MARK_DISPOSED' })

            #Mark the current_object as disposed
            @smach.cb_interface(outcomes=['done'])
            def deactivate_current_object(userdata):
                try:
                    #robot.speech.speak("I need some debugging in cleanup, please think with me here.")
                    #import ipdb; ipdb.set_trace()
                    objectID = robot.reasoner.query(Compound("current_object", "Disposed_ObjectID"))[0]["Disposed_ObjectID"]
                    robot.reasoner.query(Compound("assertz", Compound("disposed", objectID)))
                    rospy.loginfo("objectID = {0} is DISPOSED".format(objectID))

                    try:
                        robot.reasoner.detach_all_from_gripper("/amigo/grippoint_left")
                    except KeyError, ke:
                        rospy.loginfo("Could not detach object from gripper, do not know which ID: {0}".format(ke))
                    rospy.loginfo("object should be detached from gripper!")

                except:
                    pass #Just continue
                return 'done'
            smach.StateMachine.add('MARK_DISPOSED', smach.CBState(deactivate_current_object),
                                    transitions={'done':'CHECK_TIME_AFTER_FAILED_POINT'}) 

            smach.StateMachine.add('CHECK_TIME_AFTER_FAILED_POINT',
                                    utility_states.CheckTime(robot, "get_object_start", max_duration),
                                    transitions={   'ok':'DRIVE_TO_SEARCHPOS',
                                                    'timeout':'RESET_HEAD_AND_SPINDLE_UPON_TIMEOUT' })   # End State

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE_UPON_ABORTED',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'Aborted'})   # End State

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE_UPON_FAILURE',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'Failed'})   # End State

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE_UPON_TIMEOUT',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'Timeout'})   # End State            

            smach.StateMachine.add('RESET_HEAD_AND_SPINDLE_UPON_SUCCES',
                                    utility_states.ResetHeadSpindle(robot),
                                    transitions={   'done':'Done'})   # End State


class Say_and_point_location(smach.StateMachine):
    def __init__(self, 
                 sentence, side, robot):
        smach.StateMachine.__init__(self, 
                                    outcomes=["succeeded"])
        self.robot = robot
        self.say_sentence = sentence
        self.side = side

        with self:
            cc = smach.Concurrence(outcomes = ['succeeded'],
                                   default_outcome = 'succeeded',
                                   outcome_map = {'succeeded':{'EXECUTE_SAY':'spoken',
                                                               'POINT_AT_LOCATION':'pointed'}})
                                                  
            with cc:
                smach.Concurrence.add("EXECUTE_SAY",
                                       human_interaction.Say(robot, self.say_sentence))
                smach.Concurrence.add("POINT_AT_LOCATION",
                                       manipulation.Point_location_hardcoded(robot, self.side))

            smach.StateMachine.add('SUB_CONT_SAY_POINT',
                                    cc)


class LookAtItem(smach.StateMachine):
    """Enable a perception module(s), wait for a query that uses percepts from that module and look at the closest match to the item_query.
    The query should use ObjectID to mark the possible object's ID in the query"""

    face_in_front_query = Conjunction(Compound("property_expected", "ObjectID", "class_label", "face"),
                                          Compound("property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")),
                                          Compound("property_expected", "ObjectID", "position", Sequence("X","Y","Z")))
    
    anything_in_front_query = Conjunction(Compound("property_expected", "ObjectID", "class_label", "Anything"),
                                          Compound("property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")),
                                          Compound("property_expected", "ObjectID", "position", Sequence("X","Y","Z")))
    
    person_in_front_query = Conjunction(Compound("property_expected", "ObjectID", "class_label", "person"),
                                          Compound("property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")),
                                          Compound("property_expected", "ObjectID", "position", Sequence("X","Y","Z")))


    def __init__(self, robot, perception_modules, item_query, timeout=10):
        smach.StateMachine.__init__(self, outcomes=['Done', 'Aborted', 'Failed'])

        self.robot = robot

        item_to_look_at_predicate = "item_to_look_at"
        item_to_look_at = Conjunction(   Compound(item_to_look_at_predicate, "ObjectID"), 
                                         Compound("property_expected", "ObjectID", "position", Sequence("X", "Y", "Z")))

        with self:
            smach.StateMachine.add( "WAIT_FOR_POSSIBLE_DETECTION",
                                    utility_states.Wait_queried_perception(robot, perception_modules, item_query, timeout=3),
                                    transitions={   "query_true"    :"SELECT_ITEM_TO_LOOK_AT",
                                                    "timed_out"     :"Failed",
                                                    "preempted"     :"Aborted"})

            smach.StateMachine.add( 'SELECT_ITEM_TO_LOOK_AT', 
                                    reasoning.Select_object(robot, item_query, item_to_look_at_predicate),
                                    transitions={   'selected'      :'LOOK_AT_POSSIBLE_PERSON',
                                                    'no_answers'    :'Failed'})

            smach.StateMachine.add('LOOK_AT_POSSIBLE_PERSON',
                                    perception.LookAtPoint(robot, item_to_look_at),
                                    transitions={   'looking'       :'RETRACT_ITEM_TO_LOOK_AT',
                                                    'no_point_found':'Failed',
                                                    'abort'         :'Aborted'})  

            smach.StateMachine.add( 'RETRACT_ITEM_TO_LOOK_AT', 
                                    reasoning.Retract_facts(robot, Compound(item_to_look_at_predicate, "Item")),
                                    transitions={   'retracted'     :'Done'})
