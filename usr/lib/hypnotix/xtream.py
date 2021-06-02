import requests 
import time
import os.path as osp
from timeit import default_timer as timer, timeit

import json

# used for URL validation
import re

PROVIDER_NAME="Alibaba"
PROVIDERS_PATH = osp.expanduser("~/.hypnotix/providers")
TV_GROUP, MOVIES_GROUP, SERIES_GROUP = range(3)

def slugify(string):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    """
    return "".join(x.lower() for x in string if x.isalnum())

def validateURL(url: str) -> bool:
    regex = re.compile(
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
            r'localhost|' #localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return re.match(regex, url) is not None

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

    def __init__(self, group_title, stream_info, authorization):
        stream_type = stream_info['stream_type']
        # Adjust the odd "created_live" type
        if stream_type == "created_live":
            stream_type = "live"

        if stream_type != "live" and stream_type != "movie":
            print("Error the channel has unknown stream type `{}`\n`{}`".format(stream_type,stream_info))
        else:

            self.info = stream_info
            stream_name = stream_info['name']
            self.id = stream_info['stream_id']
            self.name = stream_name
            self.logo = stream_info['stream_icon']
            self.logo_path = getLogoLocalPath(self.logo)

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
                authorization['username'],
                authorization['password'],
                stream_info['stream_id'],
                stream_extension
                )
            
            if not validateURL(self.url):
                print("{} - Bad URL? `{}`".format(self.name, self.url))

    def show(self):
        print("Stream\nname: `{}`\nid: `{}`\nlogo: `{}`\nlogo_path: `{}`\ngroup_id: `{}`\ngroup_title: `{}`\nurl: `{}`\nis_adult: `{}`\nadded: `{}`".format(
            self.name,
            self.id,
            self.logo,
            self.logo_path,
            self.group_id,
            self.group_title,
            self.url,
            self.is_adult,
            self.added
        ))

def getLogoLocalPath(logoURL: str):
    """Convert the Logo URL to a local Logo Path

    Args:
        logoURL (str): The Logo URL

    Returns:
        [type]: The logo path as a string or None
    """
    local_logo_path = None
    if logoURL != None:
        if not validateURL(logoURL):
            #print("Bad URL? `{}`".format(logoURL))
            logoURL = None
        else:
            local_logo_path = osp.join(PROVIDERS_PATH, "{}-{}".format(
                slugify(PROVIDER_NAME), 
                slugify(osp.split(logoURL)[-1])
                )
            )
    return local_logo_path

class Group():
    def __init__(self, group_info: dict, stream_type: str):
        if "VOD" == stream_type:
            self.group_type = MOVIES_GROUP
        elif "Series" == stream_type:
            self.group_type = SERIES_GROUP
        elif "Live":
            self.group_type = TV_GROUP
        else:
            print("Unrecognized stream type `{}` for `{}`".format(stream_type, group_info))
        self.name = group_info['category_name']
        self.group_id = group_info['category_id']
        self.channels = []
        self.series = []

    def show(self):
        print("stream_type: `{}`\nname: `{}`\ngroup_id: `{}`\nChannel Length: `{}`\nSeries Length: `{}`".format(
            self.group_type,
            self.name,
            self.group_id,
            len(self.channels),
            len(self.series)
        ))

class Episode():
    def __init__(self, series_info, group_title, episode_info, authorization) -> None:
        self.info = episode_info
        self.title = episode_info['title']
        self.name = self.title
        self.group_title = group_title
        self.id = episode_info['id']
        self.container_extension = episode_info['container_extension']
        self.episode_number = episode_info['episode_num']
        self.av_info = episode_info['info']

        self.logo = series_info['cover']
        self.logo_path = getLogoLocalPath(self.logo)
        

        self.url = "http://mega.test25.in:80/series/{}/{}/{}.{}".format(
            authorization['username'],
            authorization['password'],
            self.id,
            self.container_extension
            )

class Serie():
    def __init__(self, series_info):
        self.info = series_info
        self.name = series_info['name']
        self.series_id = series_info['series_id']
        self.logo = series_info['cover']
        self.logo_path = getLogoLocalPath(self.logo)
        
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


# Note: The API Does not provide Full links to the requested stream. You have to build the url to the stream in order to play it.
# 
# For Live Streams the main format is
#            http(s)://domain:port/live/username/password/streamID.ext ( In  allowed_output_formats element you have the available ext )
# 
# For VOD Streams the format is:
# 
# http(s)://domain:port/movie/username/password/streamID.ext ( In  target_container element you have the available ext )
#  
# For Series Streams the format is
# 
# http(s)://domain:port/series/username/password/streamID.ext ( In  target_container element you have the available ext )

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

    catch_all_group = Group({"category_id": "9999", "category_name":"xEverythingElse","parent_id":0},liveType)

    def __init__(self, server, username, password):
        self.server = server
        self.username = username
        self.password = password
        self.authenticate()
        if int(self.authData['user_info']['active_cons']) > 0:
            print(self.authData)

    # If you want to limit the displayed output data, you can use params[offset]=X & params[items_per_page]=X on your call.

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
        full_filename = osp.join(PROVIDERS_PATH, "{}-{}".format(
                slugify(PROVIDER_NAME), 
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
                print("Could not save to file `{}`: e=`{}`".format(full_filename, e))

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
        full_filename = osp.join(PROVIDERS_PATH, "{}-{}".format(
                slugify(PROVIDER_NAME), 
                filename
        ))
        # If the path makes sense, save the file
        json_data = json.dumps(data_list, ensure_ascii=False)
        try:
            with open(full_filename, mode='wt', encoding='utf-8') as myfile:
                myfile.write(json_data)
        except Exception as e:
            print("Could not save to file `{}`: e=`{}`".format(full_filename, e))
            return False

        return True

    def load_iptv(self, provider):
        #loading_stream_type = self.liveType
        for loading_stream_type in (self.liveType, self.vodType, self.seriesType):
            # Try loading local file
            dt = 0
            all_cat = self.loadFromFile("all_groups_{}.json".format(loading_stream_type))
            # If none, download it from remote
            if all_cat == None:
                # Load all Groups and save file locally
                start = timer()
                all_cat = self.categories(loading_stream_type)
                self.saveToFile(all_cat,"all_groups_{}.json".format(loading_stream_type))
                dt = timer()-start

            if all_cat == None:
                return None
            else:
                print("Loaded {} {} Groups in {:.3f} seconds".format(len(all_cat),loading_stream_type,dt))
                # Add the catch-all-errors group for each type
                self.groups.append(self.catch_all_group)
                provider.groups.append(self.catch_all_group)

                for cat_obj in all_cat:
                    # Create Group (Category)
                    new_group = Group(cat_obj, loading_stream_type)
                    self.groups.append(new_group)
                    provider.groups.append(new_group)

            # Try loading local file
            dt = 0
            all_streams = self.loadFromFile("all_stream_{}.json".format(loading_stream_type))
            # If none, download it from remote
            if all_streams == None:
                # Load all Streams and save file locally
                start = timer()
                all_streams = self.streams(loading_stream_type)
                self.saveToFile(all_streams,"all_stream_{}.json".format(loading_stream_type))
                dt = timer()-start

            if all_streams == None:
                return None
            else:
                print("Loaded {} {} Streams in {:.3f} seconds".format(len(all_streams),loading_stream_type,dt))
                for stream_channel in all_streams:
                    #print(f"\rLoading stream number {int(stream_channel['num'])}",end="", flush=True)
                    # Generate Group Title
                    if stream_channel['name'][0].isalnum():
                        group_title = str.split(stream_channel['name'],'|')[0]

                        # Some channels have no group, so let's add them to the catche all group
                        if stream_channel['category_id'] == None:
                            stream_channel['category_id'] = '9999'
                        
                        if loading_stream_type == self.seriesType:
                            # Load all Series
                            new_series = Serie(stream_channel)
                            # To get all the Episodes for every Season or each Series is
                            # very time consuming, we will only populate the Series
                            # Once the user click on the Series, the Seasons and Episodes will 
                            # be loaded using x.getSeriesInfoByID() function

                        else:
                            new_channel = Channel(group_title, stream_channel,self.authorization)

                        # Find the first occurence of the group that the Channel or Stream is pointing to
                        the_group = next((x for x in self.groups if x.group_id == stream_channel['category_id']), None)

                        # Save the new channel to the provider object and the new_group object
                        if loading_stream_type == self.liveType:
                            provider.channels.append(new_channel)
                        elif loading_stream_type == self.vodType:
                            provider.movies.append(new_channel)
                        else:
                            provider.series.append(new_series)
                        
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
            #print("{} with {} episodes".format(season_name,len(series_seasons['episodes'][str(season_key)])))
            if "episodes" in series_seasons.keys():
                for series_season in series_seasons["episodes"].keys():
                    #print("{} with {} episodes".format(season_name,len(series_seasons['episodes'][str(series_season)])))
                    for episode_info in series_seasons["episodes"][str(series_season)]:
                        new_episode_channel = Episode(series_info,"Testing",episode_info,self.authorization)
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
    # If it is not empty, it will contain the cover, overview and the air date of the selected season.
    # In your APP if you want to display the series, you have to take that from the episodes array.

    # GET VOD Info
    def vodInfoByID(self, vod_id):  
        r = requests.get(self.get_VOD_info_URL_by_ID(vod_id)) 
        return r

    # GET short_epg for LIVE Streams (same as stalker portal, prints the next X EPG that will play soon)
    def liveEpgByStream(self, stream_id):  
        r = requests.get(self.get_live_epg_URL_by_stream(stream_id)) 
        if r.status_code == 200:
            return r.json()
        return r

    def liveEpgByStreamAndLimit(self, stream_id, limit):  
        r = requests.get(self.get_live_epg_URL_by_stream_and_limit(stream_id, limit)) 
        return r

    #  GET ALL EPG for LIVE Streams (same as stalker portal, but it will print all epg listings regardless of the day)
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