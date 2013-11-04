#!/usr/bin/python
"""Designators are intended to excapsulate the process of selecting goals and 
of marking them as finished or inachievable.

TODO:
Designators can be refined by a user of it. 
This means that the query for it is extended, for example. 
Some variables in the query can also be made constants, as to make the query more specific."""
import roslib; roslib.load_manifest('robot_smach_states')
import rospy
from psi  import Conjunction, Compound

import robot_skills.util.msg_constructors as msgs

def iter_children(term):
    if term.is_variable() or term.is_constant():
        yield term
    if term.is_compound() or term.is_sequence():
        for child in term.arguments:
            for grandchild in iter_children(child):
                yield grandchild

class NoAnswerException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


class Designator(object):
    """A Designator defines a goal, which can be defined at runtime or at write-time.
    A Designator can hold a set of goals it can choose from and finally selects one, by calling self.next.
    After that goal is finished or cannot be finished, a next option can be selected again.
    """
    def __init__(self):
        super(Designator, self).__init__()

        self._current = None

    def resolve(self):
        """Selects a new goal and sets it as the current goal"""
        self._current = None
        raise NotImplementedError("No method for goal selection implemented")
        return self.current

    @property
    def current(self):
        """The currently selected goal"""
        return self._current


class ReasonedDesignator(Designator):
    """docstring for ReasonedPose2DDesignator"""
    def __init__(self, reasoner, query, identifier="Object", 
        sort=min, 
        key=lambda x: x, 
        _filter=lambda x: True):
        """A ReasonedDesignator can be used to refer to an object in the world model,
            whose identity, ID, is not yet known. 
        Each world-model object has an ID: the identifier-variable will be unified with an object's ID
        
        Use the reasoner to find answers to the given query.
        These answers are then filtered and finally sorted by the respective functions.
        The sort-function is passed the optional key-function, control the value being sorted with
        """
        
        super(ReasonedDesignator, self).__init__()
        
        self.query = query
        self.reasoner = reasoner
        self.sort = sort
        self.sortkey = key
        self.filter = _filter

        self.identifier = identifier

        self._decorated_query = query #This will be modified by the designator itself

        self.processed_identifiers = []

    def resolve(self):
        """Pose the query to the reasoner and filter, sort the answers, returning the best answer"""
        answers = self.reasoner.query(self._decorated_query)
        if not answers:
            raise NoAnswerException("No answer for query {0}".format(self._decorated_query))
        filtered = filter(self.filter, answers)
        if not filtered:
            raise NoAnswerException("No answers left for query {0} after filtering".format(self._decorated_query))
        self._current = self.sort(filtered, key=self.sortkey)
        return self.current

    def extend(self, conjunct, add_at_end=True):
        """Extend the current query with another conjunct.
        The new conjunct may also be inserted at the beginning of the query, 
        thereby setting a variable early during resolution thus needed less backtracking"""
        if add_at_end:
            self._decorated_query = Conjunction(self._decorated_query, conjunct)
        else:
            self._decorated_query = Conjunction(conjunct, self._decorated_query)


    def refine(self, **kwargs):
        """Set a variable in the query to a constant.
        >>> query = Compound("some_predicate", "Object", "B")
        >>> desig = ReasonedDesignator(None, query, "Object")
        >>> desig.refine(Object="specific_object")
        Compound(',', Compound('=', Variable('Object'), 'specific_object'), Compound('some_predicate', Variable('Object'), Variable('B')))
        """
        
        # for child in iter_children(self._decorated_query):
        #     if child.is_variable():
        #         if child.var_name == variable:
        #             child = constant
        # return self._decorated_query
        # should return Compound('some_predicate', 'specific_object', Variable('B'))
        #But, replacing items in a Term is not that easy.
        for variable, constant in kwargs.iteritems():
            self.extend(Compound("=", variable, constant), add_at_end=False)
        return self._decorated_query


class LockVariable(ReasonedDesignator):
    """A Mixin for ReasonedDesignators that allow them to lock a specific (set of) variable(s)"""

    def lock(self, variables):
        if not isinstance(variables, list): #if its not a list yet
            variables = [variables] #then make it one

        kwargs = {}
        for variable in variables:
            kwargs[variable] = self.current[variable]
        self.refine(**kwargs)


class ReasonedPose2DDesignator(LockVariable, ReasonedDesignator):
    """docstring for ReasonedPose2DDesignator"""
    def __init__(self, reasoner, query,
        X="X", Y="Y", Phi="Phi", identifier="Object",
        finished_marker='visited', blocked_marker='unreachable',
        **kwargs):
        
        super(ReasonedPose2DDesignator, self).__init__(reasoner, query, 
            identifier=identifier,
            **kwargs)

        self.X = X
        self.Y = Y
        self.Phi = Phi

    @property
    def current_as_pose(self):
        """The current answer interpreted as a PoseStamped"""
        return self.interpret_as_pose(self.current)

    def interpret_as_pose(self, dic):
        pose = msgs.PoseStamped(
                x   = float(dic[self.X]), 
                y   = float(dic[self.Y]), 
                phi = float(dic[self.Phi]))
        return pose


class ReasonedPointDesignator(LockVariable, ReasonedDesignator):
    """docstring for ReasonedPointDesignator"""
    def __init__(self, reasoner, query,
        X="X", Y="Y", Z="Z", identifier="Object",
        finished_marker='visited', blocked_marker='unreachable',
        **kwargs):
        
        super(ReasonedPointDesignator, self).__init__(reasoner, query, 
            identifier=identifier,
            **kwargs)

        self.X = X
        self.Y = Y
        self.Z = Z

    @property
    def current_as_point(self):
        """The current answer interpreted as a PoseStamped"""
        return self.interpret_as_point(self.current)

    def interpret_as_point(self, dic):
        point = msgs.PointStamped(
                x = float(dic[self.X]), 
                y = float(dic[self.Y]), 
                z = float(dic[self.Z]))
        return point

        
if __name__ == "__main__":
    import doctest
    doctest.testmod()

    rospy.init_node('Designator_test', log_level=rospy.INFO)

    import robot_skills.amigo
    robot = robot_skills.amigo.Amigo(dontInclude=["arms", "head", "perception", "spindle","speech","leftArm","rightArm","ears","ebutton","lights"])

    r = robot.reasoner

    #r.query(r.load_database("tue_knowledge", 'prolog/locations.pl'))
    #r.assertz(r.challenge("clean_up"))
    import math

    r.assertz(r.waypoint("a", r.pose_2d(1, 2, 1.57)))
    r.assertz(r.waypoint("b", r.pose_2d(2, 3, 2.25)))
    r.assertz(r.waypoint("c", r.pose_2d(3, 4, math.pi)))

    r.assertz(r.point_of_interest("a", r.point_3d(1, 2, 4)))
    r.assertz(r.point_of_interest("b", r.point_3d(2, 3, 5)))
    r.assertz(r.point_of_interest("c", r.point_3d(3, 4, 6)))

    r.assertz(r.pos("firstObject",      r.point_3d(1.1, 2.1, 4.1))) #closest to poi a
    r.assertz(r.pos("anotherObject",    r.point_3d(1.2, 2.2, 4.2))) #further to poi a
    r.assertz(r.pos("someObject",       r.point_3d(1.3, 2.3, 4.3))) #even further to poi a

    pose_query = r.waypoint("Name", r.pose_2d("X", "Y", "Phi"))
    roi_query = r.point_of_interest("Name", r.point_3d("X", "Y", "Z"))

    rpd = ReasonedPose2DDesignator(robot.reasoner, pose_query, identifier="Name")
    rrd = ReasonedPointDesignator(robot.reasoner, roi_query, identifier="Name")

    #import ipdb; ipdb.set_trace()
    answer1 = rpd.resolve() #This basically just takes one (the first), because the sort key is not defined in any meaningful way
    rpd.refine(Name='c') #We refine the designator
    answer2 = rpd.resolve() #And let designator resolve itself to include the refinemen to Name=c
    assert answer1 != answer2 and len(answer1) == len(answer2) #The answers should not be the same, but they should have the same (amount of) keys
    assert str(answer2["Name"]) == 'c' #As we refined rpd to have Name=c, the answer after refinement should include this

    assert rpd.current_as_pose.pose.position.x == 3.0 and rpd.current_as_pose.pose.position.y == 4.0

    def LookForObjectAtROI(lookat_designator, object_designator):
        look_at = lookat_designator.resolve()
        print "Looking at {0}".format(look_at)

        best_found_object = object_designator.resolve()
        print "I found {0}".format(best_found_object)

        object_designator.lock("Name") #Lock the designator to the current value of Name

    def PointStamped_distance(a, b):
        dx = a.point.x - b.point.x
        dy = a.point.y - b.point.y
        dz = a.point.z - b.point.z
        return math.sqrt(dx**2 + dy**2 + dz**2)

    object_query = r.pos("Name", r.point_3d("X", "Y", "Z"))

    lookat_designator = ReasonedPointDesignator(robot.reasoner, roi_query, identifier="Name")

    object_designator = ReasonedPointDesignator(robot.reasoner, object_query, identifier="Name", sort=max)


    def sortkey(dic):
        as_point = object_designator.interpret_as_point(dic)
        return PointStamped_distance(lookat_designator.current_as_point, as_point)
    object_designator.sortkey = sortkey

    LookForObjectAtROI(lookat_designator, object_designator)
    #object_designator is now linked to a very specific object
    #import ipdb; ipdb.set_trace()
    resolution = object_designator.resolve()
    print resolution
    assert str(resolution["Name"]) == "someObject"

    #print "cleaning up..."
    r.query(r.retractall(r.visited("X")))
    r.query(r.retractall(r.unreachable("X")))

    r.query(r.retractall(r.waypoint("X", "Y")))
    r.query(r.retractall(r.point_of_interest("X", "Y")))
    r.query(r.retractall(r.pos("X", "Y")))
    #print "Done"
