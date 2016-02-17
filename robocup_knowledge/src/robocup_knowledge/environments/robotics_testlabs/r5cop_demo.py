starting_point = "initial_pose"

# required keys: entity_id (str), room_id (str), navigation_area (str), segment_areas (list)
inspection_places = [
    {"entity_id": "dinnertable",
     "room_id": "living_room",
     "navigate_area": "near",
     "segment_areas": ["under", "on_top_of"]},

    {"entity_id": "cabinet",
     "room_id": "kitchen",
     "navigate_area": "near",
     "segment_areas": ["on_top_of"]},
]

known_types = ["coke", "fanta", "mentos", "bifrutas"]
