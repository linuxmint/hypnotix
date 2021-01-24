project('hypnotix', version: '1.4', meson_version: '>=0.49.0')

i18n = import('i18n')
python = import('python')

python3 = python.find_installation('python3')
if not python3.found()
    error('Python 3 is required to build and use Hypnotix')
endif

prefix = get_option('prefix')

bindir = join_paths(prefix, get_option('bindir'))
datadir = join_paths(prefix, get_option('datadir'))
libexecdir = join_paths(prefix, get_option('libexecdir'))

# Ensure these dependencies are the same with /usr/lib/hypnotix/*.py.
# If you update these dependencies, update the others and the debian packaging.
dependency('python3', version: '>= 3.6')
dependency('glib-2.0')
dependency('gobject-introspection-1.0')
dependency('gtk+-3.0', version: '>= 3.20')
dependency('gio-2.0')
dependency('pango', version: '>= 1.44.0')
dependency('pygobject-3.0', version: '>= 3.30')
dependency('xapp', version: '>= 1.8.0')

subdir('install-scripts')
subdir('po')
subdir('usr')
