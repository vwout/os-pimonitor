# os-pimonitor

os-pimonitor is a display solution to show the [OpenSong](http://opensong.org) presentation image on a monitor using a Raspberry Pi - or as a matter of fact, any hardware platform that runs Python and offers a framebuffer interface. It shows the slide that is currently presented full-screen on the monitor. It can be used to easily setup an preview monitor or a presentation screen at location where installing a VGA or HDMI cable is not viable. The os-pimonitor uses the internal WebSocket server of OpenSong and only requires bandwidth when a slide change occurs. This makes this solution work very well over WiFi.

The OpenSong PI Monitor is a readonly client for the [OpenSong API](http://opensong.org/pages/api.html). It can not be used as a remote control for OpenSong.

The features are:
- display of the current slide as image on the attached monitor


## What is OpenSong?

> OpenSong is a free, open-source software application created to manage lyrics, chords, lead sheets, overheads, computer projection, and more.
>
> OpenSong releases are available for Microsoft Windows, Mac OSX, and Linux operating systems.
>
> [Download](http://opensong.org/d/downloads) the full application for free and give it a try!


### Requirements

  - An installation of OpenSong running on a PC, with enabled automation API in OpenSong (to enable, goto the generic settings, on the system tab)
  - The files in the repository, running on e.g. a Raspberry PI, with:
    - Python 2 and the packages as listed in `requirements.txt`. Install them easily via `pip`:
    ```
    $ pip install -r requirements.txt
    ```

### Usage

Change the members of the class OpenSongConfig to match the settings of the computer running OpenSong:

    class OpenSongConfig:
        host = 'localhost'
        port = 8082

Run the script, e.g. using

    python opensong_monitor.py
		
		
## License

[GNU General Public License v2.0 (GPL-2.0)](http://opensource.org/licenses/gpl-2.0.php)
