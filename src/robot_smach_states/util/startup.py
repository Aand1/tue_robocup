'''Put all the boilerplate tostart an executive in this file and functions'''

import rospy
import smach_ros
import robot_skills
import sys, traceback

from optparse import OptionParser

def startup(statemachine_creator, scenario_setup_function=None, initial_state=None, robot_name=''):
    '''Takes a FUNCTION that outputs a smach statemachine as input,
    and optionally also a FUNCTION that attaches hooks for testing the statemachine as input.
    It sets up convenient ways to handle some errors, by letting the robot announce an error,
    it parses options such as --test=part1,part2,... and runs an introspection server.

    @param statemachine_creator: a function that outputs a statemachine.
        The function should take a robot as input.
    @param scenario_setup_function: a function that sets up a scenario to test the created statemachine with.
        It must also take a robot and a statemachine as input'''

    parser = OptionParser()
    parser.add_option("--test",
        action="store",
        type="string",
        dest="testmode",
        help="Test the listed parts: --test=head,base,perception,worldmodel,arms,... or simply --test=all")
    options, arguments = parser.parse_args()

    if robot_name == '':
        robot_name = "amigo"   # Default

    rospy.loginfo("Using robot '" + robot_name + "'.")

    robot = None
    if robot_name == "amigo":
        import robot_skills.amigo
        if options.testmode:
            fakeparts = options.testmode
            fakeparts = fakeparts.split(",")
            if "all" in fakeparts:
                fakeparts=['base','arms','perception','head', 'worldmodel']
            rospy.logwarn("Executive started in TESTMODE, so mocking these parts of amigo: {0}".format(fakeparts))
            from test_tools.build_amigo import build_amigo
            robot = build_amigo(fake=fakeparts, wait_services=True)
        else:
            print "If you want to test an executive, use the --test option and specify what parts you want to mock."
            robot = robot_skills.amigo.Amigo(wait_services=True)
    elif robot_name == "sergio":
        import robot_skills.sergio
        robot = robot_skills.sergio.Sergio(wait_services=True)
    elif robot_name == "mockbot":
        import robot_skills.mockbot
        robot = robot_skills.mockbot.Mockbot(wait_services=True)

    introserver = None
    with robot:
        try:
            #build the state machine
            executioner = statemachine_creator(robot)
            if initial_state:
                executioner.set_initial_state(initial_state)
            introserver = smach_ros.IntrospectionServer('server_name', executioner, '/SM_ROOT_PRIMARY')
            introserver.start()
            if options.testmode and scenario_setup_function:
                #add side-effects to make testing possible without working perception
                scenario_setup_function(robot, executioner)

            #Run the statemachine
            outcome = executioner.execute()
            print "Final outcome: {0}".format(outcome)
        except Exception, e:
            frame = traceback.extract_tb(sys.exc_info()[2])[0]
            fname,lineno,fn,text = frame
            rospy.logerr("Error: {0},{1},{2},{3}".format(fname,lineno,fn,text))

            fname_stripped = fname.split("/")[-1:][0]

            message = "I encountered an error in '{0}'' on line {1}: '{4}'. Can I get a restart and try again?"\
                .format(fname_stripped,lineno,fn,text, e)
            message = message.replace("_", " ")
            message = message.replace(".py", "")

            print [fname,lineno,fn,text, e]
#            robot.speech.speak(message)
        finally:
            if introserver:
                introserver.stop()

# Used in final of rgo2014. Perhaps as well in brazil. Adding possibility to start in certain state.
def startup_final(statemachine_creator, initial_state, scenario_setup_function=None):
    '''Takes a FUNCTION that outputs a smach statemachine as input,
    and optionally also a FUNCTION that attaches hooks for testing the statemachine as input.
    It sets up convenient ways to handle some errors, by letting the robot announce an error,
    it parses options such as --test=part1,part2,... and runs an introspection server.

    @param statemachine_creator: a function that outputs a statemachine.
        The function should take a robot as input.
    @param scenario_setup_function: a function that sets up a scenario to test the created statemachine with.
        It must also take a robot and a statemachine as input'''

    parser = OptionParser()
    parser.add_option("--test",
        action="store",
        type="string",
        dest="testmode",
        help="Test the listed parts: --test=head,base,perception,worldmodel,arms,... or simply --test=all")
    options, arguments = parser.parse_args()


    amigo = None
    if options.testmode:
        fakeparts = options.testmode
        fakeparts = fakeparts.split(",")
        if "all" in fakeparts:
            fakeparts=['base','arms','perception','head', 'worldmodel']
        rospy.logwarn("Executive started in TESTMODE, so mocking these parts of amigo: {0}".format(fakeparts))
        from test_tools.build_amigo import build_amigo
        amigo = build_amigo(fake=fakeparts, wait_services=True)
    else:
        print "If you want to test an executive, use the --test option and specify what parts you want to mock."
        amigo = robot_skills.amigo.Amigo(wait_services=True)

    introserver = None
    with amigo:
        try:
            #build the state machine
            executioner = statemachine_creator(amigo)
            introserver = smach_ros.IntrospectionServer('server_name', executioner, '/SM_ROOT_PRIMARY')
            introserver.start()
            if options.testmode and scenario_setup_function:
                #add side-effects to make testing possible without working perception
                scenario_setup_function(amigo, executioner)

            rospy.logwarn("Setting initial state to {0}, please make sure the reasoner is reset and the robot is localized correctly".format(initial_state))
            executioner.set_initial_state(initial_state)

            #Run the statemachine
            outcome = executioner.execute()
            print "Final outcome: {0}".format(outcome)
        except Exception, e:
            frame = traceback.extract_tb(sys.exc_info()[2])[0]
            fname,lineno,fn,text = frame
            rospy.logerr("Error: {0},{1},{2},{3}".format(fname,lineno,fn,text))

            fname_stripped = fname.split("/")[-1:][0]

            message = "I encountered an error in '{0}'' on line {1}: '{4}'. Can I get a restart and try again?"\
                .format(fname_stripped,lineno,fn,text, e)
            message = message.replace("_", " ")
            message = message.replace(".py", "")

            print [fname,lineno,fn,text, e]
            amigo.speech.speak(message)
        finally:
            if introserver:
                introserver.stop()
