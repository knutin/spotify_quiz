#!/usr/bin/env python
# encoding: utf-8
"""
Spotify Quiz Client

Spotify Quiz is a small game where the players guess what track is currently
playing.

The client uses Twisted and pickled python objects are used as messages between
client and server. Using Twisted in this way is not robust or safe, but it
serves it's purpose.

The GUI is written in Pygame.

Dependencies:
 * Twisted
 * pyspotify with alsahelper/osshelper
 * Pygame

Known issues:
 * Sometimes Spotify takes some time before album covers are available.
   The game will continue without this, but it may make it impossible to
   select the correct alternative.
 * C-c during startup might send the KeyboardInterrupt to SpotifySession, 
   which will ignore it.

Usage:
 python client.py ip.of.server port

If you want to run a "dumb" client that has no GUI and plays no music:
 python client.py ip.of.server port 0

"""

import gui
import spotifysession

import getpass
import pickle
import random
import sys
import time

from spotify import Link

from twisted.internet import protocol, stdio
from twisted.protocols import basic
from twisted.internet import reactor


# Set to True if you want the client to actually play music.
# Set to False if you want to run multiple clients with the same Spotify account.
PLAY_MUSIC = True

# Set to True if you want to use the GUI.
# If False, the client will be participating in games, but not able to respond.
DISPLAY_GUI = True

class Client(object):
	def __init__(self, username):
		self.username = username
		self.running  = False
		
		# Internal bookkeeping
		self.sent_tracks   = []
		self.loaded_tracks = []

	def set_connection(self, connection):
		self.connection = connection
	
	def run(self):
		self.connect()
		
	def connect(self):
		"""
		Connect to the server and start playing a new game.
		Send any tracks that has been loaded this far.
		"""
		d = {
			'action': 'connect',
			'username': self.username
		}
		self.connection.sendLine(pickle.dumps(d))
		print 'Connected. Waiting for game to start...'
		self.send_tracks()
	
	def metadata_updated_callback(self, spotify):
		"""
		Called from libspotify when there are updates to playlists and tracks.
		"""
		for playlist in spotify.playlist_container:
			if playlist.is_loaded():
				for track in playlist:
					if track.is_loaded() and not track in self.loaded_tracks:
						self.loaded_tracks.append(track)
	
	def send_tracks(self):
		"""
		Send tracks that hasn't already been sent.
		"""
		tracks = set(self.loaded_tracks) - set(self.sent_tracks)
		tracks = list(tracks)

		tracks = [(unicode(Link.from_track(t, 0)), str(t.artists()[0]), t.name()) for t in tracks]
		# Rate limit
		tracks = tracks[:50]

		d = { 
			'action': 'add_tracks',
			'tracks': tracks
		}
		self.connection.sendLine(pickle.dumps(d))
		self.sent_tracks += tracks

	def load_track(self, link):
		if PLAY_MUSIC:
			return self.connection.factory.session.load_track(link)
		
		return True
	
	def start_playback(self):
		if PLAY_MUSIC:
			return self.connection.factory.session.play()
		
		return True
		
	def stop_playback(self):
		if PLAY_MUSIC:
			return self.connection.factory.session.stop()
		
		return True
	
	def load_cover(self, uri, load_callback, userdata):
		if PLAY_MUSIC:
			return self.connection.factory.session.load_cover(uri, load_callback, userdata)
		
		return True
	
	def clear_covers(self):
		if DISPLAY_GUI:
			return self.ui.clear_covers()

		return True

	def start_round(self, args):
		"""
		Called when a new round starts.
		 * Load the track
		 * Start timer, start playback
		 * Wait for answer
		"""
		if not self.load_track(args['spotify_uri']):
			self.ui.load_failed()
			return
		
		self.ui.clear_state()
		
		# Load album art
		for i, (uri, artist, title) in enumerate(args['choices']):
			self.load_cover(uri, self.ui.add_cover, (i, self.answer))

		self.running = True
		self.start = time.time()
		self.start_playback()
		print u"Round started."
	
	def end_round(self, args):
		"""
		Called when a round ends. If we are not participating, do nothing.
		"""
		if not self.running:
			return
		
		self.stop_playback()
		self.clear_covers()
		self.running = False
		
		total_score = sum(score for username, score in args['score'] if username == self.username)
		
		if DISPLAY_GUI:
			self.ui.set_score(total_score)
			if(args['winner'] == self.username):
				self.ui.winner()
			else:
				self.ui.loser()
		print u"Round ended. Winner is %s"  % args['winner']
		
	def intermission(self, args):
		"""
		Called whenever the server feels like notifying us that we are in 
		the intermission.
		"""
		if not args['enough_tracks']:
			if DISPLAY_GUI:
				self.ui.waiting_for_tracks()
			print u"Waiting for tracks to load..."
		elif not args['enough_players']:
			if DISPLAY_GUI:
				self.ui.waiting_for_players()
			print u"Waiting for players to join.."
		else:
			if DISPLAY_GUI:
				self.ui.intermission()
			print u"Next round will start in %d seconds" % args['timeout']
	
	def answer(self, key):
		"""Handles answers received from the GUI"""
		stop = time.time()

		answer = {
			'action': 'answer',
			'answer': key,
			'time': stop - self.start
		}
		self.connection.sendLine(pickle.dumps(answer))

	def handle_action(self, line):
		"""Dispatch action to method"""
		args = pickle.loads(line)
		action = args.pop('action')
		
		if action in ('start_round', 'end_round', 'answer', 'intermission'):
			getattr(self, action)(args)
	
class QuizClientReceiver(basic.LineReceiver):
	def connectionMade(self):
		self.factory.client.set_connection(self)
		self.factory.client.run()
	
	def lineReceived(self, line):
		self.factory.client.handle_action(line)

class QuizClientFactory(protocol.ClientFactory):
	protocol = QuizClientReceiver

	def clientConnectionFailed(self, connector, reason):
		reactor.stop()

	def clientConnectionLost(self, connector, reason):
		reactor.stop()


def main(username, password):
	client = Client(username)

	client.ui = gui.Gui()
	if DISPLAY_GUI:
		client.ui.setup()
		reactor.callLater(0.1, client.ui.tick)

	# Connect to Spotify
	session = spotifysession.SpotifySession(username, password)
	session.metadata_updated_callback = client.metadata_updated_callback
	print "Waiting for Spotify.."
		
	# Give libspotify some time to load, so we don't start doing stuff without
	# spotify available. Please don't C-c during the sleep...
	# A real solution would start the game when we know that Spotify has loaded.p
	time.sleep(6)

	factory = QuizClientFactory()
	factory.client  = client
	factory.session = session
	reactor.connectTCP(sys.argv[1], int(sys.argv[2]), factory)
	reactor.run()	

	session.terminate()
	

if __name__ == '__main__':
	print u"""
 SSS  PPPP   OOO  TTTTTT III FFFF Y   Y      QQQ   U   U III ZZZZZ 
S     P   P O   O   TT    I  F     Y Y      Q   Q  U   U  I     Z  
 SSS  PPPP  O   O   TT    I  FFF    Y       Q   Q  U   U  I    Z   
    S P     O   O   TT    I  F      Y       Q  QQ  U   U  I   Z    
SSSS  P      OOO    TT   III F      Y        QQQQ   UUU  III ZZZZZ 
                                                 Q
	"""
	if len(sys.argv) < 3:
		print >> sys.stderr, u"""
Usage:
 python client.py ip.of.server port

If you don't want a GUI or any music to play:
 python client.py ip.of.server port 0		
"""
		sys.exit(1)
	
	
	if len(sys.argv) == 4 and sys.argv[3] == '0':
		PLAY_MUSIC  = False
		DISPLAY_GUI = False

	username = raw_input("Spotify username: ")
	password = getpass.getpass(prompt = "Spotify password: ")

	main(username, password)
