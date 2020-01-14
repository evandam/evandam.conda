#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2018, Evan Van Dam <evandam92@gmail.com>
# GNU General Public License v3.0+
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: conda
short_description: Manage conda environments and packages
description:  Create new conda environments, install, update, and remove packages.
version_added: "2.6"
author: Evan Van Dam (@evandam)
options:
  name:
    description:
      - A list, or string, of package(s).
      - Versions and builds can optionally be specified per package,
      - as package=version, or package=version=build.
    required: true
    type: list
  state:
    description:
      - The desired state of the package(s) specified.
    required: false
    default: "present"
    choices:
      - present
      - latest
      - absent
    type: string
  version:
    description:
      - The version of the package to install.
      - This is only applicable with a single package specified.
      - If a version is specified within the name, this value is overridden.
    required: false
    default: null
    type: string
  executable:
    description:
      - The path to the conda executable.
      - If this is not specified, the conda executable on the PATH will be used.
      - If a valid executable cannot be found, an error will be raised.
    required: false
    default: null
    type: string
  channels:
    description:
      - Additional channels to include when installing packages.
      - These channels are passed as "--channel" arguments to the conda command.
    required: false
    default: null
    type: list
  environment:
    description:
      - The conda environment to install/remove packages in.
      - If the environment does not exist and state is present or latest,
      - it will be created.
      - The environment will not be removed if state is absent.
      - If no environment is set, the base conda environment is used.
    required: false
    default: null
    type: string
'''

EXAMPLES = '''
- name: Install jupyter with a specific build
    conda:
      name: jupyter=1.0.0=py37_4

- name: Install a previous version of conda
    conda:
      name: conda
      version: 4.8.0

- name: Update conda to latest version
    conda:
      name: conda
      state: latest

- name: Remove numpy
    conda:
      name: numpy
      state: absent

- name: Install multiple packages
    conda:
      name:
        - pandas
        - sqlalchemy
      state: present

- name: Install doc8 from conda-forge
    conda:
      name: doc8
      channels: conda-forge

- name: Create an R virtual environment
    conda:
      name: r-base=3.5.1
      environment: /opt/R
      state: present

- name: Install some R packages in a venv
    conda:
       name:
        - r-dplyr=0.7
        - r-devtools=1.13
    environment: /opt/R
    state: latest
'''

RETURN = '''
actions:
  description: A list of actions taken by conda that modified packages.
  returned: changed
  type: string
  sample: |
    {
        "jupyter_install.actions": [
            "PREFIX",
            "UNLINK",
            "LINK",
            "FETCH"
        ]
    }
'''

__metaclass__ = type

import os
import json
from ansible.module_utils.basic import AnsibleModule


class Conda(object):
    def __init__(self, module, env):
        self.module = module
        self.executable = self._get_conda(module.params['executable'])
        if env:
            env_opt = '--prefix' if os.path.sep in env else '--name'
            self.env_args = [env_opt, env]
        else:
            self.env_args = []

    @staticmethod
    def split_name_version(package_spec, default_version=None):
        name = package_spec
        version = default_version
        build = None
        if '=' in package_spec:
            splits = package_spec.split('=')
            name, version = splits[:2]
            if len(splits) > 2:
                build = splits[2]
        return {'name': name, 'version': version, 'build': build}

    def _get_conda(self, executable):
        conda_exe = None
        if executable:
            if os.path.isfile(executable):
                conda_exe = executable
            else:
                self.module.fail_json(
                    msg='%s is not a valid conda executable' % executable)
        else:
            conda_exe = self.module.get_bin_path('conda')
            if not conda_exe:
                self.module.fail_json(
                    msg='conda not found in PATH, executable not specified.'
                )
        return conda_exe

    def _run_conda(self, subcmd, *args, **kwargs):
        check_rc = kwargs.pop('check_rc', True)
        cmd = [self.executable, subcmd] + list(args) + ['--json']
        rc, out, err = self.module.run_command(cmd)
        if check_rc and rc != 0:
            try:
                outobj = json.loads(out)
                self.module.fail_json(command=cmd,
                                      msg=outobj['error'],
                                      stdout=out,
                                      stderr=err,
                                      exception_name=outobj['exception_name'],
                                      exception_type=outobj['exception_type'])
            except ValueError:
                self.module.fail_json(command=cmd, msg='Unable to parse error',
                                      rc=rc, stdout=out, stderr=err)

        try:
            return rc, json.loads(out), err
        except ValueError:
            self.module.fail_json(command=cmd,
                                  msg='Failed to parse output of command!',
                                  stdout=out,
                                  stderr=err)

    def _run_package_cmd(self, subcmd, channels, *args, **kwargs):
        for channel in channels:
            args += ('--channel', channel)
        rc, out, err = self._run_conda(subcmd,
                                       '--quiet',
                                       '--yes',
                                       *args,
                                       **kwargs
                                       )
        return out['actions'] if 'actions' in out else []

    def list_envs(self):
        """List all conda environments"""
        rc, out, err = self._run_conda('env', 'list')
        return out['envs']

    def list_packages(self, env):
        """List all packages installed in the environment"""
        rc, out, err = self._run_conda('list', *self.env_args)
        return [dict(name=p['name'], version=p['version']) for p in out]

    def check_env(self, env):
        """Check if the environment exists"""
        if env == 'base':
            return True
        if os.sep in env:
            return os.path.isdir(env)
        envs = self.list_envs()
        return any(e == env for e in envs)

    def create_env(self, env):
        """Create a new conda environment"""
        return self._run_conda('create', '--yes', '--quiet', *self.env_args)

    @staticmethod
    def _is_present(package, installed_packages, check_version=False):
        """Check if the package is present in the list of installed packages.

        Compare versions of the target and installed package
        if check_version is set.
        """
        target_name = package['name']

        match = [p for p in installed_packages if p['name'] == target_name]
        if not match:
            return False
        installed_package = match[0]

        # Match only as specific as the version is specified.
        # Ex only major/minor/patch level.
        target_version = package['version']
        if target_version and check_version:
            target_version = target_version.split('.')
            installed_version = installed_package['version'].split('.')
            return target_version == installed_version[:len(target_version)]
        return True

    def get_absent_packages(self,
                            target_packages,
                            installed_packages,
                            check_version):
        """Return the list of packages that are not installed.

        If check_version is set, result will include
        packages with the wrong version.
        """
        return [p for p in target_packages
                if not self._is_present(p, installed_packages, check_version)]

    def get_present_packages(self,
                             target_packages,
                             installed_packages,
                             check_version):
        """Return the list of packages that are
           installed and should be removed"""
        return [p for p in target_packages
                if self._is_present(p, installed_packages, check_version)]

    def install_packages(self, packages, channels):
        """Install the packages"""
        pkg_strs = []
        for package in packages:
            pkg_str = package['name']
            if package['version']:
                pkg_str += '=' + package['version']
            if package['build']:
                pkg_str += '=' + package['build']
            pkg_strs.append(pkg_str)
        return self._run_package_cmd('install',
                                     channels,
                                     *pkg_strs + self.env_args)

    def remove_packages(self, packages, channels):
        """Remove the packages"""
        return self._run_package_cmd('remove',
                                     channels,
                                     *packages + self.env_args)

    def update_packages(self, packages, channels, dry_run=False):
        """Update the packages.

        If dry_run is set, no actions are taken.
        """
        args = packages + self.env_args
        if dry_run:
            args.append('--dry-run')
        return self._run_package_cmd('update', channels, *args)


def run_module():
    """Run the Ansible module"""
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        name=dict(required=True, type='list'),
        state=dict(choices=['present', 'absent', 'latest'], default='present'),
        version=dict(required=False),
        executable=dict(required=False),
        channels=dict(required=False, type='list', default=[]),
        environment=dict(required=False),
    )

    # seed the result dict in the object
    result = dict(
        changed=False,
        actions=[],
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    names = module.params['name']
    state = module.params['state']
    default_version = module.params['version']
    env = module.params['environment']
    channels = module.params['channels']

    conda = Conda(module, env)

    if env:
        env_exists = conda.check_env(env)
        if not env_exists:
            if state == 'absent':
                result['msg'] = '%s is already absent' % env
                module.exit_json(**result)
            else:
                conda.create_env(env)
                result['changed'] = True

    target_packages = [conda.split_name_version(
        n, default_version) for n in names]
    installed_packages = conda.list_packages(env)

    # Install packages
    if state == 'present':
        absent_packages = conda.get_absent_packages(
            target_packages, installed_packages,
            check_version=True)
        if absent_packages:
            if not module.check_mode:
                actions = conda.install_packages(absent_packages, channels)
                result['actions'] += actions
            result['changed'] = True
    # Remove packages
    elif state == 'absent':
        present_packages = conda.get_present_packages(
            target_packages, installed_packages,
            check_version=False)
        if present_packages:
            names = [p['name'] for p in present_packages]
            if not module.check_mode:
                actions = conda.remove_packages(names, channels)
                result['actions'] += actions
            result['changed'] = True
    # Install and/or update packages
    elif state == 'latest':
        # Find missing packages first
        absent_packages = conda.get_absent_packages(target_packages,
                                                    installed_packages,
                                                    check_version=False)
        present_packages = conda.get_present_packages(target_packages,
                                                      installed_packages,
                                                      check_version=False)
        if absent_packages:
            if not module.check_mode:
                actions = conda.install_packages(absent_packages, channels)
                result['actions'] += actions
            result['changed'] = True

        if present_packages:
            # Check what needs to be updated with a dry run
            names = [p['name'] for p in present_packages]
            dry_actions = conda.update_packages(names, channels, dry_run=True)
            if dry_actions:
                if not module.check_mode:
                    actions = conda.update_packages(names, channels)
                    result['actions'] += actions
                result['changed'] = True

    module.exit_json(**result)


def _main():
    run_module()


if __name__ == '__main__':
    _main()
