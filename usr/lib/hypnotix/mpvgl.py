#!/usr/bin/python3
import ctypes

from gi.repository import Gdk, GLib

import mpv

GL_FRAMEBUFFER_BINDING = 0x8CA6

MOUSE_BUTTONS = {
    1: "MBTN_LEFT",
    2: "MBTN_MID",
    3: "MBTN_RIGHT",
    8: "MBTN_BACK",
    9: "MBTN_FORWARD",
}

SCROLL_KEYS = {
    Gdk.ScrollDirection.UP: "WHEEL_UP",
    Gdk.ScrollDirection.DOWN: "WHEEL_DOWN",
    Gdk.ScrollDirection.LEFT: "WHEEL_LEFT",
    Gdk.ScrollDirection.RIGHT: "WHEEL_RIGHT",
}

libgdk = ctypes.CDLL("libgdk-3.so.0")
libgdk.gdk_wayland_display_get_wl_display.restype = ctypes.c_void_p
libgdk.gdk_wayland_display_get_wl_display.argtypes = [ctypes.c_void_p]
libgdk.gdk_x11_display_get_xdisplay.restype = ctypes.c_void_p
libgdk.gdk_x11_display_get_xdisplay.argtypes = [ctypes.c_void_p]

PyCapsule_GetPointer = ctypes.pythonapi.PyCapsule_GetPointer
PyCapsule_GetPointer.restype = ctypes.c_void_p
PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]


def get_gl_loader(wayland):
    if wayland:
        loader = ctypes.CDLL("libEGL.so.1").eglGetProcAddress
    else:
        loader = ctypes.CDLL("libGL.so.1").glXGetProcAddressARB
    loader.restype = ctypes.c_void_p
    loader.argtypes = [ctypes.c_char_p]
    return loader


class MpvGLRenderer:
    """ Renders an mpv player into a Gtk.GLArea using libmpv's render API. """

    def __init__(self, area):
        self.area = area
        self.player = None
        self.context = None

        area.add_events(Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.SCROLL_MASK |
                        Gdk.EventMask.ENTER_NOTIFY_MASK |
                        Gdk.EventMask.LEAVE_NOTIFY_MASK)

        area.connect("render", self.on_render)
        area.connect("unrealize", self.on_unrealize)
        area.connect("motion-notify-event", self.on_motion)
        area.connect("button-press-event", self.on_button, "keydown")
        area.connect("button-release-event", self.on_button, "keyup")
        area.connect("scroll-event", self.on_scroll)
        area.connect("enter-notify-event", self.on_crossing, "MOUSE_ENTER")
        area.connect("leave-notify-event", self.on_crossing, "MOUSE_LEAVE")

    def start(self, player):
        self.area.make_current()
        error = self.area.get_error()
        if error is not None:
            print("Could not create an OpenGL context for mpv: %s" % error.message)
            return

        display = self.area.get_display()
        display_ptr = PyCapsule_GetPointer(display.__gpointer__, None)
        params = {}
        if display.__gtype__.name == "GdkWaylandDisplay":
            loader = get_gl_loader(wayland=True)
            params["wl_display"] = libgdk.gdk_wayland_display_get_wl_display(display_ptr)
        else:
            loader = get_gl_loader(wayland=False)
            params["x11_display"] = libgdk.gdk_x11_display_get_xdisplay(display_ptr)

        self.get_proc_address = mpv.MpvGlGetProcAddressFn(lambda ctx, name: loader(name))
        get_integerv_type = ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.POINTER(ctypes.c_int))
        self.gl_get_integerv = get_integerv_type(loader(b"glGetIntegerv"))

        self.player = player
        self.context = mpv.MpvRenderContext(player, "opengl",
                                            opengl_init_params={"get_proc_address": self.get_proc_address},
                                            **params)
        self.context.update_cb = self.on_mpv_update

    def stop(self):
        if self.context is None:
            return
        self.area.make_current()
        self.context.free()
        self.context = None
        self.player = None

    def on_mpv_update(self):
        # Called from an mpv thread
        GLib.idle_add(self.on_mpv_update_idle)

    def on_mpv_update_idle(self):
        if self.context is not None and self.context.update():
            self.area.queue_render()
        return GLib.SOURCE_REMOVE

    def on_render(self, area, gl_context):
        if self.context is None:
            return False
        scale = area.get_scale_factor()
        fbo = ctypes.c_int()
        self.gl_get_integerv(GL_FRAMEBUFFER_BINDING, ctypes.byref(fbo))
        self.context.render(flip_y=True,
                            opengl_fbo={"w": area.get_allocated_width() * scale,
                                        "h": area.get_allocated_height() * scale,
                                        "fbo": fbo.value})
        return True

    def on_unrealize(self, area):
        self.stop()

    def on_motion(self, area, event):
        if self.player is not None:
            scale = area.get_scale_factor()
            self.player.command("mouse", int(event.x * scale), int(event.y * scale))
        return True

    def on_button(self, area, event, command):
        # mpv generates its own double-clicks from the single presses
        if self.player is not None and event.type in (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE):
            button = MOUSE_BUTTONS.get(event.button)
            if button is not None:
                self.player.command(command, button)
        return True

    def on_scroll(self, area, event):
        key = SCROLL_KEYS.get(event.direction)
        if self.player is not None and key is not None:
            self.player.command("keypress", key)
        return True

    def on_crossing(self, area, event, key):
        if self.player is not None:
            self.player.command("keypress", key)
        return False
