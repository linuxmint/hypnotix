#!/usr/bin/python3
"""xtream

Module handles downloading xtream data
It does not support M3U

This application comes from the pyxtream library found at:
https://pypi.org/project/pyxtream

Part of this content comes from
https://github.com/chazlarson/py-xtream-codes/blob/master/xtream.py
https://github.com/linuxmint/hypnotix

Author: Claudio Olmi
Github: superolmo

"""

__version__ = '0.5.0'
__author__ = 'Claudio Olmi'

import json
import re  # used for URL validation
import time
from os import path as osp
from os import makedirs
from timeit import default_timer as timer  # Timing xtream json downloads
from typing import List, Tuple

import requests


class Channel():
    # Required by Hypnotix
    id = ""
    name = "" # What is the difference between the below name and title?
    logo = ""
    logo_path = ""
    group_title = ""
    title = ""
    url = ""

    # XTream
    stream_type = ""
    group_id = ""
    is_adult = 0
    added = ""
    epg_channel_id = ""
    added = ""

    # This contains the raw JSON data
    raw = ""

    def __init__(self, xtream: object, group_title, stream_info):
        stream_type = stream_info['stream_type']
        # Adjust the odd "created_live" type
        if stream_type == "created_live" or stream_type == "radio_streams":
            stream_type = "live"

        if stream_type != "live" and stream_type != "movie":
            print("Error the channel has unknown stream type `{}`\n`{}`".format(
                stream_type,stream_info
            ))
        else:
            # Raw JSON Channel
            self.raw = stream_info

            stream_name = stream_info['name']

            # Required by Hypnotix
            self.id = stream_info['stream_id']
            self.name = stream_name
            self.logo = stream_info['stream_icon']
            self.logo_path = xtream._get_logo_local_path(self.logo)
            self.group_title = group_title
            self.title = stream_name

            # Check if category_id key is available
            if "category_id" in stream_info.keys():
                self.group_id = int(stream_info['category_id'])

            if stream_type == "live":
                stream_extension = "ts"

                # Default to 0
                self.is_adult = 0
                # Check if is_adult key is available
                if "is_adult" in stream_info.keys():
                    self.is_adult = int(stream_info['is_adult'])

                # Check if epg_channel_id key is available
                if "epg_channel_id" in stream_info.keys():
                    self.epg_channel_id = stream_info['epg_channel_id']

                self.added = stream_info['added']

            elif stream_type == "movie":
                stream_extension = stream_info['container_extension']

            # Required by Hypnotix
            self.url = "{}/{}/{}/{}/{}.{}".format(
                xtream.server,
                stream_info['stream_type'],
                xtream.authorization['username'],
                xtream.authorization['password'],
                stream_info['stream_id'],
                stream_extension
                )

            # Check that the constructed URL is valid
            if not xtream._validate_url(self.url):
                print("{} - Bad URL? `{}`".format(self.name, self.url))

    def export_json(self):
        jsondata = {}

        jsondata['url'] = self.url
        jsondata.update(self.raw)
        jsondata['logo_path'] = self.logo_path

        return jsondata

class Group():
    # Required by Hypnotix
    name = ""
    group_type = ""

    # XTream
    group_id = ""

    # This contains the raw JSON data
    raw = ""

    def __init__(self, group_info: dict, stream_type: str):
        # Raw JSON Group
        self.raw = group_info

        self.channels = []
        self.series = []

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

        # Check if category_id key is available
        if "category_id" in group_info.keys():
            self.group_id = int(group_info['category_id'])

class Episode():
    # Required by Hypnotix
    title = ""
    name = ""

    # XTream

    # This contains the raw JSON data
    raw = ""

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
        self.logo_path = xtream._get_logo_local_path(self.logo)


        self.url = "{}/series/{}/{}/{}.{}".format(
            xtream.server,
            xtream.authorization['username'],
            xtream.authorization['password'],
            self.id,
            self.container_extension
            )

        # Check that the constructed URL is valid
        if not xtream._validate_url(self.url):
            print("{} - Bad URL? `{}`".format(self.name, self.url))

class Serie():
    # Required by Hypnotix
    name = ""
    logo = ""
    logo_path = ""

    # XTream
    series_id = ""
    plot = ""
    youtube_trailer = ""
    genre = ""

    # This contains the raw JSON data
    raw = ""

    def __init__(self, xtream: object, series_info):
        # Raw JSON Series
        self.raw = series_info

        # Required by Hypnotix
        self.name = series_info['name']
        self.logo = series_info['cover']
        self.logo_path = xtream._get_logo_local_path(self.logo)

        self.seasons = {}
        self.episodes = {}

        # Check if category_id key is available
        if "series_id" in series_info.keys():
            self.series_id = int(series_info['series_id'])

        # Check if plot key is available
        if "plot" in series_info.keys():
            self.plot = series_info['plot']

        # Check if youtube_trailer key is available
        if "youtube_trailer" in series_info.keys():
            self.youtube_trailer = series_info['youtube_trailer']

        # Check if genre key is available
        if "genre" in series_info.keys():
            self.genre = series_info['genre']

class Season():
    # Required by Hypnotix
    name = ""

    def __init__(self, name):
        self.name = name
        self.episodes = {}

class XTream():

    name = ""
    server = ""
    username = ""
    password = ""

    live_type = "Live"
    vod_type = "VOD"
    series_type = "Series"

    auth_data = {}
    authorization = {}

    groups = []
    channels = []
    series = []
    movies = []

    state = {'authenticated': False, 'loaded': False}

    hide_adult_content = False

    catch_all_group = Group(
        {
            "category_id": "9999",
            "category_name":"xEverythingElse",
            "parent_id":0
        },
        ""
    )
    # If the cached JSON file is older than threshold_time_sec then load a new
    # JSON dictionary from the provider
    threshold_time_sec = 60*60*8

    def __init__(self,
                provider_name: str,
                provider_username: str,
                provider_password: str,
                provider_url: str,
                hide_adult_content: bool = False,
                cache_path: str = ""
                ):
        """Initialize Xtream Class

        Args:
            provider_name     (str):            Name of the IPTV provider
            provider_username (str):            User name of the IPTV provider
            provider_password (str):            Password of the IPTV provider
            provider_url      (str):            URL of the IPTV provider
            hide_adult_content(bool):           When `True` hide stream that are marked for adult
            cache_path        (str, optional):  Location where to save loaded files. Defaults to empty string.

        Returns: XTream Class Instance

        - Note: If it fails to authorize with provided username and password,
                auth_data will be an empty dictionary.

        """
        self.server = provider_url
        self.username = provider_username
        self.password = provider_password
        self.name = provider_name
        self.cache_path = cache_path
        self.hide_adult_content = hide_adult_content

        # if the cache_path is specified, test that it is a directory
        if self.cache_path != "":
            # If the cache_path is not a directory, clear it
            if not osp.isdir(self.cache_path):
                print(" - Cache Path is not a directory, using default '~/.xtream-cache/'")
                self.cache_path == ""

        # If the cache_path is still empty, use default
        if self.cache_path == "":
            self.cache_path = osp.expanduser("~/.xtream-cache/")
            if not osp.isdir(self.cache_path):
                makedirs(self.cache_path, exist_ok=True)

        self.authenticate()

    def search_stream(self, keyword: str, ignore_case: bool = True, return_type: str = "LIST") -> List:
        """Search for streams

        Args:
            keyword (str): Keyword to search for. Supports REGEX
            ignore_case (bool, optional): True to ignore case during search. Defaults to "True".
            return_type (str, optional): Output format, 'LIST' or 'JSON'. Defaults to "LIST".

        Returns:
            List: List with all the results, it could be empty. Each result
        """

        search_result = []

        if ignore_case:
            regex = re.compile(keyword,re.IGNORECASE)
        else:
            regex = re.compile(keyword)

        print("Checking {} movies".format(len(self.movies)))
        for stream in self.movies:
            if re.match(regex, stream.name) is not None:
                search_result.append(stream.export_json())

        print("Checking {} channels".format(len(self.channels)))
        for stream in self.channels:
            if re.match(regex, stream.name) is not None:
                search_result.append(stream.export_json())

        print("Checking {} series".format(len(self.series)))
        for stream in self.series:
            if re.match(regex, stream.name) is not None:
                search_result.append(stream.export_json())

        if return_type == "JSON":
            if search_result != None:
                print("Found {} results `{}`".format(len(search_result),keyword))
                return json.dumps(search_result, ensure_ascii=False)
        else:
            return search_result


    def _slugify(self, string: str) -> str:
        """Normalize string

        Normalizes string, converts to lowercase, removes non-alpha characters,
        and converts spaces to hyphens.

        Args:
            string (str): String to be normalized

        Returns:
            str: Normalized String
        """
        return "".join(x.lower() for x in string if x.isprintable())

    def _validate_url(self, url: str) -> bool:
        regex = re.compile(
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
            r'localhost|' #localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        return re.match(regex, url) is not None

    def _get_logo_local_path(self, logo_url: str) -> str:
        """Convert the Logo URL to a local Logo Path

        Args:
            logoURL (str): The Logo URL

        Returns:
            [type]: The logo path as a string or None
        """
        local_logo_path = None
        if logo_url != None:
            if not self._validate_url(logo_url):
                logo_url = None
            else:
                local_logo_path = osp.join(self.cache_path, "{}-{}".format(
                    self._slugify(self.name),
                    self._slugify(osp.split(logo_url)[-1])
                    )
                )
        return local_logo_path

    def authenticate(self):
        """Login to provider
        """
        # If we have not yet successfully authenticated, attempt authentication
        if (self.state['authenticated'] == False):
            # Erase any previous data
            self.auth_data = {}
            try:
                # Request authentication, wait 4 seconds maximum
                r = requests.get(self.get_authenticate_URL(), timeout=(4))
                # If the answer is ok, process data and change state
                if r.ok:
                    self.auth_data = r.json()
                    self.authorization = {
                        "username": self.auth_data["user_info"]["username"],
                        "password": self.auth_data["user_info"]["password"]
                    }
                    self.state['authenticated'] = True
                else:
                    print("Provider `{}` could not be loaded. Reason: `{} {}`".format(self.name,r.status_code, r.reason))
            except requests.exceptions.ConnectionError:
                # If connection refused
                print("{} - Connection refused URL: {}".format(self.name, self.server))

    def _load_from_file(self, filename) -> dict:
        """Try to load the dictionary from file

        Args:
            filename ([type]): File name containing the data

        Returns:
            dict: Dictionary if found and no errors, None if file does not exists
        """
        #Build the full path
        full_filename = osp.join(self.cache_path, "{}-{}".format(
                self._slugify(self.name),
                filename
        ))

        if osp.isfile(full_filename):

            my_data = None

            # Get the enlapsed seconds since last file update
            diff_time = time.time() - osp.getmtime(full_filename)
            # If the file was updated less than the threshold time,
            # it means that the file is still fresh, we can load it.
            # Otherwise skip and return None to force a re-download
            if self.threshold_time_sec > diff_time:
                # Load the JSON data
                try:
                    with open(full_filename,mode='r',encoding='utf-8') as myfile:
                        my_data = json.load(myfile)
                        if len(my_data) == 0:
                            my_data = None
                except Exception as e:
                    print(" - Could not load from file `{}`: e=`{}`".format(
                        full_filename, e
                    ))
            return my_data
        else:
            return None

    def _save_to_file(self, data_list: dict, filename: str) -> bool:
        """Save a dictionary to file

        This function will overwrite the file if already exists

        Args:
            data_list (dict): Dictionary to save
            filename (str): Name of the file

        Returns:
            bool: True if successfull, False if error
        """
        if data_list != None:

            #Build the full path
            full_filename = osp.join(self.cache_path, "{}-{}".format(
                    self._slugify(self.name),
                    filename
            ))
            # If the path makes sense, save the file
            json_data = json.dumps(data_list, ensure_ascii=False)
            try:
                with open(full_filename, mode='wt', encoding='utf-8') as myfile:
                    myfile.write(json_data)
            except Exception as e:
                print(" - Could not save to file `{}`: e=`{}`".format(
                    full_filename, e
                ))
                return False

            return True
        else:
            return False

    def load_iptv(self):
        """Load XTream IPTV

        - Add all Live TV to XTream.channels
        - Add all VOD to XTream.movies
        - Add all Series to XTream.series
          Series contains Seasons and Episodes. Those are not automatically
          retrieved from the server to reduce the loading time.
        - Add all groups to XTream.groups
          Groups are for all three channel types, Live TV, VOD, and Series

        """
        # If pyxtream has already authenticated the connection and not loaded the data, start loading
        if (self.state['authenticated'] == True):
            if (self.state['loaded'] == False):

                for loading_stream_type in (self.live_type, self.vod_type, self.series_type):
                    ## Get GROUPS

                    # Try loading local file
                    dt = 0
                    all_cat = self._load_from_file("all_groups_{}.json".format(
                        loading_stream_type
                    ))
                    # If file empty or does not exists, download it from remote
                    if all_cat == None:
                        # Load all Groups and save file locally
                        start = timer()
                        all_cat = self._load_categories_from_provider(loading_stream_type)
                        self._save_to_file(all_cat,"all_groups_{}.json".format(
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
                        self.groups.append(self.catch_all_group)

                        for cat_obj in all_cat:
                            # Create Group (Category)
                            new_group = Group(cat_obj, loading_stream_type)
                            #  Add to xtream class
                            self.groups.append(new_group)

                        # Add the catch-all-errors group
                        self.groups.append(Group({"category_id": "9999","category_name":"xEverythingElse","parent_id":0},loading_stream_type))

                        # Sort Categories
                        self.groups.sort(key=lambda x: x.name)
                    else:
                        print(" - Could not load {} Groups".format(loading_stream_type))
                        break

                    ## Get Streams

                    # Try loading local file
                    dt = 0
                    all_streams = self._load_from_file("all_stream_{}.json".format(
                        loading_stream_type
                    ))
                    # If file empty or does not exists, download it from remote
                    if all_streams == None:
                        # Load all Streams and save file locally
                        start = timer()
                        all_streams = self._load_streams_from_provider(loading_stream_type)
                        self._save_to_file(all_streams,"all_stream_{}.json".format(
                            loading_stream_type
                        ))
                        dt = timer()-start

                    # If we got the STREAMS data, show the statistics and load Streams
                    if all_streams != None:
                        print("Loaded {} {} Streams in {:.3f} seconds".format(
                            len(all_streams),loading_stream_type,dt
                        ))
                        ## Add Streams to dictionaries

                        skipped_adult_content = 0
                        skipped_no_name_content = 0

                        for stream_channel in all_streams:
                            skip_stream = False

                            # Skip if the name of the stream is empty
                            if stream_channel['name'] == "":
                                skip_stream = True
                                skipped_no_name_content = skipped_no_name_content + 1
                                self._save_to_file_skipped_streams(stream_channel)

                            # Skip if the user chose to hide adult streams
                            if self.hide_adult_content and loading_stream_type == self.live_type:
                                try:
                                    if stream_channel['is_adult'] == "1":
                                        skip_stream = True
                                        skipped_adult_content = skipped_adult_content + 1
                                        self._save_to_file_skipped_streams(stream_channel)
                                except:
                                    print(" - Stream does not have `is_adult` key:\n\t`{}`".format(json.dumps(stream_channel)))
                                    pass

                            if not skip_stream:
                                # Some channels have no group,
                                # so let's add them to the catch all group
                                if stream_channel['category_id'] == None:
                                    stream_channel['category_id'] = '9999'
                                elif stream_channel['category_id'] != '1':
                                    pass

                                # Find the first occurence of the group that the
                                # Channel or Stream is pointing to
                                the_group = next(
                                    (x for x in self.groups if x.group_id == int(stream_channel['category_id'])),
                                    None
                                )

                                # Set group title
                                if the_group != None:
                                    group_title = the_group.name
                                else:
                                    group_title = self.catch_all_group.name
                                    the_group = self.catch_all_group

                                if loading_stream_type == self.series_type:
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

                                if (new_channel.group_id == '9999'):
                                    print(" - xEverythingElse Channel -> {} - {}".format(new_channel.name,new_channel.stream_type))

                                # Save the new channel to the local list of channels
                                if loading_stream_type == self.live_type:
                                    self.channels.append(new_channel)
                                elif loading_stream_type == self.vod_type:
                                    self.movies.append(new_channel)
                                else:
                                    self.series.append(new_series)

                                # Add stream to the specific Group
                                if the_group != None:
                                    if loading_stream_type != self.series_type:
                                        the_group.channels.append(new_channel)
                                    else:
                                        the_group.series.append(new_series)
                                else:
                                    print(" - Group not found `{}`".format(stream_channel['name']))

                        # Print information of which streams have been skipped
                        if self.hide_adult_content:
                            print(" - Skipped {} adult {} streams".format(skipped_adult_content, loading_stream_type))
                        if skipped_no_name_content > 0:
                            print(" - Skipped {} unprintable {} streams".format(skipped_no_name_content, loading_stream_type))
                    else:
                        print(" - Could not load {} Streams".format(loading_stream_type))

                    self.state['loaded'] = True

            else:
                print("Warning, data has already been loaded.")
        else:
            print("Warning, cannot load steams since authorization failed")

    def _save_to_file_skipped_streams(self, stream_channel: Channel):

        #Build the full path
        full_filename = osp.join(self.cache_path, "skipped_streams.json")

        # If the path makes sense, save the file
        json_data = json.dumps(stream_channel, ensure_ascii=False)
        try:
            with open(full_filename, mode='a', encoding='utf-8') as myfile:
                myfile.writelines(json_data)
        except Exception as e:
            print(" - Could not save to skipped stream file `{}`: e=`{}`".format(
                full_filename, e
            ))
            return False

    def get_series_info_by_id(self, get_series: dict):
        """Get Seasons and Episodes for a Serie

        Args:
            get_series (dict): Serie dictionary
        """
        start = timer()
        series_seasons = self._load_series_info_by_id_from_provider(get_series.series_id)
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

    def _get_request(self, URL: str, timeout: Tuple = (2,15)):
        """Generic GET Request with Error handling

        Args:
            URL (str): The URL where to GET content
            timeout (Tuple, optional): Connection and Downloading Timeout. Defaults to (2,15).

        Returns:
            [type]: JSON dictionary of the loaded data, or None
        """
        try:
            r = requests.get(URL,timeout=timeout)
            if r.status_code == 200:
                return r.json()

        except requests.exceptions.ConnectionError:
            print(" - Connection Error")

        except requests.exceptions.HTTPError:
            print(" - HTTP Error")

        except requests.exceptions.TooManyRedirects:
            print(" - TooManyRedirects")

        except requests.exceptions.ReadTimeout as e:
            print(" - Timeout while loading data")

        return None

    # GET Stream Categories
    def _load_categories_from_provider(self, stream_type: str):
        """Get from provider all category for specific stream type from provider

        Args:
            stream_type (str): Stream type can be Live, VOD, Series

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        theURL = ""
        if stream_type == self.live_type:
            theURL = self.get_live_categories_URL()
        elif stream_type == self.vod_type:
            theURL = self.get_vod_cat_URL()
        elif stream_type == self.series_type:
            theURL = self.get_series_cat_URL()
        else:
            theURL = ""

        return self._get_request(theURL)

    # GET Streams
    def _load_streams_from_provider(self, stream_type: str):
        """Get from provider all streams for specific stream type

        Args:
            stream_type (str): Stream type can be Live, VOD, Series

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        theURL = ""
        if stream_type == self.live_type:
            theURL = self.get_live_streams_URL()
        elif stream_type == self.vod_type:
            theURL = self.get_vod_streams_URL()
        elif stream_type == self.series_type:
            theURL = self.get_series_URL()
        else:
            theURL = ""

        return self._get_request(theURL)

    # GET Streams by Category
    def _load_streams_by_category_from_provider(self, stream_type: str, category_id):
        """Get from provider all streams for specific stream type with category/group ID

        Args:
            stream_type (str): Stream type can be Live, VOD, Series
            category_id ([type]): Category/Group ID.

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        theURL = ""

        if stream_type == self.live_type:
            theURL = self.get_live_streams_URL_by_category(category_id)
        elif stream_type == self.vod_type:
            theURL = self.get_vod_streams_URL_by_category(category_id)
        elif stream_type == self.series_type:
            theURL = self.get_series_URL_by_category(category_id)
        else:
            theURL = ""

        return self._get_request(theURL)

    # GET SERIES Info
    def _load_series_info_by_id_from_provider(self, series_id: str):
        """Gets informations about a Serie

        Args:
            series_id (str): Serie ID as described in Group

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        return self._get_request(self.get_series_info_URL_by_ID(series_id))

    # The seasons array, might be filled or might be completely empty.
    # If it is not empty, it will contain the cover, overview and the air date
    # of the selected season.
    # In your APP if you want to display the series, you have to take that
    # from the episodes array.

    # GET VOD Info
    def vodInfoByID(self, vod_id):
        return self._get_request(self.get_VOD_info_URL_by_ID(vod_id))

    # GET short_epg for LIVE Streams (same as stalker portal,
    # prints the next X EPG that will play soon)
    def liveEpgByStream(self, stream_id):
        return self._get_request(self.get_live_epg_URL_by_stream(stream_id))

    def liveEpgByStreamAndLimit(self, stream_id, limit):
        return self._get_request(self.get_live_epg_URL_by_stream_and_limit(stream_id, limit))

    #  GET ALL EPG for LIVE Streams (same as stalker portal,
    # but it will print all epg listings regardless of the day)
    def allLiveEpgByStream(self, stream_id):
        return self._get_request(self.get_all_live_epg_URL_by_stream(stream_id))

    # Full EPG List for all Streams
    def allEpg(self):
        return self._get_request(self.get_all_epg_URL())


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
