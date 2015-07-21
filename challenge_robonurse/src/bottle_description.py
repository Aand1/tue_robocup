#!/usr/bin/python

import rospy
import smach

from visualization_msgs.msg import Marker
from robot_smach_states.util.designators import check_resolve_type
from ed.msg import EntityInfo
from robot_skills.util import msg_constructors as geom
from collections import OrderedDict
import operator
from robot_skills.util import transformations
import random

import os
from PIL import Image
import cStringIO as StringIO
import numpy as np

from color_analysis import analyze

def save_entity_image_to_file(world_model_ed, entityID, colorname):
    """Saves an entity's measurement to a file. The filename includes the entity's ID and a colorname. """
    file_name = "images/%s_%s.jpg"%(entityID, colorname)
    if "/" in file_name and not os.path.exists(os.path.dirname(file_name)):
        os.makedirs(os.path.dirname(file_name))

    # ed request
    info = world_model_ed.get_entity_info(entityID)

    try:
        byte_array = bytearray(info.measurement_image)
        f = open(file_name, 'wb')
        f.write(byte_array)
        f.close()
        del f

        # stream = StringIO.StringIO(byte_array)
        
        # import ipdb; ipdb.set_trace()
        image = Image.open(file_name)

        image_data = np.asarray(image)
        image_data_bw = image_data.max(axis=2)
        non_empty_columns = np.where(image_data_bw.max(axis=0)>0)[0]
        non_empty_rows = np.where(image_data_bw.max(axis=1)>0)[0]
        cropBox = (min(non_empty_rows), max(non_empty_rows), min(non_empty_columns), max(non_empty_columns))

        image_data_new = image_data[cropBox[0]:cropBox[1]+1, cropBox[2]:cropBox[3]+1 , :]

        cropped_image = Image.fromarray(image_data_new)
        cropped_file_name = "images/%s_%s_cropped.jpg"%(entityID, colorname)
        cropped_image.save(cropped_file_name)
    except Exception, e:
        rospy.logerr("Could not save image for {} because {}".format(entityID, e))
        return None

    return file_name


class BottleDescription(object):
    """A description of a bottle. A bottle can be described by its size, color, label, relative position etc. """
    def __init__(self, color=None, label=None, height=None, position=None, height_description=None, position_description=None):
        self.color = color
        self.label = label
        self.height = height
        self.position = position

        self.height_description = height_description
        self.position_description = position_description

    def __eq__(self, other):
        """Check equality of self against other
        >>> assert BottleDescription() == BottleDescription()
        >>> assert BottleDescription(height_description="big") == BottleDescription(height_description="big")
        >>> assert BottleDescription(label="ibuprofen") == BottleDescription(label="ibuprofen")
        >>> assert BottleDescription(height_description="big", color="red") == BottleDescription(height_description="big", color="red")
        >>> assert BottleDescription(height_description="big", color="red", position_description="left") == BottleDescription(height_description="big", color="red", position_description="left")
        
        >>> assert BottleDescription(label="ibuprofen") != BottleDescription(height_description="small")
        >>> assert BottleDescription(height_description="big", color="red") != BottleDescription(height_description="big", color="blue")
        
        >>> assert BottleDescription(position_description="left") != BottleDescription(position_description="right")
        """
        return self.height_description == other.height_description \
            and self.color == other.color \
            and self.label == other.label \
            and self.position_description == other.position_description

    def __repr__(self):
        return "BottleDescription(height_description={height_description}, color={color}, label={label}, position_description={position_description})".format(**self.__dict__)


def get_entity_color(entity):
    """Try to get the result of the color_matcher. 
    The color_matcher's output is a dictionary mapping a color name to a value between 0-1. So, select the key (color name) maximum value (value)"""
    try:
        return max(entity.data['perception_result']['color_matcher']['colors'], key=lambda d: d['value'])['name']
    except KeyError, ke:
        rospy.logwarn("Entity {0} has no key {1}".format(entity.id, ke))
        return None
    except TypeError, te:
        rospy.logwarn("{1} for Entity {0}".format(entity.id, te))
        return None


def get_entity_size(entity):
    """Give a size label for the entity, based on an absolute scale. """
    height_description = None
    try:
        height = abs(entity.z_min - entity.z_max)
        if height < 0.05:
            height_description = "small"
        elif 0.05 <= height < 0.10:
            height_description = "normal sized"
        elif 0.10 <= height:
            height_description = "big"
        rospy.loginfo("Height of object {0} is {1} so classifying as {2}".format(entity.id, height, height_description))
    except:
        pass

    return height_description, height

class DescribeBottles(smach.State):
    def __init__(self, robot, bottle_collection_designator, spec_designator, choices_designator, bottle_desc_mapping_designator):
        """
        @param robot the robot to run this with
        @bottle_collection_designator designates a bunch of bottles/entities
        @param spec_designator based on the descriptions read aloud by the robot, a spec for speech interpretation is created and stored in this VariableDesignator
        @param choices_designator what choices are there for the speech descriptions, e.g. what colors, labels etc are there to choose from?
        @param bottle_desc_mapping_designator must be assigned a dictionary mapping EntityInfos to BottleDescriptions.
        """
        smach.State.__init__(self, outcomes=["succeeded", "failed"])
        self.robot = robot
        check_resolve_type(bottle_collection_designator, [EntityInfo])
        self.bottle_collection_designator = bottle_collection_designator

        self.spec_designator = spec_designator
        self.choices_designator = choices_designator
        self.bottle_desc_mapping_designator = bottle_desc_mapping_designator
        self._pub = rospy.Publisher("/bottles", Marker, queue_size=10)

    def execute(self, userdata=None):
        # self.robot.head.reset()
        # import ipdb; ipdb.set_trace()

        entity_ids = self.robot.ed.segment_kinect(max_sensor_range=2)
        self.robot.ed.classify(ids=entity_ids, types=[])

        bottles = self.bottle_collection_designator.resolve()
        if not bottles:
            return "failed"
        
        #Lock the IDs in the world model so that they keep their IDs persistently
        bottle_ids = [bottle.id for bottle in bottles]
        rospy.logwarn("Locking IDs {}".format(bottle_ids))
        self.robot.ed.lock_entities(bottle_ids, [])
        

        #TODO: Sort bottles by their Y-coord wrt base_link. We go from large to small, so the leftmost if first
        bottle_to_y_dict = {}
        for bottle in bottles:
            in_map = geom.PointStamped(point=bottle.pose.position, frame_id=bottle.id)
            in_base_link = transformations.tf_transform(in_map, "/map", "/"+self.robot.robot_name+"/base_link", self.robot.tf_listener)
            bottle_to_y_dict[bottle] = in_base_link.y

        sorted_bottles = sorted(bottle_to_y_dict.items(), key=operator.itemgetter(1))  # Sort dict by value, i.e. the bottle's Y

        descriptions = OrderedDict()
        for bottle, y in sorted_bottles:
            descriptions[bottle] = self.describe_bottle((bottle, y))

        # import ipdb; ipdb.set_trace()
        descriptions = self.describe_relative(descriptions)

        # self.robot.speech.speak("I see {0} bottles, which do you want?".format(len(descriptions)))
        self.robot.speech.speak("I see ")
        for bottle, desc in descriptions.iteritems():

            desc_sentence = ""
            if desc.height_description and desc.color and desc.label:
                desc_sentence = "a {height}, {color} one labeled {label}".format(height=desc.height_description, color=desc.color, label=desc.label)
            elif desc.height_description and desc.color:
                desc_sentence = "a {height}, {color} one".format(height=desc.height_description, color=desc.color)
            elif desc.color and desc.label:
                desc_sentence = "a {color} one labeled {label}".format(label=desc.label, color=desc.color)
            elif desc.height_description and desc.label:
                desc_sentence = "a {height} one labeled {label}".format(label=desc.label, height=desc.height_description)
            elif desc.height_description:
                desc_sentence = "a {height} one".format(height=desc.height_description)
            elif desc.color:
                desc_sentence = "a {color} one".format(color=desc.color)
            elif desc.label:
                desc_sentence += "one labeled {label}".format(label=desc.label)

            if desc.position_description:
                if desc.position_description == "left": desc_sentence += " on the left"
                if desc.position_description == "middle": desc_sentence += " in the middle"
                if desc.position_description == "right": desc_sentence += " on the right"
            
            rospy.loginfo("Description for {0} = {1} ({2})".format(bottle.id, desc_sentence, desc))
            self.robot.speech.speak(desc_sentence)
        self.robot.speech.speak("Which pills do you want?")

        colors = set([desc.color for desc in descriptions.values() if desc.color])
        height_descs = set([desc.height_description for desc in descriptions.values() if desc.height_description])
        labels = set([desc.label for desc in descriptions.values() if desc.label])
        positions = set([desc.position_description for desc in descriptions.values() if desc.position_description])

        m = Marker()

        the_id = 0
        for p in positions:
            the_id += 1

            m.id = the_id
            m.color.r = 1
            m.color.a = 1
            m.pose.position = p
            m.header.frame_id = "/map"
            m.header.stamp = rospy.Time.now()
            m.type = 2
            m.scale.x = 0.3
            m.scale.y = 0.3
            m.scale.z = 0.3
            m.ns = "arrow"
            self._pub.publish(m)

        choices = {}
        if colors:
            choices["color"] = colors
        if height_descs:
            choices["height_desc"] = height_descs
        if labels:
            choices["label"] = labels
        if positions:
            choices["position"] = positions
        rospy.loginfo("Choices are {}".format(choices))

        # import ipdb; ipdb.set_trace()
        if height_descs and colors and labels:
            self.spec_designator.current = "Bring me the <height_desc> <color> bottle labeled <label>"
        elif height_descs and colors:
            self.spec_designator.current = "Bring me the <height_desc> <color> bottle"
        elif colors and labels:
            self.spec_designator.current = "Bring me the <color> bottle labeled <label>"
        elif height_descs and labels:
            self.spec_designator.current = "Bring me the <height_desc> bottle labeled <label>"
        elif height_descs:
            self.spec_designator.current = "Bring me the <height_desc> bottle"
        elif colors:
            self.spec_designator.current = "Bring me the <color> bottle"
        elif labels:
            self.spec_designator.current = "Bring me the bottle labeled <label>"

        if positions:
            self.spec_designator.current += " on the <position>"
        
        self.choices_designator.current = choices

        self.bottle_desc_mapping_designator.current = descriptions

        return "succeeded"

    def describe_bottle(self, bottle_at_y):
        """Create a BottleDescription for a bottle_at_y.
        @param bottle_at_y is a tuple (EntityInfo, float) representing the bottle to describe and its numeric position."""
        bottle_entity, y = bottle_at_y

        # import ipdb; ipdb.set_trace()
        most_probable_color = get_entity_color(bottle_entity)
        try:
            filename = save_entity_image_to_file(self.robot.ed, bottle_entity.id, most_probable_color)
            
            # try:
            #     #Analyze the image and return the dominant color
            #     most_probable_color = analyze(Image.open(filename)) 
            # except Exception, e:
            #     rospy.logwarn("Could not get the dominant color in {}".format(filename))

            rospy.loginfo("{} has color {}".format(filename, most_probable_color))
        except Exception, e:
            rospy.logwarn("Could not save image of entity {}: {}".format(bottle_entity.id, e))

        height_description, height = get_entity_size(bottle_entity)

        return BottleDescription(   height_description=height_description,
                                    color=most_probable_color,
                                    label=None,
                                    position=y,
                                    height=height)

    def describe_relative(self, descriptions):
        """@param descriptions is a dict mapping EntityInfo to BottleDescription
        Based on the existing object descriptions (that include their numeric, absolute z-size and y-position,
            calculate relative positions and sizes.
        It takes the smallest/largest, splits the interval between those in some subintervals and checks into which subinterval an entity falls.
        E.g. objects are distributed like so on some axis: 1--2-------3---4--------------5
        Then the whole interval is divided in 3 parts:     |---left--|--middle--|--right--|
        So, objects 1 and 2 are both left, 3 & 4 are in the middle and 5 is on right. 

        The same happens for height
        The updated descriptions are returned."""
        ys = [desc.position for desc in descriptions.values()]
        lm, rm = min(ys), max(ys)
        hor_interval = rm-lm
        #We cut this interval in 3: a leftmost third, a middle third and a rightmost third.
        #To do this, we need to define a border between leftmost and middle (lm_m) and a border between middle and rightmost (m_rm)
        lm_m = lm + (hor_interval / 3)
        m_rm = rm - (hor_interval / 3)

        for bottle, desc in descriptions.iteritems():
            if lm <= desc.position < lm_m:
                descriptions[bottle].position_description = "left"
            elif lm_m <= desc.position < m_rm:
                descriptions[bottle].position_description = "middle"
            elif m_rm < desc.position <= rm:
                descriptions[bottle].position_description = "right"


        heights = [desc.height for desc in descriptions.values()]
        smallest, biggest = min(heights), max(heights)
        height_interval = biggest-smallest
        #We cut this interval in 3: a smallest third, a normal third and a biggest third.
        #To do this, we need to define a border between smallest and normal (smallest_m) and a border between normal and rightmost (m_biggest)
        smallest_m = smallest + (height_interval / 3)
        m_biggest = biggest - (height_interval / 3)

        for bottle, desc in descriptions.iteritems():
            if smallest <= desc.height < smallest_m:
                descriptions[bottle].height_description = "small"
            elif smallest_m <= desc.height < m_biggest:
                descriptions[bottle].height_description = "normal sized"
            elif m_biggest < desc.height <= biggest:
                descriptions[bottle].height_description = "big"

        return descriptions


if __name__ == "__main__":
    import doctest
    doctest.testmod()
