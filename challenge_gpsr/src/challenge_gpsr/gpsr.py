#!/usr/bin/python
import roslib; roslib.load_manifest('challenge_gpsr')
import rospy
#import robot_parts.speech
from std_msgs.msg import String
import geometry_msgs
import smach
import sys

from robot_skills.amigo import Amigo
import robot_smach_states as states
import robot_skills.util.msg_constructors as msgs

from robot_smach_states.util.startup import startup
from robot_smach_states.util.designators import Designator, EdEntityDesignator

import data

###########################
# Created by: Erik Geerts #
###########################

#######################
##### TODO LIST!! #####
#### NA EINDHOVEN  ####
#######################
# - dropoff points in eindhoven definieren.
# - remove timeout of 5 minutes -> DID YOU SAY SOMETHING, IN ANY CASE, I DID NOT HEAR YOU!



### EXAMPLE SENTENCES stated in new conceptual rulebook.
# Go to the bedroom, find a person and tell the time (missing object-interaction part).
# Go to the kitchen, find a person and follow her (missing object-interaction part).
# Go to the dinner-table, grasp the crackers, and take them to the TV.
# Go to the shelf, count the drinks and report to me.

# Take this object and bring it to Susan at the hall.
# Bring a coke to the person in the living room and answer him a question.
# Offer a drink to the person at the door.


class Ask_action(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["done", "failed"])
        self.robot = robot

    def execute(self, userdata):
        self.robot.head.lookAtStandingPerson()

        self.robot.speech.speak("What can I do for you?")

        res = self.robot.ears.recognize(spec=data.spec, choices=data.choices, time_out = rospy.Duration(10))
        self.robot.head.cancelGoal()
        if not res:
            self.robot.speech.speak("My ears are not working properly, can i get a restart?.")
            return "failed"
        try:
            if res.result:
                say_result = self.replace_word(res.result,"me","you")
                self.robot.speech.speak("Okay I will {0}".format(say_result))
                print say_result
                self.save_action(res)

            else:
                self.robot.speech.speak("Sorry, could you please repeat?")
        except KeyError:
            print "[what_did_you_say] Received question is not in map. THIS SHOULD NEVER HAPPEN!"
            return "failed"

        return "done"

    def replace_word(self,string,word_in,word_out):
        try:
            if string[:(len(word_in)+1)] == (word_in+" "):
                string = string.replace(string[:len(word_in)],word_out)

            if string[(len(string)-len(word_in)-1):] == (" "+word_in):
                string = string.replace(string[(len(string)-len(word_in)):],word_out)

            string = string.replace(" "+word_in+" "," "+word_out+" ")

        except KeyError:
            print "[gpsr] Received action is to short."

        return string

    def save_action(self,res):
        
        for choice_key, choice_value in res.choices.iteritems():
            print "choice_key = ", self.add_underscores(str(choice_key))
            print "choice_value = '",self.add_underscores(str(choice_value)),"'"
            print "choice_value[0] = '",str(choice_value)[0],"'"

            print "choice_value empty string = '", self.remove_empty_string(str(choice_value)), "'"
            

            if not choice_key[:1].find("1"):
                print " 1 = ", choice_key[:1]             
                self.robot.reasoner.assertz("action_info('1','"+self.add_underscores(str(choice_key))+"','"+self.add_underscores(str(choice_value))+"')")
            if not choice_key[:1].find("2") : 
                print " 2 = ", choice_key[:1] 
                self.robot.reasoner.assertz("action_info('2','"+self.add_underscores(str(choice_key))+"','"+self.add_underscores(str(choice_value))+"')")  
            if not choice_key[:1].find("3"):
                print " 3 = ", choice_key[:1]   
                self.robot.reasoner.assertz("action_info('3','"+self.add_underscores(str(choice_key))+"','"+self.add_underscores(str(choice_value))+"')")

       
    #   todo: 
    #       - First get for first action the simple action (for now only navigating to location, room or object, later also direct grabbing object)
    #       - Then get action 2
    #       - Then action 3. (mainly dropoff, report, follow, answer question (including tell time))
    #
    def add_underscores(self, string):
        return str(string.replace(" ","_"))

    # removes empty string at front and end of string if there is an empty string.
    def remove_empty_string(self, string):
        print "test = ", string.find(" ")
        return str(string.replace(" ","")) 

class Query_specific_action(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["navigate_room", "navigate_location", "test"]) #outcomes=["action_get", "action_transport","action_point","action_find","action_navigate","action_leave","error"])
        self.robot = robot

    def execute(self, userdata):

        action_nr = self.robot.reasoner.query("current_action(A)")
        #print action_nr
        if action_nr:
            #print action_nr[0]['A']
            current_action = str(action_nr[0]['A'])

        else:
            self.robot.reasoner.assertz("current_action('1')")
            current_action = str("1")
        print current_action

        if current_action == "1":
            action = self.robot.reasoner.query("action_info('1',A,B)")

            for x in action:
                for choice_key, choice_value in x.iteritems():
                    print "choice_value = ", str(choice_value)

                    if str(choice_value) == "1_locations_rooms":
                        #print "locations_rooms = ", str(self.robot.reasoner.query("action_info('1','1_locations_rooms',B)")[0]['B'])
                        print "locations_rooms = '", str(self.robot.reasoner.query_first_answer("action_info('1','1_locations_rooms',B)")), "'"
                        a = ("room_"+str(self.robot.reasoner.query_first_answer("action_info('1','1_locations_rooms',A)")))
                        print a
                        return "navigate_room"

                    if str(choice_value) == "1_locations_aeuoi":
                        print "1_locations_aeuoi = ", self.robot.reasoner.query("action_info('1','1_locations_aeuoi',B)")[0]
                        self.robot.reasoner.query("retractall(action_info('1','1_locations_aeuoi',A))")
                        self.robot.reasoner.assertz("action_info('1','1_location',"+choice_value+")")

                        return "navigate_location"
                    if str(choice_value) == "1_locations_rest":
                        print "1_locations_rest = ", self.robot.reasoner.query("action_info('1','1_locations_rest',B)")[0]
                        self.robot.reasoner.query("retractall(action_info('1','1_locations_rest',A))")
                        self.robot.reasoner.assertz("action_info('1','1_location',"+choice_value+")")

                        print "testingggg =", self.robot.reasoner.query("action_info('1','1_location',A)")

                        return "navigate_location"            

        elif current_action == "2":
            print self.robot.reasoner.query("action_info('1',A,B)")

        elif current_action == "3":
            print self.robot.reasoner.query("action_info('1',A,B)")



        # print answers[0]

        # print answers[0]['A']

        # answers = self.robot.reasoner.query("retractall(action_info(_,_))")
        # print "test"
        # print self.robot.reasoner.query("action_info(A,B)")
        return "test"

class Finished_goal(smach.State):
    # Checks how many tasks have been done and if another task is needed
    # Does this check with the database in the reasoner
    def __init__(self,robot):
        smach.State.__init__(self, outcomes=["new_task", "tasks_completed"])

        self.robot = robot

    def execute(self, userdata):


        action_nr = self.robot.reasoner.query("current_action(A)")
        print action_nr
        if action_nr:
            print "finish"
            print int(action_nr[0]['A'])
            print str(int(action_nr[0]['A'])+1)
            self.robot.reasoner.query("retractall(current_action(_))")
            self.robot.reasoner.assertz("current_action("+str(int(action_nr[0]['A'])+1)+")")
            action_nr = self.robot.reasoner.query("current_action('A')")
            print "query after = ", action_nr

        else:
            print "[gpsr] current_action not found. This should not happen."

        #rospy.sleep(2)
        return "new_task"
            


########################
##### STATEMACHINE #####
########################

class GpsrRoomDesignator(Designator):
    def __init__(self, robot, reasoner_query):
        self.robot = robot
        self.reasoner_query = reasoner_query

    def resolve(self):
        first_answer = self.robot.reasoner.query_first_answer(self.reasoner_query)
        return "room_"+str(first_answer)


def setup_statemachine(robot):

    robot.reasoner.load_database("challenge_gpsr","prolog/prolog_data.pl")
    robot.reasoner.query("retractall(current_action(_))")
    robot.reasoner.query("retractall(action_info(_,_,_))")

    sm = smach.StateMachine(outcomes=['Done','Aborted'])

    with sm:

        ######################################################
        ##################### INITIALIZE #####################             
        ######################################################

        smach.StateMachine.add('INITIALIZE',
                                states.Initialize(robot),
                                transitions={   'initialized':'ASK_ACTION',    ###### IN CASE NEXT STATE IS NOT "GO_TO_DOOR" SOMETHING IS SKIPPED
                                                'abort':'Aborted'})


        ######################################################
        #################### INSTRUCTIONS ####################             
        ######################################################


        smach.StateMachine.add("INTRODUCE_SHORT",
                               states.Say(robot,"Hi! I will just wait here and wonder if I can do something for you", block=False),
                               transitions={'spoken':'ASK_ACTION'})

        smach.StateMachine.add("ASK_ACTION",
                                Ask_action(robot),
                                transitions={'done':'QUERY_SPECIFIC_ACTION',
                                             'failed':'ASK_ACTION'})

        smach.StateMachine.add("QUERY_SPECIFIC_ACTION",
                                Query_specific_action(robot),
                                transitions={   'navigate_room':'ACTION_NAVIGATE_TO_ROOM',
                                                'navigate_location':'ACTION_NAVIGATE_TO_LOCATION',
                                                'test':'FINISHED_TASK'})

        #                                         # 'action_get':'SUB_SM_GET',
        #                                         # 'action_transport':'SUB_SM_TRANSPORT',
        #                                         # 'action_point':'SUB_SM_POINT',
        #                                         # 'action_find':'SUB_SM_FIND',
        #                                         # 'action_navigate':'SUB_SM_NAVIGATE',
        #                                         # 'action_leave':'SUB_SM_LEAVE',
        #                                         # 'error':'FINISHED_TASK'})

        # #In case goal is given via speech interpreter:
        # smach.StateMachine.add("FAILED_TASK",
        #                         Failed_goal(robot),
        #                         transitions={'new_task':'RESET_REASONER'})

        smach.StateMachine.add('ACTION_NAVIGATE_TO_LOCATION',
                                states.NavigateToSymbolic(robot, 
                                    {EdEntityDesignator(robot, id="plastic_cabinet") : "in_front_of"}, EdEntityDesignator(robot, id="plastic_cabinet")),
                                transitions={   'arrived'           :   'FINISHED_TASK',
                                                'unreachable'       :   'FINISHED_TASK',
                                                'goal_not_defined'  :   'FINISHED_TASK'}) 

        #When this state executes, it will resolve the EdEntityDesignators.
        #They in turn are built with a GpsrRoomDesignator, so they need to be resolved first. 
        #The definition is above, but basically, they execute the same code you had here first.
        #(TODO Loy: create a designator that just calls any function you give it)
        #So, the query is executed and the result is passed to EdEntityDesignator's id and used in that query. 
        smach.StateMachine.add('ACTION_NAVIGATE_TO_ROOM',
                                states.NavigateToSymbolic(robot, 
                                    {EdEntityDesignator(robot, id=GpsrRoomDesignator(robot, "action_info('1','1_locations_rooms',A)")) : "in" }, 
                                    EdEntityDesignator(robot, id=GpsrRoomDesignator(robot, "action_info('1','1_locations_rooms',A)"))),
                                    #{EdEntityDesignator(robot, id="room_hallway") : "in" },
                                    #EdEntityDesignator(robot, id="room_hallway")),
                                transitions={   'arrived'           :   'FINISHED_TASK',
                                                'unreachable'       :   'FINISHED_TASK',
                                                'goal_not_defined'  :   'FINISHED_TASK'}) 

        smach.StateMachine.add("FINISHED_TASK",
                                Finished_goal(robot),
                                transitions={'new_task':'ASK_ACTION',
                                              'tasks_completed':'ASK_ACTION'})
    return sm

if __name__ == "__main__":
    rospy.init_node('gpsr_exec')
    rospy.loginfo("----------------------------------------------------------")
    rospy.loginfo("----------------------- GPSR 2015 ------------------------")
    rospy.loginfo("----------------------------------------------------------")
    
    if len(sys.argv) > 1:
        robot_name = sys.argv[1]
    else:
        print "[CHALLENGE GPSR] Please provide robot name as argument."
        exit(1)

    states.util.startup(setup_statemachine, robot_name=robot_name)

