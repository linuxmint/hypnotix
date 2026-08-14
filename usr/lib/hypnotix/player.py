import abc
import time

vlc = None
try:
    import vlc
except (ImportError, OSError):
    pass

mpv = None
try:
    import mpv
except (ImportError, OSError):
    pass

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
    def unobserve_property(self, name, callback):
        pass

    @abc.abstractmethod
    def register_event_cb(self, callback):
        pass

    @abc.abstractmethod
    def show_osd_text(self, text: str, duration_ms: int = 6000):
        pass

    @abc.abstractmethod
    def send_keypress(self, key_name: str):
        pass

    @property
    @abc.abstractmethod
    def pause(self) -> bool:
        pass

    @property
    @abc.abstractmethod
    def idle_active(self) -> bool:
        pass

    @pause.setter
    @abc.abstractmethod
    def pause(self, value: bool):
        pass


class MpvEngine(VideoPlayer):
    def __init__(self, options=None, osc=True):
        if mpv is None:
            raise ImportError("mpv library not found")

        mpv_options = options if options is not None else {}

        self.player = mpv.MPV(
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

    def unobserve_property(self, name, callback):
        try:
            self.player.unobserve_property(name, callback)
        except Exception:
            pass

    def register_event_cb(self, callback):
        self.player.register_event_cb(callback)

    def show_osd_text(self, text: str, duration_ms: int = 6000):
        self.player.command("show-text", text, duration_ms)

    def send_keypress(self, key_name: str):
        self.player.command("keypress", key_name)

    def __setitem__(self, key, value):
        self.player[key] = value

    @property
    def pause(self) -> bool:
        return getattr(self.player, "pause", False)

    @property
    def idle_active(self) -> bool:
        return getattr(self.player, "idle_active", False)

    @pause.setter
    def pause(self, value: bool):
        self.player.pause = bool(value)


import subprocess
import os

class VlcEngine(VideoPlayer):
    def __init__(self, gui=None):
        self.gui = gui

        # Enable marquee and configure its text renderer (freetype) to match MPV's default styling
        self.instance = vlc.Instance("--no-xlib --quiet --no-video-title-show --sub-source=marq --freetype-font=sans-serif --freetype-outline-thickness=2")
        self.player = self.instance.media_player_new()

        # Instruct the video surface wrapper to ignore inputs,
        # allowing clicks to hit Hypnotix's native UI buttons.
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)

        self._user_agent = "Mozilla/5.0"
        self._referrer = ""

    def set_window(self, xid):
        self.player.set_xwindow(int(xid))

    def _resolve_ytdlp(self, url):
        local_path = os.path.expanduser("~/.cache/hypnotix/yt-dlp/yt-dlp")
        ytdlp_path = local_path if os.path.exists(local_path) else "/usr/bin/yt-dlp"

        # Fast check if it is a Youtube url, if not, do a dry-run check
        if not ("youtube.com" in url or "youtu.be" in url):
            try:
                subprocess.run([ytdlp_path, "--dump-json", "--no-download", url], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                return url, None

        try:
            result = subprocess.run([ytdlp_path, "-f", "bestvideo+bestaudio/best", "-g", url], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) == 2:
                return lines[0], lines[1]
            elif len(lines) == 1:
                return lines[0], None
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return url, None

    def play(self, url, user_agent=None, referrer=None):
        self._stopped = False
        opts = []
        ua = user_agent or self._user_agent
        ref = referrer or self._referrer

        if ua:
            opts.append(f":http-user-agent={ua}")
        if ref:
            opts.append(f":http-referrer={ref}")

        video_url, audio_url = self._resolve_ytdlp(url)

        if audio_url:
            opts.append(f":input-slave={audio_url}")

        media = self.instance.media_new(video_url, *opts)
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

    def unobserve_property(self, name, callback):
        pass

    def register_event_cb(self, callback):
        pass

    def show_osd_text(self, text: str, duration_ms: int = 6000):
        if not self.player:
            return
        if text:
            self.player.video_set_marquee_int(vlc.VideoMarqueeOption.Enable, 1)

            # Scale font size against a 720p base. Base 42 matches MPV's libass
            # point size rendering visually in VLC freetype.
            height = self.player.video_get_height()
            font_size = int((height / 720.0) * 42) if height > 0 else 42

            # Set a minimum floor so it never gets unreadable on tiny streams
            font_size = max(16, font_size)

            # VLC's Linux text renderer fails to calculate line widths properly
            # if the string only contains standard Unix newline characters
            formatted_text = text.replace('\n', '\r\n')
            self.player.video_set_marquee_string(vlc.VideoMarqueeOption.Text, formatted_text)
            self.player.video_set_marquee_int(vlc.VideoMarqueeOption.Timeout, duration_ms)
            self.player.video_set_marquee_int(vlc.VideoMarqueeOption.Position, 5)  # 5 = Top-Left (1=Left + 4=Top)
            self.player.video_set_marquee_int(vlc.VideoMarqueeOption.Size, font_size)
        else:
            self.player.video_set_marquee_int(vlc.VideoMarqueeOption.Enable, 0)

    def send_keypress(self, key_name: str):
        # Basic VLC key mapping since it lacks a native keypress injector
        key = key_name.lower()
        if key == "space":
            self.pause = not self.pause
        elif key == "right":
            # Seek forward 10 seconds
            self.player.set_time(self.player.get_time() + 10000)
        elif key == "left":
            # Seek backward 10 seconds
            self.player.set_time(max(0, self.player.get_time() - 10000))
        elif key == "m":
            self.player.audio_toggle_mute()

    def __setitem__(self, key, value):
        if key == "user-agent":
            self._user_agent = value
        elif key == "referrer":
            self._referrer = value

    @property
    def pause(self) -> bool:
        return self.player.get_rate() == 0.0

    @property
    def idle_active(self) -> bool:
        # VLC doesn't use the MPV-style idle property mechanism for its UI logic
        return False

    @pause.setter
    def pause(self, value: bool):
        if value:
            self.player.set_pause(True)
            self.player.set_rate(0.0)  # Freezes the live video container frame solid
        else:
            self.player.set_rate(1.0)  # Restores full video processing speed
            self.player.set_pause(False)
