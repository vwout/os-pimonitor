#!/usr/bin/env python2

import os
import time
import websocket
import threading
import signal
import argparse
import xml.etree.ElementTree as Et
import Queue
import tempfile
import logging

# Suppress pygame welcome message
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame


class OpenSongConfig:
    default_host = 'localhost'
    default_port = 8082

    def __init__(self):
        self.host = os.getenv("OPENSONG_HOST", self.default_host)
        self.port = os.getenv("OPENSONG_PORT", self.default_port)


class OpenSongMonitor:
    def __init__(self):
        self.config = OpenSongConfig()
        self.screen_size = (0, 0)  # Placeholder to store screen size
        self.screen_surface = None  # Placeholder to store display framebuffer image
        self.websocket = None  # Placeholder for OpenSong websocket connection
        self.shutdown = False
        self.slides = Queue.Queue()

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
            self.screen_size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
            self.screen_surface = pygame.display.set_mode(self.screen_size, pygame.FULLSCREEN)
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
                            #    print "**", child.tag, child.attrib
                            if pres.get('running') == '1':
                                itemnumber = int(pres.find("slide").attrib["itemnumber"])
                                self.load_slide(itemnumber)
                                # Queue item number for retrieval by update_slides thread
                                # slides.put(itemnumber)
                        # else:
                        #    print "** skip", xml, xml.get('resource')
                    except:
                        print("Failed to parse message from OpenSong:", data)
                else:
                    print "Not parsing:", data
            elif data_type == 0x2:  # websocket.ABNF.OPCODE_BINARY
                print "Received image"
                self.slides.put(data)

    def osws_on_error(self, _ws, error):
        print("  Connection error: " % error)

    def osws_on_close(self, _ws):
        print("  Connection to OpenSong closed")

    def osws_on_open(self, ws):
        print("  Connected to OpenSong")
        ws.send("/ws/subscribe/presentation")

    def opensong_connect(self):
        # websocket.enableTrace(True)
        url = "ws://%s:%d/ws" % (self.config.host, self.config.port)
        self.websocket = websocket.WebSocketApp(url,
                                                on_open=self.osws_on_open,
                                                on_data=self.osws_on_data,
                                                on_error=self.osws_on_error,
                                                on_close=self.osws_on_close)

    def run_os_websocket(self, *args):
        while not self.shutdown:
            try:
                self.websocket.run_forever()
            except Exception as e:
                print("Websocket connection caused a failure: %s" % str(e))

            if not self.shutdown:
                print("Waiting to (re)connect to OpenSong at %s ..." % self.websocket.url)
                time.sleep(5)

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
                        self.show_image(img)
                    finally:
                        os.remove(filename)

    def show_image(self, img):
        # img_rect = img.get_rect()
        pygame.transform.scale(img, self.screen_size, self.screen_surface)
        # screen.blit(img, img_rect)
        pygame.display.flip()

    def show_sample_images(self):
        img = pygame.image.load('fixtures/color_bars_1121.jpg').convert()
        self.show_image(img)
        time.sleep(3)

        img = pygame.image.load('fixtures/6291.png').convert()
        self.show_image(img)
        time.sleep(3)

        img = pygame.image.load('fixtures/resolution.jpg').convert()
        self.show_image(img)
        time.sleep(3)

    def signal_handler(self, _signal, _frame):
        print("Received SIGINT, shutting down...")
        self.shutdown = True
        # Insert dummy slide to let the update_slides thread finish
        self.slides.put(None)
        self.websocket.close()

    def run_monitor(self):
        try:
            self.init_screen()
            self.opensong_connect()
        except Exception as e:
            print "Aborting, initialisation failed:", str(e)
            exit(0)

        self._apply_websocket_logging_workaround()

        # Register signal handler to be able to stop
        signal.signal(signal.SIGINT, self.signal_handler)

        # Slide retrieval and drawing thread
        slide_thread = threading.Thread(name="update_slides", target=self.update_slides)
        slide_thread.start()

        # OpenSong connection thread
        ws_thread = threading.Thread(name="run_os_websocket", target=self.run_os_websocket)
        ws_thread.start()

        # Wait for Ctrl-C to exit
        try:
            signal.pause()
        except:
            # Workaround for Windows - pause method is not available on Windows
            pass

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
    arg_parser = argparse.ArgumentParser(description='OpenSong networked monitor.',
                                         formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    arg_parser.add_argument("--host", default=OpenSongConfig.default_host, help='Address of the OpenSong application')
    arg_parser.add_argument("--port", default=OpenSongConfig.default_port, type=int, help='Port of the OpenSong API server')
    args = arg_parser.parse_args()

    monitor = OpenSongMonitor()

    if args.host:
        monitor.config.host = args.host
    if args.port:
        monitor.config.port = args.port

    monitor.run_monitor()


if __name__ == '__main__':
    main()
