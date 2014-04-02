#! /usr/bin/env python
import roslib; roslib.load_manifest('robot_skills')
import rospy
from amigo_arm_navigation.msg._grasp_precomputeGoal import grasp_precomputeGoal
import actionlib
from arm_navigation_msgs.msg._MoveArmAction import MoveArmAction
from actionlib_msgs.msg._GoalStatus import GoalStatus
import amigo_actions
import amigo_actions.msg
from amigo_arm_navigation.msg._grasp_precomputeAction import grasp_precomputeAction
from geometry_msgs.msg import TwistStamped, Twist, Quaternion

from control_msgs.msg import FollowJointTrajectoryGoal, FollowJointTrajectoryAction
from trajectory_msgs.msg import JointTrajectoryPoint
from sensor_msgs.msg import JointState

# Whole-body control/planning
from amigo_whole_body_controller.msg._ArmTaskAction import ArmTaskAction
from amigo_whole_body_controller.msg._ArmTaskGoal import ArmTaskGoal

import threading
import util.concurrent_util

"""TF"""
import tf
from tf.transformations import euler_from_quaternion
import tf_server

"""Marker publisher"""
import visualization_msgs.msg

from math import degrees, radians

## TODO: Reset arm position
#TODO : (Arm.send_[a-zA-Z_]*[(]*) replace time_out
#Side en state enums
class Side:
    """Specifies a Side, either LEFT or RIGHT"""
    LEFT = 0
    RIGHT = 1
    name = {RIGHT:"right", LEFT:"left"}
    
class State:
    """Specifies a State either OPEN or CLOSE"""
    OPEN = 0
    CLOSE = 1
    
class ArmActionClients(object):
    """Collection of action clients that are needed"""
    def __init__(self):
        #Init arm actionlibs
        self._ac_move_arm_right = actionlib.SimpleActionClient("move_right_arm",  MoveArmAction)
        rospy.loginfo("waiting for arm right server")
        self._ac_move_arm_left = actionlib.SimpleActionClient("move_left_arm",  MoveArmAction)
        rospy.loginfo("waiting for arm left server")
        
        #Init gripper actionlibs
        self._ac_gripper_right = actionlib.SimpleActionClient("gripper_server_right", amigo_actions.msg.AmigoGripperCommandAction)
        rospy.loginfo("waiting for gripper right server")
        self._ac_gripper_left  = actionlib.SimpleActionClient("gripper_server_left",  amigo_actions.msg.AmigoGripperCommandAction)
        rospy.loginfo("waiting for gripper left server")

        #Init graps precompute actionlibs
        self._ac_grasp_precompute_right = actionlib.SimpleActionClient("grasp_precompute_right", grasp_precomputeAction)
        rospy.loginfo("waiting for precompute right server")
        self._ac_grasp_precompute_left = actionlib.SimpleActionClient("grasp_precompute_left",  grasp_precomputeAction)
        rospy.loginfo("waiting for precompute left server")
        
        self._ac_joint_traj_left = actionlib.SimpleActionClient("/joint_trajectory_action_left",  FollowJointTrajectoryAction)
        self._ac_joint_traj_right = actionlib.SimpleActionClient("/joint_trajectory_action_right",  FollowJointTrajectoryAction)

        #Init whole body control/planner actionlibs
        self._ac_armtask = actionlib.SimpleActionClient("whole_body_planner/motion_constraint", ArmTaskAction)
        rospy.loginfo("waiting for whole-body planner server")
    
    def close(self):
        try:
            rospy.loginfo("Arms cancelling all goals on all arm-related ACs on close")
        except AttributeError:
            print "Arms cancelling all goals on all arm-related ACs on close. Rospy is already deleted."
        self._ac_move_arm_right.cancel_all_goals()
        self._ac_move_arm_left.cancel_all_goals()
        
        self._ac_gripper_right.cancel_all_goals()
        self._ac_gripper_left.cancel_all_goals()
        
        self._ac_grasp_precompute_right.cancel_all_goals()
        self._ac_grasp_precompute_left.cancel_all_goals()

        self._ac_joint_traj_left.cancel_all_goals()
        self._ac_joint_traj_right.cancel_all_goals()

        self._ac_armtask.cancel_all_goals()
    

##intialize as a static class
actionClients = ArmActionClients()

class Offset(object):
    def __init__(self, x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0):
        self.x=x
        self.y=y
        self.z=z
        self.roll=roll
        self.pitch=pitch
        self.yaw=yaw

class Arms(object):
    """
    An interface to amigo arms, you can access both sides when specifying a side
    Can be used interactively, but it is better to use a side explicitly. 
    Run command help(left) for more info 
    
    Important to remember commands are similar, however a side which is a python-like
    enum has to be specified: Side.LEFT or Side.RIGHT

    /amigo/X_arm/measurements
    /amigo/X_arm/references

    name: ['shoulder_yaw_joint_X', 'shoulder_pitch_joint_X', 'shoulder_roll_joint_X', 'elbow_pitch_joint_X', 'elbow_roll_joint_X', 'wrist_pitch_joint_X', 'wrist_yaw_joint_X']
    """

    joint_names = ['shoulder_yaw_joint_{side}', 'shoulder_pitch_joint_{side}', 'shoulder_roll_joint_{side}', 'elbow_pitch_joint_{side}', 'elbow_roll_joint_{side}', 'wrist_pitch_joint_{side}', 'wrist_yaw_joint_{side}']

    SHOULDER_YAW = 0
    SHOULDER_PITCH =1 
    SHOULDER_ROLL = 2
    ELBOW_PITCH = 3
    ELBOW_ROLL = 4
    WRIST_PITCH = 5
    WRIST_YAW = 6

    POINT_AT_OBJECT_BACKWARD = [-0.4 ,-0.750 , 0.50 , 1.50 , 0.000 , 0.7500 , 0.000]
    POINT_AT_OBJECT_FORWARD = [-0.2 ,-0.250 , 0.40 , 1.25 , 0.000 ,0.500 , 0.000]
    HOLD_TRAY_POSE = [-0.1, 0.13, 0.4, 1.5, 0, 0.5, 0]
    SUPPORT_PERSON_POSE = [-0.1, -1.57, 0, 1.57, 0,0,0]
    RESET_POSE = [-0.1,-0.2,0.2,0.8,0.0,0.0,0.0] # This is the usual
    #RESET_POSE = [-0.3, -0.05, 0.2, 1.0, 0.0, 0.0, 0.0] # This is more useful for whole-body control

    def __init__(self, tf_listener):
        #Easy access to sides
        self.leftSide = Side.LEFT
        self.rightSide = Side.RIGHT
    
        self.openState = State.OPEN
        self.closeState = State.CLOSE
        
        self._joint_pos = {Side.LEFT:(None, None, None, None, None, None, None), Side.RIGHT: (None, None, None, None, None, None, None)}
        self._joint_names={Side.LEFT:["shoulder_yaw_joint_left",
                                      "shoulder_pitch_joint_left",
                                      "shoulder_roll_joint_left",
                                      "elbow_pitch_joint_left",
                                      "elbow_roll_joint_left",
                                      "wrist_pitch_joint_left",
                                      "wrist_yaw_joint_left"], 
                           Side.RIGHT:["shoulder_yaw_joint_right",
                                      "shoulder_pitch_joint_right",
                                      "shoulder_roll_joint_right",
                                      "elbow_pitch_joint_right",
                                      "elbow_roll_joint_right",
                                      "wrist_pitch_joint_right",
                                      "wrist_yaw_joint_right"]}

        self.arm_left_measurement_sub = rospy.Subscriber("/amigo/left_arm/measurements", JointState, self._receive_arm_left_joints)
        self.arm_right_measurement_sub = rospy.Subscriber("/amigo/right_arm/measurements", JointState, self._receive_arm_right_joints)

        self.leftOffset = Offset(x=0.10, y=-0.05, z=0.04)
        self.rightOffset = Offset(x=0.08, y=0.005, z=0.06)


        self.markerToGrippointOffset = Offset(x=-0.03, y=0.0, z=0.03)
        
        self.tf_listener = tf_listener
        
        self._marker_publisher = rospy.Publisher("grasp_target", visualization_msgs.msg.Marker)

    def close(self):
        actionClients.close()

    def send_arm_task(self, px, py, pz, roll, pitch, yaw, timeout=40, link_name="grippoint_right", frame_id='base_link', goal_type="reset"):
        """ Send a link to a desired pose using the whole-body controller/planner
            Params: Position and orientation (RPY)
                    Link_name, for which link is the goal specified, default is grippoint_right
                    Frame_id, the link_name's goal pose with respect to this frame, default is base_link
                    Goal_type, semantic description of the goal (pre-grasp, lift, retract etc), default is reset
        """

        rospy.loginfo("Received whole-body planner goal for {link} with respect to {root} of type: {type} ".format(link=link_name, root=frame_id, type=goal_type))

        # Check which side and add arm specific offset
        if "right" in link_name: 
            offset = self.rightOffset
        elif "left" in link_name: 
            offset = self.leftOffset
        else:
            rospy.loginfo("Specify a correct link name")
            return False
        
        # Create goal
        arm_task_goal = ArmTaskGoal()

        # Assign goal_type
        arm_task_goal.goal_type = goal_type

        # Assign pose
        arm_task_goal.position_constraint.header.frame_id = frame_id
        arm_task_goal.position_constraint.header.stamp = rospy.Time.now()
        arm_task_goal.position_constraint.link_name = link_name
        arm_task_goal.position_constraint.position.x = px + offset.x
        arm_task_goal.position_constraint.position.y = py + offset.y
        arm_task_goal.position_constraint.position.z = pz + offset.z

        arm_task_goal.orientation_constraint.header.frame_id = frame_id
        arm_task_goal.orientation_constraint.header.stamp = rospy.Time.now()
        arm_task_goal.orientation_constraint.link_name = link_name
        quaternion = Quaternion()
        quaternion = tf.transformations.quaternion_from_euler(roll, pitch, yaw)
        arm_task_goal.orientation_constraint.orientation.x = quaternion[0]
        arm_task_goal.orientation_constraint.orientation.y = quaternion[1]
        arm_task_goal.orientation_constraint.orientation.z = quaternion[2]
        arm_task_goal.orientation_constraint.orientation.w = quaternion[3]

        """ 
            Discuss with Janno, 
                should this be here? 
                Should they be added in action request?
                Or should planners fill these in?
        """

        # Assign stiffnesses
        arm_task_goal.stiffness.force.x = 70.0
        arm_task_goal.stiffness.force.y = 70.0
        arm_task_goal.stiffness.force.z = 70.0

        arm_task_goal.stiffness.torque.x = 15.0
        arm_task_goal.stiffness.torque.y = 15.0
        arm_task_goal.stiffness.torque.z = 15.0

        # Assign tolerances 
        arm_task_goal.position_constraint.constraint_region_shape.type = arm_task_goal.position_constraint.constraint_region_shape.SPHERE
        arm_task_goal.position_constraint.constraint_region_shape.dimensions.append(0.03)

        arm_task_goal.orientation_constraint.absolute_roll_tolerance = 0.3
        arm_task_goal.orientation_constraint.absolute_pitch_tolerance = 0.3
        arm_task_goal.orientation_constraint.absolute_yaw_tolerance = 0.3

        # Assign target point offset
        arm_task_goal.position_constraint.target_point_offset.x = 0.0;
        arm_task_goal.position_constraint.target_point_offset.y = 0.0;
        arm_task_goal.position_constraint.target_point_offset.z = 0.0;


        #rospy.loginfo(arm_task_goal)

        # Send the task
        actionClients._ac_armtask.send_goal_and_wait(arm_task_goal, rospy.Duration(timeout))
        if actionClients._ac_armtask.get_state() == GoalStatus.SUCCEEDED:
            rospy.loginfo("Arm target reached")
            return True
        else:
            rospy.loginfo("Reaching arm target failed")
            rospy.loginfo(actionClients._ac_armtask.get_state())
            return False

    def send_goal(self, px, py, pz, roll, pitch, yaw, timeout=30, side=None, pre_grasp = False, frame_id = '/amigo/base_link', use_offset = False, first_joint_pos_only=False):
        """Send a arm to a goal: 
        Using a position px,py,pz. An orientation roll,pitch,yaw. A time out time_out. And a side Side.LEFT or Side.RIGHT
        
        Optional parameters are if a pre_grasp should be performed and a frame_id which defaults to base_link """
        if side == None:
            raise Exception("Send_arm_goal: No side was specified..")

        ''' Correct offset '''
        if side == Side.LEFT:
            offset = self.leftOffset
        elif side == Side.RIGHT:
            offset = self.rightOffset
        else:
            rospy.logerr("Side undefined")
            return False
        
        # create goal:
        grasp_precompute_goal = grasp_precomputeGoal()
        grasp_precompute_goal.goal.header.frame_id = frame_id
        grasp_precompute_goal.goal.header.stamp = rospy.Time.now()
        
        grasp_precompute_goal.PERFORM_PRE_GRASP = pre_grasp
        grasp_precompute_goal.FIRST_JOINT_POS_ONLY = first_joint_pos_only
        
        grasp_precompute_goal.goal.x = px + offset.x
        grasp_precompute_goal.goal.y = py + offset.y
        grasp_precompute_goal.goal.z = pz + offset.z
        
        grasp_precompute_goal.goal.roll = roll + offset.roll
        grasp_precompute_goal.goal.pitch = pitch + offset.pitch
        grasp_precompute_goal.goal.yaw = yaw + offset.yaw
        
        #rospy.loginfo("Arm goal: {0}".format(grasp_precompute_goal))
        
        self._publish_marker(grasp_precompute_goal, "red")
    
        # send goal:
        if side == Side.LEFT:
            actionClients._ac_grasp_precompute_left.send_goal_and_wait(grasp_precompute_goal, rospy.Duration(timeout))
            if actionClients._ac_grasp_precompute_left.get_state() == GoalStatus.SUCCEEDED:
                rospy.loginfo("Arm target reached")
                return True
            else:
                rospy.loginfo("Reaching arm target failed")
                rospy.loginfo(actionClients._ac_grasp_precompute_left.get_state())
                return False
            
        elif side == Side.RIGHT:
            actionClients._ac_grasp_precompute_right.send_goal_and_wait(grasp_precompute_goal, rospy.Duration(timeout))
            if actionClients._ac_grasp_precompute_right.get_state() == GoalStatus.SUCCEEDED:
                rospy.loginfo("Arm target reached")
                return True
            else:
                rospy.loginfo("Reaching arm target failed")
                return False
            
        else: 
            rospy.logerr("side undefined")
            return False
    
    def send_delta_goal(self, px, py, pz, roll, pitch, yaw, timeout=30, side=None, pre_grasp = False, frame_id = '/amigo/base_link', use_offset = False, first_joint_pos_only=False):
        """Send arm to an offset with respect to current position: 
        Using a position px,py,pz. An orientation roll,pitch,yaw. A time out time_out. And a side Side.LEFT or Side.RIGHT
        
        Optional parameters are if a pre_grasp should be performed and a frame_id which defaults to base_link """
        if side == None:
            raise Exception("Send_arm_goal: No side was specified..")
        
        # create goal:
        grasp_precompute_goal = grasp_precomputeGoal()
        grasp_precompute_goal.delta.header.frame_id = frame_id
        grasp_precompute_goal.delta.header.stamp = rospy.Time.now()
        
        grasp_precompute_goal.PERFORM_PRE_GRASP = pre_grasp
        grasp_precompute_goal.FIRST_JOINT_POS_ONLY = first_joint_pos_only
        
        grasp_precompute_goal.delta.x = px
        grasp_precompute_goal.delta.y = py
        grasp_precompute_goal.delta.z = pz
        
        grasp_precompute_goal.delta.roll = roll
        grasp_precompute_goal.delta.pitch = pitch
        grasp_precompute_goal.delta.yaw = yaw
        
        #rospy.loginfo("Arm goal: {0}".format(grasp_precompute_goal))
        
        self._publish_marker(grasp_precompute_goal, "red")
    
        # send goal:
        if side == Side.LEFT:
            actionClients._ac_grasp_precompute_left.send_goal_and_wait(grasp_precompute_goal, rospy.Duration(timeout))
            if actionClients._ac_grasp_precompute_left.get_state() == GoalStatus.SUCCEEDED:
                rospy.loginfo("Arm target reached")
                return True
            else:
                rospy.loginfo("Reaching arm target failed")
                rospy.loginfo(actionClients._ac_grasp_precompute_left.get_state())
                return False
            
        elif side == Side.RIGHT:
            actionClients._ac_grasp_precompute_right.send_goal_and_wait(grasp_precompute_goal, rospy.Duration(timeout))
            if actionClients._ac_grasp_precompute_right.get_state() == GoalStatus.SUCCEEDED:
                rospy.loginfo("Arm target reached")
                return True
            else:
                rospy.loginfo("Reaching arm target failed")
                return False
            
        else: 
            rospy.logerr("side undefined")
            return False
     
    ################################# function cancel arm right goal ############################
    def cancel_goal(self, side=None):
        """Cancel arm goal. Specifiy side, Side.LEFT or Side.RIGHT """
        if side == None:
            raise Exception("Cancel_arm_goal: No side specified")
        elif side == Side.RIGHT:
            self.__cancel_right_goal()
        elif side == Side.LEFT:
            self.__cancel_left_goal()
    
    def __cancel_right_goal(self):
        actionClients._ac_grasp_precompute_right.cancel_all_goals()
        actionClients._ac_move_arm_right.cancel_all_goals()
        actionClients._ac_joint_traj_right.cancel_all_goals()
        return True
    
    def __cancel_left_goal(self):
        actionClients._ac_grasp_precompute_left.cancel_all_goals()
        actionClients._ac_move_arm_left.cancel_all_goals()
        actionClients._ac_joint_traj_left.cancel_all_goals()
        return True
    
    ################################# function send gripper goal ############################
    
    def send_gripper_goal_open(self, side, timeout=10):
        """
        Open gripper.
        Specify side and time_out
        """
        return self.send_gripper_goal(State.OPEN, side, timeout)
        
    def send_gripper_goal_close(self, side, timeout=10):
        """
        Close gripper
        Specify side and time_out.
        """
        return self.send_gripper_goal(State.CLOSE, side, timeout)
    
    def send_gripper_goal(self, state, side, timeout=10):
        """
        Send open or close goal to gripper.
        Specify side, state and time_out
        side := Side.LEFT | Side.RIGHT
        state := State.OPEN | State.CLOSE
        
        The max torque used is 10.0. Should this be an optional param
        just let us know ;)
        """
        gripper_goal = amigo_actions.msg.AmigoGripperCommandGoal()
        
        if state == State.OPEN:
            gripper_goal.command.direction = -1
        elif state == State.CLOSE:
            gripper_goal.command.direction = 1
            
        gripper_goal.command.max_torque = 50.0
        
        rospy.loginfo("Sending gripper target {0}".format(gripper_goal).replace('\n', ' '))
        if side == Side.LEFT:
            current_ac = actionClients._ac_gripper_left
        elif side == Side.RIGHT:
            current_ac = actionClients._ac_gripper_right
        else: 
            raise Exception("Send_gripper_goal: Invalid side specified")
            return False

        current_ac.send_goal(gripper_goal)
        if timeout == 0.0:
            return True
        else:
            current_ac.wait_for_result(rospy.Duration(timeout))
            rospy.logdebug("Gripper result: {0}".format(current_ac.get_result()).replace("\n", " "))
            if actionClients._ac_gripper_left.get_state() == GoalStatus.SUCCEEDED:
                rospy.loginfo("Gripper target reached")
                return True
            else:
                rospy.loginfo("Reaching gripper target failed")
                return False
        
        
    def check_gripper_content(self, side):
        
        if side == Side.LEFT:
            gripperresult = actionClients._ac_gripper_left.get_result()
        elif side == Side.RIGHT:
            gripperresult = actionClients._ac_gripper_right.get_result()
        else:
            raise Exception("check_gripper_content: Invalid side specified")
        #rospy.loginfo("Check gripper content: {0}".format(gripperresult))
        
        """ Gripper probably contains something if direction = CLOSE, either max_torque or max_pos is reached (grasping done) and position is larger than a certain threshold """
        content_threshold = 0.2
        if gripperresult == None:
            rospy.logwarn("No gripper target given yet")
            return False
        elif (gripperresult.measurement.direction == 1 and (gripperresult.measurement.max_torque_reached or gripperresult.measurement.end_position_reached) and gripperresult.measurement.position > content_threshold):
                return True
        else:
                return False
            
    def send_joint_goal(self, q1=None, q2=None, q3=None, q4=None, q5=None, q6=None, q7=None, side=None, timeout=0):
        """Send a goal to the arms in joint coordinates, using an action client"""
        p = JointTrajectoryPoint()
        p.positions = [q1,q2,q3,q4,q5,q6,q7]
                
        traj_goal = FollowJointTrajectoryGoal()
        traj_goal.trajectory.points = [p]
        traj_goal.trajectory.joint_names = self._joint_names[side]

        class prettyfloat(float):
            """See http://stackoverflow.com/questions/1566936/easy-pretty-printing-of-floats-in-python"""
            def __repr__(self):
                return "%0.3f" % self

        rospy.loginfo("Send arm to jointcoords {0}".format(map(prettyfloat, p.positions)))
        
        result = None

        if side == Side.LEFT:
            current_ac = actionClients._ac_joint_traj_left
        elif side == Side.RIGHT:
            current_ac = actionClients._ac_joint_traj_right
        else:
            raise Exception("check_gripper_content: Invalid side specified")
            return False

        current_ac.send_goal(traj_goal)

        if timeout == 0.0:
            return True
        else:
            current_ac.wait_for_result(rospy.Duration(timeout))
            if current_ac.get_state() == GoalStatus.SUCCEEDED:
                return True
            else:
                rospy.logwarn("Cannot reach joint goal {0}".format(traj_goal))
                return False

    def send_joint_trajectory(self, joint_positions, side=None, timeout=0):
        """Let the arms follow a trajectory. 
        @param joint_positions is a list of joint coordinate lists, so a nested list.
        e.g. joint_positions = [[0,0,0,0,0,0,0], [-0.1,0,0,0,0,0,0], [-0.1,0,1,0,0,0,0]]
        Moves the arm from its home position to -0.1 on q1, then q3 to 1. 
        All coordinates are needed"""
                
        traj_goal = FollowJointTrajectoryGoal()
        traj_goal.trajectory.joint_names = self._joint_names[side]
        
        for joint_position in joint_positions:
            p = JointTrajectoryPoint()
            p.positions = joint_position

            traj_goal.trajectory.points += [p]

        rospy.loginfo("Moving arm in trajectory of {0} length".format(len(traj_goal.trajectory.points)))

        if side == Side.LEFT:
            current_ac = actionClients._ac_joint_traj_left
        elif side == Side.RIGHT:
            current_ac = actionClients._ac_joint_traj_right
        else:
            raise Exception("check_gripper_content: Invalid side specified")
            return False

        current_ac.send_goal(traj_goal)

        if timeout == 0.0:
            return True
        else:
            current_ac.wait_for_result(rospy.Duration(timeout))
            if current_ac.get_state() == GoalStatus.SUCCEEDED:
                return True
            else:
                rospy.logwarn("Cannot reach part of joint trajectory {0}".format(traj_goal))
                return False


    def send_delta_joint_goal(self, q1=0, q2=0, q3=0, q4=0, q5=0, q6=0, q7=0, side=None, timeout=0):
        """Move joint qX by some angle in radians. """
        #Replace the None-default arguments with the reference values, received via _receive_arm_{side}_joints.
        #The reference defaults to None, we must deal with that too.
        #When the robot is running, the refs should be updated before anyone gets the chance to call this method.
        #If it is somehow called too soon, yield an error.
        delta = [q1,q2,q3,q4,q5,q6,q7]
        current = self._joint_pos[side]
        if current[0]:
            new = [A+B for A, B in zip(delta,current)] #Adds the two lists
            rospy.logdebug("Sending {side} arm from {old} to {new} with delta {delta}".format(delta=delta, new=new, old=current, side={Side.LEFT:"left", Side.RIGHT:"right"}[side]))

            n1,n2,n3,n4,n5,n6,n7 = new
            return self.send_joint_goal(n1,n2,n3,n4,n5,n6,n7, timeout=timeout)
        else:
            rospy.logerr("There is no joint reference received for {side} arm, cannot send *relative* joint goal, only absolute".format(side={Side.LEFT:"left", Side.RIGHT:"right"}[side]))

    def send_delta_joint_trajectory(self, delta_dict_list, side=None, timeout=5.0, origin=None):
        """@param delta_dict_list is a list of dictionaries with deltas per joint, per step, e.g. [{"q1":-0.1, "q2":-0.3}, {"q3":-0.6}]
        @param origin The joint position list to start from, in order to optionally have a defined start. If empty, uses the current position"""

        if origin:
            self.send_joint_goal(origin[0], origin[1], origin[2], origin[3], origin[4], origin[5], origin[6], timeout)

        for delta_dict in delta_dict_list:
            #Take joint delta if it exists, otherwise, delta is 0
            self.send_delta_joint_goal( q1=delta_dict.get("q1", 0), 
                                        q2=delta_dict.get("q2", 0), 
                                        q3=delta_dict.get("q3", 0), 
                                        q4=delta_dict.get("q4", 0), 
                                        q5=delta_dict.get("q5", 0), 
                                        q6=delta_dict.get("q6", 0), 
                                        q7=delta_dict.get("q7", 0), timeout=timeout)
    
    def update_correction(self, side=None):

        rospy.logerr("Function currently not implemented")
        return False
        
        # if side == Side.LEFT:
        #     root_frame = "/hand_left"
        #     target_frame = "/hand_marker_left"
        # elif side == Side.RIGHT:
        #     root_frame = "/hand_right"
        #     target_frame = "/hand_marker_right"
        
        # # Look up transform
        # try:
        #     (trans,rot) = self.tf_listener.lookupTransform(root_frame, target_frame, rospy.Time(0))
        # except (tf.LookupException, tf.ConnectivityException):
        #     rospy.logwarn("Cannot find transform, not updating")
        #     return False
        # angles = euler_from_quaternion(rot)
        
        # # Check whether the update is realistic
        # # If so, update parameters
        # trans_threshold = 0.1
        # rot_threshold = 3.14/4
        # if (trans[0] < trans_threshold and trans[1] < trans_threshold and trans[2] < trans_threshold and angles[0] < rot_threshold and angles[1] < rot_threshold and angles[2] < rot_threshold ):
        #     if side == Side.LEFT:
        #         self.leftOffset = [trans[0],trans[1],trans[2],angles[0],angles[1],angles[2]]
        #         rospy.loginfo("Updated correction parameters left: {0}".format(self.leftOffset))
        #     elif side == Side.RIGHT:
        #         self.rightOffset = [trans[0],trans[1],trans[2],angles[0],angles[1],angles[2]]
        #         rospy.loginfo("Updated correction parameters right: {0}".format(self.rightOffset))
        # else:
        #     rospy.logwarn("Parameters not updated, correction does not seem sensible")
        
        # return True

    def get_pose(self, root_frame_id, side=None):
        """ Get the pose of the end-effector with respect to the specified frame_id"""
        if side == Side.LEFT:
            target_frame = "/amigo/grippoint_left"
        elif side == Side.RIGHT:
            target_frame = "/amigo/grippoint_right"
        root_frame = root_frame_id
        try:
            (trans,rot) = self.tf_listener.lookupTransform(root_frame, target_frame, rospy.Time(0))
        except (tf.LookupException, tf.ConnectivityException):
            rospy.logwarn("Cannot find transform, not updating")
            return False
        #angles = euler_from_quaternion(rot)
        return (trans,rot)
        
    
    def _publish_marker(self, goal, color):
        
        marker = visualization_msgs.msg.Marker()
        marker.header.frame_id = goal.goal.header.frame_id
        marker.header.stamp = rospy.Time.now()
        marker.type = 2
        marker.pose.position.x = goal.goal.x
        marker.pose.position.y = goal.goal.y
        marker.pose.position.z = goal.goal.z
        marker.lifetime = rospy.Duration(5.0)
        marker.scale.x = 0.1
        marker.scale.y = 0.1
        marker.scale.z = 0.1
        marker.color.r = 0;
        marker.color.g = 0;
        marker.color.b = 0;
        marker.color.a = 1;
        if color == "red":
            marker.color.r = 1
        elif color == "blue":
            marker.color.b = 1

        self._marker_publisher.publish(marker)

    _lock = threading.RLock()

    @util.concurrent_util.synchronized(_lock)
    def _receive_arm_left_joints(self, jointstate):
        self._joint_pos[Side.LEFT] = jointstate.position

    @util.concurrent_util.synchronized(_lock)
    def _receive_arm_right_joints(self, jointstate):
        self._joint_pos[Side.RIGHT] = jointstate.position

def add_side_argument(ArmMethod):
    def wrapper(self, *args, **kwargs):
        print "add_side_argument.wrapper"
        kwargs["side"] = self.side
        return ArmMethod(self, *args, **kwargs)
    return wrapper

class Arm(Arms):
    """
    A single arm can be either left or right, extends Arms:
    Use left or right to get arm while running from the python console
    
    Examples:
    >>> left.send_goal(0.265, 1, 0.816, 0, 0, 0, 60)
    or Equivalently:
    >>> left.send_goal(px=0.265, py=1, pz=0.816, yaw=0, pitch=0, roll=0, time_out=60, pre_grasp=False, frame_id='/amigo/base_link')
    
    #To open left gripper
    >>> left.send_gripper_goal_open(10)
    """
    def __init__(self, side, tf_listener):
        super(Arm,self).__init__(tf_listener)
        self.side = side
        print (self.side is Side.LEFT) or (self.side is Side.RIGHT)
        if (self.side is Side.LEFT) or (self.side is Side.RIGHT):
            pass
        else:
            raise Exception("Side should be either: Side.LEFT or Side.RIGHT")

        side_name = Side.name[self.side]
        self.joint_names = [joint_name.format(side=side_name) for joint_name in self.joint_names] #The Arms-class provides a format, which we fill in here
        self.occupied = False
    
    @add_side_argument
    def send_goal(self, *args, **kwargs):
        """Send arm to a goal: using a position px,py,pz and orientation roll,pitch,yaw and a timeout
        Optional parameters are if a pre_grasp should be performed and a frame_id which defaults to /amigo/base_link """
        return super(Arm, self).send_goal(*args, **kwargs)
    
    @add_side_argument
    def send_delta_goal(self, *args, **kwargs):
        """Send arm to an offset with respect to current position: using a position px,py,pz and orientation roll,pitch,yaw and a time out time_out
        Optional parameters are if a pre_grasp should be performed and a frame_id which defaults to /amigo/base_link """        
        return super(Arm, self).send_delta_goal(*args, **kwargs)
        
    def send_joint_goal(self, q1=0, q2=0, q3=0, q4=0, q5=0, q6=0, q7=0, timeout=0):
        """Send a goal to the arms in joint coordinates"""
        return super(Arm, self).send_joint_goal(q1,q2,q3,q4,q5,q6,q7,self.side, timeout=timeout)
    
    def send_joint_trajectory(self, positions, timeout=0):
        """Send a goal to the arms in joint coordinates"""
        return super(Arm, self).send_joint_trajectory(positions,self.side, timeout=timeout)
    
    def send_delta_joint_goal(self, q1=0, q2=0, q3=0, q4=0, q5=0, q6=0, q7=0, timeout=0):
        """Move the arm joints by some angle (in radians)
        >>> from math import radians
        >>> some_arm.send_delta_joint_goal(q1=radians(-20)) #e.g. amigo.leftArm.send_delta_joint_goal(q1=radians(-20))"""
        return super(Arm, self).send_delta_joint_goal(q1,q2,q3,q4,q5,q6,q7,self.side, timeout=timeout)
    
    def send_delta_joint_trajectory(self, delta_dict_list, timeout=0, origin=None):
        """@param delta_dict_list is a list of dictionaries with deltas per joint, per step, e.g. [{q1=-0.1, q4=0.4}, {q6=1.57}]
        @param origin The joint position list to start from, in order to optionally have a defined start. If empty, uses the current position"""
        return super(Arm, self).send_delta_joint_trajectory(delta_dict_list,self.side, timeout=timeout, origin=origin)

    def send_arm_task(self, *args, **kwargs):
        """Send a goal to the whole-body planner"""
        return super(Arm, self).send_arm_task(*args, **kwargs)

    def reset_arm(self):
        """Send the arm to a suitable (natural looking) (driving) position"""
        #return super(Arm, self).send_joint_goal(-0.1,-0.2,0.2,0.8,0.0,0.0,0.0,self.side)
        return super(Arm, self).send_joint_goal(side=self.side,*(self.RESET_POSE))
    
    def cancel_goal(self):
         """Cancel arm goal """
         return super(Arm, self).cancel_goal(self.side)
    
    def send_gripper_goal(self, state, timeout=10):
        """Generic open or close gripper goal method. Expects a state: State.OPEN or State.CLOSE and a time_out"""
        return super(Arm, self).send_gripper_goal(state, self.side, timeout)
    
    def send_gripper_goal_open(self, timeout=10):
         """ Open gripper, expects a time_out parameter"""
         return self.send_gripper_goal(State.OPEN, timeout)
    
    def send_gripper_goal_close(self,  timeout=10):
         """ Close gripper, expects a time_out parameter"""
         return self.send_gripper_goal(State.CLOSE, timeout)
     
    def check_gripper_content(self):
        """ Check if the gripper has successfully grasped something """
        return super(Arm, self).check_gripper_content(self.side)
    
    def send_twist(self, twist, duration):
        super(Arm, self).send_twist(twist, duration, self.side)
        
    def update_correction(self):
        """ Update correction factor """
        return super(Arm, self).update_correction(self.side)

    
    def get_pose(self, root_frame_id):
        """ Get the pose of the end-effector with respect to the specified root_frame_id"""
        return super(Arm, self).get_pose(root_frame_id,self.side)

    @property
    def joint_pos(self):
        """The joint positions for all joints. Index individual joints via Arms.SHOULDER_..., ELBOW_.. and WRIST_..."""
        return self._joint_pos[self.side]
        

if __name__ == "__main__":
    rospy.init_node('amigo_arms_executioner', anonymous=True)
    #Easy enum access
    leftSide = Side.LEFT
    rightSide = Side.RIGHT
    
    openState = State.OPEN
    closeState = State.CLOSE
    
    tf_listener = tf_server.TFClient()

    arms = Arms(tf_listener)
    left = Arm(leftSide, tf_listener)
    right = Arm(rightSide, tf_listener)
    
