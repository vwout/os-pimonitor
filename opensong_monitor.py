#!/usr/bin/env python2

import os
import time
import websocket
import threading
import argparse
import xml.etree.ElementTree as Et
import Queue
import tempfile
import logging
from functools import partial

# Suppress pygame welcome message
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame


class OpenSongConfig:
    default_host = 'localhost'
    default_port = 8082

    def __init__(self):
        self.host = os.getenv("OPENSONG_HOST", self.default_host)
        self.port = os.getenv("OPENSONG_PORT", self.default_port)
        self.fullscreen = True


class OpenSongMonitor:
    def __init__(self):
        self.config = OpenSongConfig()
        self.screen_size = (0, 0)  # Placeholder to store screen size
        self.screen_surface = None  # Placeholder to store display framebuffer image
        self.websocket = None  # Placeholder for OpenSong websocket connection
        self.shutdown = False
        self.slides = Queue.Queue()
        self.current_slide = None

    def init_screen(self):
        # Display drivers, first empty entry will attempt autodection
        drivers = ('', 'directfb', 'fbcon', 'svgalib', 'windib')

        initialized = False
        for driver in drivers:
            if not os.getenv('SDL_VIDEODRIVER'):
                if driver:
                    os.putenv('SDL_VIDEODRIVER', driver)

            try:
                pygame.display.init()
                print("Using video driver %s%s" % (pygame.display.get_driver(), " (autodetected)" if not driver else ""))
                initialized = True
            except pygame.error:
                pass

            if initialized:
                break

        if initialized:
            if self.config.fullscreen:
                self.screen_size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
                self.screen_surface = pygame.display.set_mode(self.screen_size, flags=pygame.FULLSCREEN)
            else:
                self.screen_size = (pygame.display.Info().current_w/2, pygame.display.Info().current_h/2)
                self.screen_surface = pygame.display.set_mode(self.screen_size)

            pygame.display.set_caption('OpenSong Monitor')
            pygame.mouse.set_visible(False)
        else:
            raise Exception('No suitable framebuffer video driver found.')

    def osws_on_data(self, _ws, data, data_type, complete):
        if complete:
            if data_type == 0x1:  # websocket.ABNF.OPCODE_TEXT
                print(data)
                if data[:5] == '<?xml':
                    try:
                        xml = Et.fromstring(data)
                        if xml.tag == 'response' and xml.get('resource') == 'presentation':
                            pres = xml.find("presentation")
                            # for child in pres:
                            #    print("**", child.tag, child.attrib)
                            if pres.get('running') == '1':
                                itemnumber = int(pres.find("slide").attrib["itemnumber"])
                                self.load_slide(itemnumber)
                                # Queue item number for retrieval by update_slides thread
                                # slides.put(itemnumber)
                            else:
                                self.status("No running presentation", clear_slide=True)
                        # else:
                        #    print("** skip", xml, xml.get('resource'))
                    except:
                        print("Failed to parse message from OpenSong:", data)
                else:
                    if not data == "OK":
                        print("Not parsing: {}".format(data))
            elif data_type == 0x2:  # websocket.ABNF.OPCODE_BINARY
                print("Received image")
                self.slides.put(data)

    @staticmethod
    def osws_on_error(_ws, error):
        print("Websocket: Connection error: %s" % error)

    @staticmethod
    def osws_on_close(_ws):
        print("Websocket: Connection to OpenSong closed")

    @staticmethod
    def osws_on_open(ws):
        print("Websocket: Connected to OpenSong")
        ws.send("/ws/subscribe/presentation")

    def opensong_connect(self):
        # websocket.enableTrace(True)
        url = "ws://%s:%d/ws" % (self.config.host, self.config.port)
        self.websocket = websocket.WebSocketApp(url,
                                                on_open=self.osws_on_open,
                                                on_data=partial(self.osws_on_data),
                                                on_error=self.osws_on_error,
                                                on_close=self.osws_on_close)

    def run_os_websocket(self, *args):
        while not self.shutdown:
            try:
                self.websocket.run_forever()
            except Exception as e:
                if isinstance(e, SystemExit):
                    self.shutdown = True
                else:
                    print("Websocket: Connection caused a failure: %s" % str(e))
                    if self.websocket:
                        self.websocket.close()

            if not self.shutdown:
                self.status("Waiting to (re)connect to OpenSong", "at %s ..." % self.websocket.url, clear_slide=True)
                time.sleep(5)

    def status(self, text, details="", clear_slide=False):
        font = pygame.font.Font(pygame.font.get_default_font(), 40)
        surface = font.render(text, True, (255, 255, 255))
        rect = surface.get_rect()
        rect.center = ((self.screen_size[0]/2), (self.screen_size[1]/2))

        self.show_current_slide(clear=clear_slide)

        # background = pygame.Rect((0, 0), self.screen_size)
        # background.center = ((self.screen_size[0]/2), (self.screen_size[1]/2))
        # pygame.draw.rect(self.screen_surface, (90, 90, 90, 128), background)
        self.screen_surface.blit(surface, rect)

        pygame.display.update()
        print("Status: %s (%s)" % (text, details))

    def load_slide(self, slide_number):
        if slide_number:
            print("Loading slide number %d" % slide_number)
            # (w, h) = self.screen_size
            url = "/presentation/slide/%d/image" % slide_number
            # url = "/presentation/slide/%d/image/width:%d/height:%d" % (slide_number, w, h)
            # url = "/presentation/slide/%d/preview" % (slide_number)
            self.websocket.send(url)

    def update_slides(self, *args):
        while not self.shutdown:
            try:
                slide = self.slides.get(block=True, timeout=1.0)
            except Queue.Empty:
                slide = None

            if slide and self.slides.empty() and not self.shutdown:
                if slide:
                    fd, filename = tempfile.mkstemp()
                    try:
                        os.write(fd, slide)
                        os.close(fd)
                        img = pygame.image.load(filename).convert()
                        self.show_current_slide(img)
                    finally:
                        os.remove(filename)

    def show_current_slide(self, img=None, clear=False):
        if img:
            self.current_slide = img
        elif clear:
            self.current_slide = None

        if self.current_slide:
            print("update new slide")
            # img_rect = img.get_rect()
            pygame.transform.scale(self.current_slide, self.screen_size, self.screen_surface)
            # screen.blit(img, img_rect)
            pygame.display.flip()
        else:
            self.screen_surface.fill((0, 0, 0))

    def show_sample_images(self):
        img = pygame.image.load('fixtures/color_bars_1121.jpg').convert()
        self.show_current_slide(img)
        time.sleep(3)

        img = pygame.image.load('fixtures/6291.png').convert()
        self.show_current_slide(img)
        time.sleep(3)

        img = pygame.image.load('fixtures/resolution.jpg').convert()
        self.show_current_slide(img)
        time.sleep(3)

    def close(self):
        self.shutdown = True

        # Insert dummy slide to let the update_slides thread finish
        self.slides.put(None)
        if self.websocket:
            self.websocket.close()

    def run_monitor(self):
        try:
            self.init_screen()
            self.opensong_connect()
        except Exception as e:
            print("Aborting, initialisation failed:", str(e))
            exit(0)

        self._apply_websocket_logging_workaround()

        # Slide retrieval and drawing thread
        slide_thread = threading.Thread(name="update_slides", target=self.update_slides)
        slide_thread.start()

        # OpenSong connection thread
        ws_thread = threading.Thread(name="run_os_websocket", target=self.run_os_websocket)
        ws_thread.start()

        pygame.init()

        self.status("OpenSong Monitor")

        while not self.shutdown:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.close()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.close()
                    if event.mod == pygame.KMOD_LCTRL and event.key == pygame.K_c:
                        self.close()

            if not self.shutdown:
                pygame.display.update()
                time.sleep(0.1)

        pygame.quit()
        ws_thread.join()
        slide_thread.join()

    @staticmethod
    def _apply_websocket_logging_workaround():
        # Workaround for Websocket issue #400 Fix #342 Fix #341
        _logger = logging.getLogger('websocket')
        try:
            from logging import NullHandler
        except ImportError:
            class NullHandler(logging.Handler):
                def emit(self, record):
                    pass
        _logger.addHandler(NullHandler())


def main():
    def str2bool(v):
        if v.lower() in ('yes', 'true', 't', 'y', '1'):
            return True
        elif v.lower() in ('no', 'false', 'f', 'n', '0'):
            return False
        else:
            raise argparse.ArgumentTypeError('Boolean value expected.')

    arg_parser = argparse.ArgumentParser(description='OpenSong networked monitor.',
                                         formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    arg_parser.add_argument("--host", default=OpenSongConfig.default_host, help='Address of the OpenSong application')
    arg_parser.add_argument("--port", default=OpenSongConfig.default_port, type=int,
                            help='Port of the OpenSong API server')
    arg_parser.add_argument("--fullscreen", default=True, type=str2bool, nargs='?', help='Run in fullscreen mode')
    args = arg_parser.parse_args()

    monitor = OpenSongMonitor()

    if args.host:
        monitor.config.host = args.host
    if args.port:
        monitor.config.port = args.port
    monitor.config.fullscreen = args.fullscreen is True

    monitor.run_monitor()


if __name__ == '__main__':
    main()
