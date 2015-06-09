import math
import PyKDL as kdl

import geometry_msgs.msg as gm

from ed.msg import EntityInfo

def isLeftOfLine(p, l):
	""" Checks whether point p is left of line l
		p: geometry_msgs.Point
		l: array of size two of geometry_msgs.Point. 
		Note that only x and y are evaluated
	""" 		
	A = l[0]
	B = l[1]
	if ( (B.x() - A.x()) * (p.y() - A.y()) - (B.y() - A.y()) * (p.x() - A.x()) ) > 0:
		return True
	else:
		return False
	#position = sign( (Bx-Ax)*(Y-Ay) - (By-Ay)*(X-Ax) )

def isPointInsideHull(p, chull):
	""" Checks whether point p is inside the convex hull ch
		p: geometry_msgs.Point
		ch: array of geometry_msgs.Point. Note that the order is supposed to be anti-clockwise
		Note that only p.x and p.y are evaluated
	"""

	''' Copy list '''
	ch = list(chull)

	''' Loop over lines of chull '''
	for i in xrange(len(ch) - 1):

		''' Check whether the point is left of the line '''
		if not isLeftOfLine(p, [ch[i], ch[i+1]]):
			return False

	return True

def onTopOff(subject, container, ht=0.1):
	""" Checks whether the entity 'subject' is on top of entity 'container' 
		@param subject the EntityInfo which may be on top of the container, e.g. a cup
		@param container: the EntityInfo that may be supporting the other subject, e.g. a table.
		ht: height threshold: the bottom of entity and the top of container need to be within ht m
	"""
	''' First: check if container actually has a convex hull '''
	if len(container.convex_hull) == 0:
		print 'Error, entity {0} has no convex hull'.format(container.id)
		return False

	''' Second: turn points into KDL objects and offset '''
	center_pose = pose_msg_to_kdl_frame(container.pose)
	convex_hull = [] # Convex hull in map frame
	for point in container.convex_hull:
		p = point_msg_to_kdl_vector(point)
		p = center_pose * p
		convex_hull.append(p)

	''' Third: check if center point of entity is within convex hull of container '''
	if not isPointInsideHull(center_pose.p, convex_hull):
		return False

	subject_bottom = subject.pose.position.z+subject.z_min
	container_top = container.pose.position.z+container.z_max
	if math.fabs(subject_bottom - container_top) > ht:
		return False

	return True

def point_msg_to_kdl_vector(point):
	return kdl.Vector(point.x, point.y, point.z)

def pose_msg_to_kdl_frame(pose):
	rot = kdl.Rotation.Quaternion(pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w)
	trans = kdl.Vector(pose.position.x ,pose.position.y, pose.position.z)
	return kdl.Frame(rot, trans)