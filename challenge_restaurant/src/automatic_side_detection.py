#!/usr/bin/python

import rospy
import smach
import math
import numpy as np

from robot_smach_states.util.startup import startup
from geometry_msgs.msg import PointStamped
import robot_smach_states as states
from robot_skills.util import transformations, msg_constructors

from robocup_knowledge import load_knowledge
knowledge = load_knowledge("challenge_restaurant")

from challenge_restaurant import visualize_location


def _get_area(convex_hull):
    pts = [ [c.x, c.y] for c in convex_hull ]
    lines = np.hstack([pts,np.roll(pts,-1,axis=0)])
    area = 0.5*abs(sum(x1*y2-x2*y1 for x1,y1,x2,y2 in lines))
    return area

class WaitSay(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["done"])
        self._robot = robot

    def execute(self, userdata):
        self._robot.head.look_at_standing_person()
        answer = None
        while not answer or answer.result != "side detection":
            answer = self._robot.ears.recognize("side detection")
        self._robot.head.cancel_goal()

        return "done"

class AutomaticSideDetection(smach.State):
    def __init__(self, robot, background_padding=0.3, look_x = .2, look_y = 1.5, max_radius = 2.0, min_area = 0.3):
        self._sides = {
            "left": {
                "x": look_x,
                "y": look_y,
                "score": {},
                "entities": []
            },
            "right": {
                "x": look_x,
                "y": -look_y,
                "score": {},
                "entities": []
            },
        }
        smach.State.__init__(self, outcomes=self._sides.keys())
        self._robot = robot
        self._background_padding = background_padding
        self._max_radius = max_radius
        self._min_area = min_area

    def _get_head_goal(self, spec):
        goal = PointStamped()
        goal.header.stamp = rospy.Time.now()
        goal.header.frame_id = "/"+self._robot.robot_name+"/base_link"
        goal.point.x = spec["x"]
        goal.point.y = spec["y"]
        return goal

    def _inspect_sides(self):
        for side, spec in self._sides.iteritems():
            # Look at the side
            rospy.loginfo("looking at side %s" % side)
            self._robot.head.look_at_point(self._get_head_goal(spec))
            self._robot.head.wait_for_motion_done()
            rospy.sleep(0.2)

            base_position = self._robot.base.get_location().pose.position

            # Update kinect
            try:
                rospy.loginfo("Updating kinect for side %s" % side)
                kinect_update = self._robot.ed.update_kinect(background_padding=self._background_padding)
            except:
                rospy.logerr("Could not update_kinect")
                continue

            self._sides[side]["entities"] = [self._robot.ed.get_entity(id=id) for id in set(kinect_update.new_ids + kinect_update.updated_ids)]

            rospy.loginfo("Found %d entities for side %s" % (len(self._sides[side]["entities"]), side))

            # Filter subset
            self._sides[side]["entities"] = [ e for e in self._sides[side]["entities"] if self._subset_selection(base_position, e) ]

            # Score entities
            self._sides[side]["score"]["area_sum"] = sum([ self._score_area(e) for e in self._sides[side]["entities"] ])
            self._sides[side]["score"]["min_distance"] = self._score_closest_point(base_position, self._sides[side]["entities"])

            self._sides[side]["score"]["face_found"] = len(self._robot.ed.detect_persons()) > 0

            if self._sides[side]["score"]["face_found"]:
                self._robot.speech.speak("hi there")

    def _subset_selection(self, base_position, e):
        distance = math.hypot(e.pose.position.x - base_position.x, e.pose.position.y - base_position.y)
        return distance < self._max_radius

    def _score_area(self, e):
        return _get_area(e.convex_hull)

    def _score_closest_point(self, base_position, entities):
        distances = [ math.hypot(e.pose.position.x - base_position.x, e.pose.position.y - base_position.y) for e in entities ]
        min_distance = min(distances)

        return (self._max_radius - min_distance) / self._max_radius

    def _get_best_side(self):

        best_side = None
        for side, spec in self._sides.iteritems():
            end_score = self._sides[side]["score"]["area_sum"] + self._sides[side]["score"]["min_distance"] + 1 * self._sides[side]["score"]["face_found"]
            rospy.loginfo("Side %s scoring (%f): %s" % (side, end_score, self._sides[side]["score"]))

            if best_side is None or self._sides[side]["score"] > self._sides[best_side]["score"]:
                best_side = side

        return best_side

    def execute(self, userdata):
        rospy.sleep(0.2)
        self._inspect_sides()

        best_side = self._get_best_side()

        return best_side


class StoreWaypoint(smach.State):
    def __init__(self, robot):
        smach.State.__init__(self, outcomes=["done", "continue"])
        self._robot = robot

    def execute(self, userdata):
        # Stop the base
        self._robot.base.local_planner.cancelCurrentPlan()

        self._robot.head.look_at_standing_person()
        self._robot.speech.speak("Are we at a table?")

        result = self._robot.ears.recognize("(yes|no)",{})
        if not result or result.result == "" or result.result == "no":
            self._robot.head.cancel_goal()
            return "continue"


        # Store current base position
        base_pose = self._robot.base.get_location()

        # Create automatic side detection state and execute
        self._robot.speech.speak("I am now going to look for the table", block=False)
        automatic_side_detection = AutomaticSideDetection(self._robot)
        side = automatic_side_detection.execute({})

        self._robot.speech.speak("The table is to my %s" % side)

        location = None
        for i in range(0, 3):
            self._robot.speech.speak("Which table number is this?")
            result = self._robot.ears.recognize(knowledge.professional_guiding_spec, knowledge.professional_guiding_choices,
                                                time_out = rospy.Duration(5)) # Wait 100 secs

            if result and "location" in result.choices:
                location = result.choices["location"]
                break

            self._robot.speech.speak("Sorry, I did not understand")

        self._robot.head.cancel_goal()

        if not location:
            return "continue"

        self._robot.speech.speak("Table %s, it is!" % location)

        if side == "left":
            base_pose.pose.orientation = transformations.euler_z_to_quaternion(
                transformations.euler_z_from_quaternion(base_pose.pose.orientation) + math.pi / 2)
        elif side == "right":
            base_pose.pose.orientation = transformations.euler_z_to_quaternion(
                transformations.euler_z_from_quaternion(base_pose.pose.orientation) - math.pi / 2)

        # Add to param server
        loc_dict = {'x':base_pose.pose.position.x, 'y':base_pose.pose.position.y, 'phi':transformations.euler_z_from_quaternion(base_pose.pose.orientation)}
        rospy.set_param("/restaurant_locations/{name}".format(name=location), loc_dict)

        visualize_location(base_pose, location)
        self._robot.ed.update_entity(id=location, posestamped=base_pose, type="waypoint")

        return "done"

def setup_statemachine(robot):

    sm = smach.StateMachine(outcomes=['done', 'aborted'])
    robot.ed.reset()

    with sm:
        smach.StateMachine.add('WAIT_SAY', WaitSay(robot), transitions={ 'done' :'STORE_WAYPOINT'})
        smach.StateMachine.add('STORE_WAYPOINT', StoreWaypoint(robot), transitions={ 'done' :'WAIT_SAY', 'continue' : 'WAIT_SAY'})

    return sm

if __name__ == '__main__':
    rospy.init_node('automatic_side_detection')

    startup(setup_statemachine, challenge_name="automatic_side_detection")
