import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk


class VLCGUIController:
    """Manages the OSD playback controls and stream selection menus when using the VLC backend."""

    def __init__(self, main_window):
        self.win = main_window
        self.vlc_control_layout = None
        self.btn_toggle = None
        self.btn_stop = None
        self.btn_menu = None
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
        self.btn_stop = Gtk.Button.new_from_icon_name(
            "media-playback-stop-symbolic", Gtk.IconSize.BUTTON
        )
        self.btn_stop.connect("clicked", lambda w: self.win.on_stop_button(None))
        self.vlc_control_layout.pack_start(self.btn_stop, False, False, 5)

        # THE SANDWICH MENU BUTTON (Audio, Video, Subtitle streams)
        self.btn_menu = Gtk.MenuButton()
        self.btn_menu.set_image(
            Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
        )
        self.btn_menu.set_direction(Gtk.ArrowType.UP)
        self.vlc_stream_menu = Gtk.Menu()
        self.btn_menu.set_popup(self.vlc_stream_menu)
        self.vlc_stream_menu.connect("show", lambda w: self.on_vlc_menu_show())
        self.vlc_control_layout.pack_start(self.btn_menu, False, False, 5)

        self.win.mpv_bottom_box.pack_start(self.vlc_control_layout, True, True, 5)
        self.set_controls_sensitive(False)

    def show_controls(self):
        GLib.idle_add(self.win.mpv_bottom_box.show_all)

    def on_vlc_toggle_clicked(self):
        if not self.win.mpv:
            return

        self.win.mpv.pause = not self.win.mpv.pause
        icon = "media-playback-start-symbolic" if self.win.mpv.pause else "media-playback-pause-symbolic"
        self.btn_toggle.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))

    def set_controls_sensitive(self, sensitive: bool):
        def _update():
            for btn in (self.btn_toggle, self.btn_stop, self.btn_menu):
                if btn:
                    btn.set_sensitive(sensitive)

            if self.btn_toggle:
                icon = "media-playback-pause-symbolic" if sensitive else "media-playback-start-symbolic"
                self.btn_toggle.set_image(
                    Gtk.Image.new_from_icon_name(
                        icon, Gtk.IconSize.BUTTON
                    )
                )
            return False

        GLib.idle_add(_update)

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
