#! /usr/bin/env python
"""
Introspection for designators.
Usage: pass a Smach state-machine to analyse_designators.

A .dot and .png will be saved to the current directory, showing the relations and composition of states,
state_machines and designators.
"""

import os
import smach
from robot_smach_states.util.designators.core import Designator, VariableWriter


__author__ = 'loy'


class DesignatorUsage(object):
    def __init__(self, parent, designator, role):
        self.parent = parent
        self.designator = designator
        self.role = role


class DesignatorUsedInState(DesignatorUsage):
    def add_graphviz_edge(self, graph):
        desig_name = format_designator(self.designator)

        graph.node(gv_safe(self.parent), shape="box", color="bisque", style="filled")

        graph.edge(gv_safe(desig_name),
                   gv_safe(self.parent),
                   label=gv_safe("{}.resolve".format(self.role)),
                   color="green")

class DesignatorWrittenInState(DesignatorUsage):
    def add_graphviz_edge(self, graph):
        writer_name = format_designator(self.designator)
        variable_name = format_designator(self.designator.variable_designator)

        # graph.edge(gv_safe(self.parent),
        #            gv_safe(variable_name),
        #            label=gv_safe("sets {}".format(self.role)),
        #            color="red")

        graph.edge(gv_safe(self.parent),
                   gv_safe(variable_name),
                   label=gv_safe("write {}".format(self.role)),
                   color="red")

        graph.edge(gv_safe(variable_name),
                   gv_safe(self.parent),
                   gv_safe("{}.resolve".format(self.role)),
                   color="green")


class DesignatorUsedInDesignator(DesignatorUsage):
    def add_graphviz_edge(self, graph):
        parent_name = format_designator(self.parent)
        desig_name = format_designator(self.designator)

        graph.edge(gv_safe(desig_name),
                   gv_safe(parent_name),
                   gv_safe("{}.resolve".format(self.role)),
                   color="darkgreen",
                   style="solid")


def gv_safe(string):
    return str(string).replace("=", "_")


def format_designator(desig):
    resolve_type_format = desig.resolve_type
    if type(desig.resolve_type) == list or type(desig.resolve_type) == tuple:
        try:
            if len(desig.resolve_type) >= 1:
                # If the resolve_type is a collection, then show the type of the collection elements
                resolve_type_format = "[{}]".format(desig.resolve_type[0])
        except TypeError:
            pass
    else:
        resolve_type_format = desig.resolve_type.__name__

    desig_name = "{name}({cls}@{addr})\\n<{resolve_type}>".format(name=desig.name + " " if desig.name else "",
                                                                 cls=desig.__class__.__name__,
                                                                 addr=hex(id(desig)),
                                                                 resolve_type=resolve_type_format)
    return desig_name


def flatten(tree, parentname=None, sep="."):
    flat = []
    for branch_name, branch in tree.get_children().iteritems():
        this_name = parentname + sep + branch_name if parentname else branch_name
        if isinstance(branch, smach.StateMachine) or isinstance(branch, smach.Iterator):
            flat += [(this_name, branch)]
            flat.extend(flatten(branch, parentname=this_name, sep=sep))
        else:
            flat += [(this_name, branch)]
    return flat


def analyse_designators(statemachine=None, statemachine_name="", save_dot=False, fmt="png"):
    designators = Designator.instances
    writers = VariableWriter.instances

    if not statemachine:
        statemachine = smach.StateMachine._currently_opened_container()
    label2state = dict(flatten(statemachine, sep="\\n."))
    states = label2state.values()

    state2label = {state: label for label, state in label2state.iteritems()}

    usages = []

    for state in states:
        state_label = state2label.get(state, state)  # Get the label of state but default to ugly __repr__
        for designator_role, designator in state.__dict__.iteritems():  # Iterate the self.xxx members of each state
            # If the member is also a designator, then process it.
            if designator in designators:
                usages += [DesignatorUsedInState(state_label, designator, designator_role)]

            if designator in writers:
                usages += [DesignatorWrittenInState(state_label, designator, designator_role)]


    for parent_designator in designators:
        # Iterate the self.xxx members of each designator
        for child_role, child_designator in parent_designator.__dict__.iteritems():
            # If the member is also a designator, then process it.
            if child_designator in designators:
                usages += [DesignatorUsedInDesignator(parent_designator, child_designator, child_role)]

    from graphviz import Digraph
    dot = Digraph(comment=statemachine_name + ' Designators', format=fmt)

    for usage in usages:
        usage.add_graphviz_edge(dot)

    if save_dot:
        dot.save(statemachine_name + '_designators.dot')
    dot.render(statemachine_name + '_designators')

    os.remove(statemachine_name + '_designators')