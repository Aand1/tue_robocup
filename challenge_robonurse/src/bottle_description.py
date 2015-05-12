import rospy
import smach

from robot_smach_states.util.designators import check_resolve_type
from ed.msg import EntityInfo
from robot_skills.util import msg_constructors as geom
from collections import OrderedDict
import operator
from robot_skills.util import transformations
import random


class BottleDescription(object):
    def __init__(self, size=None, color=None, label=None):
        self.size = size
        self.color = color
        self.label = label


def get_entity_color(entity):
        try:
            return max(entity.data['perception_result']['color_matcher']['colors'], key=lambda d: d['value'])['name']
        except KeyError, ke:
            rospy.logwarn(ke)
            return ""
        except TypeError, te:
            rospy.logwarn(te)
            return ""


def get_entity_size(entity):
    size = ""
    try:
        height = abs(entity.z_min - entity.z_max)
        if height < 0.05:
            size = "small"
        elif 0.05 <= height < 0.10:
            size = "normal sized"
        elif 0.10 <= height:
            size = "big"
        rospy.loginfo("Height of object {0} is {1} so classifying as {2}".format(entity.id, height, size))
    except:
        pass

    return size

class DescribeBottles(smach.State):
    def __init__(self, robot, bottle_collection_designator, spec_designator, choices_designator):
        """
        @param robot the robot to run this with
        @bottle_collection_designator designates a bunch of bottles/entities
        @param spec_designator based on the descriptions read aloud by the robot, a spec for speech interpretation is created and stored in this VariableDesignator
        """
        smach.State.__init__(self, outcomes=["succeeded", "failed"])
        self.robot = robot
        check_resolve_type(bottle_collection_designator, [EntityInfo])
        self.bottle_collection_designator = bottle_collection_designator

        self.spec_designator = spec_designator
        self.choices_designator = choices_designator

    def execute(self, userdata=None):
        bottles = self.bottle_collection_designator.resolve()
        if not bottles:
            return "failed"

        #TODO: Sort bottles by their Y-coord wrt base_link. We go from large to small, so the leftmost if first
        bottle_to_y_dict = {}
        for bottle in bottles:
            in_map = geom.PointStamped(point=bottle.center_point, frame_id=bottle.id)
            in_base_link = transformations.tf_transform(in_map, "/map", "/"+self.robot.robot_name+"/base_link", self.robot.tf_listener)
            bottle_to_y_dict[bottle] = in_base_link.y

        sorted_bottles = sorted(bottle_to_y_dict.items(), key=operator.itemgetter(1))  # Sort dict by value, i.e. the bottle's Y

        descriptions = OrderedDict()
        for bottle_at_y in sorted_bottles:
            descriptions[bottle_at_y] = self.describe_bottle(bottle_at_y)

        self.robot.speech.speak("I see {0} bottles, which do you want?".format(len(descriptions)))
        self.robot.speech.speak("From left to right, I have a")
        for bottle, description in descriptions.iteritems():
            desc_sentence = "a {size}, {color} one".format(size=description.size, color=description.color)
            if description.label:
                desc_sentence += " labeled {label}".format(label=description.label)
            self.robot.speech.speak(desc_sentence)
        self.robot.speech.speak("Which do you want?")

        colors = set([desc.color for desc in descriptions.values()])
        sizes = set([desc.size for desc in descriptions.values()])
        labels = set([desc.label for desc in descriptions.values()])
        choices = {"color": colors, "size": sizes, "label": labels}

        # import ipdb; ipdb.set_trace()
        self.spec_designator.current = "Give me the <size> <color> bottle labeled <label>"  # TODO: allow more sentences
        self.choices_designator.current = choices

        return "succeeded"

    def describe_bottle(self, bottle_at_y):
        bottle_entity, y = bottle_at_y

        # import ipdb; ipdb.set_trace()
        most_probable_color = get_entity_color(bottle_entity)
        size = get_entity_size(bottle_entity)

        return BottleDescription(   size=size,
                                    color=most_probable_color,
                                    label=random.choice(["aspirin", "ibuprofen", ""]))