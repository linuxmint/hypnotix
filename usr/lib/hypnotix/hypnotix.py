#!/usr/bin/python3
import gettext
import locale
import os
import shutil
import sys
import time
import traceback
import warnings
import subprocess
from functools import partial
from pathlib import Path

# Force X11 on a Wayland session
if "WAYLAND_DISPLAY" in os.environ:
    os.environ["WAYLAND_DISPLAY"] = ""

# Suppress GTK deprecation warnings
warnings.filterwarnings("ignore")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("XApp", "1.0")
from gi.repository import Gtk, Gdk, Gio, XApp, GdkPixbuf, GLib, Pango

import mpv
import requests
import setproctitle
from imdb import IMDb
from unidecode import unidecode

from common import Manager, Provider, Channel, MOVIES_GROUP, PROVIDERS_PATH, SERIES_GROUP, TV_GROUP,\
    async_function, idle_function


setproctitle.setproctitle("hypnotix")

# i18n
APP = "hypnotix"
LOCALE_DIR = "/usr/share/locale"
locale.bindtextdomain(APP, LOCALE_DIR)
gettext.bindtextdomain(APP, LOCALE_DIR)
gettext.textdomain(APP)
_ = gettext.gettext


PROVIDER_OBJ, PROVIDER_NAME = range(2)
PROVIDER_TYPE_ID, PROVIDER_TYPE_NAME = range(2)

GROUP_OBJ, GROUP_NAME = range(2)
CHANNEL_OBJ, CHANNEL_NAME, CHANNEL_LOGO = range(3)

COL_PROVIDER_NAME, COL_PROVIDER = range(2)

PROVIDER_TYPE_URL = "url"
PROVIDER_TYPE_LOCAL = "local"
PROVIDER_TYPE_XTREAM = "xtream"

UPDATE_BR_INTERVAL = 5

AUDIO_SAMPLE_FORMATS = {
    "u16": "unsigned 16 bits",
    "s16": "signed 16 bits",
    "s16p": "signed 16 bits, planar",
    "flt": "float",
    "float": "float",
    "fltp": "float, planar",
    "floatp": "float, planar",
    "dbl": "double",
    "dblp": "double, planar",
}

COUNTRY_CODES = {}
with open("/usr/share/hypnotix/countries.list") as f:
    for line in f:
        line = line.strip()
        code, name = line.split(":")
        COUNTRY_CODES[name] = code

class ChannelWidget(Gtk.ListBoxRow):
    """ A custom widget for displaying and holding channel data. """

    def __init__(self, channel, logo, **kwargs):
        super().__init__(**kwargs)
        self._channel = channel
        self.set_tooltip_text(channel.name)

        frame = Gtk.Frame()
        label = Gtk.Label(channel.name)
        label.set_max_width_chars(30)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, border_width=6)
        box.pack_start(logo, False, False, 0)
        box.pack_start(label, False, False, 0)
        box.set_spacing(6)
        frame.add(box)
        self.add(frame)

    @property
    def channel(self):
        return self._channel

class MyApplication(Gtk.Application):
    # Main initialization routine
    def __init__(self, application_id, flags):
        Gtk.Application.__init__(self, application_id=application_id, flags=flags)
        self.connect("activate", self.activate)

    def activate(self, application):
        windows = self.get_windows()
        if len(windows) > 0:
            window = windows[0]
            window.present()
            window.show()
        else:
            window = MainWindow(self)
            self.add_window(window.window)
            window.window.show()


class MainWindow:
    def __init__(self, application):

        self.application = application
        self.settings = Gio.Settings(schema_id="org.x.hypnotix")
        self.icon_theme = Gtk.IconTheme.get_default()
        self.manager = Manager(self.settings)
        self.providers = []
        self.favorite_data = []
        self.active_provider = None
        self.active_group = None
        self.active_serie = None
        self.marked_provider = None
        self.content_type = TV_GROUP  # content being browsed
        self.back_page = None  # page to go back to if the back button is pressed
        self.active_channel = None
        self.fullscreen = False
        self.latest_search_bar_text = None
        self.visible_search_results = 0
        self.mpv = None
        self.ia = IMDb()

        self.page_is_loading = False # used to ignore signals while we set widget states

        self.video_properties = {}
        self.audio_properties = {}

        # Used for redownloading timer
        self.reload_timeout_sec = 60 * 5
        self._timerid = -1
        gladefile = "/usr/share/hypnotix/hypnotix.ui"
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APP)
        self.builder.add_from_file(gladefile)
        self.window = self.builder.get_object("main_window")
        self.window.set_title(_("Hypnotix"))
        self.window.set_icon_name("hypnotix")

        # The window used to display stream information
        self.info_window = self.builder.get_object("stream_info_window")

        provider = Gtk.CssProvider()
        provider.load_from_path("/usr/share/hypnotix/hypnotix.css")
        screen = Gdk.Display.get_default_screen(Gdk.Display.get_default())
        # I was unable to found instrospected version of this
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Prefs variables
        self.selected_pref_provider = None
        self.edit_mode = False

        # Create variables to quickly access dynamic widgets
        widget_names = [
            "headerbar",
            "status_label",
            "status_bar",
            "sidebar",
            "go_back_button",
            "search_button",
            "search_bar",
            "channels_box",
            "current_provider_label",
            "mpv_drawing_area",
            "stack",
            "channel_stack",
            "fullscreen_button",
            "mpv_top_box",
            "mpv_bottom_box",
            "label_channel_name",
            "label_channel_url",
            "provider_ok_button",
            "provider_cancel_button",
            "name_entry",
            "path_label",
            "path_entry",
            "browse_button",
            "url_label",
            "url_entry",
            "username_label",
            "username_entry",
            "password_label",
            "password_entry",
            "epg_label",
            "epg_entry",
            "tv_logo",
            "movies_logo",
            "series_logo",
            "tv_button",
            "movies_button",
            "series_button",
            "providers_button",
            "preferences_button",
            "favorites_button",
            "tv_label",
            "movies_label",
            "series_label",
            "categories_flowbox",
            "channels_listbox",
            "vod_flowbox",
            "episodes_box",
            "stop_button",
            "pause_button",
            "show_button",
            "playback_label",
            "playback_bar",
            "providers_flowbox",
            "new_provider_button",
            "reset_providers_button",
            "delete_no_button",
            "delete_yes_button",
            "reset_no_button",
            "reset_yes_button",
            "info_section",
            "info_revealer",
            "info_name_label",
            "info_plot_label",
            "info_rating_label",
            "info_year_label",
            "close_info_button",
            "info_genre_label",
            "info_duration_label",
            "info_votes_label",
            "info_pg_label",
            "divider_label",
            "useragent_entry",
            "referer_entry",
            "mpv_entry",
            "mpv_link",
            "ytdlp_local_switch",
            "ytdlp_system_version_label",
            "ytdlp_local_version_label",
            "ytdlp_update_button",
            "mpv_stack",
            "spinner",
            "info_window_close_button",
            "video_properties_box",
            "video_properties_label",
            "colour_properties_box",
            "colour_properties_label",
            "audio_properties_box",
            "audio_properties_label",
            "layout_properties_box",
            "layout_properties_label",
            "favorite_button",
            "favorite_button_image",
            "new_channel_button",
            "new_name_entry",
            "new_url_entry",
            "new_logo_entry",
            "new_ok_button",
            "new_cancel_button"
        ]

        for name in widget_names:
            widget = self.builder.get_object(name)
            if widget is None:
                print("Could not find widget %s!" % name)
                sys.exit(1)
            else:
                setattr(self, name, widget)

        self.divider_label.set_text("/10")

        # Widget signals
        self.window.connect("key-press-event", self.on_key_press_event)
        self.mpv_drawing_area.connect("realize", self.on_mpv_drawing_area_realize)
        self.mpv_drawing_area.connect("draw", self.on_mpv_drawing_area_draw)
        self.fullscreen_button.connect("clicked", self.on_fullscreen_button_clicked)

        self.info_window.connect("delete-event", self.on_close_info_window)
        self.info_window_close_button.connect("clicked", self.on_close_info_window_button_clicked)

        self.new_ok_button.connect("clicked", self.on_new_ok_button)
        self.new_cancel_button.connect("clicked", self.on_new_cancel_button)

        self.provider_ok_button.connect("clicked", self.on_provider_ok_button)
        self.provider_cancel_button.connect("clicked", self.on_provider_cancel_button)

        self.name_entry.connect("changed", self.toggle_ok_sensitivity)
        self.url_entry.connect("changed", self.toggle_ok_sensitivity)
        self.path_entry.connect("changed", self.toggle_ok_sensitivity)

        self.new_name_entry.connect("changed", self.toggle_new_ok_sensitivity)
        self.new_url_entry.connect("changed", self.toggle_new_ok_sensitivity)
        self.new_logo_entry.connect("changed", self.toggle_new_ok_sensitivity)

        self.tv_button.connect("clicked", self.show_groups, TV_GROUP)
        self.movies_button.connect("clicked", self.show_groups, MOVIES_GROUP)
        self.series_button.connect("clicked", self.show_groups, SERIES_GROUP)
        self.new_channel_button.connect("clicked", self.open_new_channel)
        self.favorites_button.connect("clicked", self.show_favorites)
        self.providers_button.connect("clicked", self.open_providers)
        self.preferences_button.connect("clicked", self.open_preferences)
        self.go_back_button.connect("clicked", self.on_go_back_button)

        self.search_button.connect("toggled", self.on_search_button_toggled)
        self.search_bar.connect("activate", self.on_search_bar)

        self.stop_button.connect("clicked", self.on_stop_button)
        self.pause_button.connect("clicked", self.on_pause_button)
        self.show_button.connect("clicked", self.on_show_button)

        self.new_provider_button.connect("clicked", self.on_new_provider_button)
        self.reset_providers_button.connect("clicked", self.on_reset_providers_button)
        self.delete_no_button.connect("clicked", self.on_delete_no_button)
        self.delete_yes_button.connect("clicked", self.on_delete_yes_button)
        self.reset_no_button.connect("clicked", self.on_reset_no_button)
        self.reset_yes_button.connect("clicked", self.on_reset_yes_button)

        self.browse_button.connect("clicked", self.on_browse_button)

        self.close_info_button.connect("clicked", self.on_close_info_button)

        self.channels_listbox.connect("row-activated", self.on_channel_activated)

        self.favorite_button.connect("toggled", self.on_favorite_button_toggled)

        # Settings widgets
        self.bind_setting_widget("user-agent", self.useragent_entry)
        self.bind_setting_widget("http-referer", self.referer_entry)
        self.bind_setting_widget("mpv-options", self.mpv_entry)

        # ytdlp
        self.ytdlp_local_switch.set_active(self.settings.get_boolean("use-local-ytdlp"))
        self.ytdlp_local_switch.connect("notify::active", self.on_ytdlp_local_switch_activated)
        self.ytdlp_system_version_label.set_text(subprocess.getoutput("/usr/bin/yt-dlp --version"))
        if os.path.exists(os.path.expanduser("~/.cache/hypnotix/yt-dlp/yt-dlp")):
            self.ytdlp_local_version_label.set_text(subprocess.getoutput("~/.cache/hypnotix/yt-dlp/yt-dlp --version"))
        self.ytdlp_update_button.connect("clicked", self.update_ytdlp)

        # Dark mode manager
        # keep a reference to it (otherwise it gets randomly garbage collected)
        self.dark_mode_manager = XApp.DarkModeManager.new(prefer_dark_mode=True)

        # Menubar
        accel_group = Gtk.AccelGroup()
        self.window.add_accel_group(accel_group)
        menu = self.builder.get_object("main_menu")
        item = Gtk.ImageMenuItem()
        item.set_image(Gtk.Image.new_from_icon_name("preferences-desktop-keyboard-shortcuts-symbolic", Gtk.IconSize.MENU))
        item.set_label(_("Keyboard Shortcuts"))
        item.connect("activate", self.open_keyboard_shortcuts)
        key, mod = Gtk.accelerator_parse("<Control>K")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        menu.append(item)
        self.info_menu_item = Gtk.ImageMenuItem()
        self.info_menu_item.set_image(Gtk.Image.new_from_icon_name("dialog-information-symbolic", Gtk.IconSize.MENU))
        self.info_menu_item.set_label(_("Stream Information"))
        self.info_menu_item.connect("activate", self.open_info)
        key, mod = Gtk.accelerator_parse("F2")
        self.info_menu_item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        self.info_menu_item.set_sensitive(False)
        menu.append(self.info_menu_item)
        item = Gtk.ImageMenuItem()
        item.set_image(Gtk.Image.new_from_icon_name("help-about-symbolic", Gtk.IconSize.MENU))
        item.set_label(_("About"))
        item.connect("activate", self.open_about)
        key, mod = Gtk.accelerator_parse("F1")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        menu.append(item)
        item = Gtk.ImageMenuItem(label=_("Quit"))
        image = Gtk.Image.new_from_icon_name("application-exit-symbolic", Gtk.IconSize.MENU)
        item.set_image(image)
        item.connect("activate", self.on_menu_quit)
        key, mod = Gtk.accelerator_parse("<Control>Q")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>W")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        menu.append(item)
        menu.show_all()

        # Type combox box (in preferences)
        model = Gtk.ListStore(str, str)  # PROVIDER_TYPE_ID, PROVIDER_TYPE_NAME
        model.append([PROVIDER_TYPE_URL, _("M3U URL")])
        model.append([PROVIDER_TYPE_LOCAL, _("Local M3U File")])
        model.append([PROVIDER_TYPE_XTREAM, _("Xtream API")])
        self.provider_type_combo = self.builder.get_object("provider_type_combo")
        renderer = Gtk.CellRendererText()
        self.provider_type_combo.pack_start(renderer, True)
        self.provider_type_combo.add_attribute(renderer, "text", PROVIDER_TYPE_NAME)
        self.provider_type_combo.set_model(model)
        self.provider_type_combo.set_active(0)  # Select 1st type
        self.provider_type_combo.connect("changed", self.on_provider_type_combo_changed)

        self.tv_logo.set_from_surface(self.get_surface_for_file("/usr/share/hypnotix/pictures/tv.svg", 258, 258))
        self.movies_logo.set_from_surface(self.get_surface_for_file("/usr/share/hypnotix/pictures/movies.svg", 258, 258))
        self.series_logo.set_from_surface(self.get_surface_for_file("/usr/share/hypnotix/pictures/series.svg", 258, 258))

        self.reload(page="landing_page")

        # Redownload playlists by default
        # This is going to get readjusted
        self._timerid = GLib.timeout_add_seconds(self.reload_timeout_sec, self.force_reload)

        self.window.show()
        self.playback_bar.hide()
        self.search_bar.hide()

        # Historic bitrates of the currently playing media
        self.video_bitrates = []
        self.audio_bitrates = []

    def get_surface_for_file(self, filename, width, height):
        scale = self.window.get_scale_factor()
        if width != -1:
            width = width * scale
        if height != -1:
            height = height * scale

        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, width, height)
        surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale)
        return surface

    def get_surf_based_image(self, filename, width, height):
        surf = self.get_surface_for_file(filename, width, height)
        return Gtk.Image.new_from_surface(surf)

    def add_flag(self, code, box):
        path = f"/usr/share/circle-flags-svg/{code.lower()}.svg"
        if os.path.exists(path):
            try:
                image = self.get_surf_based_image(path, -1, 32)
                box.pack_start(image, False, False, 0)
            except Exception as e:
                print("Could not load flag", path)
                print(e)
        else:
            print("Couldn't find flag", path)

    def add_badge(self, word, box, added_words):
        if word not in added_words:
            for extension in ["svg", "png"]:
                path = "/usr/share/hypnotix/pictures/badges/%s.%s" % (word, extension)
                if os.path.exists(path):
                    try:
                        image = self.get_surf_based_image(path, -1, 32)
                        box.pack_start(image, False, False, 0)
                        added_words.append(word)
                        break
                    except Exception as e:
                        print("Could not load badge", path)
                        print(e)

    def show_groups(self, widget, content_type):
        self.content_type = content_type
        self.navigate_to("categories_page")
        for child in self.categories_flowbox.get_children():
            self.categories_flowbox.remove(child)
        self.active_group = None
        found_groups = False
        for group in self.active_provider.groups:
            if group.group_type != self.content_type:
                continue
            found_groups = True
            button = Gtk.Button()
            button.connect("clicked", self.on_category_button_clicked, group)
            label = Gtk.Label()
            if self.content_type == TV_GROUP:
                label.set_text("%s (%d)" % (group.name, len(group.channels)))
            elif self.content_type == MOVIES_GROUP:
                label.set_text("%s (%d)" % (self.remove_word("VOD", group.name), len(group.channels)))
            else:
                label.set_text("%s (%d)" % (self.remove_word("SERIES", group.name), len(group.series)))
            box = Gtk.Box()
            name = group.name.lower().replace("(", " ").replace(")", " ")
            added_words = []

            found_flag = False
            for country_name in COUNTRY_CODES.keys():
                if country_name.lower() in group.name.lower():
                    found_flag = True
                    self.add_flag(COUNTRY_CODES[country_name], box)
                    break

            if not found_flag:
                print(f"No flag found for: {group.name}")

            for word in name.split():
                self.add_badge(word, box, added_words)

            box.pack_start(label, False, False, 0)
            box.set_spacing(6)
            button.add(box)
            self.categories_flowbox.add(button)
            self.categories_flowbox.show_all()

        if not found_groups:
            self.on_category_button_clicked(None, None)

    def on_category_button_clicked(self, widget, group):
        self.active_group = group
        if self.content_type == TV_GROUP:
            if group is not None:
                self.show_channels(group.channels)
            else:
                self.show_channels(self.active_provider.channels)
        elif self.content_type == MOVIES_GROUP:
            if group is not None:
                self.show_vod(group.channels)
            else:
                self.show_vod(self.active_provider.movies)
        elif self.content_type == SERIES_GROUP:
            if group is not None:
                self.show_vod(group.series)
            else:
                self.show_vod(self.active_provider.series)

    def show_favorites(self, widget=None):
        self.content_type = TV_GROUP
        channels = []
        for line in self.favorite_data:
            info, url = line.split(":::")
            channel = Channel(None, info)
            channel.url = url
            channels.append(channel)
        self.show_channels(channels, favorites=True)

    def show_channels(self, channels, favorites=False):
        self.navigate_to("channels_page", "", favorites)
        if self.content_type == TV_GROUP:
            self.sidebar.show()
            for child in self.channels_listbox.get_children():
                self.channels_listbox.remove(child)

            logos_to_refresh = []
            for channel in channels:
                image = Gtk.Image().new_from_surface(self.get_channel_surface(channel.logo_path))
                logos_to_refresh.append((channel, image))
                self.channels_listbox.add(ChannelWidget(channel, image))

            self.channels_listbox.show_all()
            self.visible_search_results = len(self.channels_listbox.get_children())
            if len(logos_to_refresh) > 0:
                self.download_channel_logos(logos_to_refresh)
        else:
            self.sidebar.hide()

    def show_vod(self, items):
        logos_to_refresh = []
        self.navigate_to("vod_page")
        for child in self.vod_flowbox.get_children():
            self.vod_flowbox.remove(child)
        for item in items:
            button = Gtk.Button()
            button.set_tooltip_text(item.name)
            if self.content_type == MOVIES_GROUP:
                button.connect("clicked", self.on_vod_movie_button_clicked, item)
            else:
                button.connect("clicked", self.on_vod_series_button_clicked, item)
            label = Gtk.Label()
            label.set_text(item.name)
            label.set_max_width_chars(30)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            image = Gtk.Image().new_from_surface(self.get_channel_surface(item.logo_path))
            logos_to_refresh.append((item, image))
            box.pack_start(image, False, False, 0)
            box.pack_start(label, False, False, 0)
            box.set_spacing(6)
            button.add(box)
            self.vod_flowbox.add(button)
        self.vod_flowbox.show_all()
        if len(logos_to_refresh) > 0:
            self.download_channel_logos(logos_to_refresh)

    def remove_word(self, word, string):
        if " " not in string:
            return string
        words = string.split()
        if word in words:
            words.remove(word)
        return " ".join(words)

    def show_episodes(self, serie):
        logos_to_refresh = []
        self.active_serie = serie
        # If we are using xtream provider
        # Load every Episodes of every Season for this Series
        if self.active_provider.type_id == "xtream":
            self.x.get_series_info_by_id(self.active_serie)

        self.navigate_to("episodes_page")
        for child in self.episodes_box.get_children():
            self.episodes_box.remove(child)
        for season_name in serie.seasons.keys():
            season = serie.seasons[season_name]
            label = Gtk.Label()
            label.set_text(_("Season %s") % season_name)
            label.get_style_context().add_class("season-label")
            flowbox = Gtk.FlowBox()
            self.episodes_box.pack_start(label, False, False, 0)
            self.episodes_box.pack_start(flowbox, False, False, 0)
            for episode_name in season.episodes.keys():
                episode = season.episodes[episode_name]
                button = Gtk.Button()
                button.set_tooltip_text(episode_name)
                button.connect("clicked", self.on_episode_button_clicked, episode)
                label = Gtk.Label()
                label.set_text(_("Episode %s") % episode_name)
                label.set_max_width_chars(30)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                image = Gtk.Image().new_from_surface(self.get_channel_surface(episode.logo_path))
                logos_to_refresh.append((episode, image))
                box.pack_start(image, False, False, 0)
                box.pack_start(label, False, False, 0)
                box.set_spacing(6)
                button.add(box)
                flowbox.add(button)
        self.episodes_box.show_all()

        if len(logos_to_refresh) > 0:
            self.download_channel_logos(logos_to_refresh)

    def on_vod_movie_button_clicked(self, widget, channel):
        self.active_channel = channel
        self.show_channels(None)
        self.play_async(channel)

    def on_episode_button_clicked(self, widget, channel):
        self.active_channel = channel
        self.show_channels(None)
        self.play_async(channel)

    def on_vod_series_button_clicked(self, widget, serie):
        self.show_episodes(serie)

    def bind_setting_widget(self, key, widget):
        widget.set_text(self.settings.get_string(key))
        widget.connect("changed", self.on_entry_changed, key)

    def on_entry_changed(self, widget, key):
        self.settings.set_string(key, widget.get_text())

    def on_ytdlp_local_switch_activated(self, widget, data=None):
        self.settings.set_boolean("use-local-ytdlp", widget.get_active())
        if widget.get_active():
            self.update_ytdlp()

    def update_ytdlp(self, widget=None):
        path = os.path.expanduser("~/.cache/hypnotix/yt-dlp")
        os.chdir(path)
        if os.path.exists("yt-dlp"):
            subprocess.getoutput("./yt-dlp --update")
        else:
            subprocess.getoutput("wget https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp")
            subprocess.getoutput("chmod a+rx ./yt-dlp")
        self.ytdlp_local_version_label.set_text(subprocess.getoutput("~/.cache/hypnotix/yt-dlp/yt-dlp --version"))

    @async_function
    def download_channel_logos(self, logos_to_refresh):
        headers = {
            "User-Agent": self.settings.get_string("user-agent"),
            "Referer": self.settings.get_string("http-referer"),
        }
        for channel, image in logos_to_refresh:
            if channel.logo_path is None:
                continue
            if os.path.isfile(channel.logo_path):
                continue
            try:
                response = requests.get(channel.logo, headers=headers, timeout=10, stream=True)
                if response.status_code == 200:
                    response.raw.decode_content = True
                    with open(channel.logo_path, "wb") as f:
                        shutil.copyfileobj(response.raw, f)
                        self.refresh_channel_logo(channel, image)
            except Exception as e:
                print(e)

    @idle_function
    def refresh_channel_logo(self, channel, image):
        image.set_from_surface(self.get_channel_surface(channel.logo_path))

    def get_channel_surface(self, path):
        try:
            if self.content_type == TV_GROUP:
                surface = self.get_surface_for_file(path, 64, 32)
            elif self.content_type == MOVIES_GROUP:
                surface = self.get_surface_for_file(path, 200, 200)
            else:
                surface = self.get_surface_for_file(path, 200, 200)
        except Exception:
            surface = self.get_surface_for_file("/usr/share/hypnotix/generic_tv_logo.png", 22, 22)
        return surface

    def on_go_back_button(self, widget):
        self.navigate_to(self.back_page)
        if self.active_channel is not None:
            self.playback_bar.show()
        if self.active_group and self.back_page == "categories_page":
            self.init_channels_listbox()

    def on_search_button_toggled(self, widget):
        if self.search_button.get_active():
            self.search_bar.show()
            self.search_bar.grab_focus()
        else:
            self.search_bar.hide()

    def on_search_bar(self, widget):
        self.content_type = TV_GROUP
        search_bar_text = unidecode(self.search_bar.get_text()).lower()
        if search_bar_text != self.latest_search_bar_text:
            self.latest_search_bar_text = search_bar_text
            self.search_bar.set_sensitive(False)
            GLib.timeout_add_seconds(0.1, self.on_search)

    def on_search(self):
        def filter_func(child):
            search_bar_text = unidecode(self.search_bar.get_text()).lower()
            label_text = unidecode(child.get_children()[0].get_children()[0].get_children()[1].get_text()).lower()
            if search_bar_text in label_text:
                self.visible_search_results += 1
                return True
            else:
                return False

        self.visible_search_results = 0
        self.channels_listbox.set_filter_func(filter_func)
        if not self.channels_listbox.get_children():
            self.show_channels(self.active_provider.channels)
        print("Filtering %d channel names containing the string '%s'..." % (len(self.channels_listbox.get_children()), self.latest_search_bar_text))
        if self.visible_search_results == 0:
            self.status(_("No channels found"))
        else:
            self.status(None)
        self.search_bar.set_sensitive(True)
        self.search_bar.grab_focus_without_selecting()
        self.navigate_to("channels_page")

    def init_channels_listbox(self):
        self.latest_search_bar_text = None
        self.active_group = None
        for child in self.channels_listbox.get_children():
            self.channels_listbox.remove(child)
        self.channels_listbox.invalidate_filter()
        self.visible_search_results = 0

    @idle_function
    def navigate_to(self, page, name="", favorites=False):
        self.go_back_button.show()
        self.search_button.show()
        self.fullscreen_button.hide()
        self.stack.set_visible_child_name(page)
        provider = self.active_provider
        self.back_page = "landing_page"
        if page == "landing_page":
            self.headerbar.set_title("Hypnotix")
            if provider is None:
                self.current_provider_label.set_text(_("No provider selected"))
                self.tv_label.set_text(_("TV Channels (%d)") % 0)
                self.movies_label.set_text(_("Movies (%d)") % 0)
                self.series_label.set_text(_("Series (%d)") % 0)
                self.tv_button.set_sensitive(False)
                self.movies_button.set_sensitive(False)
                self.series_button.set_sensitive(False)
            else:
                self.current_provider_label.set_text(provider.name)
                self.tv_label.set_text(_("TV Channels (%d)") % len(provider.channels))
                self.movies_label.set_text(_("Movies (%d)") % len(provider.movies))
                self.series_label.set_text(_("Series (%d)") % len(provider.series))
                self.tv_button.set_sensitive(len(provider.channels) > 0)
                self.movies_button.set_sensitive(len(provider.movies) > 0)
                self.series_button.set_sensitive(len(provider.series) > 0)
            self.go_back_button.hide()
        elif page == "categories_page":
            self.headerbar.set_title(provider.name)
            if self.content_type == TV_GROUP:
                self.headerbar.set_subtitle(_("TV Channels"))
            elif self.content_type == MOVIES_GROUP:
                self.headerbar.set_subtitle(_("Movies"))
            else:
                self.headerbar.set_subtitle(_("Series"))
        elif page == "channels_page":
            self.fullscreen_button.show()
            self.playback_bar.hide()
            if favorites:
                self.headerbar.set_title("Hypnotix")
                self.headerbar.set_subtitle(_("Favorites"))
            else:
                self.headerbar.set_title(provider.name)
                if self.content_type == TV_GROUP:
                    if self.active_group is None:
                        self.headerbar.set_subtitle(_("TV Channels"))
                    else:
                        self.back_page = "categories_page"
                        self.headerbar.set_subtitle(_("TV Channels > %s") % self.active_group.name)
                elif self.content_type == MOVIES_GROUP:
                    self.headerbar.set_subtitle(self.active_channel.name)
                    self.back_page = "vod_page"
                else:
                    self.headerbar.set_subtitle(self.active_channel.name)
                    self.back_page = "episodes_page"
        elif page == "vod_page":
            self.headerbar.set_title(provider.name)
            if self.content_type == MOVIES_GROUP:
                if self.active_group is None:
                    self.headerbar.set_subtitle(_("Movies"))
                else:
                    self.back_page = "categories_page"
                    self.headerbar.set_subtitle(_("Movies > %s") % self.active_group.name)
            else:
                if self.active_group is None:
                    self.headerbar.set_subtitle(_("Series"))
                else:
                    self.back_page = "categories_page"
                    self.headerbar.set_subtitle(_("Series > %s") % self.active_group.name)
        elif page == "episodes_page":
            self.back_page = "vod_page"
            self.headerbar.set_title(provider.name)
            self.headerbar.set_subtitle(self.active_serie.name)
        elif page == "new_channel_page":
            self.headerbar.set_title("Hypnotix")
            self.headerbar.set_subtitle(_("New Channel"))
        elif page == "preferences_page":
            self.headerbar.set_title("Hypnotix")
            self.headerbar.set_subtitle(_("Preferences"))
        elif page == "providers_page":
            self.headerbar.set_title("Hypnotix")
            self.headerbar.set_subtitle(_("Providers"))
        elif page == "add_page":
            self.back_page = "providers_page"
            self.headerbar.set_title("Hypnotix")
            if self.edit_mode:
                self.headerbar.set_subtitle(_("Edit %s") % name)
            else:
                self.headerbar.set_subtitle(_("Add a new provider"))
        elif page == "delete_page":
            self.back_page = "providers_page"
            self.headerbar.set_title("Hypnotix")
            self.headerbar.set_subtitle(_("Delete %s") % name)
        elif page == "reset_page":
            self.back_page = "providers_page"
            self.headerbar.set_title("Hypnotix")
            self.headerbar.set_subtitle(_("Reset providers"))

    def open_keyboard_shortcuts(self, widget):
        gladefile = "/usr/share/hypnotix/shortcuts.ui"
        builder = Gtk.Builder()
        builder.set_translation_domain(APP)
        builder.add_from_file(gladefile)
        window = builder.get_object("shortcuts")
        window.set_title(_("Hypnotix"))
        window.show()

    def on_favorite_button_toggled(self, widget):
        if self.page_is_loading:
            return
        name = self.active_channel.name
        data = f"{self.active_channel.info}:::{self.active_channel.url}"
        if widget.get_active() and data not in self.favorite_data:
            print (f"Adding {name} to favorites")
            self.favorite_data.append(data)
        elif widget.get_active() == False and data in self.favorite_data:
            print (f"Removing {name} from favorites")
            self.favorite_data.remove(data)
        self.favorite_button_image.set_from_icon_name("starred-symbolic" if widget.get_active() else "non-starred-symbolic", Gtk.IconSize.BUTTON)
        self.manager.save_favorites(self.favorite_data)

    def on_channel_activated(self, box, widget):
        self.active_channel = widget.channel
        self.play_async(self.active_channel)

    def on_prev_channel(self):
        if self.stack.get_visible_child_name() == "channels_page":
            self.channels_listbox.do_move_cursor(self.channels_listbox, Gtk.MovementStep.DISPLAY_LINES, -1)
            self.channels_listbox.do_activate_cursor_row(self.channels_listbox)

    def on_next_channel(self):
        if self.stack.get_visible_child_name() == "channels_page":
            self.channels_listbox.do_move_cursor(self.channels_listbox, Gtk.MovementStep.DISPLAY_LINES, 1)
            self.channels_listbox.do_activate_cursor_row(self.channels_listbox)

    @async_function
    def play_async(self, channel):
        print("CHANNEL: '%s' (%s)" % (channel.name, channel.url))
        if channel is not None and channel.url is not None:
            # os.system("mpv --wid=%s %s &" % (self.wid, channel.url))
            # self.mpv_drawing_area.show()
            self.info_menu_item.set_sensitive(False)
            self.before_play(channel)
            self.reinit_mpv()
            self.mpv.play(channel.url)
            self.mpv.wait_until_playing()
            self.after_play(channel)

    @idle_function
    def before_play(self, channel):
        self.channel_stack.set_visible_child_name("channel_page")
        self.mpv_stack.set_visible_child_name("spinner_page")
        self.video_properties.clear()
        self.video_properties[_("General")] = {}
        self.video_properties[_("Color")] = {}

        self.audio_properties.clear()
        self.audio_properties[_("General")] = {}
        self.audio_properties[_("Layout")] = {}

        self.video_bitrates.clear()
        self.audio_bitrates.clear()
        self.spinner.start()

        self.label_channel_name.set_text(channel.name)
        self.label_channel_url.set_text(channel.url)

        self.page_is_loading = True
        data = f"{channel.info}:::{channel.url}"
        if data in self.favorite_data:
            self.favorite_button.set_active(True)
            self.favorite_button_image.set_from_icon_name("starred-symbolic", Gtk.IconSize.BUTTON)
            self.favorite_button.set_tooltip_text(_("Remove from favorites"))
        else:
            self.favorite_button.set_active(False)
            self.favorite_button_image.set_from_icon_name("non-starred-symbolic", Gtk.IconSize.BUTTON)
            self.favorite_button.set_tooltip_text(_("Add to favorites"))
        self.page_is_loading = False

    @idle_function
    def after_play(self, channel):
        self.mpv_stack.set_visible_child_name("player_page")
        self.spinner.stop()
        self.playback_label.set_text(channel.name)
        self.info_revealer.set_reveal_child(False)
        if self.content_type == MOVIES_GROUP:
            self.get_imdb_details(channel.name)
        elif self.content_type == SERIES_GROUP:
            self.get_imdb_details(self.active_serie.name)
        self.info_menu_item.set_sensitive(True)
        self.monitor_playback()

    def monitor_playback(self):
        self.mpv.observe_property("video-params", self.on_video_params)
        self.mpv.observe_property("video-format", self.on_video_format)
        self.mpv.observe_property("audio-params", self.on_audio_params)
        self.mpv.observe_property("audio-codec", self.on_audio_codec)
        self.mpv.observe_property("video-bitrate", self.on_bitrate)
        self.mpv.observe_property("audio-bitrate", self.on_bitrate)

    @idle_function
    def on_bitrate(self, prop, bitrate):
        if not bitrate or prop not in ["video-bitrate", "audio-bitrate"]:
            return

        """
        Only update the bitrates when the info window is open unless
        we don't have any data yet.
        """
        if _("Average Bitrate") in self.video_properties:
            if _("Average Bitrate") in self.audio_properties:
                if not self.info_window.props.visible:
                    return

        rates = {"video": self.video_bitrates, "audio": self.audio_bitrates}
        rate = "video"
        if prop == "audio-bitrate":
            rate = "audio"

        rates[rate].append(int(bitrate) / 1000.0)
        rates[rate] = rates[rate][-30:]
        br = sum(rates[rate]) / float(len(rates[rate]))

        if rate == "video":
            self.video_properties[_("General")][_("Average Bitrate")] = "%.f Kbps" % br
        else:
            self.audio_properties[_("General")][_("Average Bitrate")] = "%.f Kbps" % br

    @idle_function
    def on_video_params(self, property, params):
        if not params or not type(params) == dict:
            return
        if "w" in params and "h" in params:
            self.video_properties[_("General")][_("Dimensions")] = "%sx%s" % (params["w"],params["h"])
        if "aspect" in params:
            aspect = round(float(params["aspect"]), 2)
            self.video_properties[_("General")][_("Aspect")] = "%s" % aspect
        if "pixelformat" in params:
            self.video_properties[_("Color")][_("Pixel Format")] = params["pixelformat"]
        if "gamma" in params:
            self.video_properties[_("Color")][_("Gamma")] = params["gamma"]
        if "average-bpp" in params:
            self.video_properties[_("Color")][_("Bits Per Pixel")] = params["average-bpp"]

    @idle_function
    def on_video_format(self, property, vformat):
        if not vformat:
            return
        self.video_properties[_("General")][_("Codec")] = vformat

    @idle_function
    def on_audio_params(self, property, params):
        if not params or not type(params) == dict:
            return
        if "channels" in params:
            chans = params["channels"]
            if "5.1" in chans or "7.1" in chans:
                chans += " " + _("surround sound")
            self.audio_properties[_("Layout")][_("Channels")] = chans
        if "samplerate" in params:
            sr = float(params["samplerate"]) / 1000.0
            self.audio_properties[_("General")][_("Sample Rate")] = "%.1f KHz" % sr
        if "format" in params:
            fmt = params["format"]
            if fmt in AUDIO_SAMPLE_FORMATS:
                fmt = AUDIO_SAMPLE_FORMATS[fmt]
            self.audio_properties[_("General")][_("Format")] = fmt
        if "channel-count" in params:
            self.audio_properties[_("Layout")][_("Channel Count")] = params["channel-count"]

    @idle_function
    def on_audio_codec(self, property, codec):
        if not codec:
            return
        self.audio_properties[_("General")][_("Codec")] = codec.split()[0]

    @async_function
    def get_imdb_details(self, name):
        movies = self.ia.search_movie(name)
        match = None
        for movie in movies:
            self.ia.update(movie)
            if movie.get("plot") is not None:
                match = movie
                break
        self.refresh_info_section(match)

    @idle_function
    def refresh_info_section(self, movie):
        if movie is not None:
            self.set_imdb_info(movie, "title", self.info_name_label)
            self.set_imdb_info(movie, "plot outline", self.info_plot_label)
            self.set_imdb_info(movie, "rating", self.info_rating_label)
            self.set_imdb_info(movie, "votes", self.info_votes_label)
            self.set_imdb_info(movie, "year", self.info_year_label)
            self.set_imdb_info(movie, "genres", self.info_genre_label)
            self.set_imdb_info(movie, "runtimes", self.info_duration_label)
            self.set_imdb_info(movie, "certificates", self.info_pg_label)
            self.info_revealer.set_reveal_child(True)

    def set_imdb_info(self, movie, field, widget):
        value = movie.get(field)
        if value is not None:
            if field == "plot":
                value = value[0].split("::")[0]
            elif field == "genres":
                value = ", ".join(value)
            elif field == "certificates":
                pg = ""
                for v in value:
                    if "United States:" in v:
                        pg = v.split(":")[1]
                        break
                value = pg
            elif field == "runtimes":
                value = value[0]
                n = int(value)
                hours = n // 60
                minutes = n % 60
                value = "%dh %dmin" % (hours, minutes)
        value = str(value).strip()
        if value == "" or value.lower() == "none":
            widget.hide()
        else:
            widget.set_text(value)
            widget.show()

    def on_close_info_button(self, widget):
        self.info_revealer.set_reveal_child(False)

    def on_stop_button(self, widget):
        self.mpv.stop()
        # self.mpv_drawing_area.hide()
        self.info_revealer.set_reveal_child(False)
        self.active_channel = None
        self.info_menu_item.set_sensitive(False)
        self.playback_bar.hide()

    def on_pause_button(self, widget):
        self.mpv.pause = not self.mpv.pause

    def on_show_button(self, widget):
        self.navigate_to("channels_page")

    def open_providers(self, widget):
        self.navigate_to("providers_page")

    @idle_function
    def refresh_providers_page(self):
        for child in self.providers_flowbox.get_children():
            self.providers_flowbox.remove(child)
        for provider in self.providers:
            labels_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            image = Gtk.Image()
            image.set_from_icon_name("tv-symbolic", Gtk.IconSize.BUTTON)
            labels_box.pack_start(image, False, False, 0)
            label = Gtk.Label()
            label.set_markup("<b>%s</b>" % provider.name)
            labels_box.pack_start(label, False, False, 0)
            num = len(provider.channels)
            if num > 0:
                label = Gtk.Label()
                label.set_text(gettext.ngettext("%d TV channel", "%d TV channels", num) % num)
                labels_box.pack_start(label, False, False, 0)
            num = len(provider.movies)
            if num > 0:
                label = Gtk.Label()
                label.set_text(gettext.ngettext("%d movie", "%d movies", num) % num)
                labels_box.pack_start(label, False, False, 0)
            num = len(provider.series)
            if num > 0:
                label = Gtk.Label()
                label.set_text(gettext.ngettext("%d series", "%d series", num) % num)
                labels_box.pack_start(label, False, False, 0)
            button = Gtk.Button()
            button.connect("clicked", self.on_provider_selected, provider)
            label = Gtk.Label()
            if provider == self.active_provider:
                label.set_text("%s %d (active)" % (provider.name, len(provider.channels)))
            else:
                label.set_text(provider.name)
            button.add(labels_box)
            box = Gtk.Box()
            box.pack_start(button, True, True, 0)
            box.set_spacing(6)

            # Edit button
            button = Gtk.Button()
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.connect("clicked", self.on_edit_button_clicked, provider)
            image = Gtk.Image()
            image.set_from_icon_name("xapp-edit-symbolic", Gtk.IconSize.BUTTON)
            button.set_tooltip_text(_("Edit"))
            button.add(image)
            box.pack_start(button, False, False, 0)

            # Clear icon cache button
            button = Gtk.Button()
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.connect("clicked", self.on_clear_icon_cache_button_clicked, provider)
            image = Gtk.Image()
            image.set_from_icon_name("edit-clear-symbolic", Gtk.IconSize.BUTTON)
            button.set_tooltip_text(_("Clear icon cache"))
            button.add(image)
            box.pack_start(button, False, False, 0)

            # Remove button
            button = Gtk.Button()
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.connect("clicked", self.on_delete_button_clicked, provider)
            image = Gtk.Image()
            image.set_from_icon_name("edit-delete-symbolic", Gtk.IconSize.BUTTON)
            button.set_tooltip_text(_("Remove"))
            button.add(image)
            box.pack_start(button, False, False, 0)

            self.providers_flowbox.add(box)

        self.providers_flowbox.show_all()

    def on_provider_selected(self, widget, provider):
        self.active_provider = provider
        self.settings.set_string("active-provider", provider.name)
        self.init_channels_listbox()
        self.navigate_to("landing_page")

    def open_new_channel(self, widget):
        self.new_name_entry.grab_focus()
        self.new_name_entry.set_text("")
        self.new_url_entry.set_text("")
        self.new_logo_entry.set_text("")
        self.new_ok_button.set_sensitive(False)
        self.navigate_to("new_channel_page")

    def open_preferences(self, widget):
        self.navigate_to("preferences_page")

    def on_new_provider_button(self, widget):
        self.name_entry.set_text("")
        self.url_entry.set_text("")
        self.set_provider_type(PROVIDER_TYPE_URL)
        model = self.provider_type_combo.get_model()
        iter = model.get_iter_first()
        while iter:
            type_id = model.get_value(iter, PROVIDER_TYPE_ID)
            if type_id == PROVIDER_TYPE_URL:
                self.provider_type_combo.set_active_iter(iter)
                break
            iter = model.iter_next(iter)
        self.navigate_to("add_page")
        self.edit_mode = False
        self.provider_ok_button.set_sensitive(False)
        self.name_entry.grab_focus()

    def on_reset_providers_button(self, widget):
        self.navigate_to("reset_page")

    def on_close_info_window(self, widget, event):
        self.info_window.hide()
        return True

    @async_function
    def on_clear_icon_cache_button_clicked(self, widget, provider: Provider):
        for channel in provider.channels:
            if channel.logo_path:
                Path(channel.logo_path).unlink(missing_ok=True)

    def on_delete_button_clicked(self, widget, provider):
        self.navigate_to("delete_page", provider.name)
        self.marked_provider = provider

    def on_edit_button_clicked(self, widget, provider):
        self.marked_provider = provider
        self.name_entry.set_text(provider.name)
        self.username_entry.set_text(provider.username)
        self.password_entry.set_text(provider.password)
        self.epg_entry.set_text(provider.epg)
        if provider.type_id == PROVIDER_TYPE_LOCAL:
            self.url_entry.set_text("")
            self.path_entry.set_text(provider.url)
        else:
            self.path_entry.set_text("")
            self.url_entry.set_text(provider.url)

        model = self.provider_type_combo.get_model()
        iter = model.get_iter_first()
        while iter:
            type_id = model.get_value(iter, PROVIDER_TYPE_ID)
            if provider.type_id == type_id:
                self.provider_type_combo.set_active_iter(iter)
                break
            iter = model.iter_next(iter)
        self.edit_mode = True
        self.navigate_to("add_page", provider.name)
        self.provider_ok_button.set_sensitive(True)
        self.name_entry.grab_focus()
        self.set_provider_type(provider.type_id)

    def on_delete_no_button(self, widget):
        self.navigate_to("providers_page")

    def on_reset_no_button(self, widget):
        self.navigate_to("providers_page")

    def on_delete_yes_button(self, widget):
        self.providers.remove(self.marked_provider)
        if self.active_provider == self.marked_provider:
            self.active_provider = None
        self.marked_provider = None
        self.save()

    def on_reset_yes_button(self, widget):
        self.settings.reset("providers")
        self.reload(page="providers_page")

    def on_browse_button(self, widget):
        dialog = Gtk.FileChooserDialog(parent=self.window, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        filter_m3u = Gtk.FileFilter()
        filter_m3u.set_name(_("M3U Playlists"))
        filter_m3u.add_pattern("*.m3u*")
        dialog.add_filter(filter_m3u)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.path_entry.set_text(dialog.get_filename())
        dialog.destroy()

    ######################
    #### PREFERENCES #####
    ######################

    def save(self):
        provider_strings = []
        for provider in self.providers:
            provider_strings.append(provider.get_info())
        self.settings.set_strv("providers", provider_strings)
        self.reload(page="providers_page", refresh=True)

    def on_provider_type_combo_changed(self, widget):
        type_id = self.provider_type_combo.get_model()[self.provider_type_combo.get_active()][PROVIDER_TYPE_ID]
        self.set_provider_type(type_id)

    def set_provider_type(self, type_id):
        widgets = [
            self.path_entry,
            self.path_label,
            self.browse_button,
            self.url_entry,
            self.url_label,
            self.username_entry,
            self.username_label,
            self.password_entry,
            self.password_label,
            self.epg_label,
            self.epg_entry,
        ]
        for widget in widgets:
            widget.hide()
        visible_widgets = []
        if type_id == PROVIDER_TYPE_URL:
            visible_widgets.append(self.url_entry)
            visible_widgets.append(self.url_label)
            visible_widgets.append(self.epg_label)
            visible_widgets.append(self.epg_entry)
        elif type_id == PROVIDER_TYPE_LOCAL:
            visible_widgets.append(self.path_entry)
            visible_widgets.append(self.path_label)
            visible_widgets.append(self.browse_button)
        elif type_id == PROVIDER_TYPE_XTREAM:
            visible_widgets.append(self.url_entry)
            visible_widgets.append(self.url_label)
            visible_widgets.append(self.username_entry)
            visible_widgets.append(self.username_label)
            visible_widgets.append(self.password_entry)
            visible_widgets.append(self.password_label)
            visible_widgets.append(self.epg_label)
            visible_widgets.append(self.epg_entry)
        else:
            print("Incorrect provider type: ", type_id)

        for widget in visible_widgets:
            widget.show()

    def on_provider_ok_button(self, widget):
        type_id = self.provider_type_combo.get_model()[self.provider_type_combo.get_active()][PROVIDER_TYPE_ID]
        name = self.name_entry.get_text()
        if self.edit_mode:
            provider = self.marked_provider
            provider.name = name
        else:
            provider = Provider(name=name, provider_info=None)
            self.providers.append(provider)
        provider.type_id = type_id
        provider.url = self.get_url()
        provider.username = self.username_entry.get_text()
        provider.password = self.password_entry.get_text()
        provider.epg = self.epg_entry.get_text()
        self.save()

    def on_new_ok_button(self, widget):
        name = self.new_name_entry.get_text()
        url = self.new_url_entry.get_text()
        logo = self.new_logo_entry.get_text()
        data = f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" tvg-id="{name}" group-title="",{name}:::{url}'
        if data not in self.favorite_data:
            print (f"Adding {name} to favorites")
            self.favorite_data.append(data)
        self.manager.save_favorites(self.favorite_data)
        self.show_favorites()

    def on_new_cancel_button(self, widget):
        self.navigate_to("landing_page")

    def on_provider_cancel_button(self, widget):
        self.navigate_to("providers_page")

    def toggle_ok_sensitivity(self, widget=None):
        if self.name_entry.get_text() == "":
            self.provider_ok_button.set_sensitive(False)
        elif self.get_url() == "":
            self.provider_ok_button.set_sensitive(False)
        else:
            self.provider_ok_button.set_sensitive(True)

    def toggle_new_ok_sensitivity(self, widget=None):
        self.new_ok_button.set_sensitive(True)
        if self.new_name_entry.get_text() == "":
            self.new_ok_button.set_sensitive(False)
        for widget in (self.new_url_entry, self.new_logo_entry):
            if "://" not in widget.get_text():
                self.new_ok_button.set_sensitive(False)

    def get_url(self):
        type_id = self.provider_type_combo.get_model()[self.provider_type_combo.get_active()][PROVIDER_TYPE_ID]
        if type_id == PROVIDER_TYPE_LOCAL:
            widget = self.path_entry
        else:
            widget = self.url_entry

        url = widget.get_text().strip()
        if url == "":
            return ""
        if "://" not in url:
            if type_id == PROVIDER_TYPE_LOCAL:
                url = "file://%s" % url
            else:
                url = "http://%s" % url
        return url

    ##############################
    def open_info(self, widget):
        """
        Display a dialog containing information about the currently
        playing stream based on properties emitted by MPV during playback
        """
        sections = [
            self.video_properties_box,
            self.colour_properties_box,
            self.audio_properties_box,
            self.layout_properties_box,
        ]

        for section in sections:
            for child in section.get_children():
                section.remove(child)

        props = [
            self.video_properties[_("General")],
            self.video_properties[_("Color")],
            self.audio_properties[_("General")],
            self.audio_properties[_("Layout")],
        ]

        for section, props in zip(sections, props):
            for prop_k, prop_v in props.items():
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                    margin_left=24, margin_right=24, margin_top=6, margin_bottom=6)
                box.set_halign(Gtk.Align.FILL)
                box_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                    spacing=14 * 12, expand=True)
                k = Gtk.Label(label=prop_k, margin_top=12, margin_bottom=12)
                k.set_halign(Gtk.Align.START)
                v = Gtk.Label(label=prop_v, margin_top=12, margin_bottom=12)

                def update_bitrate(label, properties):
                    """
                    Periodically update a label displaying the average
                    bitrate whilst the info dialog is visible.
                    """
                    if not self.info_window.props.visible:
                        return False
                    if _("Average Bitrate") in properties:
                        label.set_text(properties[_("Average Bitrate")])
                    return True

                if prop_k == _("Average Bitrate") and props == self.video_properties[_("General")]:
                    cb = partial(update_bitrate, v, props)
                    GLib.timeout_add_seconds(UPDATE_BR_INTERVAL, cb)

                elif prop_k == _("Average Bitrate") and props == self.audio_properties[_("General")]:
                    cb = partial(update_bitrate, v, props)
                    GLib.timeout_add_seconds(UPDATE_BR_INTERVAL, cb)

                v.set_halign(Gtk.Align.CENTER)
                box_inner.pack_start(k, True, True, 0)
                box_inner.pack_end(v, False, False, 0)
                box.add(box_inner)
                seperator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                section.add(seperator)
                section.add(box)
        self.info_window.show_all()

    def open_about(self, widget):
        dlg = Gtk.AboutDialog()
        dlg.set_transient_for(self.window)
        dlg.set_title(_("About"))
        dlg.set_program_name(_("Hypnotix"))
        dlg.set_comments(_("Watch TV"))
        try:
            h = open("/usr/share/common-licenses/GPL", encoding="utf-8")
            s = h.readlines()
            gpl = ""
            for line in s:
                gpl += line
            h.close()
            dlg.set_license(gpl)
        except Exception as e:
            print(e)

        dlg.set_version("__DEB_VERSION__")
        dlg.set_icon_name("hypnotix")
        dlg.set_logo_icon_name("hypnotix")
        dlg.set_website("https://www.github.com/linuxmint/hypnotix")

        def close(w, res):
            if res == Gtk.ResponseType.CANCEL or res == Gtk.ResponseType.DELETE_EVENT:
                w.destroy()

        dlg.connect("response", close)
        dlg.show()

    def on_menu_quit(self, widget):
        self.application.quit()

    def on_key_press_event(self, widget, event):
        # Get any active, but not pressed modifiers, like CapsLock and NumLock
        persistant_modifiers = Gtk.accelerator_get_default_mod_mask()

        # Determine the actively pressed modifier
        modifier = event.get_state() & persistant_modifiers
        # Bool of Control or Shift modifier states
        ctrl = modifier == Gdk.ModifierType.CONTROL_MASK
        shift = modifier == Gdk.ModifierType.SHIFT_MASK

        if ctrl and event.keyval == Gdk.KEY_r:
            self.reload(page=None, refresh=True)
        elif ctrl and event.keyval == Gdk.KEY_f:
            if self.search_button.get_active():
                self.search_button.set_active(False)
            else:
                self.search_button.set_active(True)
        elif event.keyval == Gdk.KEY_F11 or \
                (event.keyval == Gdk.KEY_f and not ctrl and type(widget.get_focus()) != gi.repository.Gtk.SearchEntry) or \
                (self.fullscreen and event.keyval == Gdk.KEY_Escape):
            self.toggle_fullscreen()
        elif event.keyval == Gdk.KEY_Left:
            self.on_prev_channel()
        elif event.keyval == Gdk.KEY_Right:
            self.on_next_channel()
        # elif event.keyval == Gdk.KEY_Up:
        #     # Up of in the list
        #     pass
        # elif event.keyval == Gdk.KEY_Down:
        #     # Down of in the list
        #     pass
        # elif event.keyval == Gdk.KEY_Escape:
        #    # Go back one level
        #    pass
        # #elif event.keyval == Gdk.KEY_Return:
        #     # Same as click
        # #    pass

    @async_function
    def reload(self, page=None, refresh=False):
        self.favorite_data = self.manager.load_favorites()
        self.status(_("Loading providers..."))
        self.providers = []
        for provider_info in self.settings.get_strv("providers"):
            try:
                provider = Provider(name=None, provider_info=provider_info)

                # Add provider to list. This must be done so that it shows up in the
                # list of providers for editing.
                self.providers.append(provider)

                if provider.type_id != "xtream":
                    # Download M3U
                    if refresh:
                        self.status(_("Downloading playlist..."), provider)
                    else:
                        self.status(_("Getting playlist..."), provider)
                    ret = self.manager.get_playlist(provider, refresh=refresh)
                    if ret:
                        self.status(_("Checking playlist..."), provider)
                        if self.manager.check_playlist(provider):
                            self.status(_("Loading channels..."), provider)
                            self.manager.load_channels(provider)
                            if provider.name == self.settings.get_string("active-provider"):
                                self.active_provider = provider
                            self.status(None)
                            print("%s: %d channels, %d groups, %d series, %d movies" % (provider.name, \
                                len(provider.channels), len(provider.groups), len(provider.series), len(provider.movies)))
                    else:
                        self.status(_("Failed to download playlist from %s") %  provider.name, provider)

                else:
                    # Load xtream class
                    from xtream import XTream

                    # Download via Xtream
                    self.x = XTream(
                        provider.name,
                        provider.username,
                        provider.password,
                        provider.url,
                        hide_adult_content=False,
                        cache_path=PROVIDERS_PATH,
                    )
                    if self.x.auth_data != {}:
                        print("XTREAM `{}` Loading Channels".format(provider.name))
                        # Save default cursor
                        current_cursor = self.window.get_window().get_cursor()
                        # Set waiting cursor
                        self.window.get_window().set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "wait"))
                        # Load data
                        self.x.load_iptv()
                        # Restore default cursor
                        self.window.get_window().set_cursor(current_cursor)
                        # Inform Provider of data
                        provider.channels = self.x.channels
                        provider.movies = self.x.movies
                        provider.series = self.x.series
                        provider.groups = self.x.groups

                        # Change redownload timeout
                        self.reload_timeout_sec = 60 * 60 * 2  # 2 hours
                        if self._timerid:
                            GLib.source_remove(self._timerid)
                        self._timerid = GLib.timeout_add_seconds(self.reload_timeout_sec, self.force_reload)

                        # If no errors, approve provider
                        if provider.name == self.settings.get_string("active-provider"):
                            self.active_provider = provider
                        self.status(None)
                    else:
                        print("XTREAM Authentication Failed")

            except Exception as e:
                print(e)
                traceback.print_exc()
                print("Couldn't parse provider info: ", provider_info)

        # If there are more than 1 providers and no Active Provider, set to the first one
        if len(self.providers) > 0 and self.active_provider is None:
            self.active_provider = self.providers[0]

        self.refresh_providers_page()

        if page is not None:
            self.navigate_to(page)
        self.status(None)
        self.latest_search_bar_text = None

    def force_reload(self):
        self.reload(page=None, refresh=True)
        return False

    @idle_function
    def status(self, string, provider=None):
        if string is None:
            self.status_label.set_text("")
            self.status_label.hide()
            return
        self.status_label.show()
        if provider is not None:
            self.status_label.set_text("%s: %s" % (provider.name, string))
            print("%s: %s" % (provider.name, string))
        else:
            self.status_label.set_text(string)
            print(string)

    def on_mpv_drawing_area_realize(self, widget):
        self.reinit_mpv()

    def reinit_mpv(self):
        if self.mpv is not None:
            self.mpv.stop()
        options = {}
        try:
            mpv_options = self.settings.get_string("mpv-options")
            if ("=") in mpv_options:
                pairs = mpv_options.split()
                for pair in pairs:
                    key, value = pair.split("=")
                    options[key] = value
        except Exception as e:
            print("Could not parse MPV options!")
            print(e)

        options["user_agent"] = self.settings.get_string("user-agent")
        options["referrer"] = self.settings.get_string("http-referer")

        while not self.mpv_drawing_area.get_window() and not Gtk.events_pending():
            time.sleep(0.1)

        osc = True
        if "osc" in options:
            # To prevent 'multiple values for keyword argument'!
            osc = options.pop("osc") != "no"

        self.mpv = mpv.MPV(
            **options,
            script_opts="osc-layout=box,osc-seekbarstyle=bar,osc-deadzonesize=0,osc-minmousemove=3",
            input_default_bindings=True,
            input_vo_keyboard=True,
            osc=osc,
            ytdl=True,
            wid=str(self.mpv_drawing_area.get_window().get_xid())
        )

    def on_mpv_drawing_area_draw(self, widget, cr):
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.paint()

    def toggle_fullscreen(self):
        if self.stack.get_visible_child_name() == "channels_page":
            # Toggle state
            self.fullscreen = not self.fullscreen
            if self.fullscreen:
                # Fullscreen mode
                self.window.fullscreen()
                self.mpv_top_box.hide()
                self.mpv_bottom_box.hide()
                self.sidebar.hide()
                self.headerbar.hide()
                self.status_label.hide()
                self.info_revealer.set_reveal_child(False)
                self.channels_box.set_border_width(0)
            else:
                # Normal mode
                self.window.unfullscreen()
                self.mpv_top_box.show()
                self.mpv_bottom_box.hide()
                if self.content_type == TV_GROUP:
                    self.sidebar.show()
                self.headerbar.show()
                self.channels_box.set_border_width(12)

    def on_fullscreen_button_clicked(self, widget):
        self.toggle_fullscreen()

    def on_close_info_window_button_clicked(self, widget):
        self.info_window.hide()


if __name__ == "__main__":
    application = MyApplication("org.x.hypnotix", Gio.ApplicationFlags.FLAGS_NONE)
    application.run()
