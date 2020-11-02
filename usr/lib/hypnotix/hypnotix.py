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
GROUP_OBJ, GROUP_NAME = range(2)
CHANNEL_OBJ, CHANNEL_NAME, CHANNEL_LOGO = range(3)

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

        # Set the Glade file
        gladefile = "/usr/share/hypnotix/hypnotix.ui"
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APP)
        self.builder.add_from_file(gladefile)
        self.window = self.builder.get_object("main_window")
        self.window.set_title(_("Hypnotix"))
        self.window.set_icon_name("hypnotix")

        # Create variables to quickly access dynamic widgets
        self.headerbar = self.builder.get_object("headerbar")
        self.status_label = self.builder.get_object("status_label")
        self.provider_combo = self.builder.get_object("provider_combo")
        self.group_treeview = self.builder.get_object("group_treeview")
        self.channel_treeview = self.builder.get_object("channel_treeview")
        self.generic_channel_pixbuf = self.icon_theme.load_icon("tv-symbolic", 22 * self.window.get_scale_factor(), 0)
        self.mpv_drawing_area = self.builder.get_object("mpv_drawing_area")

        # Widget signals
        self.window.connect("key-press-event",self.on_key_press_event)
        self.mpv_drawing_area.connect("realize", self.on_mpv_drawing_area_realize)
        self.mpv_drawing_area.connect("draw", self.on_mpv_drawing_area_draw)

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

    def reload(self):
        for provider in self.settings.get_strv("providers"):
            (name, url) = provider.split(":::")
            provider = Provider(name, url)
            self.manager.get_playlist(provider)
            if (self.manager.check_playlist(provider)):
                self.manager.load_channels(provider)
                self.providers.append(provider)
                self.provider_combo.get_model().append([provider, provider.name])
        self.show_selected_provider()

    def on_mpv_drawing_area_realize(self, widget):
        self.wid = str(widget.get_window().get_xid())
        self.mpv = mpv.MPV(ytdl=True, wid=str(widget.get_window().get_xid()))

    def on_mpv_drawing_area_draw(self, widget, cr):
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.paint()

    def toggle_fullscreen(self):
        self.fullscreen = (not self.fullscreen)
        if self.fullscreen:
            self.mpv.fullscreen = True
        else:
            self.mpv.fullscreen = False


if __name__ == "__main__":
    application = MyApplication("org.x.hypnotix", Gio.ApplicationFlags.FLAGS_NONE)
    application.run()
