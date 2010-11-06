# Min and max players in a single game. 
# If a game is full, a new game is started automagically.
MIN_PLAYERS = 1
MAX_PLAYERS = 3

# Duration of every round. If not every client has answered within this time,
# the round will time out and the game will continue. Value is in seconds.
ROUND_TIME = 10

# Time between each rounds, in seconds
INTERMISSION_TIMEOUT = 3

# The number of alternative options in every round, 
# includes the correct answer. 
# Max: 26(limited by the alphabet), min: 1. 
NUMBER_OF_ALTERNATIVES = 4 

# Points are given based on how fast the client responds. 
# The time is measured on the client, so network lag is not 
# included in the score. It also makes it relatively easy to cheat.
POINTS = (89, 55, 34, 21, 13, 8, 5, 3, 2, 1)
