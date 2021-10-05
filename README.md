
evandam.conda
=========


Manage your conda environment(s) with Ansible. Create new conda environments, install, update, and remove packages.

Similar to the pip module, this supports passing a list into the `name` field. This results in fast and efficient use of running conda commands.

The role is designed to make the `conda` module available for use in subsequent tasks.

Requirements
------------

* conda (tested on `4.5.0` and higher)

Basic Example Playbook
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

Example with var-looping and Mamba speed-up
----------------
Let's assume we have a yaml-dict/list in a file (./software/conda.yaml), defining all our environments and their packages staged for installation like this:
```yaml
Quality_control:
 - afterqc
 - multiqc
 - trimmomatic
Assembly:
 - spades
 - megahit
```
This can be beneficial for several reasons. Firstly, you can separate different deployments and software setups in discrete git branches referencing only this file. Secondly, if you have collaborators that are not git savvy, they only have to worry about editing this specific file in order to update any software deployments they need, and it can be done easily f.ex by editing this raw file in the browser. Thirdly, using a vars-loop, it simplifies our code a lot. As seen in the next example.

The following playbook consists of 3 discrete parts (and assumes anaconda is already installed)
1. It parses the previously mentioned conda.yaml so our target environments and packages are readily defined.
2. Installs Mamba in the base environment (see bottom for explanation).
3. Loops through our "envs" var creating every defined environment and installs its packages using Mamba 
```yaml
---
- name: Install Conda envs and packages
  hosts: my_remote_machine
  roles:
    - role: evandam.conda
  remote_user: admin
  become: yes
  tasks:
    - include_vars:
      file: ./software/conda.yaml
      name: envs
    - name: Install Mamba in base env using standard conda
      become_user: user
      conda:
	    environment: base
	    name: mamba
	    state: latest
	    channels:
	      - conda-forge
	    executable: /opt/miniconda3/bin/conda
    - name: Create Conda environments and install packages using Mamba instead of default Conda
      become_user: user
      conda:
        environment: "{{item.key}}"
        name: "{{item.value}}"
        state: latest
        channels:
          - bioconda
          - conda-forge
          - agbiome
          - hcc
          - nickp60
          - defaults
        executable: /opt/miniconda3/bin/mamba
      loop: "{{  envs  |  dict2items  }}"
```
### Notes on Mamba

One of the downsides of using Anaconda as a package manager is the bloated channels. For certain packages, especially from conda-forge, the environment solver can use hours of computation to figure out dependencies before any installation even starts. The solution: Mamba/Micromamba. Mamba wraps the executable conda, implementing the solver in C++, making it blazingly fast (notice the executable: directive change from conda to mamba in the last task). As a real world example, with some 30+ environments for a student course deployment, this reduced deployment time from 2,5 hours to 15 minutes!

License
-------

BSD
