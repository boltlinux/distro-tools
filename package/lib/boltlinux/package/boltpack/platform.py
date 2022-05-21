# -*- encoding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2016-2018 Tobias Koch <tobias.koch@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import locale
import os
import re
import subprocess

from boltlinux.package.boltpack.packagemanager import PackageManager

class Platform:

    CONFIG_GUESS = '/usr/share/misc/config.guess'

    @staticmethod
    def build_flags():
        build_flags = {}

        if "linux" in Platform.kernel_name().lower() and \
                os.path.exists("/etc/debian_version"):
            return Platform._dpkg_build_flags()
        #end if

        if Platform.find_executable("gcc"):
            build_flags["CFLAGS"] = "-g -O2 -fstack-protector-strong " \
                "-Wformat -Werror=format-security"
            build_flags["CXXFLAGS"] = "-g -O2 -fstack-protector-strong " \
                "-Wformat -Werror=format-security"
            build_flags["CPPFLAGS"] = \
                "-Wdate-time -D_FORTIFY_SOURCE=2"
            build_flags["LDFLAGS"] = \
                "-Wl,-z,relro"
        #end if

        return build_flags
    #end function

    @staticmethod
    def find_executable(executable_name, fallback=None):
        search_path = os.environ.get("PATH", "").split(os.pathsep) + [
            "/tools/bin",
            "/tools/sbin",
            "/usr/local/bin",
            "/usr/local/sbin",
            "/bin",
            "/sbin",
            "/usr/bin",
            "/usr/sbin"
        ]

        for path in search_path:
            location = os.path.join(path, executable_name)
            if os.path.exists(location):
                return location
        #end for

        return fallback
    #end function

    @staticmethod
    def config_guess():
        preferred_encoding = locale.getpreferredencoding(False)
        gcc = Platform.find_executable("gcc")

        if gcc:
            return subprocess.run([gcc, "-dumpmachine"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL)\
                            .stdout\
                            .decode(preferred_encoding)\
                            .strip()
        #end if

        if os.path.exists(Platform.CONFIG_GUESS):
            return subprocess.run([Platform.CONFIG_GUESS],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL)\
                            .stdout\
                            .decode(preferred_encoding)\
                            .strip()
        #end if

        return ""
    #end function

    @staticmethod
    def target_machine():
        result = Platform._key_value_file_lookup(
            "TARGET_MACHINE", "/etc/target"
        )

        if not result:
            result = PackageManager.instance().main_architecture()
        if not result:
            result = Platform.config_guess().split("-")[0]
        return result
    #end function

    @staticmethod
    def target_type():
        result = Platform._key_value_file_lookup("TARGET_TYPE", "/etc/target")
        if not result:
            result = Platform.config_guess()
        return result
    #end function

    @staticmethod
    def tools_machine():
        result = Platform._key_value_file_lookup("TOOLS_TYPE", "/etc/target")
        if result:
            result = result.split("-", 1)[0]
        if not result:
            result = Platform.machine_name()
        return result
    #end function

    @staticmethod
    def tools_type():
        result = Platform._key_value_file_lookup("TOOLS_TYPE", "/etc/target")
        if not result:
            result = "{}-tools-linux-{}".format(
                Platform.machine_name(), Platform.libc_vendor()
            )
        return result
    #end function

    @staticmethod
    def kernel_name():
        return Platform._uname("-s")

    @staticmethod
    def machine_name():
        return Platform._uname("-m")

    @staticmethod
    def libc_vendor():
        Platform._uname("-o").lower().split("/")[0]

    @staticmethod
    def is_bolt():
        result = Platform._key_value_file_lookup("ID", "/etc/os-release")
        return result.lower() == "bolt"

    # HIDDEN

    @staticmethod
    def _uname(*args):
        uname = Platform.find_executable("uname")
        if not uname:
            return ""

        return subprocess.run(
            [uname, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        ).stdout \
         .decode(locale.getpreferredencoding(False)) \
         .strip()
    #end function

    @staticmethod
    def _dpkg_build_flags():
        build_flags = {}
        dpkg_buildflags = Platform.find_executable("dpkg-buildflags")

        if not dpkg_buildflags:
            return build_flags

        preferred_encoding = locale.getpreferredencoding(False)

        for flag in subprocess.run([dpkg_buildflags, "--list"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)\
                        .stdout.decode(preferred_encoding).splitlines():
            flag = flag.strip()

            if not flag:
                continue

            value = subprocess.run([dpkg_buildflags, "--get", flag],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)\
                            .stdout.decode(preferred_encoding).strip()

            value = re.sub(r"\s*-fdebug-prefix-map=\S+\s*", " ", value)
            build_flags[flag] = value
        #end for

        return build_flags
    #end function

    @staticmethod
    def _key_value_file_lookup(attr_name, filename="/etc/target"):
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as fp:
                for line in fp:
                    try:
                        k, v = [x.strip() for x in line.split("=", 1)]
                    except ValueError:
                        continue
                    if k == attr_name:
                        return v
                #end for
            #end with
        #end if

        return None
    #end function

#end class
