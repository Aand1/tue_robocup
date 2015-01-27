#! /usr/bin/env python
import roslib; roslib.load_manifest('robot_skills')
import rospy

import robot
import geometry_msgs

import mock

# class MockbotArms(arms.Arms):
#     def __init__(self, tf_listener):
#         super(MockbotArms, self).__init__(tf_listener)

class Mockbot(robot.Robot):
    """
    Interface to all parts of Mockbot. When initializing Mockbot, you can choose a list of components
    which wont be needed
    
    # I want a blind and mute Mockbot!
    >>> Mockbot(['perception', 'speech'])
    
    # I want a full fledged, awesome Mockbot
    >>> Mockbot()
    """
    def __init__(self, dontInclude = [], wait_services=False):
        super(Mockbot, self).__init__(robot_name="mockbot", wait_services=wait_services)

        self.tf_listener = mock.MagicMock()

        # Body parts
        self.base = mock.MagicMock()
        self.torso = mock.MagicMock()
        self.spindle = mock.MagicMock()
        self.leftArm = mock.MagicMock()
        self.rightArm = mock.MagicMock()
        self.head = mock.MagicMock()

        # Human Robot Interaction
        self.speech = mock.MagicMock()
        self.ears = mock.MagicMock()
        self.ebutton = mock.MagicMock()
        self.lights = mock.MagicMock()

        # Perception: can we get rid of this???
        self.perception = mock.MagicMock()

        # Reasoning/world modeling
        self.ed = mock.MagicMock()
        self.reasoner = mock.MagicMock()

        # Miscellaneous
        self.pub_target = rospy.Publisher("/target_location", geometry_msgs.msg.Pose2D)
        self.base_link_frame = "/"+self.robot_name+"/base_link"

        #Grasp offsets
        #TODO: Don't hardcode, load from parameter server to make robot independent.
        self.grasp_offset = geometry_msgs.msg.Point(0.5, 0.2, 0.0)

        self.publish_target = mock.MagicMock()
        self.tf_transform_pose = mock.MagicMock()
        self.close = mock.MagicMock()
        self.__enter__ = mock.MagicMock()
        self.__exit__ = mock.MagicMock()
        self.get_base_goal_poses = mock.MagicMock()

if __name__ == "__main__":
    print "     _              __"
    print "    / `\\  (~._    ./  )"
    print "    \\__/ __`-_\\__/ ./"
    print "   _ \\ \\/  \\  \\ |_   __"
    print " (   )  \\__/ -^    \\ /  \\"
    print "  \\_/ \"  \\  | o  o  |.. /  __"
    print "       \\\\. --' ====  /  || /  \\"
    print "         \\   .  .  |---__.\\__/"
    print "         /  :     /   |   |"
    print "         /   :   /     \\_/"
    print "      --/ ::    ("
    print "     (  |     (  (____"
    print "   .--  .. ----**.____)"
    print "   \\___/          "
    import atexit
    import util.msg_constructors as msgs
    from reasoner import Compound, Conjunction, Sequence, Variable

    rospy.init_node("amigo_executioner", anonymous=True)
    amigo = Mockbot(wait_services=False)
    robot = amigo #All state machines use robot. ..., this makes copy/pasting easier.

    atexit.register(amigo.close) #When exiting the interpreter, call amigo.close(), which cancels all action goals etc.

    head_reset = lambda: amigo.head.reset_position()
    head_down  = lambda: amigo.head.look_down()
    right_close = lambda: amigo.rightArm.send_gripper_goal_close()
    left_close = lambda: amigo.leftArm.send_gripper_goal_close()
    right_open = lambda: amigo.rightArm.send_gripper_goal_open()
    left_open = lambda: amigo.leftArm.send_gripper_goal_open()
    speak = lambda sentence: amigo.speech.speak(sentence, block=False)
    praat = lambda sentence: amigo.speech.speak(sentence, language='nl', block=False)
    look_at_point = lambda x, y, z: amigo.head.send_goal(msgs.PointStamped(x, y, z, frame_id="/amigo/base_link"))
        
    r = amigo.reasoner
    q = amigo.reasoner.query

    mapgo = amigo.base.go
    
    def basego(x,y,phi):
        return amigo.base.go(x,y,phi,frame="/amigo/base_link")

    open_door   = lambda: r.assertz(r.state("door1", "open"))
    close_door  = lambda: r.assertz(r.state("door1", "close"))
    def insert_object(x,y,z):
        from test_tools.WorldFaker import WorldFaker
        wf = WorldFaker()
        wf.insert({"position":(x,y,z)})

    #Useful for making location-files
    def get_pose_2d():
       posestamped = amigo.base.location
       loc,rot = posestamped.pose.point, posestamped.pose.orientation
       rot_array = [rot.w, rot.x, rot.y, rot.z]
       rot3 = tf.transformations.euler_from_quaternion(rot_array)
       print 'x={0}, y={1}, phi={2}'.format(loc.x, loc.y, rot3[0])
       return (loc.x, loc.y, rot3[0]) 

    def hear(text):
        pub = rospy.Publisher('/pocketsphinx/output', std_msgs.msg.String)
        rospy.logdebug("Telling Mockbot '{0}'".format(text))
        pub.publish(std_msgs.msg.String(text))

    def save_sentence(sentence):
        """Let amigo say a sentence and them move the generated speech file to a separate file that will not be overwritten"""
        speak(sentence)
        import os
        path = sentence.replace(" ", "_")
        path += ".wav"
        os.system("mv /tmp/speech.wav /tmp/{0}".format(path))

    def test_audio():
        OKGREEN = '\033[92m'
        ENDC = '\033[0m'

        amigo.speech.speak("Please say: continue when I turn green", block=True) #definitely block here, otherwise we hear ourselves
        
        result = amigo.ears.ask_user("continue")
        rospy.loginfo("test_audio result: {0}".format(result))
        if result and result != "false":
            rospy.loginfo(OKGREEN+"Speach pipeline working"+ENDC)
            amigo.speech.speak("Yep, my ears are fine", block=False)
        else:
            rospy.logerr("Speech pipeline not working")
            amigo.speech.speak("Nope, my ears are clogged", block=False)


    print """\033[1;33m You can now command amigo from the python REPL. 
    Type e.g. help(amigo) for help on objects and functions, 
    or type 'amigo.' <TAB> to see what methods are available. 
    Also, try 'dir()'
    You can use both robot.foo or amigo.foo for easy copypasting.
    Press ctrl-D or type 'exit()' to exit the awesome amigo-console.
    WARNING: When the console exits, it cancels ALL arm and base goals.
    There are handy shortcuts, such as: 
        - mapgo/basego(x,y,phi), 
        - speak/praat/(sentence), save_sentence(sentence) saves the .wav file to /tmp/<sentence_you_typed>.wav
        - head_down, head_reset, left/right_close/open, look_at_point(x,y,z), 
        - get_pose_2d()
        - test_audio()
    Finally, methods can be called without parentheses, like 'speak "Look ma, no parentheses!"'\033[1;m"""
