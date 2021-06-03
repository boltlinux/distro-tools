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

import copy
import hashlib
import logging
import os
import re
import subprocess
import sys

from lxml import etree

from boltlinux.error import PackagingError
from boltlinux.ffi.libarchive import ArchiveFileReader

from boltlinux.package.boltpack.packagedesc import PackageDescription
from boltlinux.package.boltpack.basepackage import BasePackage
from boltlinux.package.boltpack.platform import Platform


LOGGER = logging.getLogger(__name__)

class SourcePackage(BasePackage):

    BOLT_HELPERS_SEARCH_PATH = [
        os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                "..", "..", "..", "..", "helpers"
            )
        ),
        os.path.join(os.sep, "usr",   "share", "bolt-pack", "helpers"),
        os.path.join(os.sep, "tools", "share", "bolt-pack", "helpers")
    ]

    def __init__(self, xml_config, **kwargs):
        actual_build_for = kwargs.get("build_for", "target")

        if "machine" in kwargs:
            machine = kwargs["machine"]
        elif actual_build_for in ["tools", "cross-tools"]:
            machine = Platform.tools_machine()
        else:
            machine = Platform.target_machine()

        if isinstance(xml_config, etree._Element):
            source_node = xml_config
        elif isinstance(xml_config, str):
            source_node = etree.fromstring(xml_config)
        else:
            msg = "expected 'etree._Element' or 'str' but got '%s'" % \
                    xml_config.__class__.__name__
            raise ValueError(msg)
        #end if

        self.basedir = "."

        self.name = source_node.get("name")
        self.repo = source_node.get("repo")
        self.description = PackageDescription(
                source_node.xpath("description")[0])

        # This is the XML attribute.
        self.build_for = source_node.get("build-for")
        if self.build_for:
            self.build_for = [v.strip() for v in self.build_for.split(",")]

        # This is the XML attribute.
        self.supported_on = source_node.get("supported-on")
        if self.supported_on:
            self.supported_on = [
                v.strip() for v in self.supported_on.split(",")
            ]

        dep_node = source_node.find("requires")

        if dep_node is None:
            dep_node = "<requires></requires>"
        else:
            for pkg_node in list(dep_node.findall(".//package")):
                pkg_prefix = pkg_node.get(actual_build_for + "-prefix", None)

                if pkg_prefix is not None:
                    pkg_node.attrib["name"] = \
                        pkg_prefix + pkg_node.attrib["name"]
                elif actual_build_for == "tools":
                    pkg_node.attrib["name"] = \
                        "tools-" + pkg_node.attrib["name"]
                elif actual_build_for == "cross-tools":
                    dep_node.append(copy.deepcopy(pkg_node))
                    pkg_node.attrib["name"] = \
                        "tools-" + pkg_node.attrib["name"]

                # This is the XML attribute.
                supported_on = pkg_node.get("supported-on")
                if supported_on:
                    supported_on = [
                        v.strip() for v in supported_on.split(",")
                    ]

                # Mark nodes which are not supported on machine.
                if not BasePackage._is_supported_on(supported_on, machine):
                    pkg_node.attrib["ignore"] = "true"
            #end for
        #end if

        self.relations = {}
        self.relations["requires"] = BasePackage.DependencySpecification\
                .from_xml(dep_node)

        self.patches = []
        for patch_set in source_node.xpath("patches/patchset"):
            patch_set_subdir = patch_set.get("subdir", "")
            patch_set_strip  = patch_set.get("strip", "1")

            for file_node in patch_set.xpath("file"):
                self.patches.append([
                    file_node.get("src", ""),
                    file_node.get("subdir", patch_set_subdir),
                    file_node.get("strip", patch_set_strip)
                ])
            #end for
        #end for

        self.sources = []
        for file_node in source_node.xpath("sources/file"):
            self.sources.append([
                file_node.get("src", ""),
                file_node.get("subdir", ""),
                file_node.get("sha256sum", "")
            ])
        #end for

        self.version    = source_node.get("version", "")
        self.maintainer = source_node.get("maintainer", "") + " <" + \
                source_node.get("email", "") + ">"

        self.rules = {
            "prepare": "",
            "build":   "",
            "install": "",
        }

        for node in source_node.xpath("rules/*"):
            if node.tag not in ["prepare", "build", "install", "clean"]:
                continue
            self.rules[node.tag] = \
                    etree.tostring(node, method="text", encoding="unicode")
        #end for
    #end function

    def build_dependencies(self):
        return self.relations["requires"]

    def unpack(self, source_dir=".", source_cache=None):
        for source, subdir, sha256sum in self.sources:
            archive_file = self._locate_archive_file(
                source,
                sha256sum,
                source_cache=source_cache,
            )

            if not (archive_file and os.path.isfile(archive_file)):
                msg = "source archive for '%s' not found." % source
                raise PackagingError(msg)
            #end if

            source_dir_and_subdir = \
                    os.path.normpath(source_dir + os.sep + subdir)
            os.makedirs(source_dir_and_subdir, exist_ok=True)

            LOGGER.info("unpacking {}".format(archive_file))

            m = re.match(
                r"^(.*?\.debdiff)\.(?:gz|xz|bz2)$",
                os.path.basename(archive_file)
            )

            if m:
                with ArchiveFileReader(archive_file, raw=True) as archive:
                    try:
                        next(iter(archive))
                    except StopIteration:
                        continue

                    outfile = os.path.join(source_dir_and_subdir, m.group(1))

                    with open(outfile, "wb+") as f:
                        for chunk in iter(lambda: archive.read_data(4096),
                                b""):
                            f.write(chunk)
                    #end with
            else:
                with ArchiveFileReader(archive_file) as archive:
                    archive.unpack_to_disk(
                        base_dir=source_dir_and_subdir,
                        strip_components=1
                    )
        #end for
    #end function

    def patch(self, source_dir="."):
        patch = Platform.find_executable("patch")

        sys.stdout.flush()
        sys.stderr.flush()

        for patch_file, subdir, strip_components in self.patches:
            patch_name = os.path.basename(patch_file)

            if not os.path.isabs(patch_file):
                patch_file = os.path.normpath(
                    source_dir + os.sep + patch_file
                )
            #end if

            LOGGER.info("applying {}".format(patch_name))

            e_source_dir = source_dir if not subdir else source_dir + \
                    os.sep + subdir
            cmd = [patch, "-f", "-p%s" % strip_components, "-d", e_source_dir,
                    "-i", patch_file]
            try:
                subprocess.run(cmd, stderr=subprocess.STDOUT, check=True)
            except subprocess.CalledProcessError:
                raise PackagingError(
                    "couldn't apply patch \"{}\"".format(patch_name)
                )
        #end for
    #end function

    def run_action(self, action, env=None):
        if env is None:
            env = {}

        if action not in ["prepare", "build", "install", "clean"]:
            raise PackagingError("invalid package action '%s'." %
                    str(action))
        #end if

        if not self.rules[action].strip():
            return

        env    = self._update_env(env)
        script = self._load_helpers() + "\n" + self.rules[action]
        cmd    = ["/bin/sh", "-e", "-x", "-s"]

        sys.stdout.flush()
        sys.stderr.flush()

        try:
            subprocess.run(cmd, env=env, input=script.encode("utf-8"),
                    stderr=subprocess.STDOUT, check=True)
        except subprocess.CalledProcessError:
            msg = "failed to %s the source package." % action
            raise PackagingError(msg)
        #end try
    #end function

    # PRIVATE

    def _locate_archive_file(self, source, sha256sum, source_cache):
        archive_file = None

        candidate = os.path.join(
            self.basedir, self.name, self.version, source
        )

        if os.path.exists(candidate):
            LOGGER.info(
                "found local candidate '{}', computing checksum."
                .format(candidate)
            )
            h = hashlib.sha256()

            with open(candidate, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    h.update(chunk)
            #end with

            if sha256sum == h.hexdigest():
                LOGGER.info(
                    "using local candidate '{}'.".format(candidate)
                )
                archive_file = candidate
            else:
                LOGGER.error(
                    "checksum of '{}' didn't match, ignoring."
                    .format(candidate)
                )
            #end if
        #end if

        if not archive_file:
            archive_file = source_cache.find_and_retrieve(
                self.repo, self.name, self.version, source, sha256sum
            )
        #end if

        return archive_file
    #end function

    def _load_helpers(self):
        result = []

        for script in ["arch.sh", "python.sh"]:
            for path in SourcePackage.BOLT_HELPERS_SEARCH_PATH:
                abs_path = os.path.join(path, script)
                if not os.path.isfile(abs_path):
                    continue
                with open(abs_path, "r", encoding="utf-8") as fp:
                    result.append(fp.read())
                    break
            #end for
        #end for

        return "\n".join(result)
    #end function

    def _update_env(self, env):
        env.update(Platform.build_flags())

        num_parallel_jobs = str(int(Platform.num_cpus() * 1.5))
        env["BOLT_PARALLEL_JOBS"] = num_parallel_jobs

        for k, v in os.environ.items():
            if k in ["BOLT_WORK_DIR", "BOLT_SOURCE_DIR", "BOLT_BUILD_DIR",
                    "BOLT_INSTALL_DIR"]:
                continue
            if k.startswith("BOLT_") or k in ["PATH", "USER", "USERNAME"]:
                env[k] = v
        #end for

        if env.get("PATH") is None:
            env["PATH"] = "/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin"

        return env
    #end function

#end function
