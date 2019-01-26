#!/usr/bin/python

# Copyright: (c) 2018, Evan Van Dam <evandam92@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: conda

short_description: Manage packages with conda

version_added: "2.8"

description:
    - "Install, update, and remove packages through Anaconda, with multiple environments."

options:
    name:
        description:
            - This is the message to send to the sample module
        required: true
    new:
        description:
            - Control to demo if the result of this module is changed or not
        required: false

extends_documentation_fragment:
    - azure

author:
    - Evan Van Dam (@evandam)
'''

EXAMPLES = '''
# Pass in a message
- name: Test with a message
  my_new_test_module:
    name: hello world

# pass in a message and have changed true
- name: Test with a message and changed output
  my_new_test_module:
    name: hello world
    new: true

# fail the module
- name: Test failure of the module
  my_new_test_module:
    name: fail me
'''

RETURN = '''
original_message:
    description: The original name param that was passed in
    type: str
message:
    description: The output message that the sample module generates
'''

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


    def _split_name_version(self, package_spec, default_version=None):
        name = package_spec
        version = default_version
        if '=' in package_spec:
            name, version = package_spec.split('=')
        return {'name': name, 'version': version}

    def _get_conda(self, executable):
        conda_exe = None
        if executable:
            if os.path.isfile(executable):
                conda_exe = executable
            else:
                self.module.fail_json(msg='%s is not a valid conda executable' % executable)
        else:
            conda_exe = self.module.get_bin_path('conda')
            if not conda_exe:
                self.module.fail_json(
                    msg='conda could not be found in the PATH and an executable was not specified.'
                )
        return conda_exe

    def _run_conda(self, subcmd, *args, **kwargs):
        check_rc = kwargs.get('check_rc', True)
        cmd = [self.executable, subcmd]
        cmd += args
        cmd.append('--json')
        print('Running %s' % cmd)
        return self.module.run_command(cmd, check_rc=check_rc)

    def _get_config(self, key):
        """Get a conda config value"""
        rc, out, err = self._run_conda('config', '--show', key)
        return json.loads(out)[key]

    def _list_envs(self):
        rc, out, err = self._run_conda('env', 'list')
        return json.loads(out)['envs']

    def list_packages(self, env):
        rc, out, err = self._run_conda('list', *self.env_args)
        packages = json.loads(out)
        return [dict(name=p['name'], version=p['version']) for p in packages]

    def check_env(self, env):
        if env == 'base':
            return True

        envs = self._list_envs()
        if os.path.sep in env:
            return any(e == env for e in envs)
        else:
            return any(os.path.basename(e) == env for e in envs)
    
    def create_env(self, env):
        self._run_conda('create', '-y', *self.env_args)

    @staticmethod
    def _is_present(package, installed_packages, check_version=False):
        target_name = package['name']
        target_version = package['version']
        # Match only as specific as the version is specified. Ex only major/minor/patch level.
        if target_version:
            target_version = target_version.split('.')
        
        for installed_package in installed_packages:
            if target_name == installed_package['name']:
                if check_version and target_version:
                    installed_version = installed_package['version'].split('.')
                    if target_version == installed_version[:len(target_version)]:
                        return True
                return True
        return False

    def get_absent_packages(self, target_packages, installed_packages, check_version):
        """Return the list of packages that are not installed, or the wrong version"""
        return [p for p in target_packages
                if not self._is_present(p, installed_packages, check_version)]

    def get_present_packages(self, target_packages, installed_packages, check_version):
        """Return the list of packages that are installed and should be removed"""
        return [p for p in target_packages
                if self._is_present(p, installed_packages, check_version)]

    def install_packages(self, packages, env=None):
        pkg_strs = []
        for package in packages:
            if package['version']:
                pkg_strs.append('{name}={version}'.format(**package))
            else:
                pkg_strs.append(package['name'])
        self._run_conda('install', '-y', *pkg_strs + self.env_args)
    
    def remove_packages(self, packages):
        self._run_conda('remove', '-y', *packages + self.env_args)

    def update_packages(self, packages, env):
        self._run_conda('update', *packages + self.env_args)


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        name=dict(required=True, type='list'),
        state=dict(choices=['present', 'absent', 'latest'], default='present'),
        version=dict(required=False),
        executable=dict(required=False),
        channels=dict(required=False, type='list'),
        environment=dict(required=False),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    names = module.params['name']
    state = module.params['state']
    default_version = module.params['version']
    env = module.params['environment']

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

    target_packages = [conda._split_name_version(n, default_version) for n in names]
    installed_packages = conda.list_packages(env)

    # Install packages
    if state == 'present':
        absent_packages = conda.get_absent_packages(target_packages, installed_packages, check_version=True)
        if absent_packages:
            if not module.check_mode:
                conda.install_packages(absent_packages)
            result['changed'] = True
    # Remove packages
    elif state == 'absent':
        present_packages = conda.get_present_packages(target_packages, installed_packages, check_version=False)
        if present_packages:
            if not module.check_mode:
                conda.remove_packages(present_packages)
            result['changed'] = True
    # Install and/or update packages
    elif state == 'latest':
        # First check if any are installed in the first place
        absent_packages = conda.get_absent_packages(target_packages, installed_packages, check_version=False)
        if absent_packages:
            if not module.check_mode:
                conda.install_packages(absent_packages)
            result['changed'] = True
        # TODO: Dry run of update

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()