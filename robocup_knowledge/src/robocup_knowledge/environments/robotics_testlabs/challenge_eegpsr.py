from robocup_knowledge import knowledge_loader
common = knowledge_loader.load_knowledge("common")

initial_pose = "initial_pose_door_B"  # initial pose
starting_pose = "eegpsr_starting_pose"  # Designated pose to wait for commands
exit_waypoint = "exit_door_B1"

rooms = common.rooms + ["entrance", "exit"]

translations = { "bookcase" : "bocase" }