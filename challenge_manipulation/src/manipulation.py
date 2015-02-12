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

from robot_smach_states.util.designators import Designator, ArmHoldingEntityDesignator, UnoccupiedArmDesignator, EdEntityDesignator
import robot_smach_states as states
from robot_smach_states.util.startup import startup
from robot_smach_states import Grab
from robot_smach_states import Place
from robot_skills.util import msg_constructors as gm

import pdf

class FormattedSentenceDesignator(Designator):
    """docstring for FormattedSentenceDesignator"""
    def __init__(self, fmt, **kwargs):
        super(FormattedSentenceDesignator, self).__init__()
        self.fmt = fmt
        self.kwargs = kwargs
    
    def resolve():
        kwargs_resolved = {key:value.resolve() for key,value in self.kwargs.iteritems()}
        return self.fmt.format(**kwargs_resolved)


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
        smach.StateMachine.__init__(self, outcomes=['succeeded','failed'])

        bookcase = EdEntityDesignator(robot, type="plastic_cabinet")  #TODO: Get the entityID of the bookcase

        current_item = Designator(manipulated_items)  # TODO: Some item to grasp from the bookcase that is _not_ already placed or on the placement-shelve.
        place_position = Designator(gm.PoseStamped(x=0, y=0, z=0.8, frame_id="/plastic_cabinet"))  # TODO: Designates an empty spot on the empty placement-shelve. 
        empty_arm_designator = UnoccupiedArmDesignator(robot.arms, robot.leftArm)
        arm_with_item_designator = ArmHoldingEntityDesignator(robot.arms, current_item)

        print "{0} = bookcase".format(bookcase)
        print "{0} = current_item".format(current_item)
        print "{0} = place_position".format(place_position)
        print "{0} = empty_arm_designator".format(empty_arm_designator)
        print "{0} = arm_with_item_designator".format(arm_with_item_designator)

        with self:
            smach.StateMachine.add( "NAV_TO_OBSERVE_BOOKCASE",
                                    states.NavigateToObserve(robot, bookcase),
                                    transitions={   'arrived'           :'LOOKAT_BOOKCASE',
                                                    'unreachable'       :'LOOKAT_BOOKCASE',
                                                    'goal_not_defined'  :'LOOKAT_BOOKCASE'})

            smach.StateMachine.add( "LOOKAT_BOOKCASE",
                                    states.Say(robot, ["I'm looking at the bookcase to see what items I can find"]),
                                    transitions={   'spoken'            :'GRAB_ITEM'})

            smach.StateMachine.add( "GRAB_ITEM",
                                    Grab(robot, current_item, empty_arm_designator),
                                    transitions={   'done'              :'STORE_ITEM',
                                                    'failed'            :'SAY_GRAB_FAILED'})

            smach.StateMachine.add( "SAY_GRAB_FAILED",
                                    states.Say(robot, ["I couldn't grab this thing"], mood="sad"),
                                    transitions={   'spoken'            :'failed'}) # should be NAV_TO_OBSERVE_BOOKCASE but thats makes an infinite loop

            @smach.cb_interface(outcomes=['stored'])
            def store(userdata):
                import ipdb; ipdb.set_trace()
                manipulated_items.current += [current_item.current]
                return 'stored'

            smach.StateMachine.add('STORE_ITEM',
                                   smach.CBState(store),
                                   transitions={'stored':'ANNOUNCE_CLASS'})

            smach.StateMachine.add( "ANNOUNCE_CLASS",
                                    states.Say(robot, FormattedSentenceDesignator("This is a {item.type}.", item=current_item), block=False),
                                    transitions={   'spoken'            :'PLACE_ITEM'})

            smach.StateMachine.add( "PLACE_ITEM",
                                    Place(robot, current_item, place_position, arm_with_item_designator),
                                    transitions={   'done'              :'succeeded',
                                                    'failed'            :'SAY_HANDOVER_TO_HUMAN'})

            smach.StateMachine.add( "SAY_HANDOVER_TO_HUMAN",
                                    states.Say(robot, ["I'm can't get rid of this item  myself, can somebody help me maybe?"]),
                                    transitions={   'spoken'            :'HANDOVER_TO_HUMAN'})
    
            smach.StateMachine.add( "HANDOVER_TO_HUMAN",
                                    states.HandoverToHuman("left", robot),  # TODO: Use arm_designator for arm
                                    transitions={   'succeeded'         :'succeeded',
                                                    'failed'            :'failed'})


def setup_statemachine(robot):

    sm = smach.StateMachine(outcomes=['Done', 'Aborted'])
    start_waypoint = EdEntityDesignator(robot, id="living_room")  # TODO: select proper waypoint
    placed_items = []

    with sm:

        # Start challenge via StartChallengeRobust
        smach.StateMachine.add("AWAIT_START",
                               states.AskContinue(robot),
                               transitions={'continue'                  :'NAV_TO_START',
                                            'no_response'               :'AWAIT_START'})

        smach.StateMachine.add("NAV_TO_START",
                                states.NavigateToWaypoint(robot, start_waypoint),
                                transitions={'arrived'                  :'RANGE_ITERATOR',
                                             'unreachable'              :'RANGE_ITERATOR',
                                             'goal_not_defined'         :'RANGE_ITERATOR'})

        # Begin setup iterator
        range_iterator = smach.Iterator(    outcomes = ['succeeded','failed'], #Outcomes of the iterator state
                                            input_keys=[], output_keys=[],
                                            it = lambda: range(5),
                                            it_label = 'index',
                                            exhausted_outcome = 'succeeded') #The exhausted argument should be set to the preffered state machine outcome

        with range_iterator:
            single_item = ManipRecogSingleItem(robot, placed_items)

            smach.Iterator.set_contained_state( 'SINGLE_ITEM', 
                                                single_item, 
                                                loop_outcomes=['succeeded','failed'])

        smach.StateMachine.add('RANGE_ITERATOR', range_iterator,
                        {   'succeeded'                                     :'EXPORT_PDF',
                            'failed'                                        :'Aborted'})
        # End setup iterator

        @smach.cb_interface(outcomes=["exported"])
        def export_to_pdf(userdata):
            pdf.items2markdown(placed_items)
            return "exported"
        smach.StateMachine.add('EXPORT_PDF',
                                smach.CBState(export_to_pdf),
                                transitions={'exported':'AT_END'})

        smach.StateMachine.add('AT_END',
                               states.Say(robot, "Goodbye"),
                               transitions={'spoken': 'Done'})
    return sm


############################## initializing program ######################
if __name__ == '__main__':
    rospy.init_node('manipulation_exec')

    if len(sys.argv) > 1:
        robot_name = sys.argv[1]
    else:
        print "[CHALLENGE MANIPULATION] Please provide robot name as argument."
        exit(1)

    startup(setup_statemachine, robot_name=robot_name)
