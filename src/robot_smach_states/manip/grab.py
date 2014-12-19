#! /usr/bin/env python
import rospy
import smach

# from geometry_msgs.msg import *
import robot_skills.util.msg_constructors as msgs
import robot_skills.util.transformations as transformations

# from cb_planner_msgs_srvs.srv import *
# from cb_planner_msgs_srvs.msg import *

from robot_smach_states.navigation import NavigateToGrasp
from robot_smach_states.designators.designator import AttrDesignator

# ----------------------------------------------------------------------------------------------------

class PickUp(smach.State):
    def __init__(self, robot, arm, grab_entity_designator):
        smach.State.__init__(self, outcomes=['succeeded','failed'])
        self._robot = robot
        self.arm = arm
        self.grab_entity_designator = grab_entity_designator

    def execute(self, userdata=None):
        rospy.loginfo('PickUp!')

        try:
            entity_id = self.grab_entity_designator.resolve().id
        except Exception, e:
            rospy.logerr('No entity found: {0}'.format(e))
            return 'failed'

        # goal in map frame
        goal_map = msgs.Point(0, 0, 0)

        # Transform to base link frame
        goal_bl = transformations.tf_transform(goal_map, entity_id, self._robot.robot_name+'/base_link', tf_listener=self._robot.tf_listener)
        if goal_bl == None:
            rospy.logerr('Transformation of goal to base failed')
            return 'failed'

        rospy.loginfo(goal_bl)

        # Arm to position in a safe way
        self.arm.send_joint_trajectory('prepare_grasp')

        # Open gripper
        self.arm.send_gripper_goal('open')

        # Pre-grasp
        rospy.loginfo('Starting Pre-grasp')
        if not self.arm.send_goal(goal_bl.x, goal_bl.y, goal_bl.z, 0, 0, 0,
                             frame_id='/'+self._robot.robot_name+'/base_link', timeout=20, pre_grasp=True, first_joint_pos_only=True):
            rospy.logerr('Pre-grasp failed:')
            
            self.arm.reset()
            self.arm.send_gripper_goal('close', timeout=None)
            return 'failed'

        # Grasp
        if not self.arm.send_goal(goal_bl.x, goal_bl.y, goal_bl.z, 0, 0, 0, frame_id='/'+self._robot.robot_name+'/base_link', timeout=120, pre_grasp = True):
            self._robot.speech.speak('I am sorry but I cannot move my arm to the object position', block=False)
            rospy.logerr('Grasp failed')
            self.arm.reset()
            self.arm.send_gripper_goal('close', timeout=None)
            return 'failed'

        # Close gripper
        self.arm.send_gripper_goal('close')

        # Lift
        if not self.arm.send_goal( goal_bl.x, goal_bl.y, goal_bl.z + 0.1, 0.0, 0.0, 0.0, timeout=20, pre_grasp=False, frame_id='/'+self._robot.robot_name+'/base_link'):
            rospy.logerr('Failed lift')

        # Retract
        if not self.arm.send_goal( goal_bl.x - 0.1, goal_bl.y, goal_bl.z + 0.1, 0.0, 0.0, 0.0, timeout=20, pre_grasp=False, frame_id='/'+self._robot.robot_name+'/base_link'):
            rospy.logerr('Failed retract')

        # Carrying pose
        if self.arm.side == 'left':
            y_home = 0.2
        else:
            y_home = -0.2

        rospy.loginfo('y_home = ' + str(y_home))
        
        rospy.loginfo('start moving to carrying pose')        
        if not self.arm.send_goal(0.18, y_home, goal_bl.z + 0.1, 0, 0, 0, 60):            
            rospy.logerr('Failed carrying pose')
        
        return 'succeeded'                


        #machine = robot_smach_states.manipulation.GrabMachineWithoutBase(side=side, robot=self._robot, grabpoint_query=query)
        #machine.execute()             
        
# ----------------------------------------------------------------------------------------------------

class Grab(smach.StateMachine):
    def __init__(self, robot, designator, arm):
        smach.StateMachine.__init__(self, outcomes=['done', 'failed'])
        self.robot = robot

        with self:
            #AttrDesignator because the designator only returns the Entity, but not the id. AttrDesignator resolves to the id attribute of whatever comes out of $designator
            smach.StateMachine.add('NAVIGATE_TO_GRAB', NavigateToGrasp(self.robot, AttrDesignator(designator, 'id'), arm.side), 
                transitions={ 'unreachable' : 'failed',
                              'goal_not_defined' : 'failed',
                              'arrived' : 'GRAB'})

            smach.StateMachine.add('GRAB', PickUp(self.robot, arm, designator),
                transitions={'succeeded' :   'done',
                             'failed' :   'failed'})