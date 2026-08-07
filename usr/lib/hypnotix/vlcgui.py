import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class VLCGUIController:
    """Manages the OSD playback controls and stream selection menus when using the VLC backend."""

    def __init__(self, main_window):
        self.win = main_window
        self.vlc_control_layout = None
        self.btn_toggle = None
        self.vlc_stream_menu = None

    def setup_ui(self):
        if self.vlc_control_layout is not None:
            return

        self.vlc_control_layout = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=15
        )
        self.vlc_control_layout.set_halign(Gtk.Align.CENTER)

        ctx = self.vlc_control_layout.get_style_context()
        ctx.add_class("osd")

        # THE DYNAMIC PLAY/PAUSE TOGGLE BUTTON
        self.btn_toggle = Gtk.Button.new_from_icon_name(
            "media-playback-pause-symbolic", Gtk.IconSize.BUTTON
        )
        self.btn_toggle.connect("clicked", lambda w: self.on_vlc_toggle_clicked())
        self.vlc_control_layout.pack_start(self.btn_toggle, False, False, 5)

        # THE SIMPLE STOP BUTTON
        btn_stop = Gtk.Button.new_from_icon_name(
            "media-playback-stop-symbolic", Gtk.IconSize.BUTTON
        )
        btn_stop.connect("clicked", lambda w: self.win.on_stop_button(None))
        self.vlc_control_layout.pack_start(btn_stop, False, False, 5)

        # THE SANDWICH MENU BUTTON (Audio, Video, Subtitle streams)
        btn_menu = Gtk.MenuButton()
        btn_menu.set_image(
            Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
        )
        btn_menu.set_direction(Gtk.ArrowType.UP)
        self.vlc_stream_menu = Gtk.Menu()
        btn_menu.set_popup(self.vlc_stream_menu)
        self.vlc_stream_menu.connect("show", lambda w: self.on_vlc_menu_show())
        self.vlc_control_layout.pack_start(btn_menu, False, False, 5)

        self.win.mpv_bottom_box.pack_start(self.vlc_control_layout, True, True, 5)

    def show_controls(self):
        from gi.repository import GLib
        GLib.idle_add(self.win.mpv_bottom_box.show_all)

    def on_vlc_toggle_clicked(self):
        if not self.win.mpv:
            return

        if getattr(self.win.mpv, "is_paused", lambda: False)():
            self.win.mpv.set_engine_resume()
            self.btn_toggle.set_image(
                Gtk.Image.new_from_icon_name(
                    "media-playback-pause-symbolic", Gtk.IconSize.BUTTON
                )
            )
        else:
            self.win.mpv.set_engine_pause()
            self.btn_toggle.set_image(
                Gtk.Image.new_from_icon_name(
                    "media-playback-start-symbolic", Gtk.IconSize.BUTTON
                )
            )

    def on_vlc_menu_show(self):
        if not self.win.mpv or not hasattr(self.win.mpv, "player"):
            return

        for child in self.vlc_stream_menu.get_children():
            self.vlc_stream_menu.remove(child)

        player = self.win.mpv.player

        stream_categories = [
            (
                "Audio",
                player.audio_get_track_description,
                player.audio_get_track,
                player.audio_set_track,
            ),
            (
                "Video",
                player.video_get_track_description,
                player.video_get_track,
                player.video_set_track,
            ),
            (
                "Subtitles",
                player.video_get_spu_description,
                player.video_get_spu,
                player.video_set_spu,
            ),
        ]

        for label, get_desc, get_curr, set_track in stream_categories:
            root_item = Gtk.MenuItem(label=label)
            submenu = Gtk.Menu()
            root_item.set_submenu(submenu)
            self.vlc_stream_menu.append(root_item)

            tracks = get_desc() or []
            current_track_id = get_curr()

            # Ensure an option to disable the stream is always available
            if not any(tid == -1 for tid, _ in tracks):
                tracks.insert(0, (-1, b"Disable"))

            group = None
            for track_id, track_name in tracks:
                name_str = (
                    track_name.decode("utf-8", "ignore")
                    if isinstance(track_name, bytes)
                    else str(track_name)
                )

                item = Gtk.RadioMenuItem(group=group, label=name_str)
                if group is None:
                    group = item

                if track_id == current_track_id:
                    item.set_active(True)

                item.connect(
                    "activate",
                    lambda w, fn=set_track, tid=track_id: (
                        fn(tid) if w.get_active() else None
                    ),
                )
                submenu.append(item)

        self.vlc_stream_menu.show_all()
