#!/usr/bin/env python
# encoding: utf-8
"""
Spotify Quiz Server

Spotify Quiz is a small game where the players guess what track is currently
playing.

The server uses Twisted and pickled python objects are used as messages between
client and server. Using Twisted in this way is not robust or safe, but it
serves it's purpose.

All clients that join will share all their tracks. The tracks used in the game
will be picked randomly from these tracks.

Dependencies:
 * Twisted

Usage:
 python server.py port

"""

import game
from conf import *

import pickle
import sys

from twisted.internet import reactor
from twisted.protocols import basic
from twisted.internet import protocol
from twisted.python import log


class Server(object):
	"""
	Game Master server.
	
	The Master is responsible for:
	 * Starting new Games when needed
	 * Removing old Games no longer in use
	"""
	def __init__(self):
		self.games = []
		self.clients = {} # client -> index into games list
	
	def add_client(self, client, args):
		"""
		Add client to an existing game or create a new game.
		"""
		available_games = filter(lambda g: not g.is_full(), self.games)
		
		if available_games:
			# Try to join all available games
			for g in available_games:
				game_id = self.join_game(g, client, args)
				if game_id != -1:
					break
		
		else:
			# If all games are full, start a new game and try the process all over again
			new_game = game.Game(self.get_next_game_id())
			self.games.append(new_game)
			log.msg("%s: Started new game." % new_game)

			return self.add_client(client, args)
	
	def join_game(self, game, client, args):
		"""Join client to game. Returns False if it was not possible to join, otherwise the id of the game."""
		if not game.add_client(client, args):
			return -1

		# Find the index of the game and set up the client -> game mapping
		i = self.games.index(game)
		self.clients[client] = i
		
		return i
	
	def get_next_game_id(self):
		return len(self.games)
	
	def client_disconnected(self, client):
		"""Client disconnected for some reason. Remove client from the game it was in."""
		game = self.games[self.clients[client]]
		game.remove_client(client)
		del self.clients[client]
	
	def received_answer(self, client, args):
		"""
		Called when an answer is received from the client
		"""
		game = self.games[self.clients[client]]
		game.received_answer(client, args)
	
	def add_tracks(self, client, args):
		"""
		Called from the client when Spotify starts loading tracks.
		The tracks should be added to the game specific list of tracks.
		"""
		game = self.games[self.clients[client]]
		game.add_tracks(client, args)
	
			
class Receiver(basic.LineReceiver):
	def connectionMade(self):
		self.factory.clients.append(self)

	def connectionLost(self, reason):
		self.factory.clients.remove(self)
		self.factory.server.client_disconnected(self)
	
	def send(self, d):
		return self.sendLine(pickle.dumps(d))
	
	def lineReceived(self, line):
		args = pickle.loads(line)
		action = args.pop('action')
		
		self.handle_client_command(action, args)
		
	def handle_client_command(self, action, args):
		# TODO: Use deferreds
		# Client is connecting for the first time.
		# Add client to existing or new game.
		if action == 'connect':
			self.factory.server.add_client(self, args)
		
		# Client is answering the quiz
		elif action == 'answer':
			self.factory.server.received_answer(self, args)
		
		elif action == 'add_tracks':
			self.factory.server.add_tracks(self, args)

		return True

if __name__ == '__main__':
	log.startLogging(sys.stdout)
	
	if len(sys.argv) < 2:
		print >> sys.stderr, u"""
Usage:
 python server.py port	
"""
		sys.exit(1)

	
	factory = protocol.ServerFactory()
	factory.protocol = Receiver
	factory.clients = []
	factory.server = Server()
	
	reactor.listenTCP(int(sys.argv[1]), factory)
	reactor.run()
	
