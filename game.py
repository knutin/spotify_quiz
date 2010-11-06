"""
Game logic
"""
from conf import *

import operator
import random
import sys
import string
import time

from twisted.internet import reactor
from twisted.python import log

class Game(object):
	"""
	Game controller
	
	A game has players and rounds. The game will start when there is enough
	players and will end if too many players leave.
	
	When a round starts, a track is randomly selected from the available
	catalogue of tracks. A list of alternatives is generated and sent to all
	clients, together with the track to play.
	
	At the end of each round, scores are calculated and sent to the clients.
	At this time the intermission starts. The intermission does nothing
	useful, it serves only as a pause between rounds for the players and as a
	state to wait in when a round cannot yet start. This is the initial state.
	
	"""
	def __init__(self, identification):
		self.id          = identification
		self.clients     = []
		self.waiting     = [] # waiting clients that will join in next round
		self.users       = {} # client -> username
		                 
		self.score       = [] # (username, points)
		self.round       = 0

		self.used_tracks = [] # Songs that we have played in this game. Do not use these again.
		self.all_tracks  = [] # Available songs. Use this for games with a certain theme.

		self.is_running  = False # True when a round is in progress, False in intermission
		self.choices     = [] # [(key, song title)]
		self.answers     = [] # [(username, answer)]
		                 
		self.callbacks   = [] # twisted callbacks
		
		# Go to initial state
		self.intermission()
	
	def __str__(self):
		return u"Game #%s" % self.id
	
	def log(self, msg):
		l = u"%s: %s" % (str(self), msg)
		log.msg(l.encode('latin-1', 'ignore'))
	
	def add_client(self, client, args):
		"""
		Adds client to game. If a game is running, the client must wait until next round.
		"""
		if self.is_full():
			return False
		
		self.users[client] = args['username']

		if self.is_running:
			self.waiting.append(client)
			self.log("Round is running. %s must wait until next round starts." % args['username'])
		else:
			self.clients.append(client)
			if self.can_start():
				self.start_round()
		
		return True
	
	def remove_client(self, client):
		"""
		Removes client from the game. May even end the current round.
		"""
		self.clients.remove(client)
		username = self.users[client]
		del self.users[client]
		
		self.score = filter(lambda score: score[0] != username, self.score)
		
		if not self.enough_players() and self.is_running:
			self.log('Round #%d: Ended because %s left' % (self.round, username))
			self.end_round()
		
	def add_tracks(self, client, args):
		# Sanity check of the format
		for spotify_uri, artist, title in args['tracks']:
			if not (spotify_uri, artist, title) in self.all_tracks:
				self.all_tracks.append((spotify_uri, artist, title))


	def can_start(self):
		"""Returns True if we have enough players and tracks"""
		return self.enough_players() and self.enough_tracks() and not self.is_running
		
	def enough_players(self):
		return len(self.clients) >= MIN_PLAYERS
	
	def enough_tracks(self):
		return len(self.all_tracks) >= NUMBER_OF_ALTERNATIVES
	
	def is_full(self):
		return len(self.clients) + len(self.waiting) >= MAX_PLAYERS

	def start_round(self):
		"""
		Start a new round:
		 * Select track
		 * Create choices
		 * Notify clients that we start the new round
		
		If it is not possible to start a new round, transition to intermission
		"""
		assert not self.is_running, "Tried to start a new round, but we are already running"
		
		if not self.can_start():
			return self.intermission()
		
		self.cancel_intermission()
		
		self.round += 1
		self.join_players()
		
		self.log(u"Starting round %d with %d players and %d tracks" % (self.round, len(self.clients), len(self.available_tracks())))
		self.is_running = True
		
		track = self.select_track()
		self.used_tracks.append(track)
		self.choices = self.generate_choices(track)
		
		for i, t in enumerate(self.choices):
			if track == t:
				self.correct_answer = i

		self.log(u"Playing '%s - %s'. Correct answer: %d" % (track[1].decode('utf-8'), track[2].decode('utf-8'), self.correct_answer))
		
		d = { 
			'action': 'start_round', 
			'spotify_uri': track[0], 
			'choices': self.choices,
			'round': self.round
		}
		self.notify_clients(d)

		self.callbacks.append(reactor.callLater(ROUND_TIME, self.round_timedout))
	
	def end_round(self):
		"""
		End an ongoing round. This is called either when all clients has answered or time runs out.
		"""
		self.is_running = False

		self.stop_callbacks()
		
		# Sort answers by time. answer = (username, answer, time)
		answers = sorted(self.answers, key = operator.itemgetter(2))
		self.answers = []		
		# Find all correct answers.
		correct_answers = filter(lambda a: a[1] == self.correct_answer, answers)
		
		winner = None
		for username, _, time in correct_answers:
			if not winner:
				winner = username
			self.score.append((username, self.time_to_points(time)))
		
		self.notify_clients({'action': 'end_round', 'winner': winner, 'score': self.score})
		self.log("Round #%d ended. Winner is %s" % (self.round, winner))
		
		self.intermission()
	
	def intermission(self, timeout = None):
		"""
		Intermission between rounds. If there are not enough players, 
		we will linger here until we have enough players.
		"""
		if not timeout:
			timeout = INTERMISSION_TIMEOUT
		
		self.notify_clients({
			'action': 'intermission', 
			'timeout': timeout, 
			# If we are waiting for players to join, notify all clients 
			# of this fact so they can tell their friends to start playing.			
			'enough_players': self.enough_players(),
			'enough_tracks': self.enough_tracks()
		})
		self.stop_callbacks()
		self.callbacks.append(reactor.callLater(timeout, self.start_round))
	
	def cancel_intermission(self):
		self.stop_callbacks()
	
	def stop_callbacks(self):
		"""Stops any pending Twisted callbacks, such as timeouts"""
		[c.cancel() for c in self.callbacks if c.active()]		
	
	def select_track(self):
		"""Selects a random track from the list of available tracks."""
		return random.choice(list(self.available_tracks()))
	
	def available_tracks(self):
		# TODO: Property
		assert len(self.all_tracks), "no tracks"
		
		tracks = set(self.all_tracks) - set(self.used_tracks)
		
		# If we have used all tracks, or don't have enough for generating alternatives, start over
		if not tracks or len(tracks) < NUMBER_OF_ALTERNATIVES:
			self.used_tracks = []
			return self.available_tracks()
		
		return tracks
	
	def generate_choices(self, track):
		"""Returns a list of tracks in random order. The list includes the correct answer."""
		assert len(self.available_tracks()) >= NUMBER_OF_ALTERNATIVES, "Running out of tracks. Crashing..."
		
		tracks = [track]
		i = 0
		while True:
			if len(tracks) == NUMBER_OF_ALTERNATIVES:
				break
			
			track = random.choice(list(self.available_tracks()))
			if track in tracks:
				continue
			
			# We don't want the same artist twice
			if filter(lambda t: t[1] == track[1], tracks):
				continue
			
			tracks.append(track)
		
		random.shuffle(tracks)
		return tracks
	
	def time_to_points(self, time):
		"""
		Returns points in integer for given time to anser
		
		Answer in 0-1 seconds: POINTS[0]
		Answer in 1-2 seconds: POINTS[1]
		Etc..
		"""
		time = int(time)
		if time > len(POINTS):
			return 0

		return POINTS[time]
	
	def round_timedout(self):
		"""Called when a round times out waiting for answers"""
		self.log("Round #%d: Ended due to timeout" % self.round)
		self.end_round()
	
	def join_players(self):
		"""Let waiting players join the netx round"""
		self.clients = self.clients + self.waiting
		self.waiting = []

	def received_answer(self, client, args):
		if not self.is_running:
			return

		username = self.users[client]
		answer   = args['answer']
		time     = args['time']
		
		# If this user has already answered, do nothing
		if filter(lambda a: a[0] == username, self.answers):
			return None
		
		self.answers.append((username, answer, time))
	
		if len(self.answers) == len(self.clients):
			self.log("%s answered %s. Received all answers, ending round." % (username, answer))
			self.end_round()
		else:
			self.log("%s answered %s. Waiting for %d clients to answer." % (username, answer, len(self.clients) - len(self.answers)))

	def notify_clients(self, d):
		"""Sends the Python object d to all clients"""
		for client in self.clients:
			client.send(d)
