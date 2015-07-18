#! /usr/bin/env python
import roslib;
import rospy
import smach
import subprocess
import inspect
# import random
# import ed_perception.msg
import robot_skills.util.msg_constructors as msgs
import geometry_msgs.msg as gm
# import math
from smach_ros import SimpleActionState
import robot_smach_states as states
from robot_smach_states.util.designators import *
from robot_smach_states.human_interaction.human_interaction import HearOptionsExtra
from ed.msg import EntityInfo
from dragonfly_speech_recognition.srv import GetSpeechResponse
from robot_smach_states.util.geometry_helpers import *

from robocup_knowledge import load_knowledge
knowledge_objs = load_knowledge('common').objects
knowledge = load_knowledge('challenge_wakemeup')

# ----------------------------------------------------------------------------------------------------

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


prefix = bcolors.OKBLUE + "[WAKE ME UP] " + bcolors.ENDC

default_milk = "fresh milk"

# load item names
names_fruit = [ o["name"] for o in knowledge_objs if "sub-category" in o and o["sub-category"] is "fruit" ]
names_cereal = [ o["name"] for o in knowledge_objs if "sub-category" in o and o["sub-category"] is "cereal" ]
names_milk = [ o["name"] for o in knowledge_objs if "sub-category" in o and o["sub-category"] is "milk" ]

# # Debug print
# print prefix + "Fruit names from Knowledge: " + str(names_fruit)
# print prefix + "Cereal names from Knowledge: " + str(names_cereal)
# print prefix + "Milk names from Knowledge: " + str(names_milk)

# ----------------------------------------------------------------------------------------------------


class FoodType:
    Cereal = 0
    Fruit = 1
    Milk = 2


def parseFoodType(item, got_fruit, got_cereal, got_milk):
    # print prefix + bcolors.OKBLUE + "parseFoodType" + bcolors.ENDC

    # if a fruit has not been picked, you can search there
    if not got_fruit and item in names_fruit:
        # print prefix + item + " its a fruit!"
        return FoodType.Fruit

    # if a cereal has not been picked, you can search there
    if not got_cereal and item in names_cereal:
        # print prefix + item + " its a cereal"
        return FoodType.Cereal

    # if a milk has not been picked, you can search there
    if not got_milk and item in names_milk:
        # print prefix + item + " its a milk!"
        return FoodType.Milk

    # print prefix + item + " was not matched!"
    return None

# ----------------------------------------------------------------------------------------------------
    
class Initialize(states.Initialize):
    def __init__(self, robot=None, ed_configuration={}):
        states.Initialize.__init__(self,robot)
        self.robot = robot
        self.ed_configuration = ed_configuration

    def execute(self, userdata):
        outcome = states.Initialize.execute(self,userdata)
        self.robot.ed.configure_kinect_segmentation(continuous=self.ed_configuration['kinect_segmentation_continuous_mode'])
        self.robot.ed.configure_perception(continuous=self.ed_configuration['perception_continuous_mode'])
        self.robot.ed.disable_plugins(plugin_names=[plugin for plugin in self.ed_configuration["disabled_plugins"]])
        self.robot.ed.reset()

        return outcome


# ----------------------------------------------------------------------------------------------------

class GetOrder(smach.State):
    def __init__(self, robot, breakfastCerealDes, breakfastFruitDes, breakfastMilkDes):
        smach.State.__init__( self, outcomes=['succeeded', 'failed'])
        self.breakfastCereal = breakfastCerealDes
        self.breakfastFruit = breakfastFruitDes
        self.breakfastMilk = breakfastMilkDes

    def execute(self, userdata):
        self.breakfastCereal.current = "coconut_cereals"
        self.breakfastMilk.current   = "papaya_milk"
        self.breakfastFruit.current  = "apple"
        return "succeeded"

# class GetOrder(smach.State):
#     def __init__(self, robot, breakfastCerealDes, breakfastFruitDes, breakfastMilkDes):
#         smach.State.__init__(   self, 
#                                 outcomes=['succeeded', 'failed'])

#         self.robot = robot
#         self.breakfastCereal = breakfastCerealDes
#         self.breakfastFruit = breakfastFruitDes
#         self.breakfastMilk = breakfastMilkDes


#     def execute(self, userdata):
#         print prefix + bcolors.OKBLUE + "GetOrder" + bcolors.ENDC

#         # import ipdb; ipdb.set_trace()
#         # Initializations

#         got_cereal = False
#         got_fruit = False
#         got_milk = False
#         heard_correctly = False

#         word_beginning = ""
#         word_preposition = ""
#         word_item1 = ""
#         word_item2 = ""
#         word_item3 = ""

#         self.breakfastFruit.current = ""
#         self.breakfastCereal.current = ""
#         self.breakfastMilk.current = ""

#         # define allowed sentences, [] means optional
#         sentence = Designator("(([<beginning>] <item1> [<preposition>] <item2> [<preposition>] <item3>) | \
#                                 ([<beginning>] <item1> [<preposition>] <item2>))")

#         choices = Designator({  "beginning" :   ["I want", "I would like", "a", "one"],
#                                 "preposition" : ["and", "and a", "and an", "with a", "with a", "with", "a"],
#                                 "item1" :       names_cereal + names_fruit + names_milk,
#                                 "item2" :       names_cereal + names_fruit + names_milk,
#                                 "item3" :       names_cereal + names_fruit + names_milk})

#         answer = VariableDesignator(resolve_type=GetSpeechResponse)

#         state = HearOptionsExtra(self.robot, sentence, choices, answer, time_out=rospy.Duration(20))
#         outcome = state.execute()

#         # process response
#         if outcome == "heard":

#             # resolve words separatey since some of them might not have been caught
#             try:
#                 word_beginning = answer.resolve().choices["beginning"]
#             except KeyError, ke:
#                 print prefix + bcolors.FAIL + "KeyError resolving: " + str(ke) + bcolors.ENDC
#                 pass

#             try:
#                 word_item3 = answer.resolve().choices["item3"]
#             except KeyError, ke:
#                 print prefix + bcolors.FAIL + "KeyError resolving: " + str(ke) + bcolors.ENDC
#                 pass

#             try:
#                 word_preposition = answer.resolve().choices["preposition"]
#                 word_item1 = answer.resolve().choices["item1"]
#                 word_item2 = answer.resolve().choices["item2"]
#             except KeyError, ke:
#                 print prefix + bcolors.FAIL + "KeyError resolving: " + str(ke) + bcolors.ENDC
#                 pass

#             print "{}What was heard: {} {} {} {} {} {}".format(prefix, word_beginning , word_item1 , word_preposition ,  word_item2 , word_preposition , word_item3)

#             # find first item's type
#             if parseFoodType(word_item1, got_fruit, got_cereal, got_milk) == FoodType.Fruit:
#                 self.breakfastFruit.current = word_item1
#                 got_fruit = True
#                 print "{}First item fruit".format(prefix)
#             elif parseFoodType(word_item1, got_fruit, got_cereal, got_milk) == FoodType.Cereal:
#                 self.breakfastCereal.current = word_item1
#                 got_cereal = True
#                 print "{}First item cereal".format(prefix)
#             elif parseFoodType(word_item1, got_fruit, got_cereal, got_milk) == FoodType.Milk:
#                 self.breakfastMilk.current = word_item1
#                 got_milk = True
#                 print "{}First item milk".format(prefix)
#             else:
#                 print "{}Could not get a match with word_item1 = {}".format(prefix, word_item1)

#             # find second item's type
#             if parseFoodType(word_item2, got_fruit, got_cereal, got_milk) == FoodType.Fruit:
#                 self.breakfastFruit.current = word_item2
#                 got_fruit = True
#                 print "{}Second item Fruit".format(prefix)
#             elif parseFoodType(word_item2, got_fruit, got_cereal, got_milk) == FoodType.Cereal:
#                 self.breakfastCereal.current = word_item2
#                 got_cereal = True
#                 print "{}Second item Cereal".format(prefix)
#             elif parseFoodType(word_item2, got_fruit, got_cereal, got_milk) == FoodType.Milk:
#                 self.breakfastMilk.current = word_item2
#                 got_milk = True
#                 print "{}Second item Milk".format(prefix)
#             else:
#                 print "{}Could not get a match with word_item2 = {}".format(prefix, word_item2)

#             # third type might not exist if its milk
#             if word_item3 :

#                 # find second item's type
#                 if parseFoodType(word_item3, got_fruit, got_cereal, got_milk) == FoodType.Fruit :
#                     self.breakfastFruit.current = word_item3
#                     got_fruit = True
#                     print "{}Third item Fruit".format(prefix)
#                 elif parseFoodType(word_item3, got_fruit, got_cereal, got_milk) == FoodType.Cereal :
#                     self.breakfastCereal.current = word_item3
#                     got_cereal = True
#                     print "{}Third item Cereal".format(prefix)
#                 elif parseFoodType(word_item3, got_fruit, got_cereal, got_milk) == FoodType.Milk :
#                     self.breakfastMilk.current = word_item3
#                     got_milk = True
#                     print "{}Third item Milk".format(prefix)
#                 else:
#                     print "{}Could not get a match with word_item3 = {}".format(prefix, word_item3)

#                 # just a consistency check
#                 if not got_milk:
#                     print prefix + "Still don't know what type of milk it is! Reseting to " + default_milk + bcolors.ENDC
#                     self.breakfastMilk.current = default_milk

#             else:
#                 self.breakfastMilk.current = default_milk
#                 got_milk = True

#             print "{}Response: fruit = {}, cereal = {} , milk = {}".format(prefix, self.breakfastFruit.resolve(), self.breakfastCereal.resolve(), self.breakfastMilk.resolve())
            
#             if not self.breakfastCereal.resolve() or not self.breakfastFruit.resolve() or not self.breakfastMilk.resolve() :
#                 heard_correctly = False
#                 print prefix + bcolors.FAIL + "One of the food types was empty" + bcolors.ENDC
#             else:
#                 heard_correctly = True

#         else:
#             heard_correctly = False

#         # rospy.sleep(2)

#         if heard_correctly:
#             return 'succeeded'
#         else:
#             return 'failed'


# ----------------------------------------------------------------------------------------------------


# Ask the persons name
class RepeatOrderToPerson(smach.State):
    def __init__(self, robot, breakfastCerealDes, breakfastFruitDes, breakfastMilkDes):
        smach.State.__init__(self, outcomes=['done'])

        self.robot = robot
        self.breakfastCereal = breakfastCerealDes
        self.breakfastFruit = breakfastFruitDes
        self.breakfastMilk = breakfastMilkDes

    def execute(self, userdata):
        print prefix + bcolors.OKBLUE + "RepeatOrderToPerson" + bcolors.ENDC

        self.robot.speech.speak("I will get you a " +  self.breakfastFruit.resolve() + " and " + self.breakfastCereal.resolve() + " with " + self.breakfastMilk.resolve() + ". Breakfast will be served in the dining room.", block=False)

        return 'done'


# ----------------------------------------------------------------------------------------------------


class CancelHeadGoals(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=['done'])
        self.robot = robot

    def execute(self, userdata):
        print prefix + bcolors.OKBLUE + "CancelHeadGoals" + bcolors.ENDC

        self.robot.head.cancel_goal()

        return 'done'


# ----------------------------------------------------------------------------------------------------


class LookAtBedTop(smach.State):
    def __init__(self, robot, entity_id, wakeup_light_color):
        smach.State.__init__(self, outcomes=['succeeded'])
        self.robot = robot
        self.entity = self.robot.ed.get_entity(id=entity_id)
        self.r = wakeup_light_color[0]
        self.g = wakeup_light_color[1]
        self.b = wakeup_light_color[2]

    def execute(self, userdata):
        print prefix + bcolors.OKBLUE + "LookAtBedTop" + bcolors.ENDC

        # set robots pose
        # self.robot.spindle.high()
        self.robot.head.cancel_goal()
        self.robot.lights.set_color(self.r,self.g,self.b)

        # TODO maybe look around a bit to make sure the vision covers the whole bed top

        # look at bed top
        headGoal = msgs.PointStamped(x=self.entity.pose.position.x, y=self.entity.pose.position.y, z=self.entity.pose.position.z+self.entity.z_max, frame_id="/map")
        self.robot.head.look_at_point(point_stamped=headGoal, end_time=0, timeout=4)

        return 'succeeded'


# ----------------------------------------------------------------------------------------------------

class LookIfSomethingsThere(smach.State):
    def __init__(self, robot, designator, timeout=0, sleep=0.2):
        smach.State.__init__(self, outcomes=['there', 'not_there'])
        self.robot = robot
        self.designator = designator
        self.timeout = rospy.Duration(timeout)
        self.sleep = sleep

    def execute(self, userdata):
        self.start_time = rospy.Time.now()

        while rospy.Time.now() - self.start_time < self.timeout:
            if self.designator.resolve():
                self.robot.lights.set_color(0,0,1)
                self.robot.ed.configure_kinect_segmentation(continuous=False)
                return 'there'
            else:
                rospy.sleep(self.sleep)

        return 'not_there'

# ----------------------------------------------------------------------------------------------------

class Evaluate(smach.State):
    def __init__(self, options, results):
        smach.State.__init__(self, outcomes=['all_succeeded','partly_succeeded','all_failed'])
        self.options = options
        self.results = results
        self.something_failed = False
        self.something_succeeded = False

    def execute(self, userdata):
        for option in self.options:
            if self.results.resolve()[option]:
                something_succeeded = True
            else:
                something_failed = True

        if something_succeeded and something_failed:
            return 'partly_succeeded'
        elif something_succeeded and not something_failed:
            return 'all_succeeded'
        elif not something_succeeded and something_failed:
            return 'all_failed'
        else:
            return 'all_failed'

# ----------------------------------------------------------------------------------------------------

class addPositive(smach.State):
    def __init__(self, results_designator, item_designator):
        smach.State.__init__(self, outcomes=['done'])
        self.results = results_designator
        self.item = item_designator

    def execute(self, userdata):
        self.results.current[self.item.resolve()] = True
        return "done"


# ----------------------------------------------------------------------------------------------------

class SelectItem(smach.State):
    def __init__(self, robot, options, asked_items, generic_item, specific_item, item_nav_goal):
        smach.State.__init__(self, outcomes=['selected', 'all_done'])
        self.robot = robot
        self.options = options
        self.asked_items_des = asked_items
        self.count = len(self.options)
        self.current = 0
        self.generic_item = generic_item
        self.specific_item = specific_item
        self.nav_goal = item_nav_goal

    def execute(self, userdata):
        self.generic_item.current = self.options[self.current]

        asked_items = [d.resolve() for d in self.asked_items_des]
        category_items = [i['name'] for i in knowledge_objs if 'sub-category' in i and i['sub-category']==self.generic_item.resolve()]

        self.specific_item.current = list(set(category_items).intersection(asked_items))[0]

        self.robot.speech.speak("I will get your "+self.generic_item.resolve()+" now.", block=False)


        self.nav_goal['at'] =   {
                                    EdEntityDesignator(self.robot, id=knowledge.item_nav_goal['near_'+self.generic_item.resolve()]) : "near",
                                    EdEntityDesignator(self.robot, id=knowledge.item_nav_goal['in']) : "in"
                                }

        self.nav_goal['lookat'] =   EdEntityDesignator(self.robot, id=knowledge.item_nav_goal['lookat_'+self.generic_item.resolve()])

        print self.nav_goal
        
        self.current += 1
        if self.current == self.count:
            self.current = 0
            return 'all_done'
        return 'selected'

# ----------------------------------------------------------------------------------------------------

class FindItem(smach.State):
    def __init__(self, robot, sensor_range, type_des, result_des, on_object_des=None):
        smach.State.__init__(self, outcomes=['item_found', 'not_found'])
        self.robot = robot
        self.on_object_des = on_object_des
        self.result_type_des = type_des
        self.result_des = result_des

    def execute(self, userdata):
        self.on_object = self.on_object_des.resolve()
        self.result_type = self.result_type_des.resolve()

        center_point = Point()
        frame_id = "/"+self.on_object.id

        center_point.z = self.on_object.z_max

        rospy.loginfo('Look at %s in frame %s' % (repr(center_point).replace('\n', ' '), frame_id))
        point_stamped = PointStamped(point=center_point,
                                     header=Header(frame_id=frame_id))
        robot.head.look_at_point(point_stamped)
        rospy.sleep(rospy.Duration(waittime))

        entity_ids = self.robot.ed.segment_kinect(max_sensor_range = sensor_range)
        filtered_ids = []
        for entity_id in entity_ids:
            e = self.robot.ed.get_entity(entity_id)

            if e and self.on_object and onTopOff(e, self.on_object) and not e.type:
                filtered_ids.append(e.id)

        entity_types = self.robot.ed.classify(ids=id_list, types=OBJECT_TYPES)

        for i in range(len(entity_ids)):
            if entity_types[i] == result_type:
                result_des.current = self.robot.ed.get_entity(id_list[i])
                return 'item_found'

        return 'not_found'

# ----------------------------------------------------------------------------------------------------

class ScanTableTop(smach.State):
    def __init__(self, robot, table):
        smach.State.__init__(self, outcomes=['done','failed'])
        self.robot = robot
        self.table = table

    def execute(self, userdata):
        center_point = Point()
        frame_id = "/"+self.table.id

        center_point.z = self.table.z_max

        rospy.loginfo('Look at %s in frame %s' % (repr(center_point).replace('\n', ' '), frame_id))
        point_stamped = PointStamped(point=center_point,
                                     header=Header(frame_id=frame_id))
        self.robot.head.look_at_point(point_stamped)
        rospy.sleep(rospy.Duration(waittime))
        
        self.robot.ed.segment_kinect(max_sensor_range = sensor_range)
        return 'done'

# ----------------------------------------------------------------------------------------------------

class EmptySpotDesignator(Designator):
    """Designates an empty spot on the empty placement-shelve.
    It does this by queying ED for entities that occupy some space.
        If the result is no entities, then we found an open spot."""
    def __init__(self, robot, closet_designator):
        super(EmptySpotDesignator, self).__init__(resolve_type=gm.PoseStamped)
        self.robot = robot
        self.closet_designator = closet_designator
        self._edge_distance = 0.1                   # Distance to table edge
        self._spacing = 0.15

    def resolve(self):
        closet = self.closet_designator.resolve()

        # points_of_interest = []
        points_of_interest = self.determinePointsOfInterest(closet)

        def is_poi_occupied(poi):
            entities_at_poi = self.robot.ed.get_entities(center_point=poi, radius=self._spacing)
            return not any(entities_at_poi)

        open_POIs = filter(is_poi_occupied, points_of_interest)

        def distance_to_poi_area(poi):
            #Derived from navigate_to_place
            radius = math.hypot(self.robot.grasp_offset.x, self.robot.grasp_offset.y)
            x = poi.point.x
            y = poi.point.y
            ro = "(x-%f)^2+(y-%f)^2 < %f^2"%(x, y, radius+0.075)
            ri = "(x-%f)^2+(y-%f)^2 > %f^2"%(x, y, radius-0.075)
            pos_constraint = PositionConstraint(constraint=ri+" and "+ro, frame="/map")

            plan_to_poi = self.robot.base.global_planner.getPlan(pos_constraint)

            distance = 10**10 #Just a really really big number for empty plans so they seem far away and are thus unfavorable
            if plan_to_poi:
                distance = len(plan_to_poi)
            print "Distance: %s"%distance
            return distance

        if any(open_POIs):
            best_poi = min(open_POIs, key=distance_to_poi_area)
            placement = geom.PoseStamped(pointstamped=best_poi)
            rospy.loginfo("Placement = {0}".format(placement).replace('\n', ' '))
            return placement
        else:
            rospy.logerr("Could not find an empty spot")
            return None

    def determinePointsOfInterest(self, e):

        points = []

        x = e.pose.position.x
        y = e.pose.position.y

        if len(e.convex_hull) == 0:
            rospy.logerr('Entity: {0} has an empty convex hull'.format(e.id))
            return []

        ''' Convert convex hull to map frame '''
        center_pose = poseMsgToKdlFrame(e.pose)
        ch = []
        for point in e.convex_hull:
            p = pointMsgToKdlVector(point)
            p = center_pose * p
            ch.append(p)

        ''' Loop over hulls '''
        ch.append(ch[0])
        for i in xrange(len(ch) - 1):
                dx = ch[i+1].x() - ch[i].x()
                dy = ch[i+1].y() - ch[i].y()
                length = math.hypot(dx, dy)

                d = self._edge_distance
                while d < (length-self._edge_distance):

                    ''' Point on edge '''
                    xs = ch[i].x() + d/length*dx
                    ys = ch[i].y() + d/length*dy

                    ''' Shift point inwards and fill message'''
                    ps = geom.PointStamped()
                    ps.header.frame_id = "/map"
                    ps.point.x = xs - dy/length * self._edge_distance
                    ps.point.y = ys + dx/length * self._edge_distance
                    ps.point.z = e.pose.position.z + e.z_max
                    points.append(ps)

                    # ToDo: check if still within hull???
                    d += self._spacing

        return points