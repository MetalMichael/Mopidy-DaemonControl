from __future__ import unicode_literals

import logging
import sys
import pykka

from mopidy.core import CoreListener
from mopidy.utils import encoding, network, process

import urllib2
import requests
from threading import Timer

logger = logging.getLogger(__name__)

class DaemonControlFrontend(pykka.ThreadingActor, CoreListener):
    def __init__(self, config, core):
        super(DaemonControlFrontend, self).__init__()
		
        self.hostname = config['daemoncontrol']['hostname']
        self.core = core
        self.time = False

    def make_request(self, parameters):
        try:
            r = requests.get('http://' + self.hostname + '/' + parameters['action'])
        except (requests.ConnectionError, requests.Timeout):
            logger.error('DaemonController Error: Cannot connect to ' + self.hostname)
            process.exit_process()
        except requests.HTTPError:
            logger.error('DaemonController Error: HTTP error')
            process.exit_process()
        return r
        
    def on_start(self):
        req = self.make_request({'action': 'status'})
        if not req or req.text != 'running':
            logger.error('DaemonController Error: There is not a radio currently running')
            process.exit_process()
            return
        logger.info('DaemonController: Found running radio')
        self.core.tracklist.consume = True
        self.track_playback_ended('starting','')
        
    def on_stop(self):
        if self.time:
            self.time.cancel()

    def track_playback_started(self, tl_track):
        logger.info('DaemonController: Playback started');
        
    def track_playback_ended(self, tl_track, time_position):
        if not tl_track == 'starting':
            logger.info('DaemonController: Playback ended')
        
        if(self.core.tracklist.length.get() == 0):
            logger.info('DaemonController: no track next. Looking up...')
            req = self.make_request({'action': 'status/getsong'})
            if(req.text == "empty"):
                logger.info("DaemonController: no songs, trying again in 10s")
                self.time = Timer(10, self.track_playback_ended, ('restarting', ''))
                self.time.start()
                return
                
            logger.info('DaemonController: Track Found - ' + req.text)
            track = self.core.library.lookup(req.text).get()
            
            if not track:
                logger.error('DaemonController: This track does not exist')
                self.track_playback_ended('retrying','')
                return
                
            tl_tracks = self.core.tracklist.add(uri=req.text, at_position=0).get()
            self.core.playback.play(tl_tracks[0]).get()
        else:
            logger.info('DaemonController: Queued track found. Not looking up')
