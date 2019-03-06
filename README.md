evandam.conda
=========

[![Build Status](https://travis-ci.org/evandam/evandam.conda.svg?branch=master)](https://travis-ci.org/evandam/evandam.conda)

Manage your conda environment(s) with Ansible. Create new conda environments, install, update, and remove packages.

Similar to the pip module, this supports passing a list into the `name` field. This results in fast and efficient use of running conda commands.

The role is designed to make the `conda` module available for use in subsequent tasks.

Requirements
------------

* conda (tested on `4.5.0` and higher)

Example Playbook
----------------

```yaml
---
- name: Test evandam.conda
  hosts: all
  roles:
    - role: evandam.conda
  tasks:
    - name: Update conda
      conda:
        name: conda
        state: latest
        executable: /opt/conda/bin/conda
    - name: Create a conda environment
      conda:
        name: python
        version: 3.7
        environment: python3
        state: present
    - name: Install some packages in the environment
      conda:
        name:
          - pandas
          - numpy
          - tensorflow
        environment: python3
    - name: Install R, using a versioned name
      conda:
        name: r-base=3.5.0
```

License
-------

BSD
