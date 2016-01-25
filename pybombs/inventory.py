#!/usr/bin/env python2
#
# Copyright 2015 Free Software Foundation, Inc.
#
# This file is part of PyBOMBS
#
# PyBOMBS is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# PyBOMBS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PyBOMBS; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#
"""
Inventory Manager
"""

import pprint
from pybombs import pb_logging

class Inventory(object):
    """
    Inventory Manager.

    Every prefix has an inventory, a list of packages that are
    installed and in which state they current are.

    Except for save(), none of the methods actually writes to the
    inventory file.
    """
    def __init__(
            self,
            prefix_path,
            inventory_file=None,
            satisfy=("src",)
        ):
        self._filename = inventory_file
        self._satisfy = satisfy
        self._contents = {}
        self.log = pb_logging.logger
        self.load()
        self._valid_states = {
            'fetched': 'Package source is in prefix, but not installed.',
            'installed': 'Package is installed into current prefix.'
        }

    def load(self):
        """
        Load the inventory file.
        If the file does not exist, initialize the internal content
        with an empty dictionary.
        This will override any internal state.
        """
        try:
            self.log.debug("Trying to load inventory file {}...".format(self._filename))
            inv_file = open(self.inv_file, 'rb')
            self.contents = pickle.load(inv_file)
            inv_file.close()
        except:
            self.log.debug("No success. Creating empty inventory.")
            self.contents = {}
        return

    def save(self):
        """
        Save current state of inventory to the inventory file.
        This will override any existing file with the same name
        and without warning, even if no such file existed.
        """
        inv_file = open(self._filename, 'wb')
        pickle.dump(self.contents, inv_file)
        inv_file.close()


    def has(self, pkg):
        """
        Returns true if the package pkg is in the inventory.
        """
        return self._contents.has_key()

    def remove(self, pkg):
        """
        Remove package pkg from the inventory.
        """
        if self.has(pkg):
            del self._contents[pkg]

    def get_state(self, pkg):
        """
        Return a package's state.
        See the documentation for Inventory for a list of valid states.
        If pkg does not exist, returns None.
        """
        try:
            return self.contents[pkg]["state"]
        except KeyError:
            return None

    def set_state(self, pkg, state):
        """
        Sets the state of pkg to state.
        If pkg does not exist, add that package to the list.
        """
        if not state in self._valid_states.keys() :
            raise ValueError("Invalid state: {}".format(state))
        if not self.has(pkg):
            self._contents[pkg] = {}
        self._contents[pkg]["state"] = state

    def get_valid_states(self):
        """
        Returns a list of valid arguments for set_state()
        """
        return self._valid_states.keys()

