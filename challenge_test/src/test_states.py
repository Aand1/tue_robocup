#! /usr/bin/env python
import roslib;
import rospy
import smach
import subprocess
import inspect
import random
import ed_perception.msg
import math
import robot_skills.util.msg_constructors as msgs

from ed.msg import EntityInfo
from smach_ros import SimpleActionState
from collections import namedtuple
from dragonfly_speech_recognition.srv import GetSpeechResponse
from robot_smach_states.util.designators import *
from robot_smach_states.human_interaction.human_interaction import HearOptionsExtra
from robot_smach_states.manipulation import SjoerdsGrab
from robocup_knowledge import load_knowledge
from robot_skills.util import transformations
from robot_skills.arms import Arm

# ClassificationResult = namedtuple("ClassificationResult", "id type probability") #Generates a class with id, type and probability.

# ----------------------------------------------------------------------------------------------------

common_knowledge = load_knowledge("common")
challenge_knowledge = load_knowledge("challenge_person_recognition")
OBJECT_TYPES = challenge_knowledge.object_types

# define print shortcuts from common knowledge
printOk, printError, printWarning = common_knowledge.make_prints("[Challenge Test] ")


# ----------------------------------------------------------------------------------------------------

class PointAtOperator(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=['done'])
        self.robot = robot

    def execute(self, robot):
        printOk("PointAtOperator")

        # Get information about the operator and point at the location
        self.robot.rightArm.send_goal(0.5, -0.2, 0.9, 0, 0, 0, 60)

        return 'done'


# ----------------------------------------------------------------------------------------------------


class AskPersonName(smach.State):
    """
        Ask the person's name, and try to hear one of the names in common_knowledge
    """
    def __init__(self, robot, personNameDes, defaultName = 'Operator'):
        smach.State.__init__(   self, outcomes=['succeded', 'failed'])

        self.robot = robot
        self.personNameDes = personNameDes
        self.defaultName = defaultName

    def execute(self, userdata):
        printOk("AskPersonName")

        self.robot.speech.speak("What is your name?", block=True)

        spec = Designator("((<prefix> <name>)|<name>)")

        choices = Designator({"name"  : common_knowledge.names,
                              "prefix": ["My name is", "I'm called", "I am"]})

        answer = VariableDesignator(resolve_type=GetSpeechResponse)

        state = HearOptionsExtra(self.robot, spec, choices, answer.writeable)
        outcome = state.execute() # REVIEW(Loy): Luis, this is really not the way to go. Nest state machines using the smach way

        if not outcome == "heard":
            self.personNameDes.write(self.defaultName)

            printWarning("Speech recognition outcome was not successful (outcome: '{0}'). Using default name '{1}'".format(str(outcome), self.personNameDes.resolve()))
            return 'failed'
        else:
            try:
                print answer.resolve()
                name = answer.resolve().choices["name"]
                self.personNameDes.write(name)

                printOk("Result received from speech recognition is '" + name + "'")
            except KeyError, ke:
                printOk("KeyError resolving the name heard: " + str(ke))
                pass

        return 'succeded'


# ----------------------------------------------------------------------------------------------------


class PickUpRandomObj(smach.State):
    """
        Ask the person's name, and try to hear one of the names in common_knowledge
    """
    def __init__(self, robot, objectsIDsDes):
        smach.State.__init__(   self, outcomes=['succeded', 'failed', 'no_objects'])

        self.robot = robot
        self.objectsIDsDes = objectsIDsDes

    def execute(self, userdata):
        printOk("PickUpRandomObj")

        objsResolved = self.objectsIDsDes.resolve()

        if not (self.objectsIDsDes) or len(objsResolved) == 0:
            self.robot.speech.speak("I don't see any objects that i can pick up!", block=False)
            return 'no_objects'
        else:
            sentence = "I see "

            # describe objects
            for idx, obj in enumerate(objsResolved):

                if (idx < len(objsResolved)-1 or len(objsResolved) == 1):
                    # if its not the last item or there is only one
                    sentence+=(", a ")
                else:
                    # if its the last item, finish with 'and'
                    sentence+=("and a ")

                sentence+=("{} ".format(objsResolved[0].type if objsResolved[0].type else "unknown object"))
            
            # print sentence

            # Anounce objects found
            self.robot.speech.speak(sentence, block=False)
            
            selectedObj = random.choice(objsResolved)

            # import ipdb; ipdb.set_trace()

            # anounce which object is going to be picked up
            self.robot.speech.speak("I am going to pick up the {}".format(
                selectedObj.type if selectedObj.type else "unknown object"), block=False)

            armDes = UnoccupiedArmDesignator(self.robot.arms, self.robot.arms['right'])
            entityDes = EdEntityDesignator(self.robot, id=selectedObj.id)

            grabState = SjoerdsGrab(self.robot, entityDes, armDes)
            result = grabState.execute()

            if result == 'done':
                return 'succeded'
            else: 
                return 'failed'
