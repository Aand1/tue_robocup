cabinet = "right_bookcase"
table1  = "dinnertable"
table2  = "counter"
table3  = "desk"
object_shelves=["right_bookcase/shelf3","right_bookcase/shelf4","right_bookcase/shelf5"]

objects = ["coke", "fanta", "beer"]

#spec find a person and talk with
spec = "( (on|in|at) the <location> ((there is)|(you can find)|(you saw)) <object1> | (on|in|at) the <location> ((there is)|(you can find)|(you saw)) <object1> and <object2> | (on|in|at) the <location> ((there is)|(you can find)|(you saw)) <object1>, <object2> and <object3> ) "

choices = {'location':[table1, table2, table3],
'object1':objects,
'object2':objects,
'object3':objects}