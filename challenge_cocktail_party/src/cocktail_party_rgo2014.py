#! /usr/bin/env python
import roslib; roslib.load_manifest('challenge_cocktail_party')
import rospy
import os
import roslib.packages as p
import smach_ros

from speech_interpreter.srv import AskUser

from robot_skills.amigo import Amigo

from robot_smach_states import *
from psi import Compound, Sequence, Conjunction, Term
import robot_skills.util.msg_constructors as msgs
from geometry_msgs.msg import PoseStamped, Pose

from pein_srvs.srv import SetObjects


grasp_arm = "left"
#grasp_arm = "right"

#===============================TODOs===========================================
# - head goal and base goal must correspond
#===============================================================================

#================================ Bugs/Issues ==================================
#
#===============================================================================

#========================== Other ideas for executive improvement ==============
#
#===============================================================================
class DeleteModels(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["done"])
        self.robot = robot
        self.set_objects = rospy.ServiceProxy('/pein/set_object_models',SetObjects)

    def execute(self, userdata=None):

        response = self.set_objects(['orange_juice','fruit_juice','ice_tea','coffee','beer'])
        print response
        folder = p.get_pkg_dir('pein_face_recognition')+'/models'
        #folder = '/path/to/folder'
        for the_file in os.listdir(folder):
            file_path = os.path.join(folder, the_file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception, e:
                print e
        rospy.loginfo("Deleted models from {0}".format(folder))
        return 'done'

class WaitForPerson(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["waiting", "unknown_person", "known_person"])
        self.robot = robot

    def execute(self, userdata=None):

        # Use reasoner to iterate over no of waited times (if face seg won't work we will continue to asking names/serving drinks!)
        return_result = self.robot.reasoner.query(Compound("waited_times_no", "X"))
        waited_no = float(return_result[0]["X"])  
        if waited_no == 3:
            # Reset the counter for waiting
            waited_no = 0;
            self.robot.reasoner.query(Compound("retractall", Compound("waited_times_no", "X")))
            self.robot.reasoner.query(Compound("assertz",Compound("waited_times_no", waited_no)))
            self.robot.speech.speak("Let's try")
            return("unknown_person")


        # reset robo pose
        self.robot.spindle.reset()
        self.robot.reasoner.reset()
        self.robot.head.set_pan_tilt(tilt=-0.2)
        self.robot.speech.speak("Please step in front of me to order your drink.")

        # prepare query for detected person
        query_detect_person = Conjunction(Compound("property_expected", "ObjectID", "class_label", "face"),
                                          Compound("property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")),
                                          Compound("property_expected", "ObjectID", "position", Sequence("X","Y","Z")))

        # start face segmentation node
        self.response_start = self.robot.perception.toggle(['face_segmentation'])

        if self.response_start.error_code == 0:
            rospy.loginfo("Face segmentation has started correctly")
        elif self.response_start.error_code == 1:
            rospy.loginfo("Face segmentation failed to start")
            self.robot.speech.speak("I was not able to start face segmentation.")
            waited_no += 1
            rospy.loginfo("Waited {0} time(s).".format(waited_no))
            self.robot.reasoner.query(Compound("retractall", Compound("waited_times_no", "X")))
            self.robot.reasoner.query(Compound("assertz",Compound("waited_times_no", waited_no)))
            return "waiting"

        # wait until the query detected person is true
        wait_machine = Wait_query_true(self.robot, query_detect_person, 10)
        wait_result = wait_machine.execute()

        # turn off face segmentation
        rospy.loginfo("Face segmentation will be stopped now")
        self.response_stop = self.robot.perception.toggle([])
        
        if self.response_stop.error_code == 0:
            rospy.loginfo("Face segmentation is stopped")
        elif self.response_stop.error_code == 1:
            rospy.loginfo("Failed stopping face segmentation")

        # if the query timed out...
        if wait_result == "timed_out":
            self.robot.speech.speak("Please, don't keep me waiting.")
            waited_no += 1
            rospy.loginfo("Waited {0} time(s).".format(waited_no))
            self.robot.reasoner.query(Compound("retractall", Compound("waited_times_no", "X")))
            self.robot.reasoner.query(Compound("assertz",Compound("waited_times_no", waited_no)))
            return "waiting"
        elif wait_result == "preempted":
            rospy.logerr("Waiting for person was preemted... I don't even know what that means!")
            return "waiting"
        # if the query succeeded
        elif wait_result == "query_true":
            answers = self.robot.reasoner.query(query_detect_person)
            # get the person location
            possible_locations = [( float(answer["X"]), 
                                    float(answer["Y"]), 
                                    float(answer["Z"])) for answer in answers]

            x,y,z = possible_locations[0]

            if z > 1.5:
                self.robot.spindle.high()
                rospy.logdebug("Spindle should come up now!")

            # look at the person
            lookat_point = msgs.PointStamped(x,y,z)
            rospy.loginfo("AMIGO should look at person now. (x = {0}, y = {1}, z = {2})".format(x,y,z))
            self.robot.head.send_goal(lookat_point,timeout=0)

            # Reset the counter for waiting for person
            waited_no = 0;
            self.robot.reasoner.query(Compound("retractall", Compound("waited_times_no", "X")))
            self.robot.reasoner.query(Compound("assertz",Compound("waited_times_no", waited_no)))

            # go to Unknown Person state
            return "unknown_person"
         

            # res = self.robot.reasoner.query(Compound("property_expected", "ObjectID", "name", "Name"))
            # if not res:
            #     return "unknown_person"
            # else:
            #     self.robot.speech.speak("Hello " + str(res[0]["Name"]) + "!")
            #     return "known_person"

# class LearnPersonName(smach.State):
#     def __init__(self, robot):
#         smach.State.__init__(self, outcomes=["learned" , "failed"])
#         self.robot = robot

#     def execute(self, userdata=None):
#         self.robot.reasoner.query(Compound("retractall", Compound("current_person", "X")))        

#         q_state = Timedout_QuestionMachine( robot=self.robot,
#                                             default_option = "john", 
#                                             sentence = "Well hello there! I don't know you yet. Can you please tell me your name?", 
#                                             options = { "john"   :Compound("current_person", "john"),
#                                                         "richard":Compound("current_person", "richard"),
#                                                         "alice"  :Compound("current_person", "alice")
#                                                       })
        
#         res = q_state.execute()
#         if res == "answered":
#             return_result = self.robot.reasoner.query(Compound("current_person", "Person"))        
#             if not return_result:
#                 self.robot.speech.speak("That's horrible, I forgot who I should bring the drink to!")
#                 return "failed"

#             serving_person = str(return_result[0]["Person"])

#             self.robot.speech.speak("Hello " + serving_person + "!")
#             return "learned"
#         else:
#             return "failed"

class LearnPersonName(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["learned" , "failed"])
        self.robot = robot
        self.ask_user_service_get_learn_person_name = rospy.ServiceProxy('interpreter/ask_user', AskUser)
        self.person_learn_failed = 0

    def execute(self, userdata=None):

        # remove user from current person being queried
        self.robot.reasoner.query(Compound("retractall", Compound("current_person", "X")))

        # ask the name of the user
        self.response = self.ask_user_service_get_learn_person_name("name", 3 , rospy.Duration(60))  # This means that within 3 tries and within 60 seconds an answer is received. 
            
        # test if the name is allowed / exists
        for x in range(0,len(self.response.keys)):
            if self.response.keys[x] == "answer":
                response_answer = self.response.values[x]

        # if no answer was found / unsupported name
        if response_answer == "no_answer" or response_answer == "wrong_answer":
            if self.person_learn_failed == 2:
                self.robot.speech.speak("I will call you David")
                response_answer = "david"
                self.person_learn_failed = 3
            if self.person_learn_failed == 1:
                self.robot.speech.speak("I will call you Michael")
                response_answer = "michael"
                self.person_learn_failed = 2
            if self.person_learn_failed == 0:
                self.robot.speech.speak("I will call you Joseph")
                response_answer = "joseph"
                self.person_learn_failed = 1


        # associate the learned name with the current person
        self.robot.reasoner.query(Compound("assert", Compound("current_person", response_answer)))
            
        # ?
        return_result = self.robot.reasoner.query(Compound("current_person", "Person"))        

        # if the name could not be matched...
        if not return_result:
            self.robot.speech.speak("I did not get a name!")
            return "failed"

        # save the name/identifier of the person being served
        serving_person = str(return_result[0]["Person"])

        #self.robot.speech.speak("Hello " + serving_person + "!")
        # Person's name successfully learned
        return "learned"


class Ask_drink(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["done" , "failed"])
        self.robot = robot
        self.ask_user_service_get_drink = rospy.ServiceProxy('interpreter/ask_user', AskUser)
        self.person_learn_failed = 0
        self.drink_learn_failed = 0

    def execute(self, userdata=None):
        # ask the name of the drink
        self.response = self.ask_user_service_get_drink("drink_cocktail", 3 , rospy.Duration(60))  # This means that within 3 tries and within 60 seconds an answer is received. 
            
        # determine if the answer is allowed
        for x in range(0,len(self.response.keys)):
            if self.response.keys[x] == "answer":
                response_answer = self.response.values[x]

        # if the answer is not allwed just assume another possible drink
        if response_answer == "no_answer" or  response_answer == "wrong_answer":
            if self.drink_learn_failed == 2:
                self.robot.speech.speak("I will bring you a fruit juice")
                response_answer = "fruit_juice"
                self.drink_learn_failed = 3
            elif self.drink_learn_failed == 1:
                self.robot.speech.speak("I will bring you a coffee")
                response_answer = "coffee"
                self.drink_learn_failed = 2
            elif self.drink_learn_failed == 0:
                self.robot.speech.speak("I will bring you a ice tea")
                response_answer = "ice_tea"
                self.drink_learn_failed = 1
            else:
                self.robot.speech.speak("I will bring you a fruit juice")
                response_answer = "fruit_juice"

        #import ipdb; ipdb.set_trace()
        # save the requested drink
        self.robot.reasoner.query(Compound("assert", Compound("goal", Compound("serve", response_answer))))
        return "done"

class LearnPersonFaceCustom(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["face_learned" , "learn_failed"])
        self.robot = robot

    def execute(self, userdata=None):

        # find out who we need to return the drink to
        return_result = self.robot.reasoner.query(Compound("current_person", "Person"))        
        if not return_result:
            self.robot.speech.speak("I forgot who I should bring the drink to!")
            return "face_learned"

        # get the name of the person being served
        serving_person = str(return_result[0]["Person"])

        #self.robot.speech.speak("Now, " + serving_person + ", let me have a look at you, such that I can remember you later.")

        # learn the face of the person
        learn_machine = Learn_Person(self.robot, serving_person)
        learn_result = learn_machine.execute()
        self.robot.reasoner.query(Compound("retractall", Compound("goal", "X")))  # Make sure we're not left with a goal from last time

        ## TO CHECK IF OUTCOME IS face_learned or learn_failed and ACT adequatly!
        if learn_result == 'face_learned':
            rospy.loginfo("Face learning succeeded")
        elif learn_result == 'learn_failed':
            rospy.logwarn("Failed learning face, WHAT TO DO!? Just continue to the next state and ask drink.")
        return learn_result

class LookForDrink(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["looking" , "found", "not_found"])
        self.robot = robot

    def execute(self, userdata=None):
        # query requested drink
        return_result = self.robot.reasoner.query(Compound("goal", Compound("serve", "Drink")))

        # if there is no drink requested, return not found
        if not return_result:
            self.robot.speech.speak("I forgot which drink you wanted")
            return "not_found"

        # get the response from the query requested drink
        serving_drink = str(return_result[0]["Drink"])  

        # get the waypoint of where to search, storage_room
        goal_answers = self.robot.reasoner.query(Conjunction(  Compound("=", "Waypoint", Compound("storage_room", "W")),
                                                 Compound("waypoint", "Waypoint", Compound("pose_2d", "X", "Y", "Phi")),
                                                 Compound("not", Compound("visited", "Waypoint"))))

        # if there is no location associated with drinks return not found
        if not goal_answers:
            self.robot.speech.speak("I cannot find your" + serving_drink, block=False)
            looked_no = 0;
            self.robot.reasoner.query(Compound("retractall", Compound("looked_drink_no", "X")))
            self.robot.reasoner.query(Compound("assertz",Compound("looked_drink_no", looked_no)))
            return "not_found"

        # get the number of the looked up drinks up until now
        return_result = self.robot.reasoner.query(Compound("looked_drink_no", "X"))
        looked_no = float(return_result[0]["X"])

        # say different phrases depending on the number of looked up drinks up until now
        if looked_no == 1:
            self.robot.speech.speak("I'm on the move, looking for your " + serving_drink,block=False)
        elif looked_no == 2:
            self.robot.speech.speak("Still on the move looking for your " + serving_drink,block=False)
        else:
            self.robot.speech.speak("I think I know the location of your " + serving_drink,block=False)

        # increment number of looked up drinks drinks
        looked_no += 1

        # update the number of looked up drinks
        self.robot.reasoner.query(Compound("retractall", Compound("looked_drink_no", "X")))
        self.robot.reasoner.query(Compound("assertz",Compound("looked_drink_no", looked_no)))
        rospy.loginfo("Looked at {0}".format(looked_no))

        # for now, take the first goal found
        goal_answer = goal_answers[0]

        goal = (float(goal_answer["X"]), float(goal_answer["Y"]), float(goal_answer["Phi"]))
        waypoint_name = goal_answer["Waypoint"]

        # navigate to the waypoint queried
        nav = NavigateGeneric(self.robot, goal_pose_2d=goal)
        nav_result = nav.execute()

        # assert that this location has been visited
        self.robot.reasoner.query(Compound("assert", Compound("visited", waypoint_name)))

        # If nav_result is unreachable DO NOT stop looking, there are more options, return not_found when list of Waypoints is empty
        if nav_result == "unreachable":                    
            return "looking"
        elif nav_result == "preempted":
            return "looking"

        # we made it to the new goal. Let's have a look to see whether we can find the object here

        # look to points of interest, if there is any, look at it
        roi_answers = self.robot.reasoner.query(Compound("point_of_interest", waypoint_name, Compound("point_3d", "X", "Y", "Z")))
        if roi_answers:
            roi_answer = roi_answers[0]
            self.robot.head.send_goal(msgs.PointStamped(float(roi_answer["X"]), float(roi_answer["Y"]), float(roi_answer["Z"]), "/map"))


        # query for detect object, finishes when something found or timeout!
        query_detect_object = Conjunction(Compound("goal", Compound("serve", "Drink")),
                                          Compound( "property_expected", "ObjectID", "class_label", "Drink"),
                                          Compound( "property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")))


        self.robot.speech.speak("Let's see what I can find here",block=False)

        # start object template matching
        self.response_start = self.robot.perception.toggle(["object_segmentation"])
        # self.response_start = self.robot.perception.toggle(["template_matching"])
 
        if self.response_start.error_code == 0:
            rospy.loginfo("Object segmentation has started correctly")

        elif self.response_start.error_code == 1:
            rospy.loginfo("Object segmentation failed to start")
            self.robot.speech.speak("I cannot recognize your " + serving_drink,block=False)

            looked_no = 0;
            self.robot.reasoner.query(Compound("retractall", Compound("looked_drink_no", "X")))
            self.robot.reasoner.query(Compound("assertz",Compound("looked_drink_no", looked_no)))
            return "not_found"

        wait_machine = Wait_query_true(self.robot, query_detect_object, 7)
        wait_result = wait_machine.execute()

        rospy.loginfo("Object segmentation will be stopped now")
        self.response_stop = self.robot.perception.toggle([])
        
        if self.response_stop.error_code == 0:
            rospy.loginfo("Object segmentation is stopped")

        elif self.response_stop.error_code == 1:
            rospy.loginfo("Failed stopping Object segmentation ")


        # interpret results wait machine
        if wait_result == "timed_out":
            self.robot.speech.speak("Did not find your " + serving_drink,block=False)
            return "looking"
        elif wait_result == "preempted":
            self.robot.speech.speak("Finding drink was preemted",block=False)
            return "looking"
        elif wait_result == "query_true":
            self.robot.speech.speak("Hey, I found your " + serving_drink,block=False)
            looked_no = 0;
            self.robot.reasoner.query(Compound("retractall", Compound("looked_drink_no", "X")))
            self.robot.reasoner.query(Compound("assertz",Compound("looked_drink_no", looked_no)))
            return "found"

class LookForPerson(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["looking" , "found", "not_found"])
        self.robot = robot

    def execute(self, userdata=None):
        
        # find out who we need to return the drink to
        return_result = self.robot.reasoner.query(Compound("current_person", "Person"))

        if not return_result:
            self.robot.speech.speak("I forgot who I should bring the drink to!",block=False)
            return "not_found"

        serving_person = str(return_result[0]["Person"])
        
        # Get the next waypoint in the party room
        goal_answers = self.robot.reasoner.query(Conjunction(  
                                                    Compound("=", "Waypoint", Compound("party_room", "W")),
                                                    Compound("waypoint", "Waypoint", Compound("pose_2d", "X", "Y", "Phi")),
                                                    Compound("not", Compound("visited", "Waypoint"))
                                                            ))

        if not goal_answers:
            return_drink_result = self.robot.reasoner.query(Compound("goal", Compound("serve", "Drink")))
            if return_drink_result:
                serving_drink = str(return_drink_result[0]["Drink"])
                self.robot.speech.speak(str(serving_person) +", I have been looking everywhere. To hand over your " + str(serving_drink),block=False)
            else:
                self.robot.speech.speak(str(serving_person) +", I have been looking everywhere. But could not find you.",block=False)
            return "not_found"

        # for now, take the first goal found
        goal_answer = goal_answers[0]

        self.robot.speech.speak(str(serving_person) + ", I'm on my way!", language="us", personality="kyle", voice="default", mood="excited",block=False)

        # convert response location to numbers
        goal = (float(goal_answer["X"]), float(goal_answer["Y"]), float(goal_answer["Phi"]))
        waypoint_name = goal_answer["Waypoint"]

        # go to waypoint
        nav = NavigateGeneric(self.robot, goal_pose_2d=goal)
        nav_result = nav.execute()
        self.robot.reasoner.query(Compound("assert", Compound("visited", waypoint_name)))

        if nav_result == "unreachable":                    
            return "looking"
        elif nav_result == "preempted":
            return "looking"

        # we made it to the new goal. Let's have a look to see whether we can find the person here
        self.robot.head.set_pan_tilt(tilt=-0.2)
        self.robot.spindle.reset()

        self.robot.speech.speak("Let me see who I can find here") # Blocking to avoid false positives by moving head
        
        # turn on face segmentation
        self.response_start = self.robot.perception.toggle(["face_segmentation"])
        if self.response_start.error_code == 0:
            rospy.loginfo("Face segmentation has started correctly")
        elif self.response_start.error_code == 1:
            rospy.loginfo("Face segmentation failed to start")
            self.robot.speech.speak("I was not able to start face segmentation.")
            return 'looking'
        rospy.sleep(2)

        rospy.loginfo("Face segmentation will be stopped now")
        self.response_stop = self.robot.perception.toggle([])
        
        if self.response_stop.error_code == 0:
            rospy.loginfo("Face segmentation is stopped")
        elif self.response_stop.error_code == 1:
            rospy.loginfo("Failed stopping face segmentation")

        # compose person query
        person_query = Conjunction(  
                                    Compound( "property_expected", "ObjectID", "class_label", "face"),
                                    Compound( "property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")),
                                    Compound( "property_expected", "ObjectID", "position", Sequence("X","Y","Z")))

        # query for people found
        person_result = self.robot.reasoner.query(person_query)
 
        # if no one was found
        if not person_result:

            # repeat the search with a different head tilt
            self.robot.head.set_pan_tilt(tilt=0.2)
            self.robot.speech.speak("Did not find a person yet.")

            self.response_start = self.robot.perception.toggle(["face_segmentation"])
            if self.response_start.error_code == 0:
                rospy.loginfo("Face segmentation has started correctly")
            elif self.response_start.error_code == 1:
                rospy.loginfo("Face segmentation failed to start")
                self.robot.speech.speak("I was not able to start face segmentation.")
                return 'looking'
            rospy.sleep(2)

            rospy.loginfo("Face segmentation will be stopped now")
            self.response_stop = self.robot.perception.toggle([])
        
            if self.response_stop.error_code == 0:
                rospy.loginfo("Face segmentation is stopped")
            elif self.response_stop.error_code == 1:
                rospy.loginfo("Failed stopping face segmentation")

            # repeat the query
            person_result = self.robot.reasoner.query(person_query)

            # if no one was found continue looking
            if not person_result:
                self.robot.speech.speak("No one here.",block=False)
                return "looking"
        if len(person_result) > 1:
            self.robot.speech.speak("I see some people!",block=False)
        else:
            self.robot.speech.speak("I found someone!",block=False)
        return "found"     

class PersonFound(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["correct", "unknown", "persons_unchecked", "not_correct"])
        self.robot = robot

    def execute(self, userdata=None):

        # prepare query to get faces detected in front of amigo
        person_query = Conjunction(  
                        Compound( "property_expected", "ObjectID", "class_label", "face"),
                        Compound( "property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")),
                        Compound( "property_expected", "ObjectID", "position", Compound("point_3d", "X", "Y", "Z")),
                        Compound( "not", Compound("registered", "ObjectID")))

        # get results from the query
        person_detection_result = self.robot.reasoner.query(person_query)
        rospy.loginfo("I found {0} peoples". format(len(person_detection_result)))
        
        # navigate to one of the detected faces
        nav = NavigateGeneric(self.robot, lookat_query=person_query)
        nav_result = nav.execute()

        # if nav_result == "unreachable":  #Compound("meeting_point", waypoint_name)
        #     self.robot.speech.speak("The location of the person unreachable", block=False)
        #     return "?"
        # elif nav_result == "preempted":
        #     return "?"
        # elif nav_result == "arrived":
        #     self.robot.speech.speak("I reached the person location", block=False)
        #     return "?"
        # else: #goal not defined
        #     self.robot.speech.speak("The location of the person is invalid", block=False)
        #     return "?"

        # retrieve all possible locations
        possible_locations = [( float(answer["X"]), 
                                float(answer["Y"]), 
                                float(answer["Z"])) for answer in person_detection_result]

        # if there are locations of interest...
        if len(possible_locations) > 0:
            x,y,z = possible_locations[0]
            if z > 1.5:
                self.robot.spindle.high()
                rospy.logdebug("Spindle should come up now!")

            # Look at person
            lookat_point = msgs.PointStamped(x,y,z)
            rospy.loginfo("AMIGO should look at person now. (x = {0}, y = {1}, z = {2})".format(x,y,z))
            self.robot.head.send_goal(lookat_point,timeout=0)

        # get the objectID of the person we are trying to serve the drink to
        self.robot.reasoner.query(Conjunction(Compound("current_person", "ObjectID"),
                                              Compound("assert", Compound("registered", "ObjectID"))))
        return_result = self.robot.reasoner.query(Compound("current_person", "Person"))       

        # if there is no result, we forgot who we were serving, return!
        if not return_result:
            self.robot.speech.speak("I forgot who I should bring the drink to!",block=False)
            return "not_correct"

        serving_person = str(return_result[0]["Person"]) 
        self.robot.speech.speak("Please look into my eyes.")
        
        # perform face recognition on the person found
        self.response_start = self.robot.perception.toggle(["face_recognition"])
        if self.response_start.error_code == 0:
            rospy.loginfo("Face recognition has started correctly")
        elif self.response_start.error_code == 1:
            rospy.loginfo("Face recognition failed to start")
            self.robot.speech.speak("I was not able to start face recognition.",block=False)
            return 'unknown'
        
        # sleep while we wait for results on the recognition
        rospy.sleep(6.0)

        rospy.loginfo("Face recognition will be stopped now")
        self.response_stop = self.robot.perception.toggle([])
        
        if self.response_stop.error_code == 0:
            rospy.loginfo("Face recognition is stopped")
        elif self.response_stop.error_code == 1:
            rospy.loginfo("Failed stopping face recognition")

        # Interpret face regnition results
        person_result = self.robot.reasoner.query(
                                            Conjunction(  
                                                Compound( "property_expected", "ObjectID", "class_label", "face"),
                                                Compound( "property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")),
                                                Compound( "property", "ObjectID", "name", Compound("discrete", "DomainSize", "NamePMF"))))
        # if there were people found...
        if len(person_result) > 0:
            name_pmf = person_result[0]["NamePMF"]

            if len(person_result) > 1:
                rospy.logwarn("Multiple faces detected, only checking the first one!")

            name=None
            name_prob=0

            for name_possibility in name_pmf:
                print name_possibility
                prob = float(name_possibility[0])
                if prob > 0.1856 and prob > name_prob:
                    name = str(name_possibility[1][0])
                    name_prob = prob

            # If the person is not recognized
            if not name:
                self.robot.speech.speak("I don't know who you are.",block=False)
                if len(person_detection_result) > 1:
                    return 'persons_unchecked'
                else:
                    return "unknown"  

            # if the person if recognized but not the one we are searching for
            if name != serving_person:
                self.robot.speech.speak("You are not the one I am looking for",block=False)
                if len(person_detection_result) > 1:
                    return 'persons_unchecked'
                else:
                    return "not_correct"      

            # if it is the persons we are searching for
            if name:
                self.robot.speech.speak("Hello " + str(name),block=False) 
                return "correct"

        # if there were no people found...
        else:
            self.robot.speech.speak("I thought there was someone here, but I'm mistaken.",block=False)
            if len(person_detection_result) > 1:
                return 'persons_unchecked'
            rospy.loginfo("No person names received from world model") 
        return "not_correct"

# class Navigate_to_queryoutcome_point_cocktail(Navigate_abstract):
#     """Move to the output of a query, which is passed to this state as a Term from the reasoner-module.
    
#     The state can take some parameters that specify which keys of the dictionary to use for which data.
#     By default, the binding-key "X" refers to the x-part of the goal, etc. 
    
#     Optionally, also a sorter can be given that sorts the bindings according to some measure.
#     """
#     def __init__(self, robot, query, X="X", Y="Y", Z="Z"):
#         Navigate_abstract.__init__(self, robot)

#         assert isinstance(query, Term)

#         self.queryTerm = query
#         self.X, self.Y, self.Z = X, Y, Z
        
#     def get_goal(self, userdata):
#         """self.get_goal gets the answer to this query and lets it parse it into a list of binding-dictionaries. """
        
#         #self.robot.reasoner.query(Compound("retractall", Compound("current_person", "X"))) 
        
#         # Gets result from the reasoner. The result is a list of dictionaries. Each dictionary
#         # is a mapping of variable to a constant, like a string or number
#         answers = self.robot.reasoner.query(self.queryTerm)

#         if not answers:
#             return None
#             rospy.logerr("No answers found for query {query}".format(query=self.queryTerm))
#         else:
#             chosen_answer = answers[0]
#             #From the summarized answer, 
#             possible_locations = [( float(answer[self.X]), 
#                                     float(answer[self.Y]), 
#                                     float(answer[self.Z])) for answer in answers]

#             x,y,z = possible_locations[0]
            
#             goal = possible_locations[0]
#             rospy.loginfo("goal = {0}".format(goal))
#             waypoint_name = chosen_answer["ObjectID"]

            
#             self.robot.reasoner.query(Compound("assert", Compound("current_person", waypoint_name))) 

#             rospy.logdebug("Found location for '{0}': {1}".format(self.queryTerm, (x,y,z)))

#             look_pose = geometry_msgs.msg.PoseStamped()
#             look_pose.pose.position = self.robot.base.point(x,y)
#             look_pose.pose.orientation = msgs.Quaternion(z=1.0)

#             look_point = geometry_msgs.msg.PointStamped()
#             look_point.point = self.robot.base.point(x,y)
#             pose = msgs.Quaternion(z=1.0)

#             base_poses_for_point = self.robot.base.get_base_goal_poses(look_point, 1.0, 0.0)
#             if base_poses_for_point:
#                 base_pose_for_point = base_poses_for_point[0]
#             else:
#                 rospy.logerr("IK returned empty pose.")
#                 return look_pose #look_point.point, pose  #outWhen the IK pose is empty, just try to drive to the point itself. Will likely also fail.
                
#             if base_pose_for_point.pose.position.x == 0 and base_pose_for_point.pose.position.y == 0:
#                 rospy.logerr("IK returned empty pose.")
#                 return look_pose#look_point.point, pose  #outWhen the IK pose is empty, just try to drive to the point itself. Will likely also fail.

#             return base_pose_for_point

class HandoverToKnownHuman(smach.StateMachine):
    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=["done"])

        if grasp_arm == "left":
            arm = robot.leftArm
        if grasp_arm == "right":
            arm = robot.rightArm

        with self:
            smach.StateMachine.add( 'PRESENT_DRINK',
                                    Say(robot, ["I'm going to hand over your drink now", "Here you go! Handing over your drink"], block=False),
                                    transitions={"spoken":"POSE"})

            smach.StateMachine.add( 'POSE',
                                    Handover_pose(arm, robot),
                                    transitions={   'succeeded':'PLEASE_TAKE',
                                                    'failed':'PLEASE_TAKE'})
            
            smach.StateMachine.add( 'PLEASE_TAKE',
                                    Say(robot, ["Please hold the drink, I'm going to let it go.", "Please take the drink, I'll let it go"]),
                                    transitions={"spoken":"OPEN_GRIPPER"})

            smach.StateMachine.add( "OPEN_GRIPPER", 
                                    SetGripper(robot, arm, gripperstate=0, drop_from_frame="/amigo/grippoint_left"), #open
                                    transitions={   'succeeded':'CLOSE_AFTER_DROP',
                                                    'failed':'CLOSE_AFTER_DROP'})
            smach.StateMachine.add( 'CLOSE_AFTER_DROP',
                                    SetGripper(robot, arm, gripperstate=1), #close
                                    transitions={   'succeeded':'RESET_ARM',
                                                    'failed':'RESET_ARM'})
            smach.StateMachine.add('RESET_ARM', 
                                    ArmToPose(robot, arm, (-0.0830 , -0.2178 , 0.0000 , 0.5900 , 0.3250 , 0.0838 , 0.0800)), 
                                    transitions={   'done':'RESET_TORSO',
                                                    'failed':'RESET_TORSO'})
            smach.StateMachine.add('RESET_TORSO',
                                    ResetTorso(robot),
                                    transitions={   'succeeded':'SAY_ENJOY',
                                                    'failed'   :'SAY_ENJOY'})

            smach.StateMachine.add( 'SAY_ENJOY',
                                    Say(robot, ["Enjoy your drink!", "I hope your thirsty, enjoy!"], block=False),
                                    transitions={"spoken":"done"})

class HandoverToUnknownHuman(smach.StateMachine):
    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=["done"])

        if grasp_arm == "left":
            arm = robot.leftArm
        if grasp_arm == "right":
            arm = robot.rightArm
        query_party_room = Compound("waypoint", "party_room", Compound("pose_2d", "X", "Y", "Phi"))    
        query_party_room_robust =Compound("point_of_interest", "party_room_robust", Compound("point_3d", "X", "Y", "Z"))

        with self:
            smach.StateMachine.add('GOTO_PARTY_ROOM_HANDOVER',
                                    NavigateGeneric(robot, goal_query=query_party_room),
                                    transitions={   "arrived":"PRESENT_DRINK", 
                                                    "unreachable":"GOTO_PARTY_ROOM_HANDOVER_ROBUST", 
                                                    "preempted":"GOTO_PARTY_ROOM_HANDOVER_ROBUST", 
                                                    "goal_not_defined":"GOTO_PARTY_ROOM_HANDOVER_ROBUST"})

            smach.StateMachine.add('GOTO_PARTY_ROOM_HANDOVER_ROBUST',
                                            NavigateGeneric(robot, lookat_query = query_party_room_robust,xy_dist_to_goal_tuple=(1.0,0)),
                                            transitions={   "arrived":"PRESENT_DRINK", 
                                                            "unreachable":"PRESENT_DRINK", 
                                                            "preempted":"PRESENT_DRINK", 
                                                            "goal_not_defined":"PRESENT_DRINK"})
            smach.StateMachine.add( 'PRESENT_DRINK',
                                    Say(robot, ["I'm going to hand over your drink now", "Here you go! Handing over your drink"],block=False),
                                    transitions={"spoken":"POSE"})

            smach.StateMachine.add( 'POSE',
                                    Handover_pose(arm, robot),
                                    transitions={   'succeeded':'PLEASE_TAKE',
                                                    'failed':'PLEASE_TAKE'})
            
            smach.StateMachine.add( 'PLEASE_TAKE',
                                    Say(robot, ["Please hold the drink, I'm going to let it go.", "Please take the drink, i'll let it go"]),
                                    transitions={"spoken":"OPEN_GRIPPER"})

            smach.StateMachine.add( "OPEN_GRIPPER", 
                                    SetGripper(robot, arm, gripperstate=0, drop_from_frame="/amigo/grippoint_right"), #open
                                    transitions={   'succeeded':'CLOSE_AFTER_DROP',
                                                    'failed':'CLOSE_AFTER_DROP'})
            smach.StateMachine.add( 'CLOSE_AFTER_DROP',
                                    SetGripper(robot, arm, gripperstate=1), #close
                                    transitions={   'succeeded':'RESET_ARM',
                                                    'failed':'RESET_ARM'})
            smach.StateMachine.add('RESET_ARM', 
                                    ArmToPose(robot, arm, (-0.0830 , -0.2178 , 0.0000 , 0.5900 , 0.3250 , 0.0838 , 0.0800)), 
                                    transitions={   'done':'RESET_TORSO',
                                                    'failed':'RESET_TORSO'})
            smach.StateMachine.add('RESET_TORSO',
                                    ResetTorso(robot),
                                    transitions={   'succeeded':'SAY_ENJOY',
                                                    'failed'   :'SAY_ENJOY'})

            smach.StateMachine.add( 'SAY_ENJOY',
                                    Say(robot, ["Enjoy your drink!", "I hope your thirsty, enjoy!"], block=False),
                                    transitions={"spoken":"done"})

class CocktailParty(smach.StateMachine):
    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=["Done", "Aborted", "Failed"])

        # Queries:
        #query_meeting_point = Compound("waypoint", Compound("meeting_point", "Object"), Compound("pose_2d", "X", "Y", "Phi"))
        query_party_room_robust =Compound("point_of_interest", "party_room_robust", Compound("point_3d", "X", "Y", "Z"))
        query_party_room = Compound("waypoint", "party_room", Compound("pose_2d", "X", "Y", "Phi"))
        query_grabpoint = Conjunction(  Compound("goal", Compound("serve", "Drink")),
                                           Compound( "property_expected", "ObjectID", "class_label", "Drink"),
                                           Compound( "property_expected", "ObjectID", "position", Compound("in_front_of", "amigo")),
                                           Compound( "property_expected", "ObjectID", "position", Sequence("X", "Y", "Z")))

        if grasp_arm == "left":
            arm = robot.leftArm
        if grasp_arm == "right":
            arm = robot.rightArm

        with self:

            smach.StateMachine.add( "START_CHALLENGE",
                                    StartChallengeRobust(robot, "initial"), #query_meeting_point
                                    transitions={   "Done":"DELETE_MODELS", 
                                                    "Aborted":"DELETE_MODELS", 
                                                    "Failed":"DELETE_MODELS"})
            smach.StateMachine.add( "DELETE_MODELS",
                                    DeleteModels(robot), 
                                    transitions={   "done":"SAY_GOTO_PARTY_ROOM"})


            smach.StateMachine.add( "SAY_GOTO_PARTY_ROOM",
                                    Say(robot, "I'm going to the party room.",block=False),
                                    transitions={   "spoken":"GOTO_PARTY_ROOM"})

            smach.StateMachine.add('GOTO_PARTY_ROOM',
                                    NavigateGeneric(robot, goal_query = query_party_room),
                                    transitions={   "arrived":"ITERATE_PERSONS", 
                                                    "unreachable":"GOTO_PARTY_ROOM_ROBUST", 
                                                    "preempted":"GOTO_PARTY_ROOM_ROBUST", 
                                                    "goal_not_defined":"GOTO_PARTY_ROOM_ROBUST"})

            smach.StateMachine.add('GOTO_PARTY_ROOM_ROBUST',
                                    NavigateGeneric(robot, lookat_query = query_party_room_robust,xy_dist_to_goal_tuple=(1.0,0)),
                                    transitions={   "arrived":"ITERATE_PERSONS", 
                                                    "unreachable":"ITERATE_PERSONS", 
                                                    "preempted":"ITERATE_PERSONS", 
                                                    "goal_not_defined":"ITERATE_PERSONS"})

            persons_iterator = smach.Iterator(  outcomes=['served', 'not_served'], 
                                                it=lambda: range(3),
                                                it_label="person_index",
                                                input_keys=[],
                                                output_keys=[],
                                                exhausted_outcome='Done')
            
            with persons_iterator:
                single = smach.StateMachine(outcomes=['served', 'not_served'])
                with single:
                    #TODO: Retract visited(X) before looking for a person back again.
                    smach.StateMachine.add( "RETRACT_VISITED",
                                            Retract_facts(robot, [Compound("visited", "X")]),
                                            transitions={"retracted":"WAIT_FOR_PERSON"})

                    smach.StateMachine.add( "WAIT_FOR_PERSON", 
                                            WaitForPerson(robot),
                                            transitions={   "waiting":"WAIT_FOR_PERSON",
                                                            "unknown_person":"LEARN_PERSON_NAME",
                                                            "known_person":"TAKE_ORDER"})

                    smach.StateMachine.add( "LEARN_PERSON_NAME",
                                            LearnPersonName(robot),
                                            transitions={   "learned":"LEARN_PERSON_FACE",
                                                            "failed":"LEARN_PERSON_NAME"})
                    
                    smach.StateMachine.add( "LEARN_PERSON_FACE",
                                            LearnPersonFaceCustom(robot),
                                            transitions={   "face_learned":"TAKE_ORDER",
                                                            "learn_failed":"LEARN_PERSON_FACE"})

                    smach.StateMachine.add( "TAKE_ORDER",
                                            Ask_drink(robot),
                                            transitions={   "done":"LOOK_FOR_DRINK",
                                                            "failed":"TAKE_ORDER"})
                                          
                    smach.StateMachine.add( 'LOOK_FOR_DRINK',
                                            LookForDrink(robot),
                                            transitions={   "looking":"LOOK_FOR_DRINK",
                                                            "found":'PICKUP_DRINK',
                                                            "not_found":'SAY_DRINK_NOT_FOUND'})
                    
                    smach.StateMachine.add( 'SAY_DRINK_NOT_FOUND',
                                            Say(robot, ["I could not find the drink you wanted.", 
                                                        "I looked really hard, but I couldn't find your drink."]),
                                            transitions={   'spoken':'GOTO_INITIAL_FAIL' }) 

                    smach.StateMachine.add( 'PICKUP_DRINK',
                                            GrabMachine(arm, robot, query_grabpoint),
                                            transitions={   "succeeded":"RETRACT_VISITED_2",
                                                            "failed":'SAY_DRINK_NOT_GRASPED' }) 

                    smach.StateMachine.add( 'SAY_DRINK_NOT_GRASPED',
                                            Say(robot, ["I could not pick up the drink you wanted", 
                                                        "I failed to grab the object you wanted."]),
                                            transitions={   'spoken':'HUMAN_HANDOVER' }) 

                    smach.StateMachine.add( 'HUMAN_HANDOVER',
                                            Human_handover(arm,robot),
                                            transitions={   'succeeded':'RETRACT_VISITED_2',
                                                            'failed':'GOTO_INITIAL_FAIL' })

                    smach.StateMachine.add( "RETRACT_VISITED_2",
                                            Retract_facts(robot, [Compound("visited", "X")]),
                                            transitions={"retracted":"LOOK_FOR_PERSON"})           

                    smach.StateMachine.add( 'LOOK_FOR_PERSON',
                                            LookForPerson(robot),
                                            transitions={   "looking":"LOOK_FOR_PERSON",
                                                            "found":'PERSON_FOUND',
                                                            "not_found":'SAY_PERSON_NOT_FOUND'})
                    smach.StateMachine.add( 'PERSON_FOUND',
                                            PersonFound(robot),
                                            transitions={   "correct":"HANDOVER_DRINK",
                                                            "unknown":'LOOK_FOR_PERSON',
                                                            "persons_unchecked":"PERSON_FOUND",
                                                            "not_correct":'LOOK_FOR_PERSON'})

                    smach.StateMachine.add( 'SAY_PERSON_NOT_FOUND',
                                            Say(robot, ["I could not find you.", 
                                                        "I can't find you. I really don't like fluids.",
                                                        "I could not find you."]),
                                            transitions={   'spoken':'HANDOVER_DRINK_UNKNOWN_PERSON' }) #GOTO_INITIAL_FAIL

                    smach.StateMachine.add( 'HANDOVER_DRINK_UNKNOWN_PERSON',
                                            HandoverToUnknownHuman(robot),
                                            transitions={"done":"GOTO_INITIAL_FAIL"})

                    smach.StateMachine.add( 'HANDOVER_DRINK',
                                            HandoverToKnownHuman(robot),
                                            transitions={"done":"GOTO_INITIAL_SUCCESS"})

                    smach.StateMachine.add( "GOTO_INITIAL_SUCCESS",
                                            NavigateGeneric(robot, goal_query=query_party_room),
                                            transitions={   "arrived":"served", 
                                                            "unreachable":"GOTO_INITIAL_SUCCESS_ROBUST", 
                                                            "preempted":"GOTO_INITIAL_SUCCESS_ROBUST", 
                                                            "goal_not_defined":"GOTO_INITIAL_SUCCESS_ROBUST"})

                    smach.StateMachine.add('GOTO_INITIAL_SUCCESS_ROBUST',
                                            NavigateGeneric(robot, lookat_query = query_party_room_robust,xy_dist_to_goal_tuple=(1.0,0)),
                                            transitions={   "arrived":"served", 
                                                            "unreachable":"served", 
                                                            "preempted":"not_served", 
                                                            "goal_not_defined":"served"})

                    smach.StateMachine.add( "GOTO_INITIAL_FAIL",
                                            NavigateGeneric(robot, goal_query=query_party_room),
                                            transitions={   "arrived":"not_served", 
                                                            "unreachable":"GOTO_INITIAL_FAIL_ROBUST", 
                                                            "preempted":"GOTO_INITIAL_FAIL_ROBUST", 
                                                            "goal_not_defined":"GOTO_INITIAL_FAIL_ROBUST"})

                    smach.StateMachine.add( "GOTO_INITIAL_FAIL_ROBUST",
                                            NavigateGeneric(robot, lookat_query = query_party_room_robust,xy_dist_to_goal_tuple=(1.0,0)),
                                            transitions={   "arrived":"not_served", 
                                                            "unreachable":"not_served", 
                                                            "preempted":"not_served", 
                                                            "goal_not_defined":"not_served"})

                persons_iterator.set_contained_state('SINGLE_COCKTAIL_SM', 
                                                          single, 
                                                          loop_outcomes=['served', 'not_served'])

            smach.StateMachine.add( 'ITERATE_PERSONS', 
                                    persons_iterator, 
                                    transitions={'served':'EXIT',
                                                'not_served':'SAY_FAILED',
                                                'Done':"SAY_FINISHED_SERVING"})

            smach.StateMachine.add('SAY_FINISHED_SERVING',
                                    Say(robot, "I finished my task, enjoy your drinks", block = False),
                                    transitions={'spoken':'EXIT'}) 

            smach.StateMachine.add('EXIT',
                                    NavigateGeneric(robot, goal_name="exit_1"),
                                    transitions={   'arrived':'FINISH', 
                                                    'preempted':'CLEAR_PATH_TO_EXIT', 
                                                    'unreachable':'CLEAR_PATH_TO_EXIT', 
                                                    'goal_not_defined':'CLEAR_PATH_TO_EXIT'})
        
            smach.StateMachine.add('CLEAR_PATH_TO_EXIT',
                                    Say(robot, "I couldn't go to the exit. Please clear the path, I will give it another try."),
                                    transitions={'spoken':'GO_TO_EXIT_SECOND_TRY'})

            smach.StateMachine.add('GO_TO_EXIT_SECOND_TRY', 
                                    NavigateGeneric(robot, goal_name="exit_2"),
                                    transitions={   'arrived':'FINISH', 
                                                    'preempted':'FINISH', 
                                                    'unreachable':'FINISH', 
                                                    'goal_not_defined':'FINISH'})

            smach.StateMachine.add( 'FINISH', Finish(robot),
                                    transitions={'stop':'Done'})

            smach.StateMachine.add("SAY_FAILED", 
                                    Say(robot, "I could not accomplish my task, sorry about that, please forgive me."),
                                    transitions={   "spoken":"EXIT"})
 
if __name__ == '__main__':
    rospy.init_node('executive_cocktail_party')
 
    amigo = Amigo(wait_services=True)

    # Retract all old facts
    amigo.reasoner.query(Compound("retractall", Compound("challenge", "X")))
    amigo.reasoner.query(Compound("retractall", Compound("goal", "X")))
    amigo.reasoner.query(Compound("retractall", Compound("explored", "X")))
    amigo.reasoner.query(Compound("retractall", Compound("state", "X", "Y")))
    amigo.reasoner.query(Compound("retractall", Compound("current_exploration_target", "X")))
    amigo.reasoner.query(Compound("retractall", Compound("current_object", "X")))
    amigo.reasoner.query(Compound("retractall", Compound("current_person", "X")))
    amigo.reasoner.query(Compound("retractall", Compound("visited", "X")))
    amigo.reasoner.query(Compound("retractall", Compound("registered", "X")))
    amigo.reasoner.query(Compound("retractall", Compound("type", "X", "Y")))

    # Load locations and objects from knowledge files
    amigo.reasoner.query(Compound("load_database", "tue_knowledge", 'prolog/locations.pl'))
    amigo.reasoner.query(Compound("load_database", "tue_knowledge", 'prolog/objects.pl'))

    # Use reasoner for max iter in LookForPerson 
    amigo.reasoner.query(Compound("retractall", Compound("looked_person_no", "X")))
    amigo.reasoner.query(Compound("assert",Compound("looked_person_no", "0")))

    # Use reasoner for max iter in LookForDrink 
    amigo.reasoner.query(Compound("retractall", Compound("looked_drink_no", "X")))
    amigo.reasoner.query(Compound("assert",Compound("looked_drink_no", "0")))

    # Use reasoner for max iter in WaitForPerson (failsafe)
    amigo.reasoner.query(Compound("retractall", Compound("waited_times_no", "X")))
    amigo.reasoner.query(Compound("assert",Compound("waited_times_no", "0")))

    # Assert current challenge
    amigo.reasoner.assertz(Compound("challenge", "cocktailparty"))

    initial_state = None


    if initial_state == "LOOK_FOR_DRINK":
        amigo.reasoner.query(Compound("assert", Compound("goal", Compound("serve", "coke"))))
        amigo.reasoner.query(Compound("assert", Compound("current_person", "john")))

    machine = CocktailParty(amigo)
    
    if initial_state != None:
        machine.set_initial_state([initial_state])

    introserver = smach_ros.IntrospectionServer('server_name', machine, '/SM_ROOT_PRIMARY')
    introserver.start()
    try:
        machine.execute()
    except Exception, e:
        amigo.speech.speak(e)
    finally:
        introserver.stop()
