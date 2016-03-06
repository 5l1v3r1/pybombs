#
# Copyright 2016 Free Software Foundation, Inc.
#
# This file is part of GNU Radio
#
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#
""" Abstraction for config files """

import yaml

class PBConfigFile(object):
    """
    Abstraction layer for our config and other files
    """
    def __init__(self, filename):
        self._filename = filename
        try:
            self.data = yaml.safe_load(open(filename).read()) or {}
        except (IOError, OSError):
            self.data = {}
        assert isinstance(self.data, dict)

    def get(self):
        " Return the data from the config file as a dict "
        return self.data or {}

    def save(self, newdata=None):
        " Write the contents of the data cache to the file. "
        if newdata is not None:
            assert isinstance(newdata, dict)
            self.data = newdata
        open(self._filename, 'wb').write(yaml.dump(self.data, default_flow_style=False))

    def update(self, newdata):
        " Overwrite the data with newdata recursively. Updates the file. "
        self.data = dict_merge(self.data, newdata)
        self.save()
        return self.data

