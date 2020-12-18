# Hypnotix

Hypnotix is an IPTV streaming application with support for live TV, movies and series.

<img src="https://user-images.githubusercontent.com/1138515/99553152-b8bac780-29b5-11eb-9d75-8756ed7581b6.png" width="500" />

It can support multiple IPTV providers of the following types:

- M3U URL
- Xtream API
- Local M3U playlist

# License

- Code: GPLv3
- Flags: https://github.com/linuxmint/flags
- Icons on the landing page: CC BY-ND 2.0

# Requirements

- libxapp 1.4+
- libmpv
- python3-imdbpy (for Older Mint and Debian releases get it from https://packages.ubuntu.com/focal/all/python3-imdbpy/download)

# TV Channels and media content

Hypnotix does not provide content or TV channels, it is a player application which streams from IPTV providers.

By default, Hypnotix is configured with one IPTV provider called Free-IPTV: https://github.com/Free-IPTV/Countries.

This provider was chosen because it satisfied the following criterias:

- It only includes free, legal, publicly available content
- It groups TV channels by countries
- It doesn't include adult content

Issues relating to TV channels and media content should be addressed directly to the relevant provider.

Note: Feel free to remove Free-IPTV from Hypnotix if you don't use it, or add any other provider you may have access to or local M3U playlists.

## HowTo make Playlists for Series

Use ExxSxx in your Playlist to get it shown as series.

- S01E12 = Season 1 Episode 12

for example:

```
#EXTM3U
#EXTINF:-1 tvg-name="Frasier S04E06" group-title="SERIES Frasier",
file:///home/brian/Videos/Frasier_4/Frasier.S04E06.mp4
#EXTINF:-1 tvg-name="Frasier S04E07" group-title="SERIES Frasier",
file:///home/brian/Videos/Frasier_4/Frasier.S04E07.mp4
#EXTINF:-1 tvg-name="Frasier S04E09" group-title="SERIES Frasier",
file:///home/brian/Videos/Frasier_4/Frasier.S04E09.mp4
#EXTINF:-1 tvg-name="Frasier S04E10" group-title="SERIES Frasier",
file:///home/brian/Videos/Frasier_4/Frasier.S04E10.mp4
```
## Build deb for Mint

If you're in Mint, you can use mint-build

```
apt install mint-dev-tools
```
to create deb file
```
mint-build -g https://github.com/Axel-Erfurt/hypnotix.git
```

to create and install deb file
```
mint-build -i -g https://github.com/Axel-Erfurt/hypnotix.git
```
