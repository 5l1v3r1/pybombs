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
Package Manager: Manages packages (no shit)
"""

import os
import operator
from distutils.version import StrictVersion

import pb_logging
from pb_exception import PBException
from pybombs.config_manager import config_manager
from pybombs import recipe
import packagers

operators = {'<=': operator.le, '==': operator.eq, '>=': operator.ge, '!=': operator.ne}
compare = lambda x, y, z: operators[z](StrictVersion(x), StrictVersion(y))

class PackageManager(object):
    """
    Meta-package manager. This will determine, according to our system
    and the configuration, who takes care of managing packages and
    then dispatches specific package managers. For example, this might
    dispatch an apt-get backend on Ubuntu and Debian systems, or a
    yum backend on Fedora systems.
    """
    def __init__(self,):
        # Set up logger:
        self.log = pb_logging.logger.getChild("PackageManager")
        self.cfg = config_manager
        if self.cfg.get_active_prefix().prefix_dir is None:
            self.log.error("No prefix specified. Aborting.")
            exit(1)
        self.prefix = self.cfg.get_active_prefix()
        # Create a source package manager
        self.src = packagers.Source()
        # Create sorted list of binary package managers
        requested_packagers = [x.strip() for x in self.cfg.get('packagers').split(',')]
        binary_pkgrs = []
        for pkgr in requested_packagers:
            self.log.debug("Attempting to add binary package manager {}".format(pkgr))
            p = packagers.get_by_name(pkgr)
            if p is None:
                self.log.warn("This binary package manager can't be instantiated: {}".format(pkgr))
                continue
            if p.supported():
                self.log.debug("{} is supported!".format(pkgr))
                binary_pkgrs.append(p)
        self._packagers = []
        for satisfy in self.cfg.get('satisfy_order').split(','):
            satisfy = satisfy.strip()
            if satisfy == 'src':
                self._packagers += [self.src,]
            elif satisfy == 'native':
                self._packagers += binary_pkgrs
            else:
                raise PBException("Invalid satisfy_order value: {}".format(satisfy))
        # Now we can use self.packagers, in order, for our commands.

    def get_packagers(self, pkgname):
        if self.prefix.packages.has_key(pkgname) and \
                self.prefix.packages[pkgname].find('forcebuild') != -1:
            return [self.src,]
        return self._packagers

    def exists(self, name, required_version=None):
        """
        Check to see if this package exists.
        If version is provided, only returns True if the version matches.
        Returns None if package does not exist.
        """
        r = recipe.get_recipe(name)
        for pkgr in self.get_packagers(name):
            pkg_version = pkgr.exists(r)
            if pkg_version is None or not pkg_version:
                continue
            if required_version is not None:
                if compare(pkg_version, required_version, '>='):
                    return pkg_version
                else:
                    continue
            else:
                return pkg_version
        return None

    def installed(self, name, required_version=None):
        """
        Check to see if this package is installed.

        If yes, it returns a version string. Otherwise, returns False.
        """
        r = recipe.get_recipe(name)
        for pkgr in self.get_packagers(name):
            pkg_version = pkgr.installed(r)
            if pkg_version is None or not pkg_version:
                continue
            if required_version is not None and compare(pkg_version, required_version, '>='):
                return pkg_version
        return False

    def install(self, name):
        """
        Install the given package. Returns True if successful, False otherwise.
        """
        r = recipe.get_recipe(name)
        for pkgr in self.get_packagers(name):
            try:
                install_result = pkgr.install(r)
            except PBException as e:
                self.log.error(
                    "Something went wrong while trying to install {} using {}: {}".format(
                        name, pkgr.name, str(e)
                    )
                )
                continue
            if install_result:
                return True
        return False

    def update(self, name):
        """
        Update the given package. Returns True if successful, False otherwise.
        """
        r = recipe.get_recipe(name)
        for pkgr in self.get_packagers(name):
            try:
                update_result = pkgr.update(r)
            except PBException as e:
                self.log.error(
                    "Something went wrong while trying to update {} using {}: {}".format(
                        name, pkgr.name, str(e)
                    )
                )
                continue
            if update_result:
                return True
        return False

# Some test code:
if __name__ == "__main__":
    config_manager.set('packagers', 'dummy')
    config_manager.set('satisfy_order', 'native')
    pm = PackageManager()
    print pm.exists('gcc')
    print pm.installed('gcc')
    print pm.install('gcc')
