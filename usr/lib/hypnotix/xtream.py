#!/usr/bin/python3
"""xtream

Module handles downloading xtream data
It does not support M3U

Part of this content comes from 
https://github.com/chazlarson/py-xtream-codes/blob/master/xtream.py
https://github.com/linuxmint/hypnotix

Author: Claudio Olmi
Github: superolmo

"""

__version__ = '0.1'
__author__ = 'Claudio Olmi'

import requests 
import time
from os import path as osp
from os import makedirs

# Timing xtream json downloads
from timeit import default_timer as timer, timeit

import json

# used for URL validation
import re

class Channel():
    stream_type = ""
    logo_path = ""
    logo = ""
    info = ""
    id = ""
    url = ""

    # What is the difference between the below name and title?
    name = ""
    title = ""

    # Group info
    group_title = ""
    group_id = ""

    is_adult = ""
    added = ""
    epg_channel_id = ""

    def __init__(self, xtream: object, group_title, stream_info):
        stream_type = stream_info['stream_type']
        # Adjust the odd "created_live" type
        if stream_type == "created_live":
            stream_type = "live"

        if stream_type != "live" and stream_type != "movie":
            print("Error the channel has unknown stream type `{}`\n`{}`".format(
                stream_type,stream_info
            ))
        else:
            # Raw JSON Channel
            self.raw = stream_info

            stream_name = stream_info['name']
            self.id = stream_info['stream_id']
            self.name = stream_name
            self.logo = stream_info['stream_icon']
            self.logo_path = xtream.getLogoLocalPath(self.logo)

            self.group_id = stream_info['category_id']

            self.group_title = group_title
            self.title = stream_name

            if stream_type == "live":
                stream_extension = "ts"
                
                self.is_adult = stream_info['is_adult']
                self.epg_channel_id = stream_info['epg_channel_id']
                self.added = stream_info['added']

            elif stream_type == "movie":
                stream_extension = stream_info['container_extension']

            self.url = "http://mega.test25.in:80/{}/{}/{}/{}.{}".format(
                stream_info['stream_type'],
                xtream.authorization['username'],
                xtream.authorization['password'],
                stream_info['stream_id'],
                stream_extension
                )
            
            # Check that the constructed URL is valid
            if not xtream.validateURL(self.url):
                print("{} - Bad URL? `{}`".format(self.name, self.url))

class Group():
    def __init__(self, group_info: dict, stream_type: str):
        # Raw JSON Group
        self.raw = group_info

        TV_GROUP, MOVIES_GROUP, SERIES_GROUP = range(3)

        if "VOD" == stream_type:
            self.group_type = MOVIES_GROUP
        elif "Series" == stream_type:
            self.group_type = SERIES_GROUP
        elif "Live":
            self.group_type = TV_GROUP
        else:
            print("Unrecognized stream type `{}` for `{}`".format(
                stream_type, group_info
            ))
        self.name = group_info['category_name']
        self.group_id = group_info['category_id']
        self.channels = []
        self.series = []

class Episode():
    def __init__(self, xtream: object, series_info, group_title, episode_info) -> None:
        # Raw JSON Episode
        self.raw = episode_info

        self.title = episode_info['title']
        self.name = self.title
        self.group_title = group_title
        self.id = episode_info['id']
        self.container_extension = episode_info['container_extension']
        self.episode_number = episode_info['episode_num']
        self.av_info = episode_info['info']

        self.logo = series_info['cover']
        self.logo_path = xtream.getLogoLocalPath(self.logo)
        

        self.url = "http://mega.test25.in:80/series/{}/{}/{}.{}".format(
            xtream.authorization['username'],
            xtream.authorization['password'],
            self.id,
            self.container_extension
            )

        # Check that the constructed URL is valid
        if not xtream.validateURL(self.url):
            print("{} - Bad URL? `{}`".format(self.name, self.url))

class Serie():
    def __init__(self, xtream: object, series_info):
        # Raw JSON Series
        self.raw = series_info

        self.name = series_info['name']
        self.series_id = series_info['series_id']
        self.logo = series_info['cover']
        self.logo_path = xtream.getLogoLocalPath(self.logo)
        
        self.seasons = {}
        self.episodes = {}

        self.plot = series_info['plot']
        self.youtube_trailer = series_info['youtube_trailer']
        self.genre = series_info['genre']

class Season():
    def __init__(self, name):
        self.name = name
        self.episodes = {}

class XTream():

    name = ""
    server = ""
    username = ""
    password = ""

    liveType = "Live"
    vodType = "VOD"
    seriesType = "Series"

    authData = {}
    authorization = {}

    groups = []
    channels = []
    series = []
    movies = []

    catch_all_group = Group(
        {
            "category_id": "9999", 
            "category_name":"xEverythingElse",
            "parent_id":0
        },
        liveType
    )

    def __init__(self, provider_name: str, provider_username: str, provider_password: str, provider_url: str, cache_path: str = ""):
        """Initialize Xtream Class

        Args:
            provider_name (str): Name of the IPTV provider
            provider_username (str): User name of the IPTV provider
            provider_password (str): Password of the IPTV provider
            provider_url (str): URL of the IPTV provider
            cache_path (str, optional): Location where to save loaded files. Defaults to "".
        """
        self.server = provider_url
        self.username = provider_username
        self.password = provider_password
        self.name = provider_name

        # if the cache_path is specified, test that it is a directory
        if cache_path != "":
            if osp.isdir(cache_path):
                self.cache_path = cache_path
            else:
                print("Cache Path is not a directory, using default '~/.xtream-cache/'")
        
        # If the cache_path is still empty, use default
        if self.cache_path == "":
            self.cache_path = osp.expanduser("~/.xtream-cache/")
            if not osp.isdir(self.cache_path):
                makedirs(self.cache_path, exist_ok=True)

        self.authenticate()

    def slugify(self, string: str) -> str:
        """Normalize string

        Normalizes string, converts to lowercase, removes non-alpha characters,
        and converts spaces to hyphens.

        Args:
            string (str): String to be normalized

        Returns:
            str: Normalized String
        """
        return "".join(x.lower() for x in string if x.isalnum())

    def validateURL(self, url: str) -> bool:
        regex = re.compile(
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
            r'localhost|' #localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        return re.match(regex, url) is not None

    def getLogoLocalPath(self, logoURL: str) -> str:
        """Convert the Logo URL to a local Logo Path

        Args:
            logoURL (str): The Logo URL

        Returns:
            [type]: The logo path as a string or None
        """
        local_logo_path = None
        if logoURL != None:
            if not self.validateURL(logoURL):
                #print("Bad URL? `{}`".format(logoURL))
                logoURL = None
            else:
                local_logo_path = osp.join(self.cache_path, "{}-{}".format(
                    self.slugify(self.name), 
                    self.slugify(osp.split(logoURL)[-1])
                    )
                )
        return local_logo_path


    # If you want to limit the displayed output data, 
    # you can use params[offset]=X & params[items_per_page]=X on your call.

    # Authentication returns information about the account and server:
    def authenticate(self):
        r = requests.get(self.get_authenticate_URL())
        self.authData = r.json()
        self.authorization = {
            "username": self.authData["user_info"]["username"],
            "password": self.authData["user_info"]["password"]
            }

    def loadFromFile(self, filename) -> dict:
        #Build the full path
        full_filename = osp.join(self.cache_path, "{}-{}".format(
                self.slugify(self.name), 
                filename
        ))


        my_data = None
        #threshold_time = time.mktime(time.gmtime(60*60*8))   # 8 hours
        threshold_time = 60*60*8

        # Get the enlapsed seconds since last file update
        diff_time = time.time() - osp.getmtime(full_filename)
        # If the file was updated less than the threshold time, 
        # it means that the file is still fresh, we can load it.
        # Otherwise skip and return None to force a re-download
        if threshold_time > diff_time:
            # Load the JSON data
            try:
                with open(full_filename,mode='r',encoding='utf-8') as myfile:
                    #my_data = myfile.read()
                    my_data = json.load(myfile)
            except Exception as e:
                print("Could not save to file `{}`: e=`{}`".format(
                    full_filename, e
                ))

        return my_data


    def saveToFile(self, data_list: dict, filename: str) -> bool:
        """Save a dictionary to file

        This function will overwrite the file if already exists

        Args:
            data_list (dict): Dictionary to save 
            filename (str): Name of the file

        Returns:
            bool: True if successfull, False if error
        """
        #Build the full path
        full_filename = osp.join(self.cache_path, "{}-{}".format(
                self.slugify(self.name), 
                filename
        ))
        # If the path makes sense, save the file
        json_data = json.dumps(data_list, ensure_ascii=False)
        try:
            with open(full_filename, mode='wt', encoding='utf-8') as myfile:
                myfile.write(json_data)
        except Exception as e:
            print("Could not save to file `{}`: e=`{}`".format(
                full_filename, e
            ))
            return False

        return True

    def load_iptv(self):
        """Load XTream IPTV

        """

        #loading_stream_type = self.liveType
        for loading_stream_type in (self.liveType, self.vodType, self.seriesType):
            ## Get GROUPS

            # Try loading local file
            dt = 0
            all_cat = self.loadFromFile("all_groups_{}.json".format(
                loading_stream_type
            ))
            # If file empty or does not exists, download it from remote
            if all_cat == None:
                # Load all Groups and save file locally
                start = timer()
                all_cat = self.categories(loading_stream_type)
                self.saveToFile(all_cat,"all_groups_{}.json".format(
                    loading_stream_type
                ))
                dt = timer()-start

            # If we got the GROUPS data, show the statistics and load GROUPS
            if all_cat != None:
                print("Loaded {} {} Groups in {:.3f} seconds".format(
                    len(all_cat),loading_stream_type,dt
                ))
                ## Add GROUPS to dictionaries

                # Add the catch-all-errors group
                #  Add to xtream class
                self.groups.append(self.catch_all_group)
                #  Add to provider
                #provider.groups.append(self.catch_all_group)

                for cat_obj in all_cat:
                    # Create Group (Category)
                    new_group = Group(cat_obj, loading_stream_type)
                    #  Add to xtream class
                    self.groups.append(new_group)
                    #  Add to provider
                    #provider.groups.append(new_group)
            else:
                print("Could not load {} Groups".format(loading_stream_type))

            ## Get Streams

            # Try loading local file
            dt = 0
            all_streams = self.loadFromFile("all_stream_{}.json".format(
                loading_stream_type
            ))
            # If file empty or does not exists, download it from remote
            if all_streams == None:
                # Load all Streams and save file locally
                start = timer()
                all_streams = self.streams(loading_stream_type)
                self.saveToFile(all_streams,"all_stream_{}.json".format(
                    loading_stream_type
                ))
                dt = timer()-start

            # If we got the STREAMS data, show the statistics and load Streams
            if all_streams != None:
                print("Loaded {} {} Streams in {:.3f} seconds".format(
                    len(all_streams),loading_stream_type,dt
                ))
                ## Add Streams to dictionaries

                for stream_channel in all_streams:
                    # Generate Group Title
                    if stream_channel['name'][0].isalnum():
                        group_title = str.split(stream_channel['name'],'|')[0]

                        # Some channels have no group, 
                        # so let's add them to the catche all group
                        if stream_channel['category_id'] == None:
                            stream_channel['category_id'] = '9999'
                        
                        if loading_stream_type == self.seriesType:
                            # Load all Series
                            new_series = Serie(self, stream_channel)
                            # To get all the Episodes for every Season of each 
                            # Series is very time consuming, we will only 
                            # populate the Series once the user click on the 
                            # Series, the Seasons and Episodes will be loaded 
                            # using x.getSeriesInfoByID() function

                        else:
                            new_channel = Channel(
                                self, 
                                group_title, 
                                stream_channel
                            )

                        # Find the first occurence of the group that the 
                        # Channel or Stream is pointing to
                        the_group = next(
                            (x for x in self.groups if x.group_id == stream_channel['category_id']),
                            None
                        )

                        # Save the new channel to the provider object and the new_group object
                        if loading_stream_type == self.liveType:
                            self.channels.append(new_channel)
                            #provider.channels.append(new_channel)
                        elif loading_stream_type == self.vodType:
                            self.movies.append(new_channel)
                            #provider.movies.append(new_channel)
                        else:
                            self.series.append(new_series)
                            #provider.series.append(new_series)
                        
                        if loading_stream_type != self.seriesType:
                            #self.channels.append(new_channel)
                            if the_group != None:
                                the_group.channels.append(new_channel)
                            else:
                                print("Group not found `{}`".format(stream_channel['name']))
                        else:
                            if the_group != None:
                                the_group.series.append(new_series)
                            else:
                                print("Group not found `{}`".format(stream_channel['name']))
            else:
                print("Could not load {} Streams".format(loading_stream_type))

    def getSeriesInfoByID(self, get_series):
        start = timer()
        series_seasons = self.seriesInfoByID(get_series.series_id)
        dt = timer()-start
        #print("Loaded in {:.3f} sec".format(dt))
        for series_info in series_seasons["seasons"]:
            season_name = series_info["name"]
            season_key = series_info['season_number']
            season = Season(season_name)
            get_series.seasons[season_name] = season
            if "episodes" in series_seasons.keys():
                for series_season in series_seasons["episodes"].keys():
                    for episode_info in series_seasons["episodes"][str(series_season)]:
                        new_episode_channel = Episode(
                            self,
                            series_info,
                            "Testing",
                            episode_info
                        )
                        season.episodes[episode_info['title']] = new_episode_channel

    # GET Stream Categories
    def categories(self, streamType: str):
        """Get from provider all category for specific stream type

        Args:
            streamType (str): Stream type can be Live, VOD, Series

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        theURL = ""
        if streamType == self.liveType:
            theURL = self.get_live_categories_URL()
        elif streamType == self.vodType:
            theURL = self.get_vod_cat_URL()
        elif streamType == self.seriesType:
            theURL = self.get_series_cat_URL()
        else:
            theURL = ""

        r = requests.get(theURL, timeout=(2,15))

        if r.status_code == 200:
            return r.json()
        return None

    # GET Streams
    def streams(self, streamType: str):
        """Get from provider all streams for specific stream type

        Args:
            streamType (str): Stream type can be Live, VOD, Series

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        theURL = ""
        if streamType == self.liveType:
            theURL = self.get_live_streams_URL()
        elif streamType == self.vodType:
            theURL = self.get_vod_streams_URL()
        elif streamType == self.seriesType:
            theURL = self.get_series_URL()
        else:
            theURL = ""

        r = requests.get(theURL, timeout=(2,15))
        if r.status_code == 200:
            return r.json()
        return None

    # GET Streams by Category
    def streamsByCategory(self, streamType: str, category_id):
        
        theURL = ""

        if streamType == self.liveType:
            theURL = self.get_live_streams_URL_by_category(category_id)
        elif streamType == self.vodType:
            theURL = self.get_vod_streams_URL_by_category(category_id)
        elif streamType == self.seriesType:
            theURL = self.get_series_URL_by_category(category_id)
        else:
            theURL = ""

        r = requests.get(theURL)
        if r.status_code == 200:
            return r.json()
        return None

    # GET SERIES Info
    def seriesInfoByID(self, series_id):  
        r = requests.get(self.get_series_info_URL_by_ID(series_id)) 
        if r.status_code == 200:
            return r.json()
        return r
    # The seasons array, might be filled or might be completely empty. 
    # If it is not empty, it will contain the cover, overview and the air date 
    # of the selected season.
    # In your APP if you want to display the series, you have to take that 
    # from the episodes array.

    # GET VOD Info
    def vodInfoByID(self, vod_id):  
        r = requests.get(self.get_VOD_info_URL_by_ID(vod_id)) 
        return r

    # GET short_epg for LIVE Streams (same as stalker portal, 
    # prints the next X EPG that will play soon)
    def liveEpgByStream(self, stream_id):  
        r = requests.get(self.get_live_epg_URL_by_stream(stream_id)) 
        if r.status_code == 200:
            return r.json()
        return r

    def liveEpgByStreamAndLimit(self, stream_id, limit):  
        r = requests.get(self.get_live_epg_URL_by_stream_and_limit(stream_id, limit)) 
        return r

    #  GET ALL EPG for LIVE Streams (same as stalker portal, 
    # but it will print all epg listings regardless of the day)
    def allLiveEpgByStream(self, stream_id):  
        r = requests.get(self.get_all_live_epg_URL_by_stream(stream_id)) 
        return r

    # Full EPG List for all Streams
    def allEpg(self):  
        r = requests.get(self.get_all_epg_URL()) 
        return r


    ## URL-builder methods

    def get_authenticate_URL(self):  
        URL = '%s/player_api.php?username=%s&password=%s' % (self.server, self.username, self.password) 
        return URL

    def get_live_categories_URL(self):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s' % (self.server, self.username, self.password, 'get_live_categories')  
        return URL

    def get_live_streams_URL(self):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s' % (self.server, self.username, self.password, 'get_live_streams')  
        return URL

    def get_live_streams_URL_by_category(self, category_id):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s&category_id=%s' % (self.server, self.username, self.password, 'get_live_streams', category_id)
        return URL

    def get_vod_cat_URL(self):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s' % (self.server, self.username, self.password, 'get_vod_categories')  
        return URL

    def get_vod_streams_URL(self):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s' % (self.server, self.username, self.password, 'get_vod_streams')  
        return URL

    def get_vod_streams_URL_by_category(self, category_id):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s&category_id=%s' % (self.server, self.username, self.password, 'get_vod_streams', category_id)
        return URL

    def get_series_cat_URL(self):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s' % (self.server, self.username, self.password, 'get_series_categories')  
        return URL

    def get_series_URL(self):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s' % (self.server, self.username, self.password, 'get_series')  
        return URL

    def get_series_URL_by_category(self, category_id):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s&category_id=%s' % (self.server, self.username, self.password, 'get_series', category_id)  
        return URL

    def get_series_info_URL_by_ID(self, series_id):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s&series_id=%s' % (self.server, self.username, self.password, 'get_series_info', series_id)  
        return URL

    def get_VOD_info_URL_by_ID(self, vod_id):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s&vod_id=%s' % (self.server, self.username, self.password, 'get_vod_info', vod_id)  
        return URL

    def get_live_epg_URL_by_stream(self, stream_id):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s&stream_id=%s' % (self.server, self.username, self.password, 'get_short_epg', stream_id)  
        return URL

    def get_live_epg_URL_by_stream_and_limit(self, stream_id, limit):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s&stream_id=%s&limit=%s' % (self.server, self.username, self.password, 'get_short_epg', stream_id, limit)  
        return URL

    def get_all_live_epg_URL_by_stream(self, stream_id):  
        URL = '%s/player_api.php?username=%s&password=%s&action=%s&stream_id=%s' % (self.server, self.username, self.password, 'get_simple_data_table', stream_id)  
        return URL

    def get_all_epg_URL(self):  
        URL = '%s/xmltv.php?username=%s&password=%s' % (self.server, self.username, self.password)  
        return URL