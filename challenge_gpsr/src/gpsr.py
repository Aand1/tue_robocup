#! /usr/bin/python

# ------------------------------------------------------------------------------------------------------------------------
# By Sjoerd van den Dries, 2016

# TODO:
# - initial pose estimate
# - bring it to me
# - "bring X from Y to Z who is in L"
# - ... left of the sink ... etc

# Cannot deal with:
#    look for a person in the entrance and answer a question

        # go to the bookcase, find a person, and say your name

        # bookcase
        #      Locate at least three objects there.

# ------------------------------------------------------------------------------------------------------------------------

import os
import sys
import yaml
import cfgparser
import rospy
import random

import robot_smach_states
from robot_smach_states.navigation import NavigateToObserve, NavigateToWaypoint, NavigateToSymbolic
from robot_smach_states import SegmentObjects, Grab
from robot_smach_states.util.designators import EdEntityDesignator, EntityByIdDesignator, VariableDesignator, DeferToRuntime, analyse_designators, UnoccupiedArmDesignator
from robot_skills.classification_result import ClassificationResult
from robocup_knowledge import load_knowledge
from command_recognizer import CommandRecognizer
from datetime import datetime, timedelta
import robot_smach_states.util.designators as ds

from robot_smach_states import LookAtArea

challenge_knowledge = load_knowledge('challenge_gpsr')
speech_data = load_knowledge('challenge_speech_recognition')

# ------------------------------------------------------------------------------------------------------------------------

def not_implemented(robot, parameters):
    rospy.logerr("This was not implemented, show this to Sjoerd: {}".format(parameters))
    robot.speech.speak("Not implemented! Warn Sjoerd", block=False)
    return

# ------------------------------------------------------------------------------------------------------------------------

def search_for_object(robot, location, entity_type):
    # classify step
    classifications_des = VariableDesignator([], resolve_type=[ClassificationResult])
    seg = SegmentObjects(robot,
        objectIDsDes=classifications_des.writeable,
        entityDes=EdEntityDesignator(robot, id=location), searchArea="on_top_of")
    seg.execute()
    results = classifications_des.resolve()

    # select the result
    if not len(results):
        robot.speech.speak("I could not find the object")
        return False

    for obj in results:
        print obj
        if obj.type == entity_type:
            return obj

    if os.environ.get('ROBOT_REAL') == 'true':
        return False

    robot.speech.speak("I'm grabbing a random object")
    return random.choice(results)

# ------------------------------------------------------------------------------------------------------------------------

class GPSR:

    def __init__(self):
        self.entity_ids = []
        self.entity_type_to_id = {}
        self.object_to_location = {}

        self.last_entity_id = None

    def resolve_entity_id(self, description):
        if isinstance(description, str):
            if description == "it":
                return self.last_entity_id
            elif description == "operator":
                return "initial_pose"
            else:
                return description

    # ------------------------------------------------------------------------------------------------------------------------

    def navigate(self, robot, parameters):
        entity_id = self.resolve_entity_id(parameters["entity"])
        self.last_entity_id = entity_id

        robot.speech.speak("I am going to the %s" % entity_id, block=False)

        if entity_id in challenge_knowledge.rooms:
            nwc =  NavigateToSymbolic(robot,
                                            { EntityByIdDesignator(robot, id=entity_id) : "in" },
                                              EntityByIdDesignator(robot, id=entity_id))
        else:
            nwc = NavigateToObserve(robot,
                                 entity_designator=EdEntityDesignator(robot, id=entity_id),
                                 radius=.5)

        nwc.execute()

    # ------------------------------------------------------------------------------------------------------------------------

    def answer_question(self, robot, parameters):
        robot.head.look_at_ground_in_front_of_robot(100)

        robot.speech.speak("What is your question?")

        res = robot.ears.recognize(spec=speech_data.spec,
                                   choices=speech_data.choices,
                                   time_out=rospy.Duration(15))

        if not res:
            robot.speech.speak("My ears are not working properly, sorry!")

        if res:
            if "question" in res.choices:
                rospy.loginfo("Question was: '%s'?"%res.result)
                robot.speech.speak("The answer is %s" % speech_data.choice_answer_mapping[res.choices['question']])
            else:
                robot.speech.speak("Sorry, I do not understand your question")

    # ------------------------------------------------------------------------------------------------------------------------

    def say(self, robot, parameters):
        sentence = parameters["sentence"]
        rospy.loginfo('Answering %s', sentence)

        if sentence == 'TIME':
            hours = datetime.now().hour
            minutes = datetime.now().minute
            line = "The time is {} {}".format(hours, minutes)
        elif sentence == "ROBOT_NAME":
            line = 'My name is %s' % robot.robot_name
        elif sentence == 'TODAY':
            line = datetime.today().strftime('Today is %A %B %d')
        elif sentence == 'TOMORROW':
            line = (datetime.today() + timedelta(days=1)).strftime('Tomorrow is %A %B %d')
        elif sentence == 'DAY_OF_MONTH':
            line = datetime.now().strftime('It is day %d of the month')
        elif sentence == 'DAY_OF_WEEK':
            line = datetime.today().strftime('Today is a %A')
        else:
            line = sentence

        robot.speech.speak(line)

    # ------------------------------------------------------------------------------------------------------------------------

    def pick_up(self, robot, parameters):
        entity_type = self.resolve_entity_id(parameters["entity"])
        self.last_entity_id = entity_type

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 

        if "from" in parameters:
            room_or_location = self.resolve_entity_id(parameters["from"])

            if room_or_location in challenge_knowledge.rooms:
                locations = [loc["name"] for loc in challenge_knowledge.common.locations
                             if loc["room"] == room_or_location and loc["manipulation"] == "yes"]
            else:
                locations = [room_or_location]

            locations_with_areas = []
            for location in locations:
                locations_with_areas += [(location, challenge_knowledge.common.get_inspect_areas(location))]
        else:
            obj_cat = None
            for obj in challenge_knowledge.common.objects:
                if obj["name"] == entity_type:
                    obj_cat = obj["category"]

            location = challenge_knowledge.common.category_locations[obj_cat].keys()[0]
            area_name = challenge_knowledge.common.category_locations[obj_cat].values()[0]

            locations_with_areas = [(location, [area_name])]

            robot.speech.speak("The {} is a {}, which is stored on the {}".format(entity_type, obj_cat, location), block=False)

        location_defined = (len(locations_with_areas) == 1)

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 

        entity_id = None

        for loc_and_areas in locations_with_areas:

            (location, area_names) = loc_and_areas

            robot.speech.speak("Going to the %s" % location, block=False)

            last_nav_area = None

            for area_name in area_names:

                nav_area = challenge_knowledge.common.get_inspect_position(location, area_name)

                if nav_area != last_nav_area:

                    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 
                    # Move to the location

                    location_des = ds.EntityByIdDesignator(robot, id=location)
                    room_des = ds.EntityByIdDesignator(robot, id=challenge_knowledge.common.get_room(location))

                    nwc = NavigateToSymbolic( robot,
                                              {location_des : nav_area, room_des : "in"},
                                              location_des)
                    nwc.execute()

                    last_nav_area = nav_area

                # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 
                # Look at the area

                look_sm = LookAtArea(robot,
                                     EdEntityDesignator(robot, id=location),
                                     area_name)
                look_sm.execute()

                import time
                time.sleep(1)

                # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 
                # Segment

                segmented_entities = robot.ed.update_kinect("{} {}".format(area_name, location))

                found_entity_ids = segmented_entities.new_ids + segmented_entities.updated_ids

                # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 
                # Classify

                entity_types_and_probs = robot.ed.classify(ids=found_entity_ids,
                                                           types=challenge_knowledge.common.objects)

                best_prob = 0
                for det in entity_types_and_probs:
                    if det.type == entity_type and det.probability > best_prob:
                        entity_id = det.id
                        best_prob = det.probability

                if not entity_id:
                    if location_defined:
                        robot.speech.speak("Oh no! The {} should be here, but I can't find it.".format(entity_type), block=False)
                        # TODO: get the entity with highest prob!
                    else:
                        robot.speech.speak("Nope, the {} is not here.!".format(entity_type), block=False)
                else:
                        robot.speech.speak("Found the {}!".format(entity_type), block=False)
                        object_found = True

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 

        if entity_id:

            robot.speech.speak("Going to grab the {}".format(entity_type))

            # grab it
            grab = Grab(robot, EdEntityDesignator(robot, id=entity_id),
                 UnoccupiedArmDesignator(robot.arms, robot.leftArm, name="empty_arm_designator"))
            result = grab.execute()            

    # ------------------------------------------------------------------------------------------------------------------------

    def bring(self, robot, parameters):

        if parameters["entity"] != "it":
            self.pick_up(robot, parameters)

        to_id = self.resolve_entity_id(parameters["to"])

        # Move to the location
        nwc = NavigateToObserve(robot,
                         entity_designator=EdEntityDesignator(robot, id=to_id),
                         radius=.5)
        nwc.execute()

        # TODO: handover

    # ------------------------------------------------------------------------------------------------------------------------

    def find(self, robot, parameters):
        entity_id = self.resolve_entity_id(parameters["entity"])

        room = self.last_entity_id
        if not room:
            robot.speech.speak("I don't know where to start looking")
            return
        if room not in challenge_knowledge.rooms:
            robot.speech.speech("I don't understand the location")
            return

        locations = challenge_knowledge.room_to_grab_locations[room]
        rospy.loginfo("Location search list: %s", str(locations))

        for location in locations:
            robot.speech.speak("I'm going to search the %s" % location)
            # drive
            nav = NavigateToSymbolic(robot, {
                    EdEntityDesignator(robot, id=room) : "in",
                    EdEntityDesignator(robot, id=location) : "in_front_of"
                }, EdEntityDesignator(robot, id=location))
            nav.execute()

            # segment
            robot.speech.speak("Is the %s here?" % entity_id)
            obj = search_for_object(robot, location, entity_id)
            if obj:
                break

        if not obj:
            robot.speech.speak("I could not find the %s" % entity_id)
            return

        robot.speech.speak("I found the %s, lets grab it" % entity_id)

        # grab it
        grab = Grab(robot, EdEntityDesignator(robot, id=obj.id),
             UnoccupiedArmDesignator(robot.arms, robot.leftArm, name="empty_arm_designator"))
        result = grab.execute()

        if result == 'done':
            robot.speech.speak("That went well")
        else:
            robot.speech.speak("Sorry, I failed")

    # ------------------------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------------

    def execute_command(self, robot, command_recognizer, action_functions, sentence=None):

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - 
        # If sentence is given on command-line

        if sentence:
            res = command_recognizer.parse(sentence)
            if not res:
                robot.speech.speak("Sorry, could not parse the given command")
                return False

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - 
        # When using text-to-speech

        else:
            import time
            time.sleep(1)
            robot.head.look_at_standing_person()
            robot.head.wait_for_motion_done()

            res = None
            while not res:
                robot.speech.speak("Give your command after the ping", block=True)
                res = command_recognizer.recognize(robot)
                if not res:
                    robot.speech.speak("Sorry, I could not understand", block=True)

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - -                    

        (sentence, semantics_str) = res
        print "Sentence: %s" % sentence
        print "Semantics: %s" % semantics_str

        robot.speech.speak("You want me to %s" % sentence.replace(" your", " my").replace(" me", " you"), block=True)

        # TODO: ask for confirmation?

        semantics = yaml.load(semantics_str)

        actions = []
        if "action1" in semantics:
            actions += [semantics["action1"]]
        if "action2" in semantics:
            actions += [semantics["action2"]]
        if "action3" in semantics:
            actions += [semantics["action3"]]

        for a in actions:
            action_type = a["action"]

            if action_type in action_functions:
                action_functions[action_type](robot, a)
            else:
                print "Unknown action type: '%s'" % action_type

    # ------------------------------------------------------------------------------------------------------------------------

    def run(self):
        rospy.init_node("gpsr")

        if len(sys.argv) < 2:
            print "Please specify a robot name 'amigo / sergio'"
            return 1

        robot_name = sys.argv[1]
        if robot_name == 'amigo':
            from robot_skills.amigo import Amigo as Robot
        elif robot_name == 'sergio':
            from robot_skills.sergio import Sergio as Robot
        else:
            print "unknown robot"
            return 1

        robot = Robot()

        command_recognizer = CommandRecognizer(os.path.dirname(sys.argv[0]) + "/grammar.fcfg", challenge_knowledge)

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

        # # Query world model for entities
        # entities = robot.ed.get_entities(parse=False)
        # for e in entities:
        #     self.entity_ids += [e.id]

        #     for t in e.types:
        #         if not t in self.entity_type_to_id:
        #             self.entity_type_to_id[t] = [e.id]
        #         else:
        #             self.entity_type_to_id[t] += [e.id]


        # for (furniture, objects) in challenge_knowledge.furniture_to_objects.iteritems():
        #     for obj in objects:
        #         self.object_to_location[obj] = furniture

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

        action_functions = {}
        action_functions["navigate"] = self.navigate
        action_functions["find"] = self.find
        action_functions["answer-question"] = self.answer_question
        action_functions["pick-up"] = self.pick_up
        action_functions["bring"] = self.bring
        action_functions["say"] =  self.say

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

        run_forever = False
        sentence = None
        if len(sys.argv) > 2 and sys.argv[2] == "--forever":
            run_forever = True
        else:
            sentence = " ".join([word for word in sys.argv[2:] if word[0] != '_'])

        done = False
        while not done:
            self.execute_command(robot, command_recognizer, action_functions, sentence)
            if not run_forever:
                done = True

# ------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    gpsr = GPSR()
    sys.exit(gpsr.run())
