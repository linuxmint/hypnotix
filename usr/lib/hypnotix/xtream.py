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

__version__ = "0.6.0"
__author__ = "Claudio Olmi"

import json
import re  # used for URL validation
import time
from os import makedirs
from os import path as osp
from sys import stdout
from timeit import default_timer as timer  # Timing xtream json downloads
from typing import List, Protocol, Tuple

import requests


class Channel:
    # Required by Hypnotix
    info = ""
    id = ""
    name = ""  # What is the difference between the below name and title?
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
        stream_type = stream_info["stream_type"]
        # Adjust the odd "created_live" type
        if stream_type in ("created_live", "radio_streams"):
            stream_type = "live"

        if stream_type not in ("live", "movie"):
            print(f"Error the channel has unknown stream type `{stream_type}`\n`{stream_info}`")
        else:
            # Raw JSON Channel
            self.raw = stream_info

            stream_name = stream_info["name"]

            # Required by Hypnotix
            self.id = stream_info["stream_id"]
            self.name = stream_name
            self.logo = stream_info["stream_icon"]
            self.logo_path = xtream._get_logo_local_path(self.logo)
            self.group_title = group_title
            self.title = stream_name

            # Check if category_id key is available
            if "category_id" in stream_info.keys():
                self.group_id = int(stream_info["category_id"])

            if stream_type == "live":
                stream_extension = "ts"

                # Default to 0
                self.is_adult = 0
                # Check if is_adult key is available
                if "is_adult" in stream_info.keys():
                    self.is_adult = int(stream_info["is_adult"])

                # Check if epg_channel_id key is available
                if "epg_channel_id" in stream_info.keys():
                    self.epg_channel_id = stream_info["epg_channel_id"]

                self.added = stream_info["added"]

            elif stream_type == "movie":
                stream_extension = stream_info["container_extension"]

            # Required by Hypnotix
            self.url = f"{xtream.server}/{stream_type}/{xtream.authorization['username']}/" \
                       f"{xtream.authorization['password']}/{stream_info['stream_id']}.{stream_extension}"

            # Check that the constructed URL is valid
            if not xtream._validate_url(self.url):
                print(f"{self.name} - Bad URL? `{self.url}`")

            # Add Channel info in M3U8 format to support Favorite Channel
            self.info = f'#EXTINF:-1 tvg-name="{self.name}" tvg-logo="{self.logo}" group-title="{self.group_title}",{self.name}'

    def export_json(self):
        jsondata = {}

        jsondata["url"] = self.url
        jsondata.update(self.raw)
        jsondata["logo_path"] = self.logo_path

        return jsondata


class Group:
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
        elif "Live" == stream_type:
            self.group_type = TV_GROUP
        else:
            print(f"Unrecognized stream type `{stream_type}` for `{group_info}`")

        self.name = group_info["category_name"]

        # Check if category_id key is available
        if "category_id" in group_info.keys():
            self.group_id = int(group_info["category_id"])


class Episode:
    # Required by Hypnotix
    title = ""
    name = ""
    info = ""

    # XTream

    # This contains the raw JSON data
    raw = ""

    def __init__(self, xtream: object, series_info, group_title, episode_info) -> None:
        # Raw JSON Episode
        self.raw = episode_info

        self.title = episode_info["title"]
        self.name = self.title
        self.group_title = group_title
        self.id = episode_info["id"]
        self.container_extension = episode_info["container_extension"]
        self.episode_number = episode_info["episode_num"]
        self.av_info = episode_info["info"]

        self.logo = series_info["cover"]
        self.logo_path = xtream._get_logo_local_path(self.logo)

        self.url =  f"{xtream.server}/series/" \
                    f"{xtream.authorization['username']}/" \
                    f"{xtream.authorization['password']}/{self.id}.{self.container_extension}"

        # Check that the constructed URL is valid
        if not xtream._validate_url(self.url):
            print(f"{self.name} - Bad URL? `{self.url}`")


class Serie:
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
        self.xtream = xtream

        # Required by Hypnotix
        self.name = series_info["name"]
        self.logo = series_info["cover"]
        self.logo_path = xtream._get_logo_local_path(self.logo)

        self.seasons = {}
        self.episodes = {}

        # Check if category_id key is available
        if "series_id" in series_info.keys():
            self.series_id = int(series_info["series_id"])

        # Check if plot key is available
        if "plot" in series_info.keys():
            self.plot = series_info["plot"]

        # Check if youtube_trailer key is available
        if "youtube_trailer" in series_info.keys():
            self.youtube_trailer = series_info["youtube_trailer"]

        # Check if genre key is available
        if "genre" in series_info.keys():
            self.genre = series_info["genre"]


class Season:
    # Required by Hypnotix
    name = ""

    def __init__(self, name):
        self.name = name
        self.episodes = {}

class MyStatus(Protocol):
    def __call__(self, string: str, guiOnly: bool) -> None: ...

class XTream:
    live_type = "Live"
    vod_type = "VOD"
    series_type = "Series"

    hide_adult_content = False

    live_catch_all_group = Group(
        {"category_id": "9999", "category_name":"xEverythingElse", "parent_id":0}, live_type
    )
    vod_catch_all_group = Group(
        {"category_id": "9999", "category_name":"xEverythingElse", "parent_id":0}, vod_type
    )
    series_catch_all_group = Group(
        {"category_id": "9999", "category_name":"xEverythingElse", "parent_id":0}, series_type
    )
    # If the cached JSON file is older than threshold_time_sec then load a new
    # JSON dictionary from the provider
    threshold_time_sec = 60 * 60 * 8

    def __init__(
        self,
        update_status: MyStatus,
        provider_name: str,
        provider_username: str,
        provider_password: str,
        provider_url: str,
        headers: dict = None,
        hide_adult_content: bool = False,
        cache_path: str = ""
    ):
        """Initialize Xtream Class

        Args:
            provider_name     (str):            Name of the IPTV provider
            provider_username (str):            User name of the IPTV provider
            provider_password (str):            Password of the IPTV provider
            provider_url      (str):            URL of the IPTV provider
            headers           (dict):           Requests Headers
            hide_adult_content(bool, optional): When `True` hide stream that are marked for adult
            cache_path        (str, optional):  Location where to save loaded files. Defaults to empty string

        Returns: XTream Class Instance

        - Note: If it fails to authorize with provided username and password,
                auth_data will be an empty dictionary.

        """

        self.state = {"authenticated": False, "loaded": False}
        self.auth_data = {}
        self.authorization = {}
        self.groups = []
        self.channels = []
        self.series = []
        self.movies = []

        self.base_url = ""
        self.base_url_ssl = ""
        self.server = provider_url
        self.username = provider_username
        self.password = provider_password
        self.name = provider_name
        self.cache_path = cache_path
        self.hide_adult_content = hide_adult_content
        self.update_status = update_status

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

        if headers is not None:
            self.connection_headers = headers
        else:
            self.connection_headers = {'User-Agent':"Wget/1.20.3 (linux-gnu)"}

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
            regex = re.compile(keyword, re.IGNORECASE)
        else:
            regex = re.compile(keyword)

        print(f"Checking {len(self.movies)} movies")
        for stream in self.movies:
            if re.match(regex, stream.name) is not None:
                search_result.append(stream.export_json())

        print(f"Checking {len(self.channels)} channels")
        for stream in self.channels:
            if re.match(regex, stream.name) is not None:
                search_result.append(stream.export_json())

        print(f"Checking {len(self.series)} series")
        for stream in self.series:
            if re.match(regex, stream.name) is not None:
                search_result.append(stream.export_json())

        if return_type == "JSON":
            if search_result is not None:
                print(f"Found {len(search_result)} results `{keyword}`")
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
            r"^(?:http|ftp)s?://"  # http:// or https://
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
            r"localhost|"  # localhost...
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
            r"(?::\d+)?"  # optional port
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )

        return re.match(regex, url) is not None

    def _get_logo_local_path(self, logo_url: str) -> str:
        """Convert the Logo URL to a local Logo Path

        Args:
            logoURL (str): The Logo URL

        Returns:
            [type]: The logo path as a string or None
        """
        local_logo_path = None
        if logo_url is not None:
            if not self._validate_url(logo_url):
                logo_url = None
            else:
                local_logo_path = osp.join(
                    self.cache_path,
                    f"{self._slugify(self.name)}-{self._slugify(osp.split(logo_url)[-1])}"
                )
        return local_logo_path

    def authenticate(self):
        """Login to provider"""
        # If we have not yet successfully authenticated, attempt authentication
        if self.state["authenticated"] is False:
            # Erase any previous data
            self.auth_data = {}
            # Loop through 30 seconds
            i = 0
            r = None
            # Prepare the authentication url
            url = f"{self.server}/player_api.php?username={self.username}&password={self.password}"
            while i < 30:
                try:
                    # Request authentication, wait 4 seconds maximum
                    r = requests.get(url, timeout=(4), headers=self.connection_headers)
                    i = 31
                except requests.exceptions.ConnectionError:
                    time.sleep(1)
                    print(i)
                    i += 1

            if r is not None:
                # If the answer is ok, process data and change state
                if r.ok:
                    self.auth_data = r.json()
                    self.authorization = {
                        "username": self.auth_data["user_info"]["username"],
                        "password": self.auth_data["user_info"]["password"]
                    }
                    # Mark connection authorized
                    self.state["authenticated"] = True
                    # Construct the base url for all requests
                    self.base_url = f"{self.server}/player_api.php?username={self.username}&password={self.password}"
                    # If there is a secure server connection, construct the base url SSL for all requests
                    if "https_port" in self.auth_data["server_info"]:
                        self.base_url_ssl = f"https://{self.auth_data['server_info']['url']}:{self.auth_data['server_info']['https_port']}" \
                                            f"/player_api.php?username={self.username}&password={self.password}"
                else:
                    self.update_status(f"{self.name}: Provider could not be loaded. Reason: `{r.status_code} {r.reason}`")
            else:
                self.update_status(f"{self.name}: Provider refused the connection")

    def _load_from_file(self, filename) -> dict:
        """Try to load the dictionary from file

        Args:
            filename ([type]): File name containing the data

        Returns:
            dict: Dictionary if found and no errors, None if file does not exists
        """
        # Build the full path
        full_filename = osp.join(self.cache_path, f"{self._slugify(self.name)}-{filename}")

        # If the cached file exists, attempt to load it
        if osp.isfile(full_filename):

            my_data = None

            # Get the enlapsed seconds since last file update
            file_age_sec = time.time() - osp.getmtime(full_filename)
            # If the file was updated less than the threshold time,
            # it means that the file is still fresh, we can load it.
            # Otherwise skip and return None to force a re-download
            if self.threshold_time_sec > file_age_sec:
                # Load the JSON data
                try:
                    with open(full_filename, mode="r", encoding="utf-8") as myfile:
                        my_data = json.load(myfile)
                        if len(my_data) == 0:
                            my_data = None
                except Exception as e:
                    print(f" - Could not load from file `{full_filename}`: e=`{e}`")
            return my_data

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
        if data_list is not None:

            #Build the full path
            full_filename = osp.join(self.cache_path, f"{self._slugify(self.name)}-{filename}")
            # If the path makes sense, save the file
            json_data = json.dumps(data_list, ensure_ascii=False)
            try:
                with open(full_filename, mode="wt", encoding="utf-8") as myfile:
                    myfile.write(json_data)
            except Exception as e:
                print(f" - Could not save to file `{full_filename}`: e=`{e}`")
                return False

            return True
        else:
            return False

    def load_iptv(self) -> bool:
        """Load XTream IPTV

        - Add all Live TV to XTream.channels
        - Add all VOD to XTream.movies
        - Add all Series to XTream.series
          Series contains Seasons and Episodes. Those are not automatically
          retrieved from the server to reduce the loading time.
        - Add all groups to XTream.groups
          Groups are for all three channel types, Live TV, VOD, and Series

        Returns:
            bool: True if successfull, False if error
        """
        # If pyxtream has not authenticated the connection, return empty
        if self.state["authenticated"] is False:
            print("Warning, cannot load steams since authorization failed")
            return False

        # If pyxtream has already loaded the data, skip and return success
        if self.state["loaded"] is True:
            print("Warning, data has already been loaded.")
            return True

        for loading_stream_type in (self.live_type, self.vod_type, self.series_type):
            ## Get GROUPS

            # Try loading local file
            dt = 0
            start = timer()
            all_cat = self._load_from_file(f"all_groups_{loading_stream_type}.json")
            # If file empty or does not exists, download it from remote
            if all_cat is None:
                # Load all Groups and save file locally
                all_cat = self._load_categories_from_provider(loading_stream_type)
                if all_cat is not None:
                    self._save_to_file(all_cat,f"all_groups_{loading_stream_type}.json")
            dt = timer() - start

            # If we got the GROUPS data, show the statistics and load GROUPS
            if all_cat is not None:
                self.update_status(
                    f"{self.name}: Loaded {len(all_cat)} {loading_stream_type} Groups in {dt:.3f} seconds"
                )

                ## Add GROUPS to dictionaries

                # Add the catch-all-errors group
                if loading_stream_type == self.live_type:
                    self.groups.append(self.live_catch_all_group)
                elif loading_stream_type == self.vod_type:
                    self.groups.append(self.vod_catch_all_group)
                elif loading_stream_type == self.series_type:
                    self.groups.append(self.series_catch_all_group)

                for cat_obj in all_cat:
                    # Create Group (Category)
                    new_group = Group(cat_obj, loading_stream_type)
                    #  Add to xtream class
                    self.groups.append(new_group)

                # Add the catch-all-errors group
                self.groups.append(Group({"category_id": "9999", "category_name": "xEverythingElse", "parent_id": 0}, loading_stream_type))

                # Sort Categories
                self.groups.sort(key=lambda x: x.name)
            else:
                print(f" - Could not load {loading_stream_type} Groups")
                break

            ## Get Streams

            # Try loading local file
            dt = 0
            start = timer()
            all_streams = self._load_from_file(f"all_stream_{loading_stream_type}.json")
            # If file empty or does not exists, download it from remote
            if all_streams is None:
                # Load all Streams and save file locally
                all_streams = self._load_streams_from_provider(loading_stream_type)
                self._save_to_file(all_streams,f"all_stream_{loading_stream_type}.json")
            dt = timer() - start

            # If we got the STREAMS data, show the statistics and load Streams
            if all_streams is not None:
                print(
                    f"{self.name}: Loaded {len(all_streams)} {loading_stream_type} Streams " \
                    f"in {dt:.3f} seconds"
                    )
                ## Add Streams to dictionaries

                skipped_adult_content = 0
                skipped_no_name_content = 0

                number_of_streams = len(all_streams)
                current_stream_number = 0
                # Calculate 1% of total number of streams
                # This is used to slow down the progress bar
                one_percent_number_of_streams = number_of_streams/100

                # Inform the user
                self.update_status(
                    f"{self.name}: Processing {number_of_streams} {loading_stream_type} Streams", 
                    None,
                    True
                    )
                start = timer()
                for stream_channel in all_streams:
                    skip_stream = False
                    current_stream_number += 1

                    # Show download progress every 1% of total number of streams
                    if current_stream_number < one_percent_number_of_streams:
                        progress(
                            current_stream_number,
                            number_of_streams,
                            f"Processing {loading_stream_type} Streams"
                            )
                        one_percent_number_of_streams *= 2

                    # Skip if the name of the stream is empty
                    if stream_channel["name"] == "":
                        skip_stream = True
                        skipped_no_name_content = skipped_no_name_content + 1
                        self._save_to_file_skipped_streams(stream_channel)

                    # Skip if the user chose to hide adult streams
                    if self.hide_adult_content and loading_stream_type == self.live_type:
                        if "is_adult" in stream_channel:
                            if stream_channel["is_adult"] == "1":
                                skip_stream = True
                                skipped_adult_content = skipped_adult_content + 1
                                self._save_to_file_skipped_streams(stream_channel)

                    if not skip_stream:
                        # Some channels have no group,
                        # so let's add them to the catch all group
                        if stream_channel["category_id"] is None:
                            stream_channel["category_id"] = "9999"
                        elif stream_channel["category_id"] != "1":
                            pass

                        # Find the first occurence of the group that the
                        # Channel or Stream is pointing to
                        the_group = next(
                            (x for x in self.groups if x.group_id == int(stream_channel["category_id"])),
                            None
                        )

                        # Set group title
                        if the_group is not None:
                            group_title = the_group.name
                        else:
                            if loading_stream_type == self.live_type:
                                group_title = self.live_catch_all_group.name
                                the_group = self.live_catch_all_group
                            elif loading_stream_type == self.vod_type:
                                group_title = self.vod_catch_all_group.name
                                the_group = self.vod_catch_all_group
                            elif loading_stream_type == self.series_type:
                                group_title = self.series_catch_all_group.name
                                the_group = self.series_catch_all_group


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
                                self, group_title, stream_channel
                            )

                        if new_channel.group_id == "9999":
                            print(f" - xEverythingElse Channel -> {new_channel.name} - {new_channel.stream_type}")

                        # Save the new channel to the local list of channels
                        if loading_stream_type == self.live_type:
                            self.channels.append(new_channel)
                        elif loading_stream_type == self.vod_type:
                            self.movies.append(new_channel)
                        else:
                            self.series.append(new_series)

                        # Add stream to the specific Group
                        if the_group is not None:
                            if loading_stream_type != self.series_type:
                                the_group.channels.append(new_channel)
                            else:
                                the_group.series.append(new_series)
                        else:
                            print(f" - Group not found `{stream_channel['name']}`")
                print("\n")
                dt = timer() - start
                # Print information of which streams have been skipped
                if self.hide_adult_content:
                    print(f" - Skipped {skipped_adult_content} adult {loading_stream_type} streams")
                if skipped_no_name_content > 0:
                    print(f" - Skipped {skipped_no_name_content} unprintable {loading_stream_type} streams")
            else:
                print(f" - Could not load {loading_stream_type} Streams")

            self.state["loaded"] = True

    def _save_to_file_skipped_streams(self, stream_channel: Channel):

        # Build the full path
        full_filename = osp.join(self.cache_path, "skipped_streams.json")

        # If the path makes sense, save the file
        json_data = json.dumps(stream_channel, ensure_ascii=False)
        try:
            with open(full_filename, mode="a", encoding="utf-8") as myfile:
                myfile.writelines(json_data)
            return True
        except Exception as e:
            print(f" - Could not save to skipped stream file `{full_filename}`: e=`{e}`")
        return False

    def get_series_info_by_id(self, get_series: dict):
        """Get Seasons and Episodes for a Series

        Args:
            get_series (dict): Series dictionary
        """

        series_seasons = self._load_series_info_by_id_from_provider(get_series.series_id)

        if series_seasons["seasons"] is None:
            series_seasons["seasons"] = [{"name": "Season 1", "cover": series_seasons["info"]["cover"]}]

        for series_info in series_seasons["seasons"]:
            season_name = series_info["name"]
            season = Season(season_name)
            get_series.seasons[season_name] = season
            if "episodes" in series_seasons.keys():
                for series_season in series_seasons["episodes"].keys():
                    for episode_info in series_seasons["episodes"][str(series_season)]:
                        new_episode_channel = Episode(
                            self, series_info, "Testing", episode_info
                        )
                        season.episodes[episode_info["title"]] = new_episode_channel

    def _get_request(self, url: str, timeout: Tuple = (2, 15)):
        """Generic GET Request with Error handling

        Args:
            URL (str): The URL where to GET content
            timeout (Tuple, optional): Connection and Downloading Timeout. Defaults to (2,15).

        Returns:
            [type]: JSON dictionary of the loaded data, or None
        """
        i = 0
        while i < 10:
            time.sleep(1)
            try:
                r = requests.get(url, timeout=timeout, headers=self.connection_headers)
                i = 20
                if r.status_code == 200:
                    return r.json()
            except requests.exceptions.ConnectionError:
                print(" - Connection Error: Possible network problem (e.g. DNS failure, refused connection, etc)")
                i += 1

            except requests.exceptions.HTTPError:
                print(" - HTTP Error")
                i += 1

            except requests.exceptions.TooManyRedirects:
                print(" - TooManyRedirects")
                i += 1

            except requests.exceptions.ReadTimeout:
                print(" - Timeout while loading data")
                i += 1

        return None

    # GET Stream Categories
    def _load_categories_from_provider(self, stream_type: str):
        """Get from provider all category for specific stream type from provider

        Args:
            stream_type (str): Stream type can be Live, VOD, Series

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        url = ""
        if stream_type == self.live_type:
            url = self.get_live_categories_URL()
        elif stream_type == self.vod_type:
            url = self.get_vod_cat_URL()
        elif stream_type == self.series_type:
            url = self.get_series_cat_URL()
        else:
            url = ""

        return self._get_request(url)

    # GET Streams
    def _load_streams_from_provider(self, stream_type: str):
        """Get from provider all streams for specific stream type

        Args:
            stream_type (str): Stream type can be Live, VOD, Series

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        url = ""
        if stream_type == self.live_type:
            url = self.get_live_streams_URL()
        elif stream_type == self.vod_type:
            url = self.get_vod_streams_URL()
        elif stream_type == self.series_type:
            url = self.get_series_URL()
        else:
            url = ""

        return self._get_request(url)

    # GET Streams by Category
    def _load_streams_by_category_from_provider(self, stream_type: str, category_id):
        """Get from provider all streams for specific stream type with category/group ID

        Args:
            stream_type (str): Stream type can be Live, VOD, Series
            category_id ([type]): Category/Group ID.

        Returns:
            [type]: JSON if successfull, otherwise None
        """
        url = ""

        if stream_type == self.live_type:
            url = self.get_live_streams_URL_by_category(category_id)
        elif stream_type == self.vod_type:
            url = self.get_vod_streams_URL_by_category(category_id)
        elif stream_type == self.series_type:
            url = self.get_series_URL_by_category(category_id)
        else:
            url = ""

        return self._get_request(url)

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
    def get_live_categories_URL(self) -> str:
        return f"{self.base_url}&action=get_live_categories"

    def get_live_streams_URL(self) -> str:
        return f"{self.base_url}&action=get_live_streams"

    def get_live_streams_URL_by_category(self, category_id) -> str:
        return f"{self.base_url}&action=get_live_streams&category_id={category_id}"

    def get_vod_cat_URL(self) -> str:
        return f"{self.base_url}&action=get_vod_categories"

    def get_vod_streams_URL(self) -> str:
        return f"{self.base_url}&action=get_vod_streams"

    def get_vod_streams_URL_by_category(self, category_id) -> str:
        return f"{self.base_url}&action=get_vod_streams&category_id={category_id}"

    def get_series_cat_URL(self) -> str:
        return f"{self.base_url}&action=get_series_categories"

    def get_series_URL(self) -> str:
        return f"{self.base_url}&action=get_series"

    def get_series_URL_by_category(self, category_id) -> str:
        return f"{self.base_url}&action=get_series&category_id={category_id}"

    def get_series_info_URL_by_ID(self, series_id) -> str:
        return f"{self.base_url}&action=get_series_info&series_id={series_id}"

    def get_VOD_info_URL_by_ID(self, vod_id) -> str:
        return f"{self.base_url}&action=get_vod_info&vod_id={vod_id}"

    def get_live_epg_URL_by_stream(self, stream_id) -> str:
        return f"{self.base_url}&action=get_short_epg&stream_id={stream_id}"

    def get_live_epg_URL_by_stream_and_limit(self, stream_id, limit) -> str:
        return f"{self.base_url}&action=get_short_epg&stream_id={stream_id}&limit={limit}"

    def get_all_live_epg_URL_by_stream(self, stream_id) -> str:
        return f"{self.base_url}&action=get_simple_data_table&stream_id={stream_id}"

    def get_all_epg_URL(self) -> str:
        return f"{self.server}/xmltv.php?username={self.username}&password={self.password}"

# The MIT License (MIT)
# Copyright (c) 2016 Vladimir Ignatev
#
# Permission is hereby granted, free of charge, to any person obtaining 
# a copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the Software 
# is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included 
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, 
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR 
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
# FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT
# OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

def progress(count, total, status=''):
    bar_len = 60
    filled_len = int(round(bar_len * count / float(total)))

    percents = round(100.0 * count / float(total), 1)
    bar_value = '=' * filled_len + '-' * (bar_len - filled_len)

    #stdout.write('[%s] %s%s ...%s\r' % (bar_value, percents, '%', status))
    stdout.write(f"[{bar_value}] {percents:.0f}% ...{status}\r")
    stdout.flush()  # As suggested by Rom Ruben (see: http://stackoverflow.com/questions/3173320/text-progress-bar-in-the-console/27871113#comment50529068_27871113)
