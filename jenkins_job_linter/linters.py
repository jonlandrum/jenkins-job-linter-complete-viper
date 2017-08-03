# Copyright (C) 2017  Daniel Watkins <daniel@daniel-watkins.co.uk>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""A collection of linters for Jenkins job XML."""
import re
from configparser import ConfigParser
from typing import Optional, Tuple
from xml.etree import ElementTree

from stevedore.extension import ExtensionManager


class Linter(object):
    """A super-class capturing the common linting pattern."""

    def __init__(self, tree: ElementTree.ElementTree,
                 config: ConfigParser) -> None:
        """
        Create an instance of a Linter.

        :param tree:
            A Jenkins job XML file parsed in to an ElementTree.
        :param config:
            The configuration for this linting run.
        """
        self._tree = tree
        self._config = config

    def actual_check(self) -> Tuple[Optional[bool], Optional[str]]:
        """Perform the actual linting check."""
        raise NotImplementedError  # pragma: nocover

    @property
    def description(self) -> str:
        """Output-friendly description of what this Linter does."""
        raise NotImplementedError  # pragma: nocover

    def check(self) -> bool:
        """Wrap actual_check in nice output."""
        print(' ... {}:'.format(self.description), end='')
        result, text = self.actual_check()
        if result is None:
            print(' N/A')
            result = True
        else:
            print(' OK' if result else ' FAILURE')
        if text:
            print('     {}'.format(text))
        return result


class EnsureTimestamps(Linter):
    """Ensure that a job is configured with timestamp output."""

    description = 'checking for timestamps'
    _xpath = (
        './buildWrappers/hudson.plugins.timestamper.TimestamperBuildWrapper')

    def actual_check(self) -> Tuple[bool, Optional[str]]:
        """Check that the TimestamperBuildWrapper element is present."""
        return self._tree.find(self._xpath) is not None, None


class CheckShebang(Linter):
    """
    Ensure that shell builders in a job have an appropriate shebang.

    Specifically, ensure that those with a shell shebang call the shell with
    -eux.

    Shell builders with no shebang or a non-shell shebang are skipped.
    """

    description = 'checking shebang of shell builders'

    def actual_check(self) -> Tuple[Optional[bool], Optional[str]]:
        """Check shell builders for an appropriate shebang."""
        shell_parts = self._tree.findall(
            './builders/hudson.tasks.Shell/command')
        if not shell_parts:
            return None, None
        for shell_part in shell_parts:
            script = shell_part.text
            if script is None:
                continue
            first_line = script.splitlines()[0]
            if not first_line.startswith('#!'):
                # This will use Jenkins' default
                continue
            if re.match(r'#!/bin/[a-z]*sh', first_line) is None:
                # This has a non-shell shebang
                continue
            line_parts = first_line.split(' ')
            if (len(line_parts) < 2
                    or re.match(r'-[eux]{3}', line_parts[1]) is None):
                return False, 'Shebang is {}'.format(first_line)
        return True, None


extension_manager = ExtensionManager(namespace='jjl.linters')
LINTERS = [ext.plugin for ext in extension_manager]
