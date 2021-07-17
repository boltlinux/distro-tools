# -*- encoding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2021 Tobias Koch <tobias.koch@gmail.com>
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

import collections
import logging
import os
import re
import shlex
import shutil
import textwrap

from boltlinux.error import BoltError
from boltlinux.miscellaneous.userinfo import UserInfo
from boltlinux.miscellaneous.platform import Platform
from boltlinux.osimage.specfile import SpecfileParser
from boltlinux.osimage.subprocess import Subprocess

LOGGER = logging.getLogger(__name__)

class ImageGenerator:

    OPKG_OPTIONS_TEMPLATE = textwrap.dedent(
        """\
        dest root /

        option signature_type usign
        option no_install_recommends
        option force_removal_of_dependent_packages
        option force_postinstall

        {opt_check_sig}
        """
    )  # noqa

    OPKG_FEEDS_TEMPLATE = textwrap.dedent(
        """\
        src/gz main {repo_base}/{release}/core/{arch}/{libc}/main
        """)  # noqa

    OPKG_ARCH_TEMPLATE = textwrap.dedent(
        """\
        arch {arch} 1
        arch all 1
        """
    )  # noqa

    DIRS_TO_CREATE = [
        (0o0755, "/dev"),
        (0o0755, "/etc"),
        (0o0755, "/etc/opkg"),
        (0o0755, "/etc/opkg/usign"),
        (0o0755, "/proc"),
        (0o0755, "/run"),
        (0o0755, "/sys"),
        (0o1777, "/tmp"),
        (0o0755, "/usr"),
        (0o0755, "/usr/bin"),
        (0o0755, "/var"),
    ]

    DIRS_TO_CLEAN = [
        "/tmp",
        "/var/tmp",
    ]

    ETC_PASSWD = textwrap.dedent(
        """\
        root:x:0:0:root:/root:/bin/sh
        daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
        bin:x:2:2:bin:/bin:/usr/sbin/nologin
        sys:x:3:3:sys:/dev:/usr/sbin/nologin
        sync:x:4:65534:sync:/bin:/bin/sync
        games:x:5:60:games:/usr/games:/usr/sbin/nologin
        man:x:6:12:man:/var/cache/man:/usr/sbin/nologin
        lp:x:7:7:lp:/var/spool/lpd:/usr/sbin/nologin
        mail:x:8:8:mail:/var/mail:/usr/sbin/nologin
        news:x:9:9:news:/var/spool/news:/usr/sbin/nologin
        uucp:x:10:10:uucp:/var/spool/uucp:/usr/sbin/nologin
        proxy:x:13:13:proxy:/bin:/usr/sbin/nologin
        www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin
        backup:x:34:34:backup:/var/backups:/usr/sbin/nologin
        list:x:38:38:Mailing List Manager:/var/list:/usr/sbin/nologin
        irc:x:39:39:ircd:/var/run/ircd:/usr/sbin/nologin
        nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
        """
    )

    ETC_GROUP = textwrap.dedent(
        """\
        root:x:0:
        daemon:x:1:
        bin:x:2:
        sys:x:3:
        adm:x:4:
        tty:x:5:
        disk:x:6:
        lp:x:7:
        mail:x:8:
        news:x:9:
        uucp:x:10:
        man:x:12:
        proxy:x:13:
        kmem:x:15:
        dialout:x:20:
        fax:x:21:
        voice:x:22:
        cdrom:x:24:
        floppy:x:25:
        tape:x:26:
        sudo:x:27:
        audio:x:29:
        dip:x:30:
        www-data:x:33:
        backup:x:34:
        operator:x:37:
        list:x:38:
        irc:x:39:
        src:x:40:
        shadow:x:42:
        utmp:x:43:
        video:x:44:
        sasl:x:45:
        plugdev:x:46:
        staff:x:50:
        games:x:60:
        users:x:100:
        nogroup:x:65534:
        """
    )

    ETC_HOSTS = textwrap.dedent(
        """\
        127.0.0.1 localhost

        ::1     localhost ip6-localhost ip6-loopback
        ff02::1 ip6-allnodes
        ff02::2 ip6-allrouters
        """
    )

    class Error(BoltError):
        pass

    def __init__(self, release, arch, libc="musl", verify=True,
            copy_qemu=False, repo_base=None, cache_dir=None):
        self._release   = release
        self._arch      = arch
        self._libc      = libc
        self._verify    = verify
        self._copy_qemu = copy_qemu
        self._repo_base = repo_base or "http://archive.boltlinux.org/dists"
        self._cache_dir = cache_dir or UserInfo.cache_dir()

        if not self._cache_dir:
            raise ImageGenerator.Error(
                "unable to determine cache directory location."
            )

        opt_check_sig = "option check_signature" if self._verify else ""

        self.context = {
            "release":
                self._release,
            "libc":
                self._libc,
            "arch":
                self._arch,
            "host_arch":
                Platform.uname("-m"),
            "machine":
                self._arch,
            "target_type":
                Platform.target_for_machine(self._arch),
            "opt_check_sig":
                opt_check_sig,
            "repo_base":
                self._repo_base
        }
    #end function

    def prepare(self, sysroot):
        if not os.path.isdir(sysroot):
            raise ImageGenerator.Error("no such directory: {}".format(sysroot))

        LOGGER.info("preparing system root.")

        sysroot = os.path.realpath(sysroot)

        for mode, dirname in self.DIRS_TO_CREATE:
            full_path = sysroot + dirname
            os.makedirs(full_path, exist_ok=True)
            os.chmod(full_path, mode)
        #end for

        var_run_symlink = sysroot + "/var/run"
        if not os.path.exists(var_run_symlink):
            os.symlink("../run", var_run_symlink)

        if self._copy_qemu:
            self._copy_qemu_to_sysroot(sysroot)

        self._write_config_files(sysroot)

        files_to_copy = [
            "/etc/hosts",
            "/etc/resolv.conf",
        ]

        for file_ in files_to_copy:
            shutil.copy2(file_, sysroot + file_)

        opkg_cmd = shlex.split(
            "opkg --offline-root '{}' update".format(sysroot)
        )

        Subprocess.run(sysroot, opkg_cmd[0], opkg_cmd)
    #end function

    def customize(self, sysroot, specfile):
        if not os.path.isdir(sysroot):
            raise ImageGenerator.Error("no such directory: {}".format(sysroot))

        LOGGER.info("================")
        LOGGER.info("loading specfile {}".format(specfile))
        LOGGER.info("================")

        sysroot = os.path.realpath(sysroot)

        with open(specfile, "r", encoding="utf-8") as f:
            parts = SpecfileParser.load(f)

        env = self._prepare_environment(sysroot)

        for start_line, end_line, p in parts:
            what = re.sub(r"([a-z])([A-Z])", r"\1 \2", p.__class__.__name__)
            what = what.lower()

            LOGGER.info(
                "applying {} from line {} to {}.".format(
                    what, start_line, end_line
                )
            )

            p.apply(sysroot, env=env)
        #end for
    #end function

    def cleanup(self, sysroot):
        if not os.path.isdir(sysroot):
            raise ImageGenerator.Error("no such directory: {}".format(sysroot))

        sysroot = os.path.realpath(sysroot)

        self._write_config_files(sysroot)
        try:
            os.unlink(sysroot + "/etc/resolv.conf")
        except OSError:
            pass

        for directory in self.DIRS_TO_CLEAN:
            full_path = sysroot + directory

            stat = os.lstat(full_path)
            shutil.rmtree(full_path)

            os.makedirs(full_path)
            os.chown(full_path, stat.st_uid, stat.st_gid)
            os.chmod(full_path, stat.st_mode)
        #end for
    #end function

    # HELPERS

    def _prepare_environment(self, sysroot):
        env = {}

        entries_to_keep = {
            "DISPLAY",
            "SSH_CONNECTION",
            "SSH_CLIENT",
            "SSH_TTY",
            "USER",
            "TERM",
            "HOME",
        }

        for key in list(os.environ.keys()):
            if not (key.startswith("BOLT_") or key in entries_to_keep):
                continue
            env[key] = os.environ[key]

        # These cannot be overridden by user.
        env["BOLT_SYSROOT"] = sysroot
        env["BOLT_RELEASE"] = self._release
        env["BOLT_ARCH"]    = self._arch
        env["BOLT_LIBC"]    = self._libc

        return env
    #end function

    def _copy_qemu_to_sysroot(self, sysroot):
        qemu_user_static = ""

        prefix_map = collections.OrderedDict([
            ("aarch64",
                "qemu-aarch64-static"),
            ("arm",
                "qemu-arm-static"),
            ("mips64el",
                "qemu-mips64el-static"),
            ("mipsel",
                "qemu-mipsel-static"),
            ("powerpc64el",
                "qemu-ppc64le-static"),
            ("powerpc64le",
                "qemu-ppc64le-static"),
            ("ppc64le",
                "qemu-ppc64le-static"),
            ("powerpc",
                "qemu-ppc-static"),
            ("riscv64",
                "qemu-riscv64-static"),
            ("s390x",
                "qemu-s390x-static"),
        ])

        for prefix, qemu_binary in prefix_map.items():
            if self._arch.startswith(prefix):
                qemu_user_static = qemu_binary
                break

        if not qemu_user_static:
            return

        qemu_exe = Platform.find_executable(qemu_user_static)
        if not qemu_exe:
            raise ImageGenerator.Error(
                'could not find QEMU executable "{}".'.format(qemu_user_static)
            )

        target_dir = os.path.dirname(
            os.path.join(sysroot, qemu_exe.lstrip("/"))
        )
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        LOGGER.info('copying QEMU binary "{}".'.format(qemu_exe))
        shutil.copy2(qemu_exe, target_dir)
    #end function

    def _write_config_files(self, sysroot):
        conffile_list = [
            "/etc/opkg/arch.conf",
            "/etc/opkg/options.conf",
            "/etc/opkg/feeds.conf",
            "/etc/passwd",
            "/etc/group",
            "/etc/hosts",
        ]

        template_list = [
            self.OPKG_ARCH_TEMPLATE,
            self.OPKG_OPTIONS_TEMPLATE,
            self.OPKG_FEEDS_TEMPLATE,
            self.ETC_PASSWD,
            self.ETC_GROUP,
            self.ETC_HOSTS,
        ]

        for conffile, template in zip(conffile_list, template_list):
            with open(sysroot + conffile, "w+", encoding="utf-8") as f:
                f.write(template.format(**self.context))
    #end function

#end class
