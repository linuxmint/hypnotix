#!/usr/bin/python3
import gettext
import gi
import locale
import os
import re
import setproctitle
import shutil
import subprocess
import warnings
import sys
import time
import traceback

# Suppress GTK deprecation warnings
warnings.filterwarnings("ignore")

gi.require_version("Gtk", "3.0")
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, Gdk, Gio, XApp, GdkPixbuf, GLib, Pango

from common import *

import mpv

from imdb import IMDb

setproctitle.setproctitle("hypnotix")

# i18n
APP = 'hypnotix'
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

SPECIFICITIES = {}
SPECIFICITIES[TV_GROUP] = _("TV Channels")
SPECIFICITIES[MOVIES_GROUP] = _("Movies")
SPECIFICITIES[SERIES_GROUP] = _("Series")

class MyApplication(Gtk.Application):
    # Main initialization routine
    def __init__(self, application_id, flags):
        Gtk.Application.__init__(self, application_id=application_id, flags=flags)
        self.connect("activate", self.activate)

    def activate(self, application):
        windows = self.get_windows()
        if (len(windows) > 0):
            window = windows[0]
            window.present()
            window.show()
        else:
            window = MainWindow(self)
            self.add_window(window.window)
            window.window.show()

class MainWindow():

    def __init__(self, application):

        self.application = application
        self.settings = Gio.Settings(schema_id="org.x.hypnotix")
        self.icon_theme = Gtk.IconTheme.get_default()
        self.manager = Manager()
        self.providers = []
        self.active_provider = None
        self.marked_provider = None
        self.content_type = TV_GROUP # content being browsed
        self.active_channel = None
        self.fullscreen = False
        self.mpv = None
        self.skip_group_page = False
        self.ia = IMDb()

        # Set the Glade file
        gladefile = "/usr/share/hypnotix/hypnotix.ui"
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APP)
        self.builder.add_from_file(gladefile)
        self.window = self.builder.get_object("main_window")
        self.window.set_title(_("Hypnotix"))
        self.window.set_icon_name("hypnotix")

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
        self.generic_channel_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size("/usr/share/hypnotix/generic_tv_logo.png", 22, 22)
        widget_names = ["headerbar", "status_label", "status_bar", "top_bar", "sidebar", \
            "provider_button", "preferences_button", \
            "mpv_drawing_area", "stack", "fullscreen_button", \
            "add_label", "provider_ok_button", "provider_cancel_button", \
            "name_entry", "path_label", "path_entry", "browse_button", "url_label", "url_entry", \
            "username_label", "username_entry", "password_label", "password_entry", "epg_label", "epg_entry", \
            "tv_logo", "movies_logo", "series_logo", "tv_button", "movies_button", "series_button", \
            "provider_label", "tv_label", "movies_label", "series_label", \
            "categories_flowbox", "categories_label", "categories_go_back_button",
            "channels_flowbox", "channels_label", "channels_go_back_button", \
            "vod_flowbox", "vod_label", "vod_go_back_button", \
            "episodes_box", "episodes_label", "episodes_go_back_button", \
            "stop_button", "pause_button", "show_button", "playback_label", "playback_bar",
            "preferences_go_back_button", "providers_go_back_button", \
            "providers_flowbox", "new_provider_button", "reset_providers_button", \
            "delete_provider_label", "delete_no_button", "delete_yes_button", \
            "reset_no_button", "reset_yes_button", \
            "preferences_label", \
            "info_section", "info_name_label", "info_plot_label", "info_rating_label", "info_year_label", "info_genre_label", "info_duration_label", "info_votes_label", "info_pg_label"]

        for name in widget_names:
            widget = self.builder.get_object(name)
            if widget == None:
                print("Could not find widget %s!" % name)
                sys.exit(1)
            else:
                setattr(self, name, widget)

        self.fullscreen_widgets = []
        self.fullscreen_widgets.append(self.sidebar)
        self.fullscreen_widgets.append(self.headerbar)
        self.fullscreen_widgets.append(self.status_label)
        self.fullscreen_widgets.append(self.top_bar)

        # Widget signals
        self.window.connect("key-press-event",self.on_key_press_event)
        self.mpv_drawing_area.connect("realize", self.on_mpv_drawing_area_realize)
        self.mpv_drawing_area.connect("draw", self.on_mpv_drawing_area_draw)
        self.fullscreen_button.connect("clicked", self.on_fullscreen_button_clicked)

        self.provider_ok_button.connect("clicked", self.on_provider_ok_button)
        self.provider_cancel_button.connect("clicked", self.on_provider_cancel_button)

        self.name_entry.connect("changed", self.toggle_ok_sensitivity)
        self.url_entry.connect("changed", self.toggle_ok_sensitivity)
        self.path_entry.connect("changed", self.toggle_ok_sensitivity)

        self.tv_button.connect("clicked", self.show_groups, TV_GROUP)
        self.movies_button.connect("clicked", self.show_groups, MOVIES_GROUP)
        self.series_button.connect("clicked", self.show_groups, SERIES_GROUP)
        self.categories_go_back_button.connect("clicked", self.on_categories_go_back_button)
        self.channels_go_back_button.connect("clicked", self.on_channels_go_back_button)
        self.vod_go_back_button.connect("clicked", self.on_vod_go_back_button)
        self.preferences_go_back_button.connect("clicked", self.on_preferences_go_back_button)
        self.providers_go_back_button.connect("clicked", self.on_providers_go_back_button)
        self.episodes_go_back_button.connect("clicked", self.on_episodes_go_back_button)

        self.stop_button.connect("clicked", self.on_stop_button)
        self.pause_button.connect("clicked", self.on_pause_button)
        self.show_button.connect("clicked", self.on_show_button)

        self.provider_button.connect("clicked", self.on_provider_button)
        self.preferences_button.connect("clicked", self.on_preferences_button)

        self.new_provider_button.connect("clicked", self.on_new_provider_button)
        self.reset_providers_button.connect("clicked", self.on_reset_providers_button)
        self.delete_no_button.connect("clicked", self.on_delete_no_button)
        self.delete_yes_button.connect("clicked", self.on_delete_yes_button)
        self.reset_no_button.connect("clicked", self.on_reset_no_button)
        self.reset_yes_button.connect("clicked", self.on_reset_yes_button)

        self.browse_button.connect("clicked", self.on_browse_button)

        # Menubar
        accel_group = Gtk.AccelGroup()
        self.window.add_accel_group(accel_group)
        menu = self.builder.get_object("main_menu")
        item = Gtk.MenuItem()
        item.set_label(_("Preferences"))
        item.connect("activate", self.open_preferences)
        menu.append(item)
        item = Gtk.ImageMenuItem()
        item.set_image(Gtk.Image.new_from_icon_name("preferences-desktop-keyboard-shortcuts-symbolic", Gtk.IconSize.MENU))
        item.set_label(_("Keyboard Shortcuts"))
        item.connect("activate", self.open_keyboard_shortcuts)
        key, mod = Gtk.accelerator_parse("<Control>K")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        menu.append(item)
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
        item.connect('activate', self.on_menu_quit)
        key, mod = Gtk.accelerator_parse("<Control>Q")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>W")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        menu.append(item)
        menu.show_all()

        # Type combox box (in preferences)
        model = Gtk.ListStore(str,str) # PROVIDER_TYPE_ID, PROVIDER_TYPE_NAME
        model.append([PROVIDER_TYPE_URL,_("M3U URL")])
        model.append([PROVIDER_TYPE_LOCAL,_("Local M3U File")])
        model.append([PROVIDER_TYPE_XTREAM,_("Xtream API")])
        self.provider_type_combo = self.builder.get_object("provider_type_combo")
        renderer = Gtk.CellRendererText()
        self.provider_type_combo.pack_start(renderer, True)
        self.provider_type_combo.add_attribute(renderer, "text", PROVIDER_TYPE_NAME)
        self.provider_type_combo.set_model(model)
        self.provider_type_combo.set_active(0) # Select 1st type
        self.provider_type_combo.connect("changed", self.on_provider_type_combo_changed)

        self.tv_logo.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size("/usr/share/hypnotix/pictures/tv.svg", 258, 258))
        self.movies_logo.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size("/usr/share/hypnotix/pictures/movies.svg", 258, 258))
        self.series_logo.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size("/usr/share/hypnotix/pictures/series.svg", 258, 258))

        self.reload(page="landing_page")

        # Redownload playlists after a little while...
        GLib.timeout_add_seconds(60 * 5, self.force_reload)

        self.window.show()
        self.playback_bar.hide()

    def show_groups(self, widget, content_type):
        self.content_type = content_type
        title = SPECIFICITIES[self.content_type]
        self.stack.set_visible_child_name("categories_page")
        self.categories_label.set_text("%s: %s" % (self.active_provider.name, title))
        for child in self.categories_flowbox.get_children():
            self.categories_flowbox.remove(child)
        self.skip_group_page = True
        for group in self.active_provider.groups:
            if group.group_type != self.content_type:
                continue
            self.skip_group_page = False
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
            for word in group.name.split():
                word = word.lower()
                badge = "/usr/share/hypnotix/pictures/badges/%s.png" % word
                if os.path.exists(badge):
                    try:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(badge, -1, 16)
                        surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, self.window.get_scale_factor())
                        image = Gtk.Image().new_from_surface(surface)
                        box.pack_start(image, False, False, 0)
                    except:
                        print("Could not load badge", badge)
                elif word in BADGES.keys():
                    badge = "/usr/share/hypnotix/pictures/badges/%s.png" % BADGES[word]
                    try:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(badge, -1, 16)
                        surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, self.window.get_scale_factor())
                        image = Gtk.Image().new_from_surface(surface)
                        box.pack_start(image, False, False, 0)
                    except:
                        print("Could not load badge", badge)

            box.pack_start(label, False, False, 0)
            box.set_spacing(6)
            button.add(box)
            self.categories_flowbox.add(button)
            self.categories_flowbox.show_all()

        if self.skip_group_page:
            self.on_category_button_clicked(None, None)

    def on_category_button_clicked(self, widget, group):

        group_name = self.active_provider.name
        if group != None:
                group_name = group.name

        if self.content_type == TV_GROUP:
            if group != None:
                self.show_channels(group.name, group.channels)
            else:
                self.show_channels(self.active_provider.name, self.active_provider.channels)
        elif self.content_type == MOVIES_GROUP:
            if group != None:
                self.show_vod(group.name, group.channels)
            else:
                self.show_vod(self.active_provider.name, self.active_provider.movies)
        elif self.content_type == SERIES_GROUP:
            if group != None:
                self.show_vod(group.name, group.series)
            else:
                self.show_vod(self.active_provider.name, self.active_provider.series)

    def show_channels(self, group_name, channels):
        self.stack.set_visible_child_name("channels_page")
        if self.content_type == TV_GROUP:
            self.sidebar.show()
            logos_to_refresh = []
            self.channels_label.set_text(group_name)
            self.playback_bar.hide()
            for child in self.channels_flowbox.get_children():
                self.channels_flowbox.remove(child)
            for channel in channels:
                button = Gtk.Button()
                button.connect("clicked", self.on_channel_button_clicked, channel)
                label = Gtk.Label()
                label.set_text(channel.name)
                label.set_max_width_chars(30)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                pixbuf = self.get_pixbuf(channel.logo_path)
                surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, self.window.get_scale_factor())
                image = Gtk.Image().new_from_surface(surface)
                logos_to_refresh.append((channel, image))
                box.pack_start(image, False, False, 0)
                box.pack_start(label, False, False, 0)
                box.set_spacing(6)
                button.add(box)
                self.channels_flowbox.add(button)
            self.channels_flowbox.show_all()
            if len(logos_to_refresh) > 0:
                self.download_channel_logos(logos_to_refresh)
        else:
            self.sidebar.hide()

    def show_vod(self, group_name, items):
        logos_to_refresh = []
        self.vod_label.set_text(self.remove_word("VOD", group_name))
        self.stack.set_visible_child_name("vod_page")
        for child in self.vod_flowbox.get_children():
            self.vod_flowbox.remove(child)
        for item in items:
            button = Gtk.Button()
            if self.content_type == MOVIES_GROUP:
                button.connect("clicked", self.on_vod_movie_button_clicked, item)
            else:
                button.connect("clicked", self.on_vod_series_button_clicked, item)
            label = Gtk.Label()
            label.set_text(item.name)
            label.set_max_width_chars(30)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            pixbuf = self.get_pixbuf(item.logo_path)
            surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, self.window.get_scale_factor())
            image = Gtk.Image().new_from_surface(surface)
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
        if not " " in string:
            return string
        words = string.split()
        if word in string:
            words.remove(word)
        return " ".join(words)

    def show_episodes(self, serie):
        logos_to_refresh = []
        self.episodes_label.set_text(serie.name)
        self.stack.set_visible_child_name("episodes_page")
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
                button.connect("clicked", self.on_episode_button_clicked, episode)
                label = Gtk.Label()
                label.set_text(_("Episode %s") % episode_name)
                label.set_max_width_chars(30)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                pixbuf = self.get_pixbuf(episode.logo_path)
                surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, self.window.get_scale_factor())
                image = Gtk.Image().new_from_surface(surface)
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
        self.channels_label.set_text(channel.name)
        self.show_channels(None, None)
        self.play_async(channel)

    def on_episode_button_clicked(self, widget, channel):
        self.channels_label.set_text(channel.name)
        self.show_channels(None, None)
        self.play_async(channel)

    def on_vod_series_button_clicked(self, widget, serie):
        self.show_episodes(serie)

    @async_function
    def download_channel_logos(self, logos_to_refresh):
        with requests.session() as s:
            s.headers['user-agent'] = 'Mozilla/5.0'
            for channel, image in logos_to_refresh:
                if channel.logo_path == None:
                    continue
                try:
                    # self.status("Downloading logo for %s" % channel.name)
                    response = requests.get(channel.logo, timeout=10, stream=True)
                    if response.status_code == 200:
                        response.raw.decode_content = True
                        with open(channel.logo_path, 'wb') as f:
                            shutil.copyfileobj(response.raw, f)
                            self.refresh_channel_logo(channel, image)
                except Exception as e:
                    print(e)
            # self.status(None)

    @idle_function
    def refresh_channel_logo(self, channel, image):
        pixbuf = self.get_pixbuf(channel.logo_path)
        surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, self.window.get_scale_factor())
        image.set_from_surface(surface)

    def get_pixbuf(self, path):
        try:
            if self.content_type == TV_GROUP:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, 64, 32)
            elif self.content_type == MOVIES_GROUP:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, 200, 200)
            else:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, 200, 200)
        except:
            pixbuf = self.generic_channel_pixbuf
        return pixbuf

    def on_categories_go_back_button(self, widget):
        self.stack.set_visible_child_name("landing_page")

    def on_channels_go_back_button(self, widget):
        if self.content_type == TV_GROUP:
            if self.skip_group_page:
                self.stack.set_visible_child_name("landing_page")
            else:
                self.stack.set_visible_child_name("categories_page")
            if self.active_channel != None:
                self.playback_bar.show()
        elif self.content_type == MOVIES_GROUP:
            self.stack.set_visible_child_name("vod_page")
        else:
            self.stack.set_visible_child_name("episodes_page")

    def on_vod_go_back_button(self, widget):
        if self.skip_group_page:
            self.stack.set_visible_child_name("landing_page")
        else:
            self.stack.set_visible_child_name("categories_page")

    def on_preferences_go_back_button(self, widget):
        self.stack.set_visible_child_name("landing_page")

    def on_providers_go_back_button(self, widget):
        self.stack.set_visible_child_name("landing_page")

    def on_episodes_go_back_button(self, widget):
        self.stack.set_visible_child_name("vod_page")

    def open_keyboard_shortcuts(self, widget):
        gladefile = "/usr/share/hypnotix/shortcuts.ui"
        builder = Gtk.Builder()
        builder.set_translation_domain(APP)
        builder.add_from_file(gladefile)
        window = builder.get_object("shortcuts")
        window.set_title(_("Hypnotix"))
        window.show()

    def on_channel_button_clicked(self, widget, channel):
        self.play(channel)

    @async_function
    def play_async(self, channel):
        while self.mpv == None:
            time.sleep(1)
        self.play(channel)

    @idle_function
    def play(self, channel):
        print ("CHANNEL: '%s' (%s)" % (channel.name, channel.url))
        if channel != None and channel.url != None:
            #os.system("mpv --wid=%s %s &" % (self.wid, channel.url))
            # self.mpv_drawing_area.show()
            self.mpv.play(channel.url)
            self.playback_label.set_text(channel.name)
            self.active_channel = channel
            self.info_section.hide()
            if self.content_type == MOVIES_GROUP:
                self.get_imdb_details(channel)

    @async_function
    def get_imdb_details(self, channel):
        movies = self.ia.search_movie(channel.name)
        match = None
        for movie in movies:
            self.ia.update(movie)
            if movie.get('plot') != None:
                match = movie
                break
        self.refresh_info_section(match)

    @idle_function
    def refresh_info_section(self, movie):
        if movie != None:
            self.set_imdb_info(movie, 'title', self.info_name_label)
            self.set_imdb_info(movie, 'plot outline', self.info_plot_label)
            self.set_imdb_info(movie, 'rating', self.info_rating_label)
            self.set_imdb_info(movie, 'votes', self.info_votes_label)
            self.set_imdb_info(movie, 'year', self.info_year_label)
            self.set_imdb_info(movie, 'genres', self.info_genre_label)
            self.set_imdb_info(movie, 'runtimes', self.info_duration_label)
            self.set_imdb_info(movie, 'certificates', self.info_pg_label)
            self.info_section.show()

    def set_imdb_info(self, movie, field, widget):
        value = movie.get(field)
        if value != None:
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

    def on_stop_button(self, widget):
        self.mpv.stop()
        # self.mpv_drawing_area.hide()
        self.info_section.hide()
        self.active_channel = None
        self.playback_bar.hide()

    def on_pause_button(self, widget):
        self.mpv.pause = not self.mpv.pause

    def on_show_button(self, widget):
        self.stack.set_visible_child_name("channels_page")
        self.playback_bar.hide()

    def on_provider_button(self, widget):
        self.stack.set_visible_child_name("providers_page")

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
            label = Gtk.Label()
            label.set_text(_("%s TV channels") % len(provider.channels))
            labels_box.pack_start(label, False, False, 0)
            label = Gtk.Label()
            label.set_text(_("%s movies") % len(provider.movies))
            labels_box.pack_start(label, False, False, 0)
            label = Gtk.Label()
            label.set_text(_("%s series") % len(provider.series))
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
            image.set_from_icon_name("list-edit-symbolic", Gtk.IconSize.BUTTON)
            button.set_tooltip_text(_("Edit"))
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
        self.show_page("landing_page")

    def on_preferences_button(self, widget):
        self.stack.set_visible_child_name("preferences_page")
        self.preferences_label.set_text("%s: Preferences" % self.active_provider.name)

    def on_new_provider_button(self, widget):
        self.add_label.set_text(_("Add a new provider"))
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
        self.stack.set_visible_child_name("add_page")
        self.edit_mode = False
        self.provider_ok_button.set_sensitive(False)
        self.name_entry.grab_focus()

    def on_reset_providers_button(self, widget):
        self.stack.set_visible_child_name("reset_page")

    def on_delete_button_clicked(self, widget, provider):
        self.stack.set_visible_child_name("delete_page")
        self.delete_provider_label.set_text(provider.name)
        self.marked_provider = provider

    def on_edit_button_clicked(self, widget, provider):
        self.marked_provider = provider
        self.add_label.set_text(_("Edit the provider"))
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
        self.stack.set_visible_child_name("add_page")
        self.edit_mode = True
        self.provider_ok_button.set_sensitive(True)
        self.name_entry.grab_focus()
        self.set_provider_type(provider.type_id)

    def on_delete_no_button(self, widget):
        self.stack.set_visible_child_name("providers_page")

    def on_reset_no_button(self, widget):
        self.stack.set_visible_child_name("providers_page")

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

    def open_preferences(self, widget):
        self.stack.set_visible_child_name("preferences_page")

    def save(self):
        provider_strings = []
        for provider in self.providers:
            provider_strings.append(provider.get_info())
        self.settings.set_strv("providers", provider_strings)
        self.reload(page="providers_page")

    def on_provider_type_combo_changed(self, widget):
        type_id = self.provider_type_combo.get_model()[self.provider_type_combo.get_active()][PROVIDER_TYPE_ID]
        self.set_provider_type(type_id)

    def set_provider_type(self, type_id):
        widgets = [self.path_entry, self.path_label, self.browse_button, \
                   self.url_entry, self.url_label, \
                   self.username_entry, self.username_label, \
                   self.password_entry, self.password_label, \
                   self.epg_label, self.epg_entry]
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

    def on_provider_cancel_button(self, widget):
        self.stack.set_visible_child_name("providers_page")

    def toggle_ok_sensitivity(self, widget=None):
        if self.name_entry.get_text() == "":
            self.provider_ok_button.set_sensitive(False)
        elif self.get_url() == "":
            self.provider_ok_button.set_sensitive(False)
        else:
            self.provider_ok_button.set_sensitive(True)

    def get_url(self):
        type_id = self.provider_type_combo.get_model()[self.provider_type_combo.get_active()][PROVIDER_TYPE_ID]
        if type_id == PROVIDER_TYPE_LOCAL:
            widget = self.path_entry
        else:
            widget = self.url_entry

        url = widget.get_text().strip()
        if url == "":
            return ""
        if not "://" in url:
            if type_id == PROVIDER_TYPE_LOCAL:
                url = "file://%s" % url
            else:
                url = "http://%s" % url
        return url

##############################

    def open_about(self, widget):
        dlg = Gtk.AboutDialog()
        dlg.set_transient_for(self.window)
        dlg.set_title(_("About"))
        dlg.set_program_name(_("Hypnotix"))
        dlg.set_comments(_("Watch TV"))
        try:
            h = open('/usr/share/common-licenses/GPL', encoding="utf-8")
            s = h.readlines()
            gpl = ""
            for line in s:
                gpl += line
            h.close()
            dlg.set_license(gpl)
        except Exception as e:
            print (e)

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
        ctrl = (event.state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and event.keyval == Gdk.KEY_r:
            self.reload()
        elif event.keyval == Gdk.KEY_F11 or \
             event.keyval == Gdk.KEY_f or \
             (self.fullscreen and event.keyval == Gdk.KEY_Escape):
            self.toggle_fullscreen()

    @async_function
    def reload(self, page=None, refresh=False):
        self.status("Loading providers...")
        self.providers = []
        for provider_info in self.settings.get_strv("providers"):
            try:
                provider = Provider(name=None, provider_info=provider_info)
                if refresh:
                    self.status("Downloading playlist...", provider)
                else:
                    self.status("Getting playlist...", provider)
                self.manager.get_playlist(provider, refresh=refresh)
                self.status("Checking playlist...", provider)
                if (self.manager.check_playlist(provider)):
                    self.status("Loading channels...", provider)
                    self.manager.load_channels(provider)
                    self.providers.append(provider)
                    if provider.name == self.settings.get_string("active-provider"):
                        self.active_provider = provider
                    self.status(None)
            except Exception as e:
                print(e)
                traceback.print_exc()
                print("Couldn't parse provider info: ", provider_info)
        if len(self.providers) > 0 and self.active_provider == None:
            self.active_provider = self.providers[0]

        self.refresh_providers_page()

        if page != None:
            self.show_page(page)
        self.status(None)

    def force_reload(self):
        self.reload(page=None, refresh=True)
        return False

    @idle_function
    def status(self, string, provider=None):
        if string == None:
            self.status_label.set_text("")
            self.status_label.hide()
            return
        self.status_label.show()
        if provider != None:
            self.status_label.set_text("%s: %s" % (provider.name, string))
            print("%s: %s" % (provider.name, string))
        else:
            self.status_label.set_text(string)
            print(string)

    @idle_function
    def show_page(self, page):
        provider = self.active_provider
        if provider == None:
            self.provider_label.set_text("Hypnotix")
            self.tv_label.set_text("TV Channels (%d)" % 0)
            self.movies_label.set_text("Movies (%d)" % 0)
            self.series_label.set_text("Series (%d)" % 0)
            self.preferences_button.set_sensitive(False)
            self.tv_button.set_sensitive(False)
            self.movies_button.set_sensitive(False)
            self.series_button.set_sensitive(False)
        else:
            self.provider_label.set_text(provider.name)
            self.tv_label.set_text("TV Channels (%d)" % len(provider.channels))
            self.movies_label.set_text("Movies (%d)" % len(provider.movies))
            self.series_label.set_text("Series (%d)" % len(provider.series))
            self.preferences_button.set_sensitive(True)
            self.tv_button.set_sensitive(len(provider.channels) > 0)
            self.movies_button.set_sensitive(len(provider.movies) > 0)
            self.series_button.set_sensitive(len(provider.series) > 0)
        self.stack.set_visible_child_name(page)

    def on_mpv_drawing_area_realize(self, widget):
        if self.mpv == None:
            self.mpv = mpv.MPV(script_opts='osc-layout=box,osc-seekbarstyle=bar,osc-deadzonesize=0,osc-minmousemove=3', input_default_bindings=True, \
                 input_vo_keyboard=True,osc=True, ytdl=True, wid=str(widget.get_window().get_xid()))

    def on_mpv_drawing_area_draw(self, widget, cr):
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.paint()

    def toggle_fullscreen(self):
        # Toggle state
        self.fullscreen = (not self.fullscreen)
        if self.fullscreen:
            # Fullscreen mode
            self.window.fullscreen()
            for widget in self.fullscreen_widgets:
                widget.set_visible(False)
            self.stack.set_border_width(0)
        else:
            # Normal mode
            self.window.unfullscreen()
            for widget in self.fullscreen_widgets:
                widget.set_visible(True)
            self.stack.set_border_width(12)

    def on_fullscreen_button_clicked(self, widget):
        self.toggle_fullscreen()

if __name__ == "__main__":
    application = MyApplication("org.x.hypnotix", Gio.ApplicationFlags.FLAGS_NONE)
    application.run()
