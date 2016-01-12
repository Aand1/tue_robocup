#!/usr/bin/python

"""This challenge is defined in https://raw.githubusercontent.com/RoboCupAtHome/RuleBook/master/Manipulation.tex

In short, the robot starts at 1-1.5m from a bookcase and must wait until started by an operator (by voice or a start button)

This bookcase has a couple of shelves on which some items are placed.
**The middle shelve starts empty**, this is where the objects need to be placed.

The robot must take objects form the shelves and place them on the middle shelve and indicate the class of each grasped object.

After the robot is started by voice or a button,
    the ManipRecogSingleItem state machine is repeated at least 5 times (for 5 objects).
Afterwards, a PDF report has to be made:
'After the test is completed or the time has run out,
    the robot may upload a single PDF report file including the list of recognized objects with a picture showing:
    - the object,
    - the object name,
    - the bounding box of the object.'
"""

import rospy
import smach
import sys
import random
import math

import robot_smach_states.util.designators as ds
import robot_smach_states as states
from robot_smach_states.util.startup import startup
from robot_smach_states import Grab
from robot_smach_states import Place
from robot_smach_states import world_model
from robot_smach_states.util.geometry_helpers import *
from robot_skills.util import msg_constructors as geom
from robot_skills.util import transformations
import geometry_msgs.msg as gm
from robot_skills.util import transformations
from cb_planner_msgs_srvs.msg import PositionConstraint


import pdf

from robocup_knowledge import load_knowledge
challenge_knowledge = load_knowledge('challenge_manipulation')
OBJECT_SHELVES = challenge_knowledge.object_shelves
PICK_SHELF = challenge_knowledge.grasp_shelf
PLACE_SHELF = challenge_knowledge.place_shelf
ROOM = challenge_knowledge.room
OBJECT_TYPES = challenge_knowledge.object_types
MAX_NUM_ENTITIES_IN_PDF = 10

DETECTED_OBJECTS_WITH_PROBS = []

DEBUG = False

''' Sanity check '''
if PLACE_SHELF in OBJECT_SHELVES:
    rospy.logerr("Place shelve {0} will not contain objects, but is still in object shelves, will remove".format(PLACE_SHELF))
    # ToDo
    #import ipdb; ipdb.set_trace()
if not PICK_SHELF in OBJECT_SHELVES:
    rospy.logerr("Pick shelf {0} not in object shelves, will add".format(PICK_SHELF))
    OBJECT_SHELVES.append(PICK_SHELF)

ignore_ids = ['robotics_testlabs']
ignore_types = ['waypoint', 'floor','room']
#PICK_SHELF = "plastic_cabinet_shelf_1"
#PLACE_SHELF = "plastic_cabinet_shelf_2"
#ROOM = "room_living_room"
PLACE_HEIGHT = 1.0


not_ignored = lambda entity: not entity.type in ignore_types and not entity.id in ignore_ids
size = lambda entity: abs(entity.z_max - entity.z_min) < 0.4
# not_manipulated = lambda entity: not entity in manipulated_items.resolve()
has_type = lambda entity: entity.type != ""
min_height = lambda entity: entity.min_z > 0.3
min_entity_height = lambda entity: abs(entity.z_max - entity.z_min) > 0.04
def max_width(entity):
    max_bb_x = max(ch.x for ch in entity.convex_hull)
    min_bb_x = min(ch.x for ch in entity.convex_hull)
    max_bb_y = max(ch.y for ch in entity.convex_hull)
    min_bb_y = min(ch.y for ch in entity.convex_hull)

    x_size = abs(max_bb_x - min_bb_x)
    y_size = abs(max_bb_y - min_bb_y)

    x_ok = 0.02 < x_size < 0.15
    y_ok = 0.02 < y_size < 0.15

    return x_ok and y_ok

class FormattedSentenceDesignator(ds.Designator):
    """docstring for FormattedSentenceDesignator"""
    def __init__(self, fmt, **kwargs):
        super(FormattedSentenceDesignator, self).__init__(resolve_type=str)
        self.fmt = fmt
        self.kwargs = kwargs

    def _resolve(self):
        kwargs_resolved = {key:value.resolve() for key,value in self.kwargs.iteritems()}
        return self.fmt.format(**kwargs_resolved)


class EntityDescriptionDesignator(ds.Designator):
    """EntityDescriptionDesignator"""
    def __init__(self, formats, entity_designator, name=None):
        super(EntityDescriptionDesignator, self).__init__(resolve_type=str, name=name)
        self.entity_designator = entity_designator
        self.formats = formats

    def _resolve(self):
        entity = self.entity_designator.resolve()
        if not entity:
            return None
        short_id = entity.id[:5]
        typ = entity.type
        fmt = self.formats
        if not isinstance(fmt, str) and isinstance(fmt, list):
            fmt = random.choice(fmt)
        sentence = fmt.format(type=typ, id=short_id)
        return sentence


# class EmptySpotDesignator(ds.Designator):
#     """Designates an empty spot on the empty placement-shelve.
#     It does this by queying ED for entities that occupy some space.
#         If the result is no entities, then we found an open spot."""
#     def __init__(self, robot, closet_designator):
#         super(EmptySpotDesignator, self).__init__(resolve_type=gm.PoseStamped)
#         self.robot = robot
#         self.closet_designator = closet_designator
#         self._edge_distance = 0.1                   # Distance to table edge
#         self._spacing = 0.15

#     def _resolve(self):
#         closet = self.closet_designator.resolve()

#         # points_of_interest = []
#         points_of_interest = self.determinePointsOfInterest(closet)

#         def is_poi_occupied(poi):
#             entities_at_poi = self.robot.ed.get_entities(center_point=poi, radius=self._spacing)
#             return not any(entities_at_poi)

#         open_POIs = filter(is_poi_occupied, points_of_interest)

#         def distance_to_poi_area(poi):
#             #Derived from navigate_to_place
#             radius = math.hypot(self.robot.grasp_offset.x, self.robot.grasp_offset.y)
#             x = poi.point.x
#             y = poi.point.y
#             ro = "(x-%f)^2+(y-%f)^2 < %f^2"%(x, y, radius+0.075)
#             ri = "(x-%f)^2+(y-%f)^2 > %f^2"%(x, y, radius-0.075)
#             pos_constraint = PositionConstraint(constraint=ri+" and "+ro, frame="/map")

#             plan_to_poi = self.robot.base.global_planner.getPlan(pos_constraint)

#             distance = 10**10 #Just a really really big number for empty plans so they seem far away and are thus unfavorable
#             if plan_to_poi:
#                 distance = len(plan_to_poi)
#             print "Distance: %s"%distance
#             return distance

#         if any(open_POIs):
#             best_poi = min(open_POIs, key=distance_to_poi_area)
#             placement = geom.PoseStamped(pointstamped=best_poi)
#             rospy.loginfo("Placement = {0}".format(placement).replace('\n', ' '))
#             return placement
#         else:
#             rospy.logerr("Could not find an empty spot")
#             return None

#     def determinePointsOfInterest(self, e):

#         points = []

#         x = e.pose.position.x
#         y = e.pose.position.y

#         if len(e.convex_hull) == 0:
#             rospy.logerr('Entity: {0} has an empty convex hull'.format(e.id))
#             return []

#         ''' Convert convex hull to map frame '''
#         center_pose = poseMsgToKdlFrame(e.pose)
#         ch = []
#         for point in e.convex_hull:
#             p = pointMsgToKdlVector(point)
#             p = center_pose * p
#             ch.append(p)

#         ''' Loop over hulls '''
#         ch.append(ch[0])
#         for i in xrange(len(ch) - 1):
#                 dx = ch[i+1].x() - ch[i].x()
#                 dy = ch[i+1].y() - ch[i].y()
#                 length = math.hypot(dx, dy)

#                 d = self._edge_distance
#                 while d < (length-self._edge_distance):

#                     ''' Point on edge '''
#                     xs = ch[i].x() + d/length*dx
#                     ys = ch[i].y() + d/length*dy

#                     ''' Shift point inwards and fill message'''
#                     ps = geom.PointStamped()
#                     ps.header.frame_id = "/map"
#                     ps.point.x = xs - dy/length * self._edge_distance
#                     ps.point.y = ys + dx/length * self._edge_distance
#                     ps.point.z = e.pose.position.z + e.z_max
#                     points.append(ps)

#                     # ToDo: check if still within hull???
#                     d += self._spacing

#         return points

class InspectShelves(smach.State):
    """ Inspect all object shelves """

    def __init__(self, robot, object_shelves):
        smach.State.__init__(self, outcomes=['succeeded', 'failed', 'nothing_found'])
        self.robot = robot
        self.object_shelves = object_shelves

    def execute(self, userdata):

        global DETECTED_OBJECTS_WITH_PROBS

        ''' Loop over shelves '''
        for shelf in self.object_shelves:

            rospy.loginfo("Shelf: {0}".format(shelf))

            ''' Get entities '''
            shelf_entity = self.robot.ed.get_entity(id=shelf, parse=False)

            if shelf_entity:

                ''' Extract center point '''
                cp = shelf_entity.pose.position

                ''' Look at target '''
                self.robot.head.look_at_point(geom.PointStamped(cp.x, cp.y, cp.z, "/map"))

                ''' Move spindle
                    Implemented only for AMIGO (hence the hardcoding)
                    Assume table height of 0.8 corresponds with spindle reset = 0.35 '''
                # def _send_goal(self, torso_pos, timeout=0.0, tolerance = []):
                # ToDo: do head and torso simultaneously
                height = min(0.4, max(0.1, cp.z-0.55))
                self.robot.torso._send_goal([height], timeout=5.0)

                ''' Sleep for 1 second '''
                import os; do_wait = os.environ.get('ROBOT_REAL')
                if do_wait == 'true':
                    rospy.sleep(3.0) # ToDo: remove???

                if DEBUG:
                    rospy.loginfo('Stopping: debug mode. Press c to continue to the next point')
                    import ipdb;ipdb.set_trace()
                    continue

                ''' Enable kinect segmentation plugin (only one image frame) '''
                # entity_ids = self.robot.ed.segment_kinect(max_sensor_range=2)  ## Old
                segmented_entities = self.robot.ed.update_kinect("{} {}".format("on_top_of", shelf))
                # import ipdb;ipdb.set_trace();return 'no_objects_found'

                ''' Get all entities that are returned by the segmentation and are on top of the shelf '''
                # # id_list = [] # List with entities that are flagged with 'perception'
                # detected_entities = []
                # for entity_id in entity_ids:
                #     e = self.robot.ed.get_entity(entity_id)
                #
                #     # if e and onTopOff(e, shelf_entity) and not e.type:
                #     if e and onTopOff(e, shelf_entity) and size(e) and min_entity_height(e) and not e.type:
                #         # ToDo: filter on size in x, y, z
                #         # self.robot.ed.update_entity(id=e.id, flags=[{"add":"perception"}])
                #         id_list.append(e.id)
                #         detected_entities.append(e)

                ''' Try to classify the objects on the shelf '''
                # entity_types_and_probs = self.robot.ed.classify_with_probs(ids=segmented_entities.new_ids, types=OBJECT_TYPES)
                entity_types_and_probs = self.robot.ed.classify(ids=segmented_entities.new_ids, types=OBJECT_TYPES)
                import ipdb; ipdb.set_trace();

                # print "entity types: {}".format(entity_types_and_probs)

                ''' Check all entities that were flagged to see if they have received a 'type' it_label
                if so: recite them and lock them '''
                for i in range(0, len(id_list)):
                    e_id = id_list[i]
                    (e_type, e_type_prob) = entity_types_and_probs[i]

                    e = detected_entities[i]
                    e.type = e_type

                    if e_type:
                        self.robot.speech.speak("I have seen {0}".format(e_type), block=False)
                        self.robot.ed.update_entity(id=e.id, flags=[{"add": "locked"}])

                        DETECTED_OBJECTS_WITH_PROBS += [(e, e_type_prob)]

                # TODO: Store the entities in the pdf (and let AMIGO name them)
                # ...
                # for e in entities:
                #     Say e.type
                #     Store e in pdf
                #
                #      OR
                #
                # Lock the items in the world model, and create the pdf afterwards
                # ...
                # for e in entities:
                #     self.robot.ed.update_entity(e.id, flags=["locked"])
                #
                # ... (later)
                # # Getting all locked entities:
                # for e in entities:
                #     if "locked" in e.flags:
                #         ...

                # self.robot.ed.disable_plugins(["kinect_integration", "perception"])

        if not DETECTED_OBJECTS_WITH_PROBS:
            return "nothing_found"

        # Sort based on probability
        DETECTED_OBJECTS_WITH_PROBS = sorted(DETECTED_OBJECTS_WITH_PROBS, key=lambda o: o[1], reverse=True)

        return 'succeeded'

# class InspectEntity(smach.State):
#     """Inspect an entity, i.e. look at all points that make up some entity"""
#     # ToDo: Is this obsolete???

#     def __init__(self, robot, entity_designator):
#         smach.State.__init__(self, outcomes=['succeeded','failed'])
#         self.robot = robot
#         self.entity_designator = entity_designator

#     def execute(self, userdata=None):
#         entity = self.entity_designator.resolve()

#         if not entity:
#             return "failed"

#         for point in entity.convex_hull:
#             point_stamped = geom.PointStamped(point=point, frame_id=entity.id)
#             self.robot.head.look_at_point(point_stamped, timeout=1)

#         return "succeeded"

# ----------------------------------------------------------------------------------------------------

class InitializeWorldModel(smach.State):

    def __init__(self, robot):
        smach.State.__init__(self, outcomes=['done'])
        self.robot = robot

    def execute(self, userdata=None):
        # self.robot.ed.configure_kinect_segmentation(continuous=False)
        # self.robot.ed.configure_perception(continuous=False)
        self.robot.ed.disable_plugins(plugin_names=["laser_integration"])
        self.robot.ed.reset()

        return "done"

# ----------------------------------------------------------------------------------------------------

class ManipRecogSingleItem(smach.StateMachine):
    """The ManipRecogSingleItem state machine (for one object) is:
    - Stand of front of the bookcase
    - Look at the bookcase
    - Select an item, which is:
        - inside the bookcase
        - not yet grasped/not on the middle shelve
    - Grab that item
    - Say the class of the grabbed item
    - Place the item in an open spot on the middle shelve. """

    def __init__(self, robot, manipulated_items):
        """@param manipulated_items is VariableDesignator that will be a list of items manipulated by the robot."""
        self.manipulated_items = manipulated_items
        smach.StateMachine.__init__(self, outcomes=['succeeded','failed'])

        self.pick_shelf = ds.EntityByIdDesignator(robot, id=PICK_SHELF, name="pick_shelf")
        self.place_shelf = ds.EntityByIdDesignator(robot, id=PLACE_SHELF, name="place_shelf")

        # TODO: Designate items that are
        # inside pick_shelf
        # and are _not_:
        #   already placed
        #   on the placement-shelve.
        # not_ignored = lambda entity: not entity.type in ignore_types and not entity.id in ignore_ids
        # size = lambda entity: abs(entity.z_max - entity.z_min) < 0.4
        not_manipulated = lambda entity: not entity in self.manipulated_items.resolve()
        # has_type = lambda entity: entity.type != ""
        # min_height = lambda entity: entity.min_z > 0.3
        # min_entity_height = lambda entity: abs(entity.z_max - entity.z_min) > 0.04
        # def max_width(entity):
        #     max_bb_x = max(ch.x for ch in entity.convex_hull)
        #     min_bb_x = min(ch.x for ch in entity.convex_hull)
        #     max_bb_y = max(ch.y for ch in entity.convex_hull)
        #     min_bb_y = min(ch.y for ch in entity.convex_hull)

        #     x_size = abs(max_bb_x - min_bb_x)
        #     y_size = abs(max_bb_y - min_bb_y)

        #     x_ok = 0.02 < x_size < 0.15
        #     y_ok = 0.02 < y_size < 0.15

        #     return x_ok and y_ok

        def on_top(entity):
            container_entity = self.pick_shelf.resolve()
            return onTopOff(entity, container_entity)

        # select the entity closest in x direction to the robot in base_link frame
        def weight_function(entity):
            # TODO: return x coordinate of entity.center_point in base_link frame
            p = transformations.tf_transform(entity.pose.position, "/map", robot.robot_name+"/base_link", robot.tf_listener)
            return p.x*p.x

        # self.current_item = EntityByIdDesignator(robot, id="beer1")  # TODO: For testing only
        # self.current_item = LockingDesignator(EdEntityDesignator(robot,
        #     center_point=geom.PointStamped(frame_id="/"+PICK_SHELF), radius=2.0,
        #     criteriafuncs=[not_ignored, size, not_manipulated, has_type, on_top], debug=False))
        # self.current_item = LockingDesignator(EdEntityDesignator(robot,
        #     criteriafuncs=[not_ignored, size, not_manipulated, has_type, on_top, min_entity_height, max_width], weight_function=weight_function, debug=False))
        self.current_item = ds.LockingDesignator(ds.EdEntityDesignator(robot,
            criteriafuncs=[not_ignored, size, not_manipulated, on_top, min_entity_height, max_width], weight_function=weight_function, debug=False, name="item"), name="current_item")

        #This makes that the empty spot is resolved only once, even when the robot moves. This is important because the sort is based on distance between robot and constrait-area
        self.place_position = ds.LockingDesignator(ds.EmptySpotDesignator(robot, self.place_shelf, name="placement"), name="place_position")

        self.empty_arm_designator = ds.UnoccupiedArmDesignator(robot.arms, robot.leftArm, name="empty_arm_designator")
        self.arm_with_item_designator = ds.ArmHoldingEntityDesignator(robot.arms, self.current_item, name="arm_with_item_designator")

        # print "{0} = pick_shelf".format(self.pick_shelf)
        # print "{0} = current_item".format(self.current_item)
        # print "{0} = place_position".format(self.place_position)
        # print "{0} = empty_arm_designator".format(self.empty_arm_designator)
        # print "{0} = arm_with_item_designator".format(self.arm_with_item_designator)

        with self:
            # smach.StateMachine.add( "NAV_TO_OBSERVE_PICK_SHELF",
            #                         #states.NavigateToObserve(robot, self.pick_shelf),
            #                         states.NavigateToSymbolic(robot, {self.pick_shelf:"in_front_of", EntityByIdDesignator(robot, id=ROOM):"in"}, self.pick_shelf),
            #                         transitions={   'arrived'           :'LOOKAT_PICK_SHELF',
            #                                         'unreachable'       :'LOOKAT_PICK_SHELF',
            #                                         'goal_not_defined'  :'LOOKAT_PICK_SHELF'})

            ''' Look at pick shelf '''
            smach.StateMachine.add("LOOKAT_PICK_SHELF",
                                     states.LookAtEntity(robot, self.pick_shelf, keep_following=True),
                                     transitions={  'succeeded'         :'LOCK_ITEM'})

            # smach.StateMachine.add( "SAY_LOOKAT_PICK_SHELF",
            #                         states.Say(robot, ["I'm looking at the self.pick_shelf to see what items I can find"]),
            #                         transitions={   'spoken'            :'LOCK_ITEM'})

            @smach.cb_interface(outcomes=['locked'])
            def lock(userdata):
                self.current_item.lock() #This determines that self.current_item cannot not resolve to a new value until it is unlocked again.
                if self.current_item.resolve():
                    rospy.loginfo("Current_item is now locked to {0}".format(self.current_item.resolve().id))

                self.place_position.lock() #This determines that self.place_position will lock/cache its result after its resolved the first time.
                return 'locked'
            smach.StateMachine.add('LOCK_ITEM',
                                   smach.CBState(lock),
                                   transitions={'locked':'ANNOUNCE_ITEM'})

            smach.StateMachine.add( "ANNOUNCE_ITEM",
                                    states.Say(robot, EntityDescriptionDesignator("I'm trying to grab item {id} which is a {type}.", self.current_item, name="current_item_desc"), block=False),
                                    transitions={   'spoken'            :'GRAB_ITEM'})

            smach.StateMachine.add( "GRAB_ITEM",
                                    Grab(robot, self.current_item, self.empty_arm_designator),
                                    transitions={   'done'              :'STORE_ITEM',
                                                    'failed'            :'SAY_GRAB_FAILED'})

            smach.StateMachine.add( "SAY_GRAB_FAILED",
                                    states.Say(robot, ["I couldn't grab this thing"], mood="sad"),
                                    transitions={   'spoken'            :'UNLOCK_ITEM_AFTER_FAILED_GRAB'}) # Not sure whether to fail or keep looping with NAV_TO_OBSERVE_PICK_SHELF

            @smach.cb_interface(outcomes=['unlocked'])
            def unlock_and_ignore(userdata):
                global ignore_ids
                # import ipdb; ipdb.set_trace()
                if self.current_item.resolve():
                    ignore_ids += [self.current_item.resolve().id]
                    rospy.loginfo("Current_item WAS now locked to {0}".format(self.current_item.resolve().id))
                self.current_item.unlock() #This determines that self.current_item can now resolve to a new value on the next call
                self.place_position.unlock() #This determines that self.place_position can now resolve to a new position on the next call
                return 'unlocked'
            smach.StateMachine.add('UNLOCK_ITEM_AFTER_FAILED_GRAB',
                                   smach.CBState(unlock_and_ignore),
                                   transitions={'unlocked'              :'failed'})

            @smach.cb_interface(outcomes=['stored'])
            def store_as_manipulated(userdata):
                manipulated_items.current += [self.current_item.current]
                return 'stored'

            smach.StateMachine.add('STORE_ITEM',
                                   smach.CBState(store_as_manipulated),
                                   transitions={'stored':'ANNOUNCE_CLASS'})

            smach.StateMachine.add( "ANNOUNCE_CLASS",
                                    states.Say(robot, FormattedSentenceDesignator("This is a {item.type}.", item=self.current_item, name="item_type_sentence"), block=False),
                                    transitions={   'spoken'            :'LOOKAT_PLACE_SHELF'})

            smach.StateMachine.add("LOOKAT_PLACE_SHELF",
                                     states.LookAtEntity(robot, self.pick_shelf, keep_following=True),
                                     transitions={  'succeeded'         :'PLACE_ITEM'})

            smach.StateMachine.add( "PLACE_ITEM",
                                    Place(robot, self.current_item, self.place_position, self.arm_with_item_designator),
                                    transitions={   'done'              :'RESET_HEAD_PLACE',
                                                    'failed'            :'RESET_HEAD_HUMAN'})

            smach.StateMachine.add( "RESET_HEAD_PLACE",
                                    states.CancelHead(robot),
                                    transitions={   'done'              :'UNLOCK_ITEM_AFTER_SUCCESSFUL_PLACE'})

            smach.StateMachine.add( "RESET_HEAD_HUMAN",
                                    states.CancelHead(robot),
                                    transitions={   'done'               :'SAY_HANDOVER_TO_HUMAN'})

            smach.StateMachine.add('UNLOCK_ITEM_AFTER_SUCCESSFUL_PLACE',
                                   smach.CBState(unlock_and_ignore),
                                   transitions={'unlocked'              :'succeeded'})

            smach.StateMachine.add( "SAY_HANDOVER_TO_HUMAN",
                                    states.Say(robot, ["I'm can't get rid of this item  myself, can somebody help me maybe?"]),
                                    transitions={   'spoken'            :'HANDOVER_TO_HUMAN'})

            smach.StateMachine.add('HANDOVER_TO_HUMAN',
                                   states.HandoverToHuman(robot, self.arm_with_item_designator),
                                   transitions={   'succeeded'         :'UNLOCK_AFTER_HANDOVER',
                                                    'failed'           :'UNLOCK_AFTER_HANDOVER'})

            smach.StateMachine.add('UNLOCK_AFTER_HANDOVER',
                                   smach.CBState(unlock_and_ignore),
                                   transitions={'unlocked'              :'failed'})


def setup_statemachine(robot):

    sm = smach.StateMachine(outcomes=['Done', 'Aborted'])
    start_waypoint = ds.EntityByIdDesignator(robot, id="manipulation_init_pose", name="start_waypoint")
    placed_items = []

    with sm:
        smach.StateMachine.add('INITIALIZE',
                                states.Initialize(robot),
                                transitions={   'initialized':'INIT_WM',
                                                'abort':'Aborted'})

        smach.StateMachine.add("INIT_WM",
                               InitializeWorldModel(robot),
                               transitions={'done'                      :'AWAIT_START'})

        smach.StateMachine.add("AWAIT_START",
                               states.AskContinue(robot),
                               transitions={'continue'                  :'NAV_TO_START',
                                            'no_response'               :'AWAIT_START'})

        pick_shelf = ds.EntityByIdDesignator(robot, id=PICK_SHELF)
        room = ds.EntityByIdDesignator(robot, id=ROOM)
        smach.StateMachine.add( "NAV_TO_START",
                                #states.NavigateToObserve(robot, pick_shelf),
                                states.NavigateToSymbolic(robot,
                                                          {pick_shelf:"in_front_of", room:"in"},
                                                          pick_shelf),
                                transitions={   'arrived'           :'RESET_ED',
                                                'unreachable'       :'RESET_ED',
                                                'goal_not_defined'  :'RESET_ED'})

        # smach.StateMachine.add("NAV_TO_START",
        #                         states.NavigateToWaypoint(robot, start_waypoint),
        #                         transitions={'arrived'                  :'RESET_ED',
        #                                      'unreachable'              :'RESET_ED',
        #                                      'goal_not_defined'         :'RESET_ED'})

        smach.StateMachine.add("RESET_ED",
                                states.ResetED(robot),
                                transitions={'done'                     :'INSPECT_SHELVES'})

        smach.StateMachine.add("INSPECT_SHELVES",
                                InspectShelves(robot, OBJECT_SHELVES),
                                transitions={'succeeded'                :'EXPORT_PDF',
                                             'nothing_found'            :'EXPORT_PDF',
                                             'failed'                   :'EXPORT_PDF'})

        @smach.cb_interface(outcomes=["exported"])
        def export_to_pdf(userdata):
            global DETECTED_OBJECTS_WITH_PROBS

            entities = [ e[0] for e in DETECTED_OBJECTS_WITH_PROBS ]

            # Export images (Only best MAX_NUM_ENTITIES_IN_PDF)
            pdf.entities_to_pdf(robot.ed, entities[:MAX_NUM_ENTITIES_IN_PDF], "tech_united_manipulation_challenge")

            return "exported"
        smach.StateMachine.add('EXPORT_PDF',
                                smach.CBState(export_to_pdf),
                                transitions={'exported':'RANGE_ITERATOR'})

        # Begin setup iterator
        range_iterator = smach.Iterator(    outcomes = ['succeeded','failed'], #Outcomes of the iterator state
                                            input_keys=[], output_keys=[],
                                            it = lambda: range(5),
                                            it_label = 'index',
                                            exhausted_outcome = 'succeeded') #The exhausted argument should be set to the preffered state machine outcome

        with range_iterator:
            single_item = ManipRecogSingleItem(robot, ds.VariableDesignator(placed_items, list, name="placed_items"))

            smach.Iterator.set_contained_state( 'SINGLE_ITEM',
                                                single_item,
                                                loop_outcomes=['succeeded','failed'])

        smach.StateMachine.add('RANGE_ITERATOR', range_iterator,
                        {   'succeeded'                                     :'AT_END',
                            'failed'                                        :'Aborted'})
        # End setup iterator


        smach.StateMachine.add('AT_END',
                               states.Say(robot, "Goodbye"),
                               transitions={'spoken': 'Done'})

        ds.analyse_designators(sm, "manipulation")

    return sm


############################## initializing program ######################
if __name__ == '__main__':
    rospy.init_node('manipulation_exec')

    startup(setup_statemachine)
