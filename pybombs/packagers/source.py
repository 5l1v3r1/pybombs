#
# Copyright 2015 Free Software Foundation, Inc.
#
# This file is part of PyBOMBS
#
# PyBOMBS is free software you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation either version 3, or (at your option)
# any later version.
#
# PyBOMBS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PyBOMBS see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#
"""
Packager: Source packages
"""

import os
import re
import copy
import shutil
from pybombs import pb_logging
from pybombs import inventory
from pybombs.utils import subproc
from pybombs.utils import output_proc
from pybombs.pb_exception import PBException
from pybombs.fetch import make_fetcher
from pybombs.config_manager import config_manager
from pybombs.packagers.base import PackagerBase

class Source(PackagerBase):
    name = "source"

    """
    Source package manager.
    """
    def __init__(self):
        PackagerBase.__init__(self)
        if self.cfg.get_active_prefix().prefix_dir is None:
            self.log.error("No prefix specified. Aborting.")
            exit(1)
        self.prefix = self.cfg.get_active_prefix()
        self.inventory = inventory.Inventory(self.prefix.inv_file)
        self.inventory.load()

    def supported(self):
        """
        We can always build source packages.
        """
        return True

    def exists(self, recipe):
        """
        This will work whenever any sources are defined.
        """
        # Return a pseudo-version
        # TODO check if we can get something better from the inventory
        return "0.0"

    def install(self, recipe):
        """
        Run the source installation process for package 'recipe'.

        May raise an exception if things go terribly wrong.
        Otherwise, return True on success and False if installing failed.
        """
        if len(recipe.srcs) == 0:
            self.log.warning("Cannot find a source URI for package {}".format(recipe.id))
            return False
        ### Fetch sources:
        self.log.debug("Source URI: {}".format(recipe.srcs[0].split("://", 1)[1]))
        fetched = False
        for src in recipe.srcs:
            fetcher = make_fetcher(recipe, src)
            try:
                fetch_result = fetcher.refetch(recipe, src)
                if not fetch_result:
                    self.log.warning("Fetching source {0} failed.".format(src))
                    continue
                fetched = True
                break
            except Exception:
                self.log.error("Unable to fetch source for package {}".format(recipe.id))
        if not fetched:
            self.log.error("Unable to fetch.")
        self.inventory.set_state(recipe.id, "fetch")
        self.inventory.save()
        ### Set up the build dir
        pkg_src_dir = "{src_dir}/{package}".format(
            src_dir=self.prefix.src_dir,
            package=recipe.id,
        )
        builddir = os.path.join(pkg_src_dir, recipe.install_dir)
        # The package source dir must exist, or something is wrong.
        # If the build dir exists, clear it.
        if not os.path.isdir(pkg_src_dir):
            self.log.error("There should be a source dir in {}, but there isn't.".format(pkg_src_dir))
            return False
        if os.path.exists(os.path.join(pkg_src_dir, builddir)):
            shutil.rmtree(builddir)
        os.mkdir(builddir)
        cwd = os.getcwd()
        os.chdir(builddir)
        ### Run the build process
        try:
            self.configure(recipe)
            self.inventory.set_state(recipe.id, "configure")
            self.inventory.save()
            self.make(recipe)
            self.inventory.set_state(recipe.id, "make")
            self.inventory.save()
            self.make_install(recipe)
            self.inventory.set_state(recipe.id, "installed")
            self.inventory.save()
        except PBException as err:
            self.log.error("Problem occured while building package {}:\n{}".format(recipe.id, str(err)))
            return False
        ### Housekeeping
        os.chdir(cwd)
        return True

    def installed(self, recipe):
        """
        We read the version number from the inventory. It might not exist,
        but that's OK.
        """
        if self.inventory.has(recipe.id) and self.inventory.get_state(recipe.id) == 'installed':
            return self.inventory.get_version(recipe.id, True)
        return False

    def configure(self, recipe, try_again=False):
        """
        Run the configuration step for this recipe.
        If try_again is set, it will assume the configuration failed before
        and we're trying to run it again.
        """
        self.log.debug("Configuring recipe {}".format(recipe.id))
        self.log.debug("Configure command - {0}".format(recipe.src_configure))
        self.log.debug("Using lvars - {}".format(recipe.lvars))
        self.log.debug("In cwd - {}".format(os.getcwd()))
        pre_cmd = self.var_replace_all(recipe, recipe.src_configure)
        cmd = self.config_filter(pre_cmd)
        self.log.debug('Configure command: {}'.format(cmd))
        o_proc = None
        if self.log.getEffectiveLevel() < pb_logging.OBNOXIOUS and not try_again:
            o_proc = output_proc.OutputProcessorMake(preamble="Configuring: ")
        #pre_filt_command = self.scanner.var_replace_all(self.scr_configure)
        #st = bashexec(self.scanner.config_filter(pre_filt_command), o_proc)
        if subproc.monitor_process(cmd, shell=True, o_proc=o_proc) == 0:
            self.log.debug("Configure successful.")
            return True
        # OK, something went wrong.
        if try_again == False:
            self.log.warning("Configuration failed. Re-trying with higher verbosity.")
            return self.configure(recipe, try_again=True)
        else:
            self.log.error("Configuration failed after running at least twice.")
            raise PBException("Configuration failed")


    def make(self, recipe, try_again=False):
        """
        Build this recipe.
        If try_again is set, it will assume the build failed before
        and we're trying to run it again. In this case, reduce the
        makewidth to 1 and show the build output.
        """
        self.log.debug("Building recipe {}".format(recipe.id))
        self.log.debug("In cwd - {}".format(os.getcwd()))
        o_proc = None
        if self.log.getEffectiveLevel() < pb_logging.OBNOXIOUS and not try_again:
            o_proc = output_proc.OutputProcessorMake(preamble="Building: ")
        cmd = self.var_replace_all(recipe, recipe.src_make)
        self.log.debug("Make command - {0}".format(cmd))
        if subproc.monitor_process(cmd, shell=True, o_proc=o_proc) == 0:
            self.log.debug("Make successful")
            return True
        # OK, something bad happened.
        # Stash the makewidth so we can set it back later:
        makewidth = recipe.lvars['makewidth']
        if try_again == False:
            recipe.lvars['makewidth'] = '1'
            self.make(recipe, try_again=True)
            recipe.lvars['makewidth'] = makewidth
        else:
            self.log.error("Build failed. See output above for error messages.")
            raise PBException("Build failed.")

    def make_install(self, recipe):
        """
        Run 'make install' or whatever copies the files to the right place.
        """
        self.log.debug("Installing package {}".format(recipe.id))
        self.log.debug("In cwd - {}".format(os.getcwd()))
        pre_cmd = self.var_replace_all(recipe, recipe.src_install)
        cmd = self.install_filter(pre_cmd)
        self.log.debug("Install command - {1}".format(cmd))
        o_proc = None
        if self.log.getEffectiveLevel() < pb_logging.OBNOXIOUS:
            o_proc = output_proc.OutputProcessorMake(preamble="Installing: ")
        if subproc.monitor_process(cmd, shell=True, o_proc=o_proc) == 0:
            self.log.debug("Installation successful")
            return True
        self.log.error("Make failed")
        return False

    def var_replace(self,s, lvars):
        #for k in vars.keys():
        #    s = s.replace("$%s"%(k), vars[k])
        for k in lvars.keys():
            s = s.replace("$%s"%(k), str(lvars[k]))
        #for k in lvars.keys():
        #    s = s.replace("$%s"%(k), lvars[k])
        options = self.cfg.cfg_cascade[0]
        self.log.debug("Options --> {}".format(options))
        options['prefix'] = "{}/target".format(self.prefix.prefix_dir)
        for k in options.keys():
            s = s.replace("$%s"%(k).lower(), str(options[k]))
        return s

    ### NOT BEING USED ###
    def fancy_var_replace(self,s,d):
        finished = False
        while not finished:
            os = s
            for k in d.keys():
                s = s.replace("$%s"%(k), d[k])
            self.log.debug(s,os)
            if(os == s):
                finished = True
        return s

    def replc(self, m):
#        print "GOT REPL C: %s"%(str([m.group(1), m.group(2), m.group(3)]))
        if m.group(1) == self.tmpcond:
            return  m.group(2)
        else:
            return  m.group(3)

    def var_replace_all(self, recipe, s):
        finished = False
        lvars = copy.copy(recipe.lvars)
        lvars.update(vars(self.cfg))
        s = self.var_replace(s, lvars)
        for k in lvars:
            fm = "\{([^\}]*)\}"
            rg = r"%s==(\w+)\?%s:%s"%(k,fm,fm)
            self.tmpcond = lvars[k]
            s = re.sub(rg, self.replc, s)
        return s

    def config_filter(self, in_string):
        prefix = re.compile("-DCMAKE_INSTALL_PREFIX=\S*")
        toolchain = re.compile("-DCMAKE_TOOLCHAIN_FILE=\S*")
        cmake = re.compile("cmake \S* ")
        CC = re.compile("CC=\S* ")
        CXX = re.compile("CXX=\S* ")
        if str(os.environ.get('PYBOMBS_SDK')) == 'True':
            cmk_cmd_match = re.search(cmake, in_string)
            if cmk_cmd_match:
                idx = in_string.find(cmk_cmd_match.group(0)) + len(cmk_cmd_match.group(0))
                in_string = re.sub(prefix, "-DCMAKE_INSTALL_PREFIX=" + self.cfg.get('config', 'sdk_prefix'), in_string)
                if re.search(toolchain, in_string):
                    in_string = re.sub(toolchain, "-DCMAKE_TOOLCHAIN_FILE=" + self.cfg.get('config', 'toolchain'), in_string)
                else:
                    in_string = in_string[:idx] +  "-DCMAKE_TOOLCHAIN_FILE=" + self.cfg.get('config', 'toolchain') + ' ' + in_string[idx:]
                if re.search(CC, in_string):
                    in_string = re.sub(CC, "", in_string)
                if re.search(CXX, in_string):
                    in_string = re.sub(CXX, "", in_string)
        return in_string

    # Not really sure what this is for from the original
    def install_filter(self, in_string):
        return in_string
        #installed = re.compile("make install")
        #if str(os.environ.get('PYBOMBS_SDK')) == 'True':
            #print in_string
            #mk_inst_match = re.search(installed, in_string)
            #if mk_inst_match:
                #idx = in_string.find(mk_inst_match.group(0)) + len(mk_inst_match.group(0))
                #in_string = in_string[:idx] +  " DESTDIR=" + config.get('config', 'sandbox') + ' ' + in_string[idx:]
        #return in_string



    #def is_installed(self, recipe):
        #"""
        #Check if a package is installed.
        #"""
        #return self.inventory.get_state(recipe.id) == 'installed'

    #def remove(self, recipe):
        #pass # tbw



    #def fetch(self):
        #pass
        ### this is not possible if we do not have sources
        ##if(len(self.source) == 0):
            ##v.print_v(v.WARN, "WARNING: no sources available for package %s!"%(self.name))
            ##return True
        ##fetcher = fetch.fetcher(self.source, self)
        ##fetcher.fetch()
        ##if(not fetcher.success):
            ##if(len(self.source) == 0):
                ##raise PBRecipeException("Failed to Fetch package '%s' no sources were provided! '%s'!"%(self.name, self.source))
            ##else:
                ##raise PBRecipeException("Failed to Fetch package '%s' sources were '%s'!"%(self.name, self.source))
        ### update value in inventory
        ##inv.set_state(self.name, "fetch")
        ##self.last_fetcher = fetcher
        ##v.print_v(v.DEBUG, "Setting fetched version info (%s,%s)"%(fetcher.used_source, fetcher.version))
        ##inv.set_prop(self.name, "source", fetcher.used_source)
        ##inv.set_prop(self.name, "version", fetcher.version)


    #def configure(self, recipe, try_again=False):
        #"""
        #Run the configuration step for this recipe.
        #If try_again is set, it will assume the configuration failed before
        #and we're trying to run it again.
        #"""
        #self.log.debug("Configuring recipe {}".format(recipe.id))
        ##mkchdir(topdir + "/src/" + self.name + "/" + self.installdir)
        ##if v.VERBOSITY_LEVEL >= v.DEBUG or try_again:
            ##o_proc = None
        ##else:
            ##o_proc = output_proc.OutputProcessorMake(preamble="Configuring: ")
        ##pre_filt_command = self.scanner.var_replace_all(self.scr_configure)
        ##st = bashexec(self.scanner.config_filter(pre_filt_command), o_proc)
        ##if (st == 0):
            ##return
        ### If configuration fails:
        ##if try_again == False:
            ##v.print_v(v.ERROR, "Configuration failed. Re-trying with higher verbosity.")
            ##self.make(try_again=True)
        ##else:
            ##v.print_v(v.ERROR, "Configuration failed. See output above for error messages.")
            ##raise PBRecipeException("Configuration failed")


    #def make(self, try_again=False):
        #"""
        #Build this recipe.
        #If try_again is set, it will assume the build failed before
        #and we're trying to run it again. In this case, reduce the
        #makewidth to 1 and show the build output.
        #"""
        #self.log.debug("Building recipe {}".format(recipe.id))
        ##v.print_v(v.PDEBUG, "make")
        ##mkchdir(topdir + "/src/" + self.name + "/" + self.installdir)
        ##if v.VERBOSITY_LEVEL >= v.DEBUG or try_again:
            ##o_proc = None
        ##else:
            ##o_proc = output_proc.OutputProcessorMake(preamble="Building:    ")
        ### Stash the makewidth so we can set it back later
        ##makewidth = self.scanner.lvars['makewidth']
        ##if try_again:
            ##self.scanner.lvars['makewidth'] = '1'
        ##st = bashexec(self.scanner.var_replace_all(self.scr_make), o_proc)
        ##self.scanner.lvars['makewidth'] = makewidth
        ##if st == 0:
            ##return
        ### If build fails, try again with more output:
        ##if try_again == False:
            ##v.print_v(v.ERROR, "Build failed. Re-trying with reduced makewidth and higher verbosity.")
            ##self.make(try_again=True)
        ##else:
            ##v.print_v(v.ERROR, "Build failed. See output above for error messages.")
            ##raise PBRecipeException("Build failed.")

    ##def installed(self):
        ### perform installation, file copy
        ##v.print_v(v.PDEBUG, "installed")
        ##mkchdir(topdir + "/src/" + self.name + "/" + self.installdir)
        ##if v.VERBOSITY_LEVEL >= v.DEBUG:
            ##o_proc = None
        ##else:
            ##o_proc = output_proc.OutputProcessorMake(preamble="Installing: ")
        ##pre_filt_command = self.scanner.var_replace_all(self.scr_install)
        ##st = bashexec(self.scanner.installed_filter(pre_filt_command), o_proc)
        ##if (st != 0):
            ##raise PBRecipeException("Installation failed.")

    ### run package specific make uninstall
    ##def uninstall(self):
        ##try:
            ##if(self.satisfier == "inventory"):
                ##mkchdir(topdir + "/src/" + self.name + "/" + self.installdir)
                ##st = bashexec(self.scanner.var_replace_all(self.scr_uninstall))
                ##self.satisfier = None
                ##del vars["%s.satisfier"%(self.name)]
            ##else:
                ##v.print_v(v.WARN, "pkg not installed from source, ignoring")
        ##except:
            ##v.print_v(v.DEBUG, "local build dir does not exist")

    ### clean the src dir
    ##def clean(self):
        ##os.chdir(topdir + "/src/")
        ##rmrf(self.name)
        ##inv.set_state(self.name,None)


    ##def run_install(self, pkgname):
        ##"""
        ##Install the package called pkgname.

        ##Order of ops for each pkgname:
        ##- Check if pkgname is in the recipe list
        ##- Ask for a Recipe object and see if it's already installed
          ##- If yes, figure out if we want to reinstall
            ##- If no, return
        ##- Ask the RecipeListManager for a list of dependencies (recursively)
        ##- For every dependency, ask Recipe if it's already installed in
          ##the current prefix
        ##- Create a new list of all Recipes that need to be installed
        ##- Install each of these
        ##"""
        ##self.log.info("Starting installation of package {0}".format(pkgname))


        ##if not check_recipe(pkgname):
            ##die("unknown package "+pkgname)
        ##if die_if_already and check_installed(pkgname):
            ##print pkgname + " already installed"
            ##return
        ##validate_write_perm(vars["prefix"])
        ##rc = global_recipes[pkgname]
        ##pkg_missing = rc.recursive_satisfy()

        ### remove duplicates while preserving list order (lowest nodes first)
        ##pkg_missing = list_unique_ord(pkg_missing)
        ##self.log.info("Installing packages:\n" + "\n".join(["* {0}".format(x) for x in pkg_missing]))

        ### prompt if list is ok?
        ### provide choice of deb satisfiers or source build?

        ##for pkg in pkg_missing:
            ##global_recipes[pkg].install()
            ##if(pkg == "gnuradio"):
                ##if(confirm("Run VOLK Profile to choose fastest kernels?","Y",5)):
                    ##run_volk_profile()
    ###    global_recipes[pkgname].install()
