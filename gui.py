"""
Simple GUI
"""

import cStringIO
import string

from twisted.internet import reactor

import pygame
from pygame.locals import *

HEIGHT = 400
WIDTH  = 800

COVER_HEIGHT = 150
COVER_WIDTH  = 150

NUMBER_OF_COVERS = 4


class Cover(pygame.sprite.Sprite):
	"""
	Album Cover. Responds to key presses.
	"""
	def __init__(self, screen, img, index, callback):
		pygame.sprite.Sprite.__init__(self)
		self.screen = screen
		
		self.selected = False
		
		self.index = index
		# callback is called when this cover is clicked. 
		# It receives the index of this sprite as an argument
		self.callback = callback

		self.image = pygame.image.load(img).convert()
		self.image = pygame.transform.scale(self.image, (COVER_WIDTH, COVER_HEIGHT))

		self.rect = self.image.get_rect()
		self.rect.topleft = self.index_to_pos()
		
	
	def index_to_pos(self):
		cell = int(WIDTH / NUMBER_OF_COVERS)
		padding = cell - COVER_WIDTH
		return (self.index * cell) + int(padding / 2), 100
	
	def update(self):
		if self.selected:
			self.original = self.image
			center = self.rect.center
			self.selection = pygame.draw.rect(self.screen, (112, 202, 0), self.rect, 5)
			
	def remove_selection(self):
		if self.selected:
			pygame.draw.rect(self.screen, (255, 255, 255), self.rect, 5)
	
	def clear_if_not_selected(self):
		"""Clears the sprite, if it was not the selected sprite"""
		if not self.selected:
			pygame.draw.rect(self.screen, (255, 255, 255), self.rect, 0)
	
	def process_click(self, pos):
		hitbox = pygame.Rect(pos[0], pos[1], 1, 1)
		if hitbox.colliderect(self.rect):
			self.selected = True
			# Hopefully the callback won't take long...
			self.callback(self.index)

			return True
		
class Gui(object):
	def __init__(self):
		# Do nothing in init so we can be called without any side effects
		
		self.selected = False
		
		self.score = 0
		self.score_pos = None
		self.state_pos = None

	def setup(self):
		pygame.init()
		# Disable the mixer in order to avoid conflicts with pyspotify
		pygame.mixer.quit()		
	
		self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
		pygame.display.update()
		pygame.display.set_caption("Spotify Quiz")

		self.background = pygame.Surface(self.screen.get_size())
		self.background = self.background.convert()
		self.background.fill((255, 255, 255))
	
		font = pygame.font.Font(None, 64)
		title = font.render(u"Spotify Quiz", 1, (20, 20, 20))
		pos = title.get_rect(centerx = self.background.get_width() / 2)
		self.background.blit(title, pos)	
		
		self.show_loading()
		self.set_score(0)
	
		self.screen.blit(self.background, (0, 0))
		pygame.display.flip()

		self.sprites = pygame.sprite.RenderPlain()
	
	def show_loading(self):
		loading_font = pygame.font.Font(None, 32)
		loading = loading_font.render(u"Waiting for Spotify...", 1, (10, 10, 10))
		self.loading_pos = loading.get_rect(centerx = self.background.get_width() / 2, centery = self.background.get_height() / 2)
		self.background.blit(loading, self.loading_pos)		
	
	def hide_loading(self):
		# Simple overwrite the location of the loading text with a white filled rect
		pygame.draw.rect(self.screen, (255, 255, 255), self.loading_pos)
		self.loading_pos = None

	def tick(self):
		"""Called from the twisted loop"""
		# Remove the loading text as we are now running
		if self.loading_pos:
			self.hide_loading()
		
		self.sprites.update()
		self.sprites.draw(self.screen)
		pygame.display.flip()
		
		for event in pygame.event.get():
			if event.type == QUIT:
				reactor.stop()
			elif event.type == KEYDOWN and event.key == K_ESCAPE:
				reactor.stop()
			elif event.type == MOUSEBUTTONDOWN:
				if self.selected:
					continue

				for cover in self.sprites.sprites():
					if cover.process_click(event.pos):
						self.selected = True
		
		# Run at 10 fps
		reactor.callLater(0.1, self.tick)
	
	def set_score(self, score):
		if self.score_pos:
			pygame.draw.rect(self.screen, (255, 255, 255), self.score_pos)
		
		font = pygame.font.Font(None, 24)
		text = font.render(u"Score: %d" % score, 1, (10, 10, 10))
		self.score_pos = text.get_rect(topleft = (10, 10))
		self.screen.blit(text, self.score_pos)
		
	def display_state(self, state):
		font = pygame.font.Font(None, 32)
		text = font.render(state, 1, (10, 10, 10))
		self.state_pos = text.get_rect(centerx = self.background.get_width() / 2, centery = HEIGHT - 50)
		self.screen.blit(text, self.state_pos)
		
	def winner(self):
		"""Called when we win the game"""
		self.display_state("WIN!")
		
	def loser(self):
		"""Called when we lost"""
		self.display_state("FAIL")
	
	def clear_state(self):
		if self.state_pos:
			pygame.draw.rect(self.screen, (255, 255, 255), self.state_pos)
			self.state_pos = None

	def load_failed(self):
		"""Called when Spotify fails to load a track in time"""
		self.display_state(u"Waiting for next round to start...")
	
	def waiting_for_tracks(self):
		self.display_state(u"Waiting for tracks..")
	
	def waiting_for_players(self):
		self.display_state(u"Waiting for players..")
	
	def intermission(self):
		pass
	
	def add_cover(self, img, data):
		index, callback = data

		data = str(img.data())
		f = cStringIO.StringIO(data)

		self.sprites.add(Cover(self.screen, f, index, callback))
	
	def clear_covers(self):
		self.selected = False
		# Remove any selection
		for sprite in self.sprites.sprites():
			sprite.remove_selection()
			# Clear all covers, except the selected one
			sprite.clear_if_not_selected()
		
		# Clear state
		self.clear_state()

		self.sprites.empty()
		self.tick()
	
