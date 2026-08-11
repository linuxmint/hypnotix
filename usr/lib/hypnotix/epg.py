import datetime
import gzip
import json
import os
import sqlite3
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import formatdate

from common import EPG_PATH, async_function, slugify


def parse_xmltv_time(s: str) -> int:
    """Converts XMLTV timestamp ('20260807143000 +0200') to a Unix epoch integer."""
    if not s:
        return 0
    parts = s.strip().split()
    dt_str = parts[0][:14]
    try:
        dt = datetime.datetime.strptime(dt_str, "%Y%m%d%H%M%S")
        if len(parts) > 1:
            tz_str = parts[1]
            sign = 1 if tz_str[0] == "+" else -1
            hours = int(tz_str[1:3])
            mins = int(tz_str[3:5])
            offset = datetime.timedelta(hours=hours, minutes=mins)
            if sign == 1:
                dt -= offset
            else:
                dt += offset
        return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())
    except Exception:
        return 0


import re

class IPTVSimpleMatcher:
    """
    Implements Kodi pvr.iptvsimple's channel-to-XMLTV matching algorithm,
    with an added fallback pass to strip technical quality descriptors.
    """

    # Regex for common technical noise, quality tags, and codecs
    TECH_TAGS_REGEX = re.compile(
        r'\b(hd|sd|fhd|uhd|qhd|4k|8k|1080p|1080i|720p|576i|hevc|h264|h265|hdr|60fps|fps60)\b',
        re.IGNORECASE
    )

    def __init__(self, xmltv_channels):
        self.xml_by_id = {}
        self.xml_by_display_name = {}
        self.name_by_id = {}

        for ch in xmltv_channels:
            cid = ch.get("id")
            if not cid or not cid.strip():
                continue

            cid_clean = cid.strip()
            cid_lower = cid_clean.lower()

            if cid_lower not in self.xml_by_id:
                self.xml_by_id[cid_lower] = cid_clean

            names = ch.get("display_names", [])
            if names and names[0]:
                self.name_by_id[cid_clean] = names[0]

            for name in names:
                if name and name.strip():
                    name_lower = name.strip().lower()
                    if name_lower not in self.xml_by_display_name:
                        self.xml_by_display_name[name_lower] = cid_clean

                    # Index stripped version of XMLTV display names
                    clean_name = self._strip_tech_info(name_lower)
                    if clean_name and clean_name not in self.xml_by_display_name:
                        self.xml_by_display_name[clean_name] = cid_clean

    @classmethod
    def _strip_tech_info(cls, text: str) -> str:
        """Removes technical tags (HD, FHD, 1080p, etc.) and clean residual punctuation."""
        if not text:
            return ""
        # remove anything inside parentheses/brackets (e.g. "(AC3 eng)")
        clean = re.sub(r'\s*[(\[].*?[)\]]', '', text)
        # Strip tech terms
        clean = cls.TECH_TAGS_REGEX.sub('', clean)
        # Clean up empty brackets, pipes, or leftover punctuation
        clean = re.sub(r'[()\[\]{}|]', ' ', clean)
        # Normalize whitespace
        return ' '.join(clean.split())

    def _match_candidate(self, candidate: str) -> str:
        if not candidate:
            return None

        clean = candidate.strip().lower()
        if not clean:
            return None

        # 1. Exact match against XMLTV channel ID
        if clean in self.xml_by_id:
            return self.xml_by_id[clean]

        # 2. Exact match against XMLTV display-name
        if clean in self.xml_by_display_name:
            return self.xml_by_display_name[clean]

        # 3. Match spaces converted to underscores ("bbc one" -> "bbc_one")
        space_to_underscore = clean.replace(" ", "_")
        if space_to_underscore in self.xml_by_display_name:
            return self.xml_by_display_name[space_to_underscore]

        # 4. Match underscores converted to spaces ("bbc_one" -> "bbc one")
        underscore_to_space = clean.replace("_", " ")
        if underscore_to_space in self.xml_by_display_name:
            return self.xml_by_display_name[underscore_to_space]

        # 5. Technical-stripped fallback pass ("BBC One HD [1080p]" -> "bbc one")
        stripped = self._strip_tech_info(clean)
        if stripped and stripped != clean:
            if stripped in self.xml_by_display_name:
                return self.xml_by_display_name[stripped]

            stripped_underscore = stripped.replace(" ", "_")
            if stripped_underscore in self.xml_by_display_name:
                return self.xml_by_display_name[stripped_underscore]

        return None

    def match_channel(self, tvg_id: str, tvg_name: str, m3u_title: str) -> str:
        # Pass 1: tvg-id
        match = self._match_candidate(tvg_id)
        if match:
            return match

        # Pass 2: tvg-name
        match = self._match_candidate(tvg_name)
        if match:
            return match

        # Pass 3: M3U channel stream title
        return self._match_candidate(m3u_title)

class XMLTVParser:
    """Stream-parses XMLTV data without loading the entire DOM into RAM."""

    @staticmethod
    def _open_source(file_path: str):
        # Download URLs and cache filenames may not reflect the actual format.
        with open(file_path, "rb") as source:
            is_gzip = source.read(2) == b"\x1f\x8b"
        if is_gzip:
            return gzip.open(file_path, "rb")
        return open(file_path, "rb")

    @classmethod
    def parse_channels(cls, file_path: str):
        """Pass 1: Parses only <channel> elements to enable early matching."""
        channels = []
        try:
            with cls._open_source(file_path) as f:
                for event, elem in ET.iterparse(f, events=("end",)):
                    if elem.tag == "channel":
                        cid = elem.attrib.get("id")
                        if cid and cid.strip():
                            cid = cid.strip()
                            names = [e.text for e in elem.findall("display-name") if e.text]
                            channels.append({"id": cid, "display_names": names})
                        elem.clear()
                    elif elem.tag == "programme":
                        elem.clear()
        except Exception as e:
            print(f"[EPG] Parse channels error ({file_path}): {e}")

        return channels

    @classmethod
    def parse_programmes(cls, file_path: str, valid_xmltv_ids: set = None):
        """Pass 2: Parses <programme> elements, pruning past shows and unmatched channels."""
        programmes = {}
        now = int(time.time())

        try:
            with cls._open_source(file_path) as f:
                for event, elem in ET.iterparse(f, events=("end",)):
                    if elem.tag == "programme":
                        cid = elem.attrib.get("channel")
                        if not cid:
                            elem.clear()
                            continue

                        cid = cid.strip()
                        # Optimization: Ignore <programme> entries not matched to provider.channels
                        if valid_xmltv_ids is not None and cid not in valid_xmltv_ids:
                            elem.clear()
                            continue

                        stop = parse_xmltv_time(elem.attrib.get("stop"))
                        start = parse_xmltv_time(elem.attrib.get("start"))

                        title_elem = elem.find("title")
                        title = title_elem.text if title_elem is not None else ""

                        desc_elem = elem.find("desc")
                        desc = desc_elem.text if desc_elem is not None else ""

                        if start and title:
                            if cid not in programmes:
                                programmes[cid] = []
                            programmes[cid].append({
                                "start": start,
                                "stop": stop,
                                "title": title,
                                "desc": desc
                            })
                        elem.clear()
                    elif elem.tag == "channel":
                        elem.clear()
        except Exception as e:
            print(f"[EPG] Parse programmes error ({file_path}): {e}")

        return programmes

class EPGManager:
    """Handles fetching, caching, matching, and querying EPG data."""

    def __init__(self, user_agent="Hypnotix"):
        self.user_agent = user_agent
        self.programmes = {}  # { xmltv_id: [program_dicts] }

    def resolve_epg_path(self, provider) -> str:
        """Resolves provider.epg into a local file path."""
        epg_src = provider.epg.strip() if provider.epg else ""
        if not epg_src:
            return None

        # Local file URI or raw filesystem path
        if epg_src.startswith("file://") or epg_src.startswith("/"):
            path = epg_src[7:] if epg_src.startswith("file://") else epg_src
            return os.path.expanduser(path)

        # Remote URL: cache locally in ~/.cache/hypnotix/epg/
        ext = ".xml.gz" if epg_src.endswith(".gz") else ".xml"
        return os.path.join(EPG_PATH, f"{slugify(provider.name)}{ext}")

    def get_db_path(self, local_path: str) -> str:
        """Returns the SQLite database cache path corresponding to the XML file."""
        return local_path + ".db"

    def is_cache_valid(self, local_path: str, ttl_hours: int = 24) -> bool:
        """Checks if the local cache file exists and is newer than TTL."""
        if not local_path or not os.path.exists(local_path):
            return False
        mtime = os.path.getmtime(local_path)
        return (time.time() - mtime) < (ttl_hours * 3600)

    def is_db_valid(self, db_path: str, xml_path: str) -> bool:
        """Checks if the SQLite database exists and is newer than the XMLTV file."""
        if not db_path or not os.path.exists(db_path):
            return False
        if isinstance(xml_path, list):
            for xp in xml_path:
                if not os.path.exists(xp) or os.path.getmtime(db_path) < os.path.getmtime(xp):
                    return False
            return True
        else:
            return os.path.exists(xml_path) and os.path.getmtime(db_path) >= os.path.getmtime(xml_path)

    def download_epg(self, epg_url: str, local_path: str) -> bool:
        """Downloads a remote EPG XML file to the local cache path."""
        try:
            req = urllib.request.Request(epg_url, headers={"User-Agent": self.user_agent})
            if os.path.exists(local_path):
                mtime = os.path.getmtime(local_path)
                req.add_header("If-Modified-Since", formatdate(mtime, usegmt=True))
            with urllib.request.urlopen(req, timeout=30) as resp, open(local_path, "wb") as out:
                out.write(resp.read())
            return True
        except urllib.error.HTTPError as e:
            if e.code == 304:
                print(f"[EPG] Not modified (304), using cached EPG for {epg_url}")
                return True
            print(f"[EPG] Download failed for {epg_url}: {e}")
            return False
        except Exception as e:
            print(f"[EPG] Download failed for {epg_url}: {e}")
            return False

    def save_to_db(self, db_path: str, channels: list, programmes: dict):
        """Caches parsed XMLTV channels and programmes into SQLite."""
        try:
            print(f"[EPG] Saving EPG cache to SQLite database: {db_path}")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS channels")
            cursor.execute("DROP TABLE IF EXISTS programmes")
            cursor.execute("""
                CREATE TABLE channels (
                    id TEXT PRIMARY KEY,
                    display_names TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE programmes (
                    channel_id TEXT,
                    start INTEGER,
                    stop INTEGER,
                    title TEXT,
                    desc TEXT,
                    UNIQUE(channel_id, start)
                )
            """)

            ch_rows = [(ch["id"], json.dumps(ch["display_names"])) for ch in channels]
            cursor.executemany("INSERT OR REPLACE INTO channels VALUES (?, ?)", ch_rows)

            prog_rows = []
            for cid, progs in programmes.items():
                for p in progs:
                    prog_rows.append((cid, p["start"], p["stop"], p["title"], p["desc"]))
            cursor.executemany("INSERT OR IGNORE INTO programmes VALUES (?, ?, ?, ?, ?)", prog_rows)

            cursor.execute("CREATE INDEX idx_programmes_channel ON programmes(channel_id)")
            cursor.execute("CREATE INDEX idx_programmes_stop ON programmes(stop)")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[EPG] Failed to save SQLite cache ({db_path}): {e}")

    def load_channels_from_db(self, db_path: str) -> list:
        """Loads channel definitions from SQLite database."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, display_names FROM channels")
        channels = []
        for cid, names_json in cursor.fetchall():
            try:
                names = json.loads(names_json)
            except Exception:
                names = []
            channels.append({"id": cid, "display_names": names})
        conn.close()
        return channels

    def load_programmes_from_db(self, db_path: str, valid_xmltv_ids: set = None) -> dict:
        """Loads all EPG programmes from SQLite database (including historical)."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, start, stop, title, desc FROM programmes")

        programmes = {}
        for cid, start, stop, title, desc in cursor.fetchall():
            if valid_xmltv_ids is not None and cid not in valid_xmltv_ids:
                continue
            if cid not in programmes:
                programmes[cid] = []
            programmes[cid].append({
                "start": start,
                "stop": stop,
                "title": title,
                "desc": desc
            })
        conn.close()
        return programmes

    def dump_matches_xml(self, provider):
        """Dumps channel matching results to an XML file in the EPG cache folder."""
        root = ET.Element("epg_matches", provider=provider.name)

        for ch in provider.channels:
            elem = ET.SubElement(root, "channel")
            elem.attrib["name"] = ch.name or ""
            elem.attrib["tvg_id"] = ch.tvg_id or ""
            elem.attrib["tvg_name"] = ch.tvg_name or ""
            elem.attrib["title"] = ch.title or ""
            elem.attrib["xmltv_id"] = ch.xmltv_id or ""
            elem.attrib["matched"] = "true" if ch.xmltv_id else "false"

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")

        dump_file = os.path.join(EPG_PATH, f"{slugify(provider.name)}_matches.xml")
        tree.write(dump_file, encoding="utf-8", xml_declaration=True)
        print(f"[EPG] Debug match XML dumped to: {dump_file}")

    def load_epg_for_provider(self, provider, refresh: bool = False):
        """Fetches, loads, and matches EPG channels to provider.channels."""
        if not provider.epg:
            return

        epg_urls = [u.strip() for u in provider.epg.replace(',', ' ').split() if u.strip()]
        if not epg_urls:
            return

        db_path = os.path.join(EPG_PATH, f"{slugify(provider.name)}.db")
        xml_paths = []

        for i, epg_url in enumerate(epg_urls):
            local_path = os.path.join(EPG_PATH, f"{slugify(provider.name)}_{i}.xml.gz" if epg_url.endswith(".gz") else f"{slugify(provider.name)}_{i}.xml")
            xml_paths.append(local_path)

            if epg_url.startswith("http://") or epg_url.startswith("https://"):
                if refresh or not self.is_cache_valid(local_path):
                    print(f"[EPG] Downloading EPG {i+1}/{len(epg_urls)} for provider '{provider.name}'...")
                    self.download_epg(epg_url, local_path)
            elif epg_url.startswith("file://") or epg_url.startswith("/"):
                path = epg_url[7:] if epg_url.startswith("file://") else epg_url
                xml_paths[-1] = os.path.expanduser(path)

        use_db = (not refresh) and self.is_db_valid(db_path, xml_paths)

        # Step 1: Get channels (from SQLite if valid, otherwise XML)
        if use_db:
            print(f"[EPG] Loading EPG channels from SQLite cache: {db_path}")
            xml_channels = self.load_channels_from_db(db_path)
        else:
            xml_channels = []
            for xp in xml_paths:
                if os.path.exists(xp):
                    print(f"[EPG] Parsing EPG channels from XML: {xp}")
                    xml_channels.extend(XMLTVParser.parse_channels(xp))

        # Step 2: Match M3U channels with XMLTV channels
        matcher = IPTVSimpleMatcher(xml_channels)
        matched_count = 0
        for channel in provider.channels:
            channel.xmltv_id = matcher.match_channel(channel.tvg_id, channel.tvg_name, channel.title)
            if channel.xmltv_id:
                matched_count += 1
                epg_name = matcher.name_by_id.get(channel.xmltv_id)
                if epg_name:
                    channel.tvg_name = epg_name
                    channel.name = epg_name

        print(f"[EPG] Matched {matched_count}/{len(provider.channels)} channels for provider '{provider.name}'")

        # Step 3: Build the filter set of active XMLTV IDs
        valid_xmltv_ids = {ch.xmltv_id for ch in provider.channels if ch.xmltv_id}

        # Step 4: Load programmes from SQLite or parse from XML and build SQLite cache
        if use_db:
            print(f"[EPG] Loading EPG programmes from SQLite cache for {len(valid_xmltv_ids)} matched channels...")
            self.programmes = self.load_programmes_from_db(db_path, valid_xmltv_ids=valid_xmltv_ids)
        else:
            print(f"[EPG] Parsing full EPG programmes from XML(s) to build database cache...")
            all_programmes = {}
            for xp in xml_paths:
                if os.path.exists(xp):
                    progs = XMLTVParser.parse_programmes(xp, valid_xmltv_ids=None)
                    for cid, p_list in progs.items():
                        if cid not in all_programmes:
                            all_programmes[cid] = []
                        all_programmes[cid].extend(p_list)
            self.save_to_db(db_path, xml_channels, all_programmes)
            self.programmes = {cid: progs for cid, progs in all_programmes.items() if cid in valid_xmltv_ids}

        # Dump debug report
        self.dump_matches_xml(provider)

    def get_current_and_next(self, xmltv_id: str):
        """Returns (now_playing, next_up) dicts for a channel at the current time."""
        if not xmltv_id or xmltv_id not in self.programmes:
            return None, None

        now = int(time.time())
        now_playing = None
        next_up = None

        for prog in self.programmes[xmltv_id]:
            if prog["start"] <= now < prog["stop"]:
                now_playing = prog
            elif prog["start"] >= now:
                if next_up is None or prog["start"] < next_up["start"]:
                    next_up = prog

        return now_playing, next_up
