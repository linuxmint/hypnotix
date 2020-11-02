#!/usr/bin/python3
import configparser
import gi
import os
import requests
import shutil
import string
import threading
import re
from gi.repository import GObject
from random import choice

# M3U parsing regex
PARAMS = re.compile(r'(\S+)="(.*?)"')
EXTINF = re.compile(r'^#EXTINF:(?P<duration>-?\d+?) ?(?P<params>.*),(?P<title>.*?)$')
PROVIDERS_PATH = os.path.expanduser("~/.hypnotix/providers")

# Used as a decorator to run things in the background
def _async(func):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        return thread
    return wrapper

# Used as a decorator to run things in the main loop, from another thread
def idle(func):
    def wrapper(*args):
        GObject.idle_add(func, *args)
    return wrapper

def slugify(string):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    """
    return "".join(x.lower() for x in string if x.isalnum())

class Provider():
    def __init__(self, name, url):
        self.name = name
        self.path = os.path.join(PROVIDERS_PATH, slugify(name))
        self.url = url
        self.groups = []
        self.channels = []

class Group():
    def __init__(self, name):
        self.name = name
        self.channels = []

class Channel():
    def __init__(self, info):
        self.info = info
        self.id = None
        self.name = None
        self.logo = None
        self.logo_path = None
        self.group_title = None
        self.title = None
        self.url = None
        match = EXTINF.fullmatch(info)
        if match != None:
            res = match.groupdict()
            if 'params' in res:
                params = dict(PARAMS.findall(res['params']))
                if "tvg-name" in params and params['tvg-name'].strip() != "":
                    self.name = params['tvg-name'].strip()
                if "tvg-logo" in params and params['tvg-logo'].strip() != "":
                    self.logo = params['tvg-logo'].strip()
                if "group-title" in params and params['group-title'].strip() != "":
                    self.group_title = params['group-title'].strip()
            if 'title' in res:
                self.title = res['title']
        if self.name == None and "," in info:
            self.name = info.split(",")[-1].strip()
        if self.logo != None:
            ext = None
            for known_ext in [".png", ".jpg", ".gif", ".jpeg"]:
                if self.logo.lower().endswith(known_ext):
                    ext = known_ext
                    break
            if ext == ".jpeg":
                ext = ".jpg"
            self.logo_path = os.path.join(PROVIDERS_PATH, "%s-%s%s" % (slugify(self.name), slugify(self.name), ext))

class Manager():

    def __init__(self):
        os.system("mkdir -p '%s'" % PROVIDERS_PATH)

    def get_playlist(self, provider):
        try:
            if "file://" in provider.url:
                # local file
                provider.path = provider.url.replace("file://", "")
            elif "://" in provider.url:
                # Other protocol, assume it's http
                response = requests.get(provider.url, timeout=10)
                if response.status_code == 200:
                    try:
                        source = response.content.decode("UTF-8")
                    except UnicodeDecodeError as e:
                        source = response.content.decode("latin1")
                    with open(provider.path, "w") as file:
                        file.write(source)
            else:
                # No protocol, assume it's local
                provider.path = provider.url
        except Exception as e:
            print(e)

    @_async
    def get_channel_logos(self, provider, refresh_existing_logos=False):
        with requests.session() as s:
            s.headers['user-agent'] = 'Mozilla/5.0'
            for channel in provider.channels:
                if channel.logo_path == None:
                    continue
                if os.path.exists(channel.logo_path) and not refresh_existing_logos:
                    continue
                try:
                    response = requests.get(channel.logo, timeout=10, stream=True)
                    if response.status_code == 200:
                        response.raw.decode_content = True
                        print("Downloading logo", channel.logo_path, channel.logo)
                        with open(channel.logo_path, 'wb') as f:
                            shutil.copyfileobj(response.raw, f)
                except Exception as e:
                    print(e)

    def check_playlist(self, provider):
        legit = False
        if os.path.exists(provider.path):
            with open(provider.path, "r") as file:
                content = file.read()
                if ("#EXTM3U" in content and "#EXTINF" in content):
                    legit = True
                    print("Content looks legit: %s" % provider.name)
                else:
                    print("Nope: %s" % provider.path)
        return legit

    def load_channels(self, provider):
        with open(provider.path, "r") as file:
            channel = None
            group = None
            groups = {}
            for line in file:
                line = line.strip()
                if line.startswith("#EXTM3U"):
                    continue
                if line.startswith("#EXTINF"):
                    channel = Channel(line)
                    print("New channel: ", line)
                    continue
                if "://" in line and not (line.startswith("#")):
                    print("    ", line)
                    if channel == None:
                        print("    --> channel is None")
                        continue
                    if channel.url != None:
                        # We already found the URL, skip the line
                        print("    --> channel URL was already found")
                        continue
                    if channel.name == None or "***" in channel.name:
                        print("    --> channel name is None")
                        continue
                    channel.url = line
                    print("    --> URL found: ", line)
                    provider.channels.append(channel)
                    if channel.group_title != None and channel.group_title.strip() != "":
                        if group == None or group.name != channel.group_title:
                            if channel.group_title in groups.keys():
                                group = groups[channel.group_title]
                            else:
                                group = Group(channel.group_title)
                                provider.groups.append(group)
                                groups[channel.group_title] = group
                        group.channels.append(channel)

