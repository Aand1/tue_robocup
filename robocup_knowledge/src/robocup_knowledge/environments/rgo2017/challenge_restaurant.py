# TU/e Robotics
from robocup_knowledge import knowledge_loader

# Common knowledge
common = knowledge_loader.load_knowledge("common")

order_grammar = """
O[P] -> can i have a ORDER[P] | i would like ORDER[P] | can i have ORDER[P] | i would like ORDER[P]
ORDER[OO] -> COMBO[OO] | BEVERAGE[OO]
BEVERAGE[{"beverage": B}] -> BEV[B]
COMBO[{"food1": F1, "food2": F2}] -> FOOD[F1] and FOOD[F2] | FOOD[F1] with FOOD[F2]
"""

# Add drinks
for d in common.objects:
    if d["category"] == "drink":
        order_grammar += "\nBEV['{}'] -> {}[B]".format(d["name"], d["name"].replace('_', ' '))
    elif d["category"] == "food":
        order_grammar += "\nFOOD['{}'] -> {}".format(d["name"], d["name"].replace('_', ' '))

if __name__ == "__main__":
    import rospy
    from robot_skills.api import Api
    rospy.init_node('blaat')
    a = Api("", None)
    rospy.sleep(rospy.Duration(0.5))
    while True:
        result = a.query("blaat", order_grammar, "O")
        import ipdb;ipdb.set_trace()
