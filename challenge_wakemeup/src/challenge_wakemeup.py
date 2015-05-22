#!/usr/bin/python

"""This challenge is defined in https://raw.githubusercontent.com/RoboCupAtHome/RuleBook/master/WakeMeUp.tex

In short, the robot must go the the homeowners bedroom, wake him up gently and ask what he want for breakfast.
Then of course fetch that breakfast, bring it to the homeowner and optionally make the bed.
"""

import rospy
import smach
import sys
import random
import smach_ros

import wakemeup_states as wakeStates
from robot_smach_states.util.designators import Designator, VariableDesignator, EdEntityDesignator
import robot_smach_states as states
from robot_smach_states.util.startup import startup
from robot_smach_states import Grab
from robot_smach_states import Place
from robot_skills.util import msg_constructors as geom
from robot_skills.util import transformations
from dragonfly_speech_recognition.srv import GetSpeechResponse

from robot_skills.amigo import Amigo
from robot_skills.sergio import Sergio
from robot_skills.mockbot import Mockbot


# ----------------------------------------------------------------------------------------------------

ROOM = "room_bedroom"

class WakeMeUp(smach.StateMachine):
    def __init__(self, robot):
        smach.StateMachine.__init__(self, outcomes=['Done','Aborted'])

        # ------------------------ DEFINITIONS ------------------------

        def is_awake(entity):
            #Check that the operator is awake
            return True

        # ------------------------ INITIALIZATIONS ------------------------

        waypoint_bedside_1 = EdEntityDesignator(robot, id="wakemeup_bedside_1")
        waypoint_bedside_2 = EdEntityDesignator(robot, id="wakemeup_bedside_2")
        waypoint_bedside_3 = EdEntityDesignator(robot, id="wakemeup_bedside_3")
        waypoint_bedside_4 = EdEntityDesignator(robot, id="wakemeup_bedside_4")
        waypoint_kitchen = EdEntityDesignator(robot, id="wakemeup_kitchen_table")

        homeowner = EdEntityDesignator(robot, type='human', criteriafuncs=[is_awake])
        bed = EdEntityDesignator(robot, type='bed')

        # TODO
        spec = Designator("I want <fruit_snack> with <cereal> and <milk> for breakfast")
        choices = Designator({  "fruit_snack"  : ["apple" ], "cereal" : ["cereal", "choco-flakes"], "milk": ["whole-milk"]})
        answer = VariableDesignator(resolve_type=GetSpeechResponse)


        #REVIEW: You can do breakfastCerealDes = VariableDesignator("") directly. The resole_type will be inferred from that
        breakfastCerealDes = VariableDesignator(resolve_type=str)       # designator containing chosen cereal name
        breakfastCerealDes.current = ""

        breakfastFruitDes = VariableDesignator(resolve_type=str)        # designator containing chosen fruit name
        breakfastFruitDes.current = ""

        breakfastMilkDes = VariableDesignator(resolve_type=str)         # designator containing chosen milk name
        breakfastMilkDes.current = ""

        loop_counter_des = VariableDesignator(resolve_type=int)         # counter for general looping (because smach iterator sucks)
        loop_counter_des.current = 0

        wakeup_limit_des = VariableDesignator(resolve_type=int)         # number of times to repeat wake up loop
        wakeup_limit_des.current = 3

        # ------------------------ STATE MACHINE ------------------------

        with self:
            # smach.StateMachine.add('INITIALIZE',
            #                     states.Initialize(robot),
            #                     transitions={   'initialized':'GOTO_BEDSIDE_1',
            #                                     'abort':'Aborted'})

            smach.StateMachine.add( 'START_CHALLENGE',
                                    states.StartChallengeRobust(robot, 'initial_pose'),
                                    transitions={   'Done':'SAY_OPERATOR_AWAKE',
                                                    'Aborted':'Aborted',
                                                    'Failed':'SAY_OPERATOR_AWAKE'})

            smach.StateMachine.add( "SAY_OPERATOR_AWAKE",
                                    states.Say(robot, "Lets see if my operator is awake", block=False), 
                                    transitions={"spoken":"GOTO_BEDSIDE_2"})

            smach.StateMachine.add('GOTO_BEDSIDE_1',
                                    states.NavigateToWaypoint(robot, waypoint_bedside_1),
                                    transitions={   'arrived':'WAKEUP_CONTAINER',
                                                    'unreachable':'GOTO_BEDSIDE_2',
                                                    'goal_not_defined':'GOTO_BEDSIDE_2'})

            smach.StateMachine.add('GOTO_BEDSIDE_2',
                                    states.NavigateToWaypoint(robot, waypoint_bedside_2),
                                    transitions={   'arrived':'WAKEUP_CONTAINER',
                                                    'unreachable':'GOTO_BEDSIDE_3',
                                                    'goal_not_defined':'GOTO_BEDSIDE_3'})

            smach.StateMachine.add('GOTO_BEDSIDE_3',
                                    states.NavigateToWaypoint(robot, waypoint_bedside_3),
                                    transitions={   'arrived':'WAKEUP_CONTAINER',
                                                    'unreachable':'GOTO_BEDSIDE_4',
                                                    'goal_not_defined':'GOTO_BEDSIDE_4'})

            smach.StateMachine.add('GOTO_BEDSIDE_4',
                                    states.NavigateToWaypoint(robot, waypoint_bedside_4),
                                    transitions={   'arrived':'WAKEUP_CONTAINER',
                                                    'unreachable':'WAKEUP_CONTAINER',
                                                    'goal_not_defined':'WAKEUP_CONTAINER'})


            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
            #                                 WAKEUP_CONTAINER
            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

            # container for this stage
            wakeupContainer = smach.StateMachine(outcomes = ['container_successed', 'container_failed'])

            with wakeupContainer:

                smach.StateMachine.add( "SAY_GOODMORNING",
                                        states.Say(robot, [ "Are you awake?", 
                                                            "Rise and shine, and look at me!", 
                                                            "Wakey wakey!", 
                                                            "Hello there sleepy head! Please face me", 
                                                            "Time for breakfast!"]),
                                        transitions={   'spoken' :'LOOK_AT_BED'})

                #TODO: Add concurrence to play music to wake someone up and monitor whether the dude is awake
                # smach.StateMachine.add( "AWAIT_HUMAN_AWAKE",
                #                         states.WaitForDesignator(robot, homeowner, attempts=2, sleep_interval=3),  # Wait 60 seconds
                #                         transitions={   'success' : 'container_successed',
                #                                         'failed' :  'container_successed'})
    
                smach.StateMachine.add( 'LOOK_AT_BED',
                                        wakeStates.LookAtBedTop(robot),
                                        transitions={    'done':'AWAIT_HUMAN_AWAKE'})

                smach.StateMachine.add("AWAIT_HUMAN_AWAKE",
                                        states.WaitForPersonInFront(robot, attempts=10, sleep_interval=1),  # resolve 10 time, with a 1 second sleep in between
                                        transitions={   'success':'container_successed',
                                                        'failed':'LOOP_BREAKER'})

                smach.StateMachine.add( 'LOOP_BREAKER',
                                        wakeStates.LoopBreaker(robot, counter_designator=loop_counter_des, limit_designator=wakeup_limit_des),
                                        transitions={   'break':'container_failed',
                                                        'continue':'SAY_GOODMORNING'})

            smach.StateMachine.add( 'WAKEUP_CONTAINER',
                                    wakeupContainer,
                                    transitions={   'container_successed':'CANCEL_HEAD_GOALS_1',
                                                    'container_failed': 'CANCEL_HEAD_GOALS_1'})

            smach.StateMachine.add( 'CANCEL_HEAD_GOALS_1',
                                    wakeStates.CancelHeadGoals(robot),
                                    transitions={    'done':'TAKE_ORDER_CONTAINER'})



            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
            #                                 TAKE_ORDER_CONTAINER
            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

            # container for this stage
            takeOrderContainer = smach.StateMachine(outcomes = ['container_successed', 'container_failed'])
            with takeOrderContainer:

                smach.StateMachine.add( "SAY_WHAT_BREAKFAST",
                                        states.Say(robot, [ "What would you like to have for breakfast?", 
                                                            "Please tell me your breakfast order.", 
                                                            "What do you want to eat?"], block=True),
                                        transitions={   'spoken' :'GET_ORDER'})


                smach.StateMachine.add( "GET_ORDER",
                                        wakeStates.GetOrder(robot, breakfastCerealDes, breakfastFruitDes, breakfastMilkDes),
                                        transitions={   'succeeded' :   'SAY_REPEAT_ORDER',
                                                        'failed':       'SAY_INCORRECT_ORDER'})

                smach.StateMachine.add( "SAY_INCORRECT_ORDER",
                                        states.Say(robot, [ "I didn't get that.",
                                                            "I missunderstood something," ], block=False),
                                        transitions={   'spoken' :'SAY_WHAT_BREAKFAST'})

                smach.StateMachine.add( "SAY_REPEAT_ORDER",
                                        wakeStates.RepeatOrderToPerson(robot, breakfastCerealDes, breakfastFruitDes, breakfastMilkDes),
                                        transitions={   'done' :'container_successed'})

            smach.StateMachine.add( 'TAKE_ORDER_CONTAINER',
                                    takeOrderContainer,
                                    transitions={   'container_successed':'PREP_BREAKFAST_CONTAINER',
                                                    'container_failed': 'SAY_ILL_CHOOSE_BREAKFAST'})


            smach.StateMachine.add( "SAY_ILL_CHOOSE_BREAKFAST",
                                    states.Say(robot, "I couldn't understand the breakfast order. I'll choose something for you.", block=False),
                                    transitions={   'spoken' :'PREP_BREAKFAST_CONTAINER'})


            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
            #                                 PREP_BREAKFAST_CONTAINER
            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

            # container for this stage
            prepBreakfastContainer = smach.StateMachine(outcomes = ['container_successed', 'container_failed'])
            with prepBreakfastContainer:

                smach.StateMachine.add( "SAY_PREPARING",
                                        states.Say(robot, [ "I'm preparing your breakfast! La la la la la." ], block=False),
                                        transitions={   'spoken' :'GOTO_KITCHEN'})

                smach.StateMachine.add('GOTO_KITCHEN',
                                    states.NavigateToWaypoint(robot, waypoint_kitchen),
                                    transitions={   'arrived':'container_successed',
                                                    'unreachable':'container_successed',
                                                    'goal_not_defined':'container_successed'})

            smach.StateMachine.add( 'PREP_BREAKFAST_CONTAINER',
                                    prepBreakfastContainer,
                                    transitions={   'container_successed':'DELIVER_BREAKFAST_CONTAINER',
                                                    'container_failed': 'DELIVER_BREAKFAST_CONTAINER'})


            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
            #                                 DELIVER_BREAKFAST_CONTAINER
            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

            # container for this stage
            deliverBreakfastContainer = smach.StateMachine(outcomes = ['container_successed', 'container_failed'])
            with deliverBreakfastContainer:

                smach.StateMachine.add('GOTO_BEDSIDE',
                                    states.NavigateToWaypoint(robot, waypoint_bedside_3),
                                    transitions={   'arrived':'SAY_COULD_NOT_PREPARE',
                                                    'unreachable':'SAY_COULD_NOT_PREPARE',
                                                    'goal_not_defined':'SAY_COULD_NOT_PREPARE'})

                smach.StateMachine.add( "SAY_COULD_NOT_PREPARE",
                                        states.Say(robot, [ "I'm sorry but i could not prepare your breakfast." ], block=False),
                                        transitions={   'spoken' :'container_successed'})

            smach.StateMachine.add( 'DELIVER_BREAKFAST_CONTAINER',
                                    deliverBreakfastContainer,
                                    transitions={   'container_successed':'END_CHALLENGE',
                                                    'container_failed': 'END_CHALLENGE'})


            smach.StateMachine.add('END_CHALLENGE',
                                   states.Say(robot,"My work here is done, goodbye!"),
                                   transitions={'spoken':'Done'})



# ------------------------ MAIN ------------------------


if __name__ == '__main__':
    rospy.init_node('wakemeup_exec')

    if len(sys.argv) > 1:
        robot_name = sys.argv[1]
    else:
        print "[CHALLENGE MANIPULATION] Please provide robot name as argument."
        exit(1)

    if robot_name == 'amigo':
        robot = Amigo(wait_services=True)
    elif robot_name == 'sergio':
        robot = Sergio(wait_services=True)
    elif robot_name == 'mockbot':
        robot = Mockbot(wait_services=True)
    else:
        print "Don't recognize that robot name: " + robot_name

    ''' If necessary: set initial state '''
    rospy.loginfo("Sys.argv = {0}, Length = {1}".format(sys.argv,len(sys.argv)))

    ''' Setup state machine'''
    machine = WakeMeUp(robot)

    if  len(sys.argv) > 2:
        print wakeStates.bcolors.WARNING + "Overriding initial_state to '" + sys.argv[2] +  "'" + wakeStates.bcolors.ENDC

        initial_state = [sys.argv[2]]
        machine.set_initial_state(initial_state)

    # for using smach viewer
    introserver = smach_ros.IntrospectionServer('server_name', machine, '/SM_ROOT_PRIMARY')
    introserver.start()

    try:
        machine.execute()
        # startup(WakeMeUp, robot_name=robot_name)
    except Exception, e:
        print "Exception occurred on state machine execution"

    introserver.stop()
