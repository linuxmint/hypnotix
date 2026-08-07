import abc
import time

class VideoPlayer(abc.ABC):
    """Abstract base class defining the media player engine interface."""

    @abc.abstractmethod
    def set_window(self, xid):
        pass

    @abc.abstractmethod
    def play(self, url, user_agent=None, referrer=None):
        pass

    @abc.abstractmethod
    def stop(self):
        pass

    @abc.abstractmethod
    def terminate(self):
        pass

    @abc.abstractmethod
    def set_volume(self, value):
        pass

    @abc.abstractmethod
    def is_playing(self) -> bool:
        pass

    @abc.abstractmethod
    def wait_until_playing(self):
        pass

    @abc.abstractmethod
    def observe_property(self, name, callback):
        pass

    @abc.abstractmethod
    def register_event_cb(self, callback):
        pass

    @property
    @abc.abstractmethod
    def pause(self) -> bool:
        pass

    @pause.setter
    @abc.abstractmethod
    def pause(self, value: bool):
        pass


class MpvEngine(VideoPlayer):
    def __init__(self, options=None, osc=True):
        try:
            from . import mpv as hypnotix_mpv
        except ImportError:
            import mpv as hypnotix_mpv

        mpv_options = options if options is not None else {}

        self.player = hypnotix_mpv.MPV(
            **mpv_options,
            script_opts="osc-layout=box,osc-seekbarstyle=bar,osc-deadzonesize=0,osc-minmousemove=3",
            input_default_bindings=True,
            input_vo_keyboard=True,
            osc=osc,
            ytdl=True
        )

    def set_window(self, xid):
        self.player.wid = str(xid)

    def play(self, url, user_agent=None, referrer=None):
        if user_agent:
            self.player["user-agent"] = user_agent
        if referrer:
            self.player["referrer"] = referrer
        self.player.play(url)

    def stop(self):
        try:
            self.player.stop()
        except Exception:
            pass

    def terminate(self):
        self.stop()
        try:
            self.player.terminate()
        except Exception:
            pass

    def set_volume(self, value):
        self.player.volume = value

    def is_playing(self) -> bool:
        return getattr(self.player, "core_idle", True) is False

    def wait_until_playing(self):
        # Direct proxy to the original hypnotix mpv.py wait_until_playing implementation
        self.player.wait_until_playing()

    def observe_property(self, name, callback):
        self.player.observe_property(name, callback)

    def register_event_cb(self, callback):
        self.player.register_event_cb(callback)

    def __setitem__(self, key, value):
        self.player[key] = value

    @property
    def pause(self) -> bool:
        return getattr(self.player, "pause", False)

    @pause.setter
    def pause(self, value: bool):
        self.player.pause = bool(value)


class VlcEngine(VideoPlayer):
    def __init__(self, gui=None):
        import vlc
        self.gui = gui

        self.instance = vlc.Instance("--no-xlib --quiet --no-video-title-show")
        self.player = self.instance.media_player_new()

        # Instruct the video surface wrapper to ignore inputs,
        # allowing clicks to hit Hypnotix's native UI buttons.
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)

        self._user_agent = "Mozilla/5.0"
        self._referrer = ""

    def set_window(self, xid):
        self.player.set_xwindow(int(xid))

    def play(self, url, user_agent=None, referrer=None):
        self._stopped = False
        opts = []
        ua = user_agent or self._user_agent
        ref = referrer or self._referrer

        if ua:
            opts.append(f":http-user-agent={ua}")
        if ref:
            opts.append(f":http-referrer={ref}")

        media = self.instance.media_new(url, *opts)
        self.player.set_media(media)
        self.player.play()
        if self.gui:
            self.gui.set_controls_sensitive(True)

    def stop(self):
        self._stopped = True
        self.player.stop()
        if self.gui:
            self.gui.set_controls_sensitive(False)

    def terminate(self):
        self.stop()
        try:
            self.player.release()
            self.instance.release()
        except Exception:
            pass

    def set_volume(self, value):
        self.player.audio_set_volume(int(value))

    def is_playing(self) -> bool:
        import vlc

        return self.player.get_state() in [vlc.State.Playing, vlc.State.Buffering]

    def wait_until_playing(self):
        # Safe thread-blocking implementation mimicking the MPV behaviour
        # Prevents Hypnotix from closing its loading spinner overlay too early
        timeout = 10.0  # seconds to wait before bailing out
        start_time = time.time()
        while not self.is_playing():
            time.sleep(0.1)
            if time.time() - start_time > timeout:
                break
        if self.gui and not getattr(self, "_stopped", False):
            self.gui.set_controls_sensitive(True)

    def observe_property(self, name, callback):
        pass

    def register_event_cb(self, callback):
        pass

    def __setitem__(self, key, value):
        if key == "user-agent":
            self._user_agent = value
        elif key == "referrer":
            self._referrer = value

    @property
    def pause(self) -> bool:
        return self.player.get_rate() == 0.0

    @pause.setter
    def pause(self, value: bool):
        if value:
            self.player.set_pause(True)
            self.player.set_rate(0.0)  # Freezes the live video container frame solid
        else:
            self.player.set_rate(1.0)  # Restores full video processing speed
            self.player.set_pause(False)
