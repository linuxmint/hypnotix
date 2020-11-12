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
import traceback

# Suppress GTK deprecation warnings
warnings.filterwarnings("ignore")

gi.require_version("Gtk", "3.0")
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, Gdk, Gio, XApp, GdkPixbuf, GLib

from common import *

import mpv

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
        self.loading = False
        self.fullscreen = False
        self.mpv = None

        # Set the Glade file
        gladefile = "/usr/share/hypnotix/hypnotix.ui"
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APP)
        self.builder.add_from_file(gladefile)
        self.window = self.builder.get_object("main_window")
        self.window.set_title(_("Hypnotix"))
        self.window.set_icon_name("hypnotix")

        # Prefs variables
        self.selected_pref_provider = None
        self.edit_mode = False

        # Create variables to quickly access dynamic widgets
        self.generic_channel_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size("/usr/share/hypnotix/generic_tv_logo.png", 22, 22)
        widget_names = ["headerbar", "status_label", "provider_combo", "group_treeview", "channel_treeview", \
            "mpv_drawing_area", "mpv_box", "main_box", "stack", "fullscreen_button", \
            "add_label", "ok_button", "add_button", "edit_button", "remove_button", "provider_ok_button", "provider_cancel_button", \
            "name_entry", "path_label", "path_entry", "path_button", "url_label", "url_entry", \
            "username_label", "username_entry", "password_label", "password_entry", "epg_label", "epg_entry"]
        for name in widget_names:
            widget = self.builder.get_object(name)
            if widget == None:
                print("Could not find widget %s!" % name)
                sys.exit(1)
            else:
                setattr(self, name, widget)

        self.fullscreen_widgets = []
        self.fullscreen_widgets.append(self.builder.get_object("sidebar"))
        self.fullscreen_widgets.append(self.headerbar)
        self.fullscreen_widgets.append(self.status_label)

        # Widget signals
        self.window.connect("key-press-event",self.on_key_press_event)
        self.mpv_drawing_area.connect("realize", self.on_mpv_drawing_area_realize)
        self.mpv_drawing_area.connect("draw", self.on_mpv_drawing_area_draw)
        self.fullscreen_button.connect("clicked", self.on_fullscreen_button_clicked)

        self.ok_button.connect("clicked", self.on_ok_button)
        self.add_button.connect("clicked", self.on_add_button)
        self.edit_button.connect("clicked", self.on_edit_button)
        self.remove_button.connect("clicked", self.on_remove_button)
        self.provider_ok_button.connect("clicked", self.on_provider_ok_button)
        self.provider_cancel_button.connect("clicked", self.on_provider_cancel_button)

        self.name_entry.connect("changed", self.toggle_ok_sensitivity)
        self.url_entry.connect("changed", self.toggle_ok_sensitivity)
        self.path_entry.connect("changed", self.toggle_ok_sensitivity)

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

        # Provider Treeview (in preferences)
        self.provider_treeview = self.builder.get_object("provider_treeview")
        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=COL_PROVIDER_NAME)
        column.set_sort_column_id(COL_PROVIDER_NAME)
        column.set_resizable(True)
        self.provider_treeview.append_column(column)
        self.provider_treeview.show()
        self.provider_model = Gtk.TreeStore(str, object) # name, object
        self.provider_model.set_sort_column_id(COL_PROVIDER_NAME, Gtk.SortType.ASCENDING)
        self.provider_treeview.set_model(self.provider_model)
        self.provider_treeview.get_selection().connect("changed", self.pref_on_provider_selected)
        self.provider_treeview.connect("row-activated", self.pref_on_provider_activated)

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

        # Provider combox
        model = Gtk.ListStore(object, str) # obj, name
        model.append([None, _("All")])
        renderer = Gtk.CellRendererText()
        self.provider_combo.pack_start(renderer, True)
        self.provider_combo.add_attribute(renderer, "text", PROVIDER_NAME)
        self.provider_combo.set_model(model)
        self.provider_combo.set_active(0) # Select 1st

        # Group treeview
        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=GROUP_NAME)
        column.set_sort_column_id(GROUP_NAME)
        column.set_resizable(True)
        self.group_treeview.append_column(column)
        self.group_treeview.show()
        model = Gtk.ListStore(object, str) # object, name
        model.set_sort_column_id(GROUP_NAME, Gtk.SortType.ASCENDING)
        self.group_treeview.set_model(model)
        self.group_treeview.get_selection().connect("changed", self.on_group_selected)

        # Channel treeview
        renderer = Gtk.CellRendererPixbuf()
        column = Gtk.TreeViewColumn("", renderer, pixbuf=CHANNEL_LOGO)
        column.set_cell_data_func(renderer, self.data_func_surface)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.channel_treeview.append_column(column)
        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=CHANNEL_NAME)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.channel_treeview.append_column(column)
        self.channel_treeview.show()
        model = Gtk.ListStore(object, str, GdkPixbuf.Pixbuf) # obj, name, logo
        self.channel_treeview.set_model(model)
        self.channel_treeview.get_selection().connect("changed", self.on_channel_selected)

        self.reload()

        self.provider_combo.connect("changed", self.on_provider_changed)

        self.window.show()

    def data_func_surface(self, column, cell, model, iter_, *args):
        pixbuf = model.get_value(iter_, CHANNEL_LOGO)
        surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, self.window.get_scale_factor())
        cell.set_property("surface", surface)

    def on_provider_changed(self, widget):
        if not self.loading:
            self.show_selected_provider()

    def on_group_selected(self, selection):
        if self.loading:
            return
        model, iter = selection.get_selected()
        if iter is not None:
            group = model.get_value(iter, GROUP_OBJ)
            if group == None:
                self.show_selected_provider(reload_groups=False)
            else:
                print("GROUP: '%s'" % group.name)
                self.load_channels(group.channels)

    def on_channel_selected(self, selection):
        if self.loading:
            return
        model, iter = selection.get_selected()
        if iter is not None:
            channel = model.get_value(iter, CHANNEL_OBJ)
            print ("CHANNEL: '%s' (%s)" % (channel.name, channel.url))
            if channel != None and channel.url != None:
                #os.system("mpv --wid=%s %s &" % (self.wid, channel.url))
                self.mpv.play(channel.url)

    def show_selected_provider(self, reload_groups=True):
        combo = self.provider_combo
        active_index = combo.get_active()
        if active_index > 0:
            provider = combo.get_model()[combo.get_active()][PROVIDER_OBJ]
            if provider == None:
                # Show all providers
                groups = []
                channels = []
                for provider in self.providers:
                    groups += provider.groups
                    channels += provider.channels
            else:
                groups = provider.groups
                channels = provider.channels

            if reload_groups:
                self.load_groups(groups)
            self.load_channels(channels)

    def load_groups(self, groups):
        self.loading = True
        model = self.group_treeview.get_model()
        model.clear()
        model.append([None, _("All")])
        for group in groups:
            iter = model.insert_before(None, None)
            model.set_value(iter, GROUP_OBJ, group)
            model.set_value(iter, GROUP_NAME, group.name)
        self.loading = False

    def load_channels(self, channels):
        self.loading = True
        model = self.channel_treeview.get_model()
        model.clear()
        for channel in channels:
            try:
               pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(channel.logo_path, 22, 22)
            except:
                pass
                pixbuf = self.generic_channel_pixbuf
            if channel.name != None:
                model.insert_with_valuesv(-1, range(3), [channel, channel.name, pixbuf])
        self.loading = False

    def open_keyboard_shortcuts(self, widget):
        gladefile = "/usr/share/hypnotix/shortcuts.ui"
        builder = Gtk.Builder()
        builder.set_translation_domain(APP)
        builder.add_from_file(gladefile)
        window = builder.get_object("shortcuts")
        window.set_title(_("Hypnotix"))
        window.show()

######################
#### PREFERENCES #####
######################

    def open_preferences(self, widget):
        self.stack.set_visible_child_name("preferences_page")

    def pref_on_provider_selected(self, selection):
        model, iter = selection.get_selected()
        if iter is not None:
            self.selected_pref_provider = model.get_value(iter, COL_PROVIDER)
            self.remove_button.set_sensitive(True)
            self.edit_button.set_sensitive(True)

    def pref_on_provider_activated(self, treeview, path, column):
        self.on_edit_button(self, None)

    def on_remove_button(self, widget):
        if self.selected_pref_provider != None:
            self.providers.remove(self.selected_pref_provider)
            self.save()

    def save(self):
        provider_strings = []
        for provider in self.providers:
            provider_strings.append(provider.get_info())
        self.settings.set_strv("providers", provider_strings)
        self.reload()

    def on_add_button(self, widget):
        self.add_label.set_text(_("Add a new provider"))
        self.name_entry.set_text("")
        self.url_entry.set_text("")
        self.set_provider_type(PROVIDER_TYPE_URL)
        self.stack.set_visible_child_name("page_provider")
        self.edit_mode = False
        self.provider_ok_button.set_sensitive(False)
        self.name_entry.grab_focus()

    def on_provider_type_combo_changed(self, widget):
        type_id = self.provider_type_combo.get_model()[self.provider_type_combo.get_active()][PROVIDER_TYPE_ID]
        self.set_provider_type(type_id)

    def set_provider_type(self, type_id):
        widgets = [self.path_entry, self.path_label, self.path_button, \
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
            visible_widgets.append(self.path_button)
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

    def on_edit_button(self, widget):
        if self.selected_pref_provider != None:
            provider = self.selected_pref_provider
            print(provider.name)
            self.add_label.set_text(_("Edit the provider"))
            self.name_entry.set_text(provider.name)
            self.username_entry.set_text(provider.username)
            self.password_entry.set_text(provider.password)
            self.epg_entry.set_text(provider.epg)
            if provider.type_id == PROVIDER_TYPE_LOCAL:
                self.url_entry = ""
                self.path_entry = provider.url
            else:
                self.path_entry = ""
                self.url_entry = provider.url

            model = self.provider_type_combo.get_model()
            iter = model.get_iter_first()
            while iter:
                type_id = model.get_value(iter, PROVIDER_TYPE_ID)
                if provider.type_id == type_id:
                    self.provider_type_combo.set_active_iter(iter)
                    break
                iter = model.iter_next(iter)
            self.stack.set_visible_child_name("page_provider")
            self.edit_mode = True
            self.provider_ok_button.set_sensitive(True)
            self.name_entry.grab_focus()

    def on_provider_ok_button(self, widget):
        type_id = self.provider_type_combo.get_model()[self.provider_type_combo.get_active()][PROVIDER_TYPE_ID]
        name = self.name_entry.get_text()
        if self.edit_mode:
            provider = self.selected_pref_provider
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
        self.stack.set_visible_child_name("preferences_page")

    def on_ok_button(self, widget):
        self.stack.set_visible_child_name("main_page")

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
    def reload(self):
        self.loading = True
        self.status("Loading providers...")
        self.providers = []
        for provider_info in self.settings.get_strv("providers"):
            try:
                provider = Provider(name=None, provider_info=provider_info)
                self.status("Getting playlist...", provider)
                self.manager.get_playlist(provider, refresh=False)
                self.status("Checking playlist...", provider)
                if (self.manager.check_playlist(provider)):
                    self.status("Loading channels...", provider)
                    self.manager.load_channels(provider)
                    # self.manager.get_channel_logos(provider)
                    self.providers.append(provider)
                    self.status(None)
            except Exception as e:
                print(e)
                traceback.print_exc()
                print("Couldn't parse provider info: ", provider_info)
        self.reload_ui()
        self.status(None)

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
    def reload_ui(self):
        print("Loading UI...")
        self.provider_combo.get_model().clear()
        self.provider_model.clear()
        for provider in self.providers:
            self.provider_combo.get_model().append([provider, provider.name])
            iter = self.provider_model.insert_before(None, None)
            self.provider_model.set_value(iter, COL_PROVIDER_NAME, provider.name)
            self.provider_model.set_value(iter, COL_PROVIDER, provider)
        self.provider_combo.set_active(0) # Select 1st
        self.loading = False
        print("Loading selected provider...")
        self.show_selected_provider()
        print("Done")


    def on_mpv_drawing_area_realize(self, widget):
        if self.mpv == None:
            self.mpv = mpv.MPV(ytdl=True, wid=str(widget.get_window().get_xid()))

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
