"""
State machine startup

Usage:
  challenge_xxx.py <robotname>
  challenge_xxx.py <robotname> --initial=<init>

Options:
  -h --help     Show this screen.
  --initial=<init>  Initial state
"""


import rospy
import smach_ros
import robot_skills
import sys
import traceback
from docopt import docopt


def startup(statemachine_creator, initial_state=None, robot_name=''):
    '''
    :param statemachine_creator: a function that outputs a statemachine.
        The function should take a robot as input.
    :param initial_state the state to start the state machine in. Can be supplied as command line argument
    :param robot_name name of the robot to initialize and start to pass to the state machine'''

    if initial_state or robot_name:
        rospy.logwarn("Setting initial_state and robot_name via the startup is not needed and deprecated. "
                      "This is inferred by startup from the command line")

    arguments = docopt(__doc__, version='robot_smach_states startup 2.0')
    robot_name = arguments["<robotname>"]
    initial_state = arguments["--initial"]

    robot = None
    available_robots = ['amigo', 'sergio', 'mockbot']
    if robot_name == "amigo":
        import robot_skills.amigo
        robot = robot_skills.amigo.Amigo(wait_services=True)
    elif robot_name == "sergio":
        import robot_skills.sergio
        robot = robot_skills.sergio.Sergio(wait_services=True)
    elif robot_name == "mockbot":
        import robot_skills.mockbot
        robot = robot_skills.mockbot.Mockbot(wait_services=True)
    else:
        rospy.logerr(
            "No robot named '{}'. Options: {}".format(robot_name, available_robots))
        exit(-1)

    rospy.loginfo("Using robot '" + robot_name + "'.")

    introserver = None

    with robot:
        try:
            # build the state machine
            executioner = statemachine_creator(robot)
            if initial_state:
                initial_state = [initial_state]
                rospy.logwarn(
                    "Overriding initial state with {}".format(initial_state))
                executioner.set_initial_state(initial_state)

            introserver = smach_ros.IntrospectionServer(
                statemachine_creator.__name__, executioner, '/SM_ROOT_PRIMARY')
            introserver.start()

            # Run the statemachine
            outcome = executioner.execute()
            print "Final outcome: {0}".format(outcome)
        except Exception, e:
            frame = traceback.extract_tb(sys.exc_info()[2])[0]
            fname, lineno, fn, text = frame
            rospy.logerr(
                "Error: {0},{1},{2},{3}".format(fname, lineno, fn, text))

            fname_stripped = fname.split("/")[-1:][0]

            message = "I encountered an error in '{0}'' on line {1}: '{4}'. Can I get a restart and try again?"\
                .format(fname_stripped, lineno, fn, text, e)
            message = message.replace("_", " ")
            message = message.replace(".py", "")

            print[fname, lineno, fn, text, e]
#            robot.speech.speak(message)
        finally:
            if introserver:
                introserver.stop()

