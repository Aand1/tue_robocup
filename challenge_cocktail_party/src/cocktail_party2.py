#! /usr/bin/env python
import roslib; roslib.load_manifest('challenge_cocktail_party')
import rospy

#from tue_execution_pack import states, smach, util, robot_parts
from tue_execution_pack import robot_parts
#from robot_parts.reasoner import *

from psi import *

def navigate_to(robot, x, y, phi, frame_id):
    pos = robot.base.point(x,y)
    orient = robot.base.orient(phi)
    robot.base.send_goal(pos, orient, block=True)

def look_at(robot, x, y, z, frame_id):
    robot.head.send_goal(robot.head.point(x, y, z), frame_id)

def listen(robot, options):
    robot.ears.forget()
    robot.ears.start_listening()
    rospy.sleep(5)
    words = [ str(word) for word in options ]
    print words
    answer = robot.ears.last_heard_words(words, 5)
    robot.ears.stop_listening()
    print answer
    robot.reasoner.query(Compound("retractall", Compound("heard_words", "X")))
    robot.reasoner.assert_fact(Compound("heard_words", str(answer)))

def toggle_module(robot, module, status):
    if str(status) == "on":
        robot.perception.toggle([module])
    else:
        robot.perception.toggle([])   

def do_action(robot, action):
    if action.is_compound():
        if action.get_functor() == 'navigate_to':
            navigate_to(robot, float(action[0]), float(action[1]), float(action[2]), str(action[3]))
        elif action.get_functor() == 'say':
            robot.speech.speak(str(action[0]))
        elif action.get_functor() == 'listen':
            listen(robot, action[0])
        elif action.get_functor() == 'wait':
            rospy.sleep(action[0].get_number())
        elif action.get_functor() == 'look_at':
            look_at(robot, float(action[0]), float(action[1]), float(action[2]), str(action[3]))
        elif action.get_functor() == 'toggle_module':
            toggle_module(robot, str(action[0]), str(action[1]))

    #print action.functor()
  
if __name__ == '__main__':
    rospy.init_node('executioner')

    robot = robot_parts.amigo.Amigo(wait_services=True)
    
    client = Client("/reasoner/query", "/reasoner/assert")

    client.query(Compound("load_database", "tue_knowledge", 'prolog/locations.pl'))
    client.query(Compound("load_database", "challenge_cocktail_party", 'prolog/cocktail_party.pl'))

    client.assert_fact(Compound("challenge", "cocktailparty"))

    finished = False
    while not finished:

        print "* * * * * * * * * * * * * * * * * "
        print ""

        result = client.query(Compound("step", "Actions", "Transitions", "Warnings"))
        if result:
            actions = result[0]["Actions"]
            transitions = result[0]["Transitions"]
            warnings = result[0]["Warnings"]
            
            if actions.is_sequence() and actions.get_size() > 0:
                print "ACTIONS:"
                for action in actions:
                    print "    " + str(action)
                    do_action(robot, action)
                print ""

            if transitions.is_sequence() and transitions.get_size() > 0:
                print "TRANSITIONS:"
                for transition in transitions:
                    print "    " + str(transition[0]) + ":" + str(transition[1]) + " ---> " + str(transition[0]) + ":" + str(transition[2])
                print ""

            if warnings.is_sequence() and warnings.get_size() > 0:
                print "WARNINGS:"
                for warning in warnings:
                    print "    " + str(warning)
                print ""

        else:
            print "ERROR: step/2 did not succeed!"
            finished = True

        rospy.sleep(1)
    #print Compound("bla")