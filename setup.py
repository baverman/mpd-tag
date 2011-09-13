from setuptools import setup, find_packages
from setuptools.command import easy_install

def install_script(self, dist, script_name, script_text, dev_path=None):
    script_text = easy_install.get_script_header(script_text) + (
        ''.join(script_text.splitlines(True)[1:]))

    self.write_script(script_name, script_text, 'b')

easy_install.easy_install.install_script = install_script

setup(
    name     = 'mpd-tag',
    version  = '0.3',
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
