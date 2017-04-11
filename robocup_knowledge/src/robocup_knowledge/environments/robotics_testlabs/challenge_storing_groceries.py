# Entity where the shelves are part of
cabinet_amcl = "bookcase"

# Shelves where objects might be
# object_shelves = ["bookcase/shelf2", "bookcase/shelf3"]
object_shelves = ["shelf1", "shelf2", "shelf3", "shelf4", "shelf5"]

# Shelf where we will actually try to grasp
grasp_surface = "dinner_table"

# place_area = "shelf2"

# Room where everything will take place
room = "livingroom"

# Object types that can be recognized
object_types = ['beer', 'bifrutas', 'coffee_pads', 'coke',
                'deodorant', 'fanta', 'ice_tea', 'mentos',
                'sprite', 'tea', 'teddy_bear', 'water',
                'xylit24_spearmint', 'xylit24_white']

# Default place poses (only for testing)
default_place_entity = "bookcase"
default_place_area = "shelf3"

# # Minimum and maximum height from which to grab an object
# min_grasp_height = 0.0  # ToDo
# max_grasp_height = 1.5  # ToDo
