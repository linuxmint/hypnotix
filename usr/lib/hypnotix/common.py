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

class Manager():

    def __init__(self):
        os.system("mkdir -p '%s'" % PROVIDERS_PATH)

    def download_playlist(self, provider):
        success = False
        try:
            response = requests.get(provider.url, timeout=10)
            if response.status_code == 200:
                print("Download success")
                try:
                    source = response.content.decode("UTF-8")
                except UnicodeDecodeError as e:
                    source = response.content.decode("latin1")
                if (source.count("#EXTM3U") > 0 and source.count("#EXTINF") > 0):
                    print("Content looks legit")
                    with open(provider.path, "w") as file:
                        file.write(source)
                        success = True
        except Exception as e:
            print(e)
        finally:
            return success

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
                    continue
                if "://" in line:
                    if channel == None:
                        continue
                    if channel.url != None:
                        # We already found the URL, skip the line
                        continue
                    if channel.name == None or "***" in channel.name:
                        continue
                    channel.url = line
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

