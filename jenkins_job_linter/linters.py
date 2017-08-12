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
from enum import Enum
from typing import Any, Dict, Optional, Set, Tuple  # noqa

from stevedore.extension import ExtensionManager

from jenkins_job_linter.models import LintContext


class LintResult(Enum):
    """
    The result of a linting check (i.e. pass/fail/skip).

    The value of each element represents whether or not the result should be
    considered a success when reducing down to just pass/fail.
    """

    PASS = True
    FAIL = False
    SKIP = True


class Linter:
    """A super-class capturing the common linting pattern."""

    default_config = {}  # type: Dict[str, Any]

    def __init__(self, ctx: LintContext) -> None:
        """
        Create an instance of a Linter.

        :param ctx:
            A LintContext which the linter should operate against.
        """
        self._ctx = ctx

    def actual_check(self) -> Tuple[LintResult, Optional[str]]:
        """Perform the actual linting check."""
        raise NotImplementedError  # pragma: nocover

    def check(self) -> Tuple[LintResult, Optional[str]]:
        """Check the root tag of the object and call actual_check."""
        if self._ctx.tree.getroot().tag != self.root_tag:
            return LintResult.SKIP, None
        return self.actual_check()

    @property
    def description(self) -> str:
        """Output-friendly description of what this Linter does."""
        raise NotImplementedError  # pragma: nocover

    @property
    def root_tag(self) -> str:
        """XML tag name that this linter operates against."""
        raise NotImplementedError  # pragma: nocover


class JobLinter(Linter):
    """A Linter that should operate against Jenkins job objects."""

    root_tag = 'project'


class EnsureTimestamps(JobLinter):
    """Ensure that a job is configured with timestamp output."""

    description = 'checking for timestamps'
    _xpath = (
        './buildWrappers/hudson.plugins.timestamper.TimestamperBuildWrapper')

    def actual_check(self) -> Tuple[LintResult, Optional[str]]:
        """Check that the TimestamperBuildWrapper element is present."""
        result = LintResult.FAIL
        if self._ctx.tree.find(self._xpath) is not None:
            result = LintResult.PASS
        return result, None


class ShellBuilderLinter(JobLinter):
    """A linter that operates on the shell builders of jobs."""

    _xpath = './builders/hudson.tasks.Shell/command'

    def actual_check(self) -> Tuple[LintResult, Optional[str]]:
        """
        Iterate over the shell builders in a job calling self.shell_check.

        If any of the self.shell_check calls fail, this returns that result
        immediately.  (Note also that it assumes that there will only be text
        to return on that single failure.)
        """
        shell_builders = self._ctx.tree.findall(self._xpath)
        if not shell_builders:
            return LintResult.SKIP, None
        for shell_builder in shell_builders:
            shell_script = shell_builder.text
            result, text = self.shell_check(shell_script)
            if result == LintResult.FAIL:
                return result, text
        return LintResult.PASS, None

    def shell_check(self, shell_script: Optional[str]) -> Tuple[LintResult,
                                                                Optional[str]]:
        """Perform a check for a specific shell builder."""
        raise NotImplementedError  # pragma: nocover


class CheckForEmptyShell(ShellBuilderLinter):
    """Ensure that shell builders in a job have some content."""

    description = 'checking shell builder shell scripts are not empty'

    def shell_check(self, shell_script: Optional[str]) -> Tuple[LintResult,
                                                                None]:
        """Check that a shell script is not empty."""
        if shell_script is None:
            return LintResult.FAIL, None
        return LintResult.PASS, None


class CheckShebang(ShellBuilderLinter):
    """
    Ensure that shell builders in a job have an appropriate shebang.

    Specifically, ensure that those with a shell shebang call the shell with
    -eux.

    Shell builders with no shebang or a non-shell shebang are skipped.
    """

    default_config = {
        'allow_default_shebang': True,
        'required_shell_options': 'eux',
    }

    description = 'checking shebang of shell builders'

    def _check_shell_shebang(self, required_shell_options_set: Set[str],
                             first_line: str) -> bool:
        """Given a shell shebang and required options, check it."""
        line_parts = first_line.split(' ')
        if len(line_parts) < 2:
            return False
        shell_options_match = re.match(r'-([a-z]+)', line_parts[1])
        if shell_options_match is None:
            return False
        if not required_shell_options_set.issubset(
                set(shell_options_match.group(1))):
            return False
        return True

    def _handle_jenkins_default(self) -> Tuple[LintResult, Optional[str]]:
        """Return the appropriate result for a Jenkins-default shebang."""
        if self._ctx.config.getboolean('allow_default_shebang'):
            return LintResult.SKIP, None
        else:
            return LintResult.FAIL, "Shebang is Jenkins' default"

    def shell_check(self, shell_script: Optional[str]) -> Tuple[LintResult,
                                                                Optional[str]]:
        """Check a shell script for an appropriate shebang."""
        if shell_script is None:
            return LintResult.SKIP, None
        first_line = shell_script.splitlines()[0]
        if not first_line.startswith('#!'):
            # This will use Jenkins' default
            return self._handle_jenkins_default()
        if re.match(r'#!/bin/[a-z]*sh', first_line) is None:
            # This has a non-shell shebang
            return LintResult.SKIP, None
        required_shell_options_set = set(
            self._ctx.config['required_shell_options'])
        if not required_shell_options_set:
            return LintResult.PASS, None
        if not self._check_shell_shebang(required_shell_options_set,
                                         first_line):
            return LintResult.FAIL, 'Shebang is {}'.format(first_line)
        return LintResult.PASS, None


extension_manager = ExtensionManager(namespace='jjl.linters')
LINTERS = {ext.name: ext.plugin for ext in extension_manager}
