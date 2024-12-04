# Hypnotix for Windows

Hypnotix for Windows is an IPTV streaming application with support for live TV.

It is a fork of [hypnotix](https://github.com/linuxmint/hypnotix) which is a Linux only app built and maintained for Linux Mint. It is built with GTK3 and my aim is to port this over to Windows with as minimal changes as required and future compatibility in mind.

I have only an initial build running in the crudest way possible and I have plans to bring this up to spec and also make it package/ship ready in future. For now, you will need to build the app on your own for now with the instructions below.

**Known Issues:**
- Live TV video overlay controls are not available. This is potentially a libmpv issue. See [this issue in python-mpv](https://github.com/jaseg/python-mpv/issues/103) for details.
- Movie and Series modules are not tested and are not a priority.
- There could be other issues

![shadow](https://github.com/user-attachments/assets/9735d7a2-7867-48c4-aa80-8b024c8488d8)

# License

- Code: GPLv3
- Icons on the landing page: CC BY-ND 2.0

# Development Requirements

- [MSYS2](https://github.com/msys2) (tested with UCRT64 profile)
- MSYS2 packages  
    
    > Note 1: Not all packages might be required and there might be duplicates. I need to test this in a fresh VM to find only the essential ones later.  

    > Note 2: Install the packages as ```pacman -S <packagename>``` in MSYS2

    GTK
    - mingw-w64-x86_64-gtk3
    - mingw-w64-x86_64-glib2
    - mingw-w64-x86_64-glade
    - mingw-w64-x86_64-gstreamer

    MPV
    - mingw-w64-x86_64-mpv
    - ucrt64/mingw-w64-ucrt-x86_64-mpv

    GCC and Build
    - mingw-w64-x86_64-gcc
    - mingw-w64-x86_64-make
    - mingw-w64-x86_64-pkg-config

    Python
    - mingw-w64-x86_64-python3
    - mingw-w64-x86_64-python3-gobject
    - mingw-w64-x86_64-python-pip

    XML
    - mingw-w64-x86_64-libxml2
    - mingw-w64-x86_64-libxslt

    Adwaita Theme for icons
    - mingw64/mingw-w64-x86_64-adwaita-icon-theme 
    - ucrt64/mingw-w64-ucrt-x86_64-adwaita-icon-theme


# Run Steps:

1) Install MSYS2 and git clone repo.
    > **Note:** Use Windows Terminal (with MSYS2/UCRT64 shell profile) or MSYS2 app directly or whichever terminal app you are comfortable with for shell access.  
    ```git clone git@github.com:lakshminarayananb/hypnotix-windows.git```

2) Install the above mentioned development packages.  
    ```
    pacman -S mingw-w64-x86_64-gtk3
    pacman -S mingw-w64-x86_64-glade
    pacman -S mingw-w64-x86_64-glib2
    pacman -S mingw-w64-x86_64-gstreamer

    pacman -S mingw-w64-x86_64-mpv
    pacman -S ucrt64/mingw-w64-ucrt-x86_64-mpv

    pacman -S mingw-w64-x86_64-gcc
    pacman -S mingw-w64-x86_64-make
    pacman -S mingw-w64-x86_64-pkg-config

    pacman -S mingw-w64-x86_64-python3
    pacman -S mingw-w64-x86_64-python3-gobject
    pacman -S mingw-w64-x86_64-python-pip

    pacman -S mingw-w64-x86_64-libxml2
    pacman -S mingw-w64-x86_64-libxslt

    pacman -S ucrt64/mingw-w64-ucrt-x86_64-adwaita-icon-theme
    pacman -S mingw64/mingw-w64-x86_64-adwaita-icon-theme
    ```

3) Install python dependencies (you may try with venv)
    ```
    pip install mpv
    pip install requests
    pip install setproctitle
    pip install unidecode
    ```
    > **Note:** ```pip install IMDbPY``` is removed for now due to build issues and related features are commented out.

4) Now running the hypnotix.py should launch the app
    ```python3 usr/lib/hypnotix/hypnotix.py``` 


# TV Channels and media content

Hypnotix for Windows or  Hypnotix does not provide content or TV channels, it is a player application which streams from IPTV providers.

By default, Hypnotix for Windows is configured with an IPTV provider called Free-TV: https://github.com/Free-TV/IPTV.

This provider was chosen because it satisfied the following criterias:

- It only includes free, legal, publicly available content
- It groups TV channels by countries
- It doesn't include adult content

Issues relating to TV channels and media content should be addressed directly to the relevant provider.

Note: Feel free to remove Free-TV from Hypnotix if you don't use it, or add any other provider you may have access to or local M3U playlists.