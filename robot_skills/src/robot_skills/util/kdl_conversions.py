import PyKDL as kdl

import geometry_msgs.msg as gm

def pointMsgToKdlVector(point):
    """
    Convert a ROS geometry_msgs.msg.Point message to a PyKDL.Vector object
    :type point:  geometry_msgs.msg.Point
    :rtype: PyKDL.Vector
    """
    return kdl.Vector(point.x, point.y, point.z)

def kdlVectorToPointMsg(vector):
    """
    Convert a PyKDL.Vector object to a ROS geometry_msgs.msg.Point message
    :type vector: PyKDL.Vector
    :rtype: geometry_msgs.msg.Point
    """
    return gm.Point(vector.x(), vector.y(), vector.z())

def kdlRotationToQuaternionMsg(rotation):
    """
    Convert a PyKDL.Rotation object to a ROS geometry_msgs.msg.Quaternion message
    :param rotation: Rotation to be converted
    :type rotation: PyKDL.Rotation
    :rtype: geometry_msgs.msg.Quaternion
    """
    return gm.Quaternion(rotation.GetQuaternion())

def quaternionMsgToKdlRotation(quaternion):
    """
    Convert a geometry_msgs.msg.Quaternion message to a ROS PyKDL.Rotation object
    :param quaternion: Rotation to be converted
    :type quaternion: geometry_msgs.msg.Quaternion
    :rtype: PyKDL.Rotation
    """
    return kdl.Rotation.Quaternion(quaternion.x, quaternion.y, quaternion.z, quaternion.w)

def poseMsgToKdlFrame(pose):
    """
    Convert a geometry_msgs.msg.Pose message to a ROS PyKDL.Frame object
    :param pose: Pose to be converted
    :type pose: geometry_msgs.msg.Quaternion
    :rtype: PyKDL.Rotation
    """
    rot = kdl.Rotation.Quaternion(pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w)
    trans = kdl.Vector(pose.position.x ,pose.position.y, pose.position.z)
    return kdl.Frame(rot, trans)

def kdlFrameToPoseMsg(frame):
    """
    Convert a ROS PyKDL.Frame object to a geometry_msgs.msg.Pose message
    :param frame: Frame to be converted
    :type frame: PyKDL.Rotation
    :rtype: geometry_msgs.msg.Quaternion
    """
    pose = gm.Pose()
    pose.position = kdlVectorToPointMsg(frame.p)
    pose.orientation = kdlRotationToQuaternionMsg(frame.M)
    return pose

if __name__ == "__main__":
    import doctest
    doctest.testmod()
