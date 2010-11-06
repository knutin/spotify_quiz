import threading

from spotify.manager import SpotifySessionManager
from spotify import Link, SpotifyError

try:
    from spotify.alsahelper import AlsaController
except ImportError:
    from spotify.osshelper import OssController as AlsaController


class SpotifySession(SpotifySessionManager, threading.Thread):
	def __init__(self, *args, **kwargs):
		threading.Thread.__init__(self)
		SpotifySessionManager.__init__(self, *args, **kwargs)

		self.audio = AlsaController()
		self.playing = False
		self.loaded_tracks = []
		self.start()
		
	def run(self):
		self.connect()
	
	def logged_in(self, session, error):
		if error:
			# TODO: Halt the client
			print 'sp_error: ', error

		self.session = session
	
	def is_loaded(self):
		return getattr(self, 'session', False)

	def metadata_updated(self, session):
		"""
		Store all loaded tracks in self.loaded_tracks so we can 
		supply them to the server.
		
		Called when libspotify has new metadata.
		"""
		self.playlist_container = session.playlist_container()
		self.metadata_updated_callback(self)

	def load_track(self, track):
		if self.playing:
			self.stop()

		# If spotify has not yet been initialized, wait a second and try again
		if not self.is_loaded():
			return False
		
		link = Link.from_string(track)
		assert link.type() == Link.LINK_TRACK
		
		try:
			self.session.load(link.as_track())
		except SpotifyError:
			return False

		return True
	
	def load_cover(self, link, callback, userdata):
		track = Link.from_string(link).as_track()
		
		covid = track.album().cover()
		if covid:
			img = self.session.image_create(covid)
			if img.is_loaded():
				callback(img, userdata)
			else:
				img.add_load_callback(callback, userdata)
		
	def play(self):
		self.session.play(1)
		self.playing = True
	
	def stop(self):
		self.session.play(0)
		self.playing = False
	
	def music_delivery(self, *args, **kwargs):
		return self.audio.music_delivery(*args, **kwargs)
