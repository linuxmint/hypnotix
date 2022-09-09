#!/usr/bin/python3
import os
import re
import threading

import requests
from gi.repository import GLib, GObject

# M3U parsing regex
PARAMS = re.compile(r'(\S+)="(.*?)"')
EXTINF = re.compile(r'^#EXTINF:(?P<duration>-?\d+?) ?(?P<params>.*),(?P<title>.*?)$')
SERIES = re.compile(r"(?P<series>.*?) S(?P<season>.\d{1,2}).*E(?P<episode>.\d{1,2}.*)$", re.IGNORECASE)

PROVIDERS_PATH = os.path.join(GLib.get_user_cache_dir(), "hypnotix", "providers")

TV_GROUP, MOVIES_GROUP, SERIES_GROUP = range(3)

BADGES = {}
BADGES['musik'] = "music"
BADGES['zeland'] = "newzealand"

# Used as a decorator to run things in the background
def async_function(func):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        return thread
    return wrapper

# Used as a decorator to run things in the main loop, from another thread
def idle_function(func):
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
    def __init__(self, name, provider_info):
        if provider_info != None:
            self.name, self.type_id, self.url, self.username, self.password, self.epg = provider_info.split(":::")
        else:
            self.name = name
        self.path = os.path.join(PROVIDERS_PATH, slugify(self.name))
        self.groups = []
        self.channels = []
        self.movies = []
        self.series = []

    def get_info(self):
        return "%s:::%s:::%s:::%s:::%s:::%s" % (self.name, self.type_id, self.url, self.username, self.password, self.epg)

class Group():
    def __init__(self, name):
        if "VOD" in name.split():
            self.group_type = MOVIES_GROUP
        elif "SERIES" in name.split():
            self.group_type = SERIES_GROUP
        else:
            self.group_type = TV_GROUP
        self.name = name
        self.channels = []
        self.series = []

class Serie():
    def __init__(self, name):
        self.name = name
        self.logo = None
        self.logo_path = None
        self.seasons = {}
        self.episodes = []

class Season():
    def __init__(self, name):
        self.name = name
        self.episodes = {}

class Channel():
    def __init__(self, provider, info):
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
                    self.group_title = params['group-title'].strip().replace(";", " ").replace("  ", " ")
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
            self.logo_path = os.path.join(PROVIDERS_PATH, "%s-%s%s" % (slugify(provider.name), slugify(self.name), ext))

class Manager():

    def __init__(self, settings):
        os.system("mkdir -p '%s'" % PROVIDERS_PATH)
        self.verbose = False
        self.settings = settings

    def debug(self, *args):
        if self.verbose:
            print(args)

    def get_playlist(self, provider, refresh=False) -> bool:
        """Get the playlist from the provided URL

        Args:
            provider ([type]): [description]
            refresh (bool, optional): [description]. Defaults to False.

        Returns:
            bool: True for SUCCESS, False for ERROR
        """
        ret_code = True

        if "file://" in provider.url:
            # local file
            provider.path = provider.url.replace("file://", "")

        elif "://" in provider.url:
            # Other protocol, assume it's http
            if refresh or not os.path.exists(provider.path):
                # Assume it is not going to make it
                ret_code = False

                headers = {
                    'User-Agent': self.settings.get_string("user-agent"),
                    'Referer': self.settings.get_string("http-referer")
                }
                try:
                    response = requests.get(provider.url, headers=headers, timeout=(5,120), stream=True)

                    # If there is an answer from the remote server
                    if response.status_code == 200:
                        # Set downloaded size
                        downloaded_bytes = 0
                        # Get total playlist byte size
                        total_content_size = int(response.headers.get('content-length', 15))
                        # Set stream blocks
                        block_bytes = int(4*1024*1024)     # 4 MB

                        response.encoding = response.apparent_encoding
                        #try:
                        #    source = response.content.decode("UTF-8")
                        #except UnicodeDecodeError as e:
                        #    source = response.content.decode("latin1")
                        with open(provider.path, "w") as file:
                            # Grab data by block_bytes
                            for data in response.iter_content(block_bytes,decode_unicode=True):
                                downloaded_bytes += block_bytes
                                print("{} bytes".format(downloaded_bytes))
                                file.write(str(data))
                        if downloaded_bytes < total_content_size:
                            print("The file size is incorrect, deleting")
                            os.remove(provider.path)
                        else:
                            # Set the datatime when it was last retreived
                            # self.settings.set_
                            ret_code = True
                    else:
                        print("HTTP error %d while retrieving from %s!" % (response.status_code, provider.url))
                except Exception as e:
                    print(e)
        else:
            # No protocol, assume it's local
            provider.path = provider.url

        return ret_code

    def check_playlist(self, provider):
        legit = False
        if os.path.exists(provider.path):
            with open(provider.path, "r") as file:
                content = file.read()
                if ("#EXTM3U" in content and "#EXTINF" in content):
                    legit = True
                    self.debug("Content looks legit: %s" % provider.name)
                else:
                    self.debug("Nope: %s" % provider.path)
        return legit

    def load_channels(self, provider):
        with open(provider.path, "r") as file:
            channel = None
            group = None
            groups = {}
            series = {}
            for line in file:
                line = line.strip()
                if line.startswith("#EXTM3U"):
                    continue
                if line.startswith("#EXTINF"):
                    channel = Channel(provider, line)
                    self.debug("New channel: ", line)
                    continue
                if "://" in line and not (line.startswith("#")):
                    self.debug("    ", line)
                    if channel == None:
                        self.debug("    --> channel is None")
                        continue
                    if channel.url != None:
                        # We already found the URL, skip the line
                        self.debug("    --> channel URL was already found")
                        continue
                    if channel.name == None or "***" in channel.name:
                        self.debug("    --> channel name is None")
                        continue
                    channel.url = line
                    self.debug("    --> URL found: ", line)

                    serie = None
                    f = SERIES.fullmatch(channel.name)
                    if f != None:
                        res = f.groupdict()
                        series_name = res['series']
                        if series_name in series.keys():
                            serie = series[series_name]
                        else:
                            serie = Serie(series_name)
                            #todo put in group
                            provider.series.append(serie)
                            series[series_name] = serie
                            serie.logo = channel.logo
                            serie.logo_path = channel.logo_path
                        season_name = res['season']
                        if season_name in serie.seasons.keys():
                            season = serie.seasons[season_name]
                        else:
                            season = Season(season_name)
                            serie.seasons[season_name] = season

                        episode_name = res['episode']
                        season.episodes[episode_name] = channel
                        serie.episodes.append(channel)

                    if channel.group_title != None and channel.group_title.strip() != "":
                        if group == None or group.name != channel.group_title:
                            if channel.group_title in groups.keys():
                                group = groups[channel.group_title]
                            else:
                                group = Group(channel.group_title)
                                provider.groups.append(group)
                                groups[channel.group_title] = group
                        if serie != None and serie not in group.series:
                            group.series.append(serie)
                        group.channels.append(channel)
                        if group.group_type == TV_GROUP:
                            provider.channels.append(channel)
                        elif group.group_type == MOVIES_GROUP:
                            provider.movies.append(channel)
                    else:
                        provider.channels.append(channel)
