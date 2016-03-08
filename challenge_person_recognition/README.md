# Responsible: Loy

amigo1/sergio1:

    - astart/sstart # (if not already running)

amigo2/sergio1:

    - ahardware/shardware: base, spindle, arms, head

amigo1/sergio1:

    - amiddle/smiddle

amigo3:

    - The robot has to be positioned in the correct location before starting the executive! Place him at the entrance of the living room, facing backwards to it.

    - rosrun challenge_person_recognition person_recognition.py [robot_name]
        - optional, test specific container: rosrun challenge_person_recognition person_recognition.py [robot_name] [container name]


#--------------------------------------------------------------


During the challenge:
    - The robot will wait for the Operator to stand in front of him
    - After he sees someone in front, the robot will ask the person's name and learn his/her face
    - When the learning is complete the robot will ask the Operator to go to the living room and mix with the crowd, so go....
    - The robot will navigate between waypoints in the living room trying to find a crowd or at least a person
    - when he finishes visiting every person he will choose the most likely to be the operator and point at him
    - Finally the robot has to describe the crowd, saying how many males and females are present as well as their pose

#TODO