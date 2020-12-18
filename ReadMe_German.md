# Hypnotix

Hypnotix ist eine IPTV-Streaming-Anwendung mit Unterstützung für Live-TV, Filme und Serien.

<img src="https://user-images.githubusercontent.com/1138515/99553152-b8bac780-29b5-11eb-9d75-8756ed7581b6.png" width="500" />

Es kann mehrere IPTV-Anbieter der folgenden Typen unterstützen:

    M3U URL
    Xtream-API
    Lokale M3U-Wiedergabeliste

Lizenz

    Code: GPLv3
    Flags: https://github.com/linuxmint/flags
    Symbole: CC BY-ND 2.0

# Voraussetzungen

- libxapp 1.4+
- libmpv
- python3-imdbpy  [für ältere Mint and Debian Versionen siehe hier](https://packages.ubuntu.com/focal/all/python3-imdbpy/download)

# Fernsehkanäle und Medieninhalte

Hypnotix bietet keine Inhalte oder TV-Kanäle, sondern ist eine Player-Anwendung, die von IPTV-Anbietern gestreamt wird.

Standardmäßig ist Hypnotix mit einem IPTV-Anbieter namens Free-IPTV konfiguriert: https://github.com/Free-IPTV/Countries.

Dieser Anbieter wurde ausgewählt, weil er die folgenden Kriterien erfüllt:

    Es enthält nur kostenlose, legale und öffentlich zugängliche Inhalte
    Es gruppiert Fernsehkanäle nach Ländern
    Es enthält keine sogenannten xxx Inhalte für Erwachsene

Probleme im Zusammenhang mit Fernsehkanälen und Medieninhalten sollten direkt an den jeweiligen Anbieter gerichtet werden.

Hinweis: Free-IPTV kann jederzeit von Hypnotix entfernt werden.

## Playlists für Serien erstellen

Nutze ExxSxx in der Playlist um es in Serien zu platzieren.

- S01E12 = Saffel 1 Episode 12

z.B.

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
## deb für Mint erstellen

In Mint kann man mint-build nutzen

```
apt install mint-dev-tools
mint-build -i -g hypnotix
```
