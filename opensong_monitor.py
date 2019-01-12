#!/usr/bin/env python2

import os
import time
import pygame
import websocket
import threading
import signal
import sys
import argparse
import xml.etree.ElementTree as ET
import Queue
import tempfile
import logging


class OpenSongConfig:
    host = 'localhost'
    port = 8082


# Global variables
screen_size    = (0,0)   # Placeholder to store screen size
screen_surface = None    # Placeholder to store display framebuffer image
opensong_ws    = None    # Placeholder for OpenSong websocket connection
shutdown       = False
slides         = Queue.Queue()


def init_screen():
    global screen_size
    global screen_surface

    drivers = ('directfb', 'fbcon', 'svgalib')

    initialized = False
    for driver in drivers:
        if not os.getenv('SDL_VIDEODRIVER'):
            os.putenv('SDL_VIDEODRIVER', driver)

        try:
            pygame.display.init()
            initialized = True
            break
        except pygame.error:
            pass

    if initialized:
        screen_size    = (pygame.display.Info().current_w,
                          pygame.display.Info().current_h)
        screen_surface = pygame.display.set_mode(screen_size, pygame.FULLSCREEN)

        pygame.mouse.set_visible(False)
    else:
       raise Exception('No suitable framebuffer video driver found.')

def osws_on_data(ws, data, data_type, complete):
    if complete:
        if data_type == 0x1: #websocket.ABNF.OPCODE_TEXT
            print(data)
            if data[:5] == '<?xml':
                try:
                    xml = ET.fromstring(data)
                    if xml.tag == 'response' and xml.get('resource') == 'presentation':
                        pres = xml.find("presentation")
                        #for child in pres:
                        #    print "**", child.tag, child.attrib
                        if pres.get('running') == '1':
                            itemnumber = int(pres.find("slide").attrib["itemnumber"])
                            load_slide(itemnumber)
                            ## Queue item number for retrieval by update_slides thread
                            #slides.put(itemnumber)
                    #else:
                    #    print "** skip", xml, xml.get('resource')
                except:
                    print("Failed to parse message from OpenSong:", message)
            else:
                print "Not parsing:", message[:5]
        elif data_type == 0x2: #websocket.ABNF.OPCODE_BINARY
            print "Received image"
            slides.put(data)

def osws_on_error(ws, error):
    print("  Connection error: " % (error))

def osws_on_close(ws):
    print("  Connection to OpenSong closed")

def osws_on_open(ws):
    print("  Connected to OpenSong")
    ws.send("/ws/subscribe/presentation")

def opensong_connect(opensong_cfg):
    global opensong_ws

    #websocket.enableTrace(True)
    url = "ws://%s:%d/ws" % (opensong_cfg.host, opensong_cfg.port)
    opensong_ws = websocket.WebSocketApp(url,
                                         on_open    = osws_on_open,
                                         on_data    = osws_on_data,
                                         on_error   = osws_on_error,
                                         on_close   = osws_on_close)

def run_os_websocket(*args):
    global opensong_ws
    global shutdown

    while not shutdown:
        opensong_ws.run_forever()

        if not shutdown:
            print("Waiting to connect to OpenSong at %s ..." % (opensong_ws.url))
            time.sleep(5)

def load_slide(slide_number):
    if slide_number:
        print("Loading slide number %d" % (slide_number))
        (w, h) = screen_size
        url = "/presentation/slide/%d/image" % (slide_number)
        #url = "/presentation/slide/%d/image/width:%d/height:%d" % (slide_number, w, h)
        #url = "/presentation/slide/%d/preview" % (slide_number)
        opensong_ws.send(url)

def update_slides(*args):
    global opensong_ws
    global shutdown
    global slides

    while not shutdown:
        slide = slides.get()
        if slides.empty():
            if slide:
                fd, filename = tempfile.mkstemp()
                try:
                    os.write(fd, slide)
                    os.close(fd)
                    img = pygame.image.load(filename).convert()
                    show_image(img)
                finally:
                    os.remove(filename)

def show_image(img):
    img_rect = img.get_rect()
    pygame.transform.scale(img, screen_size, screen_surface)
    #screen.blit(img, img_rect)
    pygame.display.flip()

def show_sample_images():
    img = pygame.image.load('fixtures/color_bars_1121.jpg').convert()
    show_image(img)
    time.sleep(3)

    img = pygame.image.load('fixtures/6291.png').convert()
    show_image(img)
    time.sleep(3)

    img = pygame.image.load('fixtures/resolution.jpg').convert()
    show_image(img)
    time.sleep(3)

def signal_handler(signal, frame):
    global shutdown
    global opensong_ws

    print("Shutting down")
    shutdown = True
    # Insert dummy slide to let the update_slides thread finish
    slides.put(None)
    opensong_ws.close()

def main():
    opensong_cfg = OpenSongConfig()

    arg_parser = argparse.ArgumentParser(description='OpenSong networked monitor.',
                                         formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    arg_parser.add_argument("--host", default=opensong_cfg.host, help='Address of the OpenSong application')
    arg_parser.add_argument("--port", default=opensong_cfg.port, type=int, help='Port of the OpenSong API server')
    args = arg_parser.parse_args()

    if args.host:
        opensong_cfg.host = args.host
    if args.port:
        opensong_cfg.port = args.port

    try:
        init_screen()
        opensong_connect(opensong_cfg)
    except Exception as e:
        print "Aborting:", str(e)
        exit(0)

    # Workaround for Websocket issue #400 Fix #342 Fix #341
    _logger = logging.getLogger('websocket')
    try:
        from logging import NullHandler
    except ImportError:
        class NullHandler(logging.Handler):
            def emit(self, record):
                pass
    _logger.addHandler(NullHandler())

    # Register signal handler to be able to stop
    signal.signal(signal.SIGINT, signal_handler)

    # Slide retrieval and drawing thread
    slide_thread = threading.Thread(name="update_slides", target=update_slides)
    slide_thread.start()

    # OpenSong connection thread
    ws_thread = threading.Thread(name="run_os_websocket", target=run_os_websocket)
    ws_thread.start()

    #show_sample_images()

    # Wait for Ctrl-C to exit
    signal.pause()
    ws_thread.join()
    slide_thread.join()


if __name__ == '__main__':
    main()
