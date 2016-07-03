#!/usr/bin/python

from action_result import ActionResult
import rospy
import robot_smach_states as states
import json
import tf
import math
from robot_skills.amigo import Amigo

BAR_ENTITY_FRAME_ID = "bar"
DIST_FROM_BAR = 1.0
PLACE_JOINT_CONFIG = [-1.0, 0.0, -1.57, 0.7, 0.0, -.2, 0]
RESET_JOINT_CONFIG = [-0.1, -0.2, 0.2, 0.8, 0.0, 0.0, 0.0]
PLACE_TORSO_HEIGHT = 0.15
RETRACT_TORSO_HEIGHT = 0.2
HANDOVER_POSE_RADIUS =0.20
ARM_SIDE = "left"

def amigo_navigate_to_handover_pose(amigo, frame_id=BAR_ENTITY_FRAME_ID, dist_from_bar=DIST_FROM_BAR):
    navigateToPoseSM = states.NavigateToPose(amigo,
                                             x=dist_from_bar,
                                             y=0.0,
                                             rz=-math.pi/2.0,
                                             radius=HANDOVER_POSE_RADIUS,
                                             frame_id=frame_id)

    nav_res = navigateToPoseSM.execute()
    if nav_res == "arrived":
        return ActionResult(ActionResult.SUCCEEDED, "Amigo: Arrived at handover pose")
    else:
        return ActionResult(ActionResult.FAILED, ("Amigo: handover pose %s",nav_res))

def amigo_move_arm_to_place_position(amigo):
    res = ActionResult.FAILED
    if ARM_SIDE == "left":
        if amigo.leftArm._send_joint_trajectory([PLACE_JOINT_CONFIG]):
            res = ActionResult.SUCCEEDED
    elif ARM_SIDE == "right":
        if amigo.rightArm._send_joint_trajectory([PLACE_JOINT_CONFIG]):
            res = ActionResult.SUCCEEDED

    if res == ActionResult.SUCCEEDED:
        (x, y, z), (rx, ry, rz, rw) = amigo.tf_listener.lookupTransform("/map", "/amigo/grippoint_%s" % ARM_SIDE)
        (roll, pitch, yaw) = tf.transformations.euler_from_quaternion([rx, ry, rz, rw])
        print "Amigo gripper height: %f" % z
        msg = "Amigo: I'm ready to place the drink at: %s" % json.dumps({'x': x, 'y': y, 'yaw': yaw})
    else:
        msg = "Amigo: Place joint goal could not be reached"

    return ActionResult(res,msg)

def amigo_place(amigo):
    res = ActionResult.FAILED

    # Send lower torso goal and wait for the torso to reach it
    if not amigo.torso._send_goal([PLACE_TORSO_HEIGHT]):
        return ActionResult(res,"Amigo: Could not reach lower torso goal")
    amigo.torso.wait_for_motion_done()

    # Open gripper and wait for it to open
    if ARM_SIDE == "left":
        amigo.leftArm.send_gripper_goal('open')
    elif ARM_SIDE == "right":
        amigo.rightArm.send_gripper_goal('open')
    rospy.sleep(1.0)

    # Send upper torso goal and wait for the torso to reach it
    if not amigo.torso._send_goal([RETRACT_TORSO_HEIGHT]):
        return ActionResult(res,"Amigo: Could not reach upper torso goal")
    amigo.torso.wait_for_motion_done()

    # Close gripper and wait for it to close
    if ARM_SIDE == "left":
        amigo.leftArm.send_gripper_goal('close')
    elif ARM_SIDE == "right":
        amigo.rightArm.send_gripper_goal('close')
    rospy.sleep(1.0)

    # If all went wel, return succeeded
    res = ActionResult.SUCCEEDED
    return ActionResult(res, "Amigo: Successfully placed item")

def amigo_reset_arm(amigo):
    if ARM_SIDE == "left":
        if not amigo.leftArm._send_joint_trajectory([RESET_JOINT_CONFIG]):
            return ActionResult(ActionResult.FAILED, "Amigo: Failed to move arm to reset position")
        amigo.leftArm.wait_for_motion_done()
    elif ARM_SIDE == "right":
        if not amigo.rightArm._send_joint_trajectory([RESET_JOINT_CONFIG]):
            return ActionResult(ActionResult.FAILED, "Amigo: Failed to move arm to reset position")
        amigo.rightArm.wait_for_motion_done()

    return ActionResult(ActionResult.SUCCEEDED, "Amigo: Reset arm succeeded")

if __name__ == "__main__":

    """ Test stuff """
    rospy.init_node("Test handover motions: Amigo")
    amigo = Amigo(wait_services=True)

    rospy.loginfo("AMIGO is loaded and will move to the pre-handover pose")
    result = amigo_navigate_to_handover_pose(amigo)
    rospy.loginfo("{0}".format(result.message))

    rospy.loginfo("AMIGO will move its arm to the place position")
    result = amigo_move_arm_to_place_position(amigo)
    rospy.loginfo("{0}".format(result.message))

    raw_input("Press enter when SERGIO has its tray under amigo's gripper")
    result = amigo_place(amigo)
    rospy.loginfo("{0}".format(result.message))

    raw_input("Press enter as soon as SERGIO has moved away from under AMIGO'S arm")
    result = amigo_reset_arm(amigo)
    rospy.loginfo("{0}".format(result.message))