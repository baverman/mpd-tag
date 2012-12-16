from setuptools import setup

from mpd_tag import VERSION

setup(
    name     = 'mpd-tag',
    version  = VERSION,
    author   = 'Anton Bobrov',
    author_email = 'bobrov@vl.ru',
    description = 'MPD tag manager',
    #long_description = open('README.rst').read().replace('https', 'http'),
    install_requires = ['python-mpd'],
    zip_safe   = False,
    py_modules = ['mpd_tag'],
    scripts = ['bin/mtag'],
    include_package_data = True,
    url = 'http://github.com/baverman/mpd-tag',
    classifiers = [
        "Programming Language :: Python",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Natural Language :: English",
    ],
)
