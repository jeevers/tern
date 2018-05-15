'''
Copyright (c) 2017 VMware, Inc. All Rights Reserved.
SPDX-License-Identifier: BSD-2-Clause
'''
import grp
# import io
import logging
import os
import pwd
import subprocess
import tarfile
import time

import docker

from .constants import container
from .constants import logger_name
from .constants import temp_folder

from .general import pushd

DOCKER_CLIENT = docker.from_env()

'''
Container operations
'''
# docker commands
check_images = ['docker', 'images']
pull = ['docker', 'pull']
build = ['docker', 'build']
run = ['docker', 'run', '-td']
check_running = ['docker', 'ps', '-a']
copy = ['docker', 'cp']
execute = ['docker', 'exec']
inspect = ['docker', 'inspect']
stop = ['docker', 'stop']
remove = ['docker', 'rm']
delete = ['docker', 'rmi', '-f']
save = ['docker', 'save']

# docker container names
# TODO: randomly generated image and container names
# image = const.image
tag = str(int(time.time()))

# global logger
logger = logging.getLogger(logger_name)


def docker_command(command, *extra):
    '''Invoke docker command. If the command fails nothing is returned
    If it passes then the result is returned'''
    full_cmd = []
    sudo = True
    try:
        members = grp.getgrnam('docker').gr_mem
        if pwd.getpwuid(os.getuid()).pw_name in members:
            sudo = False
    except KeyError:
        pass
    if sudo:
        full_cmd.append('sudo')
    full_cmd.extend(command)
    for arg in extra:
        full_cmd.append(arg)
    # invoke
    logger.debug("Running command: %s", ' '.join(full_cmd))
    pipes = subprocess.Popen(full_cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    result, error = pipes.communicate()
    if error:
        raise subprocess.CalledProcessError(1, cmd=full_cmd, output=error)
    else:
        return result


def check_container():
    '''Check if a container exists'''
    is_container = False
    try:
        container_id = DOCKER_CLIENT.containers.get(container)
        logger.debug("Found container %s with ID %s",
                     container,
                     container_id)
        is_container = True
    except docker.errors.NotFound:
        logger.debug("Container %s not found", container)
        is_container = False
    return is_container


def check_image(image_tag_string):
    '''Check if image exists'''
    is_image = False
    try:
        image_id = DOCKER_CLIENT.images.get(image_tag_string)
        logger.debug("Found image %s with ID %s",
                     image_tag_string,
                     image_id)
        is_image = True
    except docker.errors.NotFound:
        logger.debug("Image %s not found", image_tag_string)
        is_image = False
    return is_image


def pull_image(image_tag_string):
    '''Try to pull an image from Dockerhub'''
    is_there = False
    try:
        image = DOCKER_CLIENT.images.pull(image_tag_string)
        print(image.attrs['Id'])
        is_there = True
    except docker.errors.ImageNotFound as error:
        print(error)
        is_there = False
    return is_there


def build_container(dockerfile, image_tag_string):
    '''Invoke docker command to build a docker image from the dockerfile
    It is assumed that docker is installed and the docker daemon is running'''
    path = os.path.dirname(dockerfile)
    if not check_image(image_tag_string):
        with pushd(path):
            try:
                DOCKER_CLIENT.images.build(tag=image_tag_string,
                                           path=os.path.basename(dockerfile),
                                           rm=True)
            except docker.errors.BuildError as error:
                raise docker.errors.BuildError(error)


def start_container(image_tag_string):
    '''Invoke docker command to start a container
    If one already exists then stop it
    Use this only in the beginning of running commands within a container
    Assumptions: Docker is installed and the docker daemon is running
    There is no other running container from the given image'''
    if check_container():
        c = DOCKER_CLIENT.container.get(container)
        c.stop()
        c.remove()
    DOCKER_CLIENT.containers.run(name=container,
                                 tag=image_tag_string,
                                 detach=True)


def remove_container():
    '''Remove a running container'''
    if check_container():
        c = DOCKER_CLIENT.container.get(container)
        c.stop()
        c.remove()


def remove_image(image_tag_string):
    '''Remove an image'''
    if check_image(image_tag_string):
        DOCKER_CLIENT.images.remove(image_tag_string)


def get_image_id(image_tag_string):
    '''Get the image ID by inspecting the image'''
    image = DOCKER_CLIENT.images.get(image_tag_string)
    return image.split(':').pop()


def extract_image_metadata(image_tag_string):
    '''Run docker save and extract the files in a temporary directory'''
    temp_path = os.path.abspath(temp_folder)
    tar_path = os.path.join(temp_path,
                            "{}.tar".format(image_tag_string.replace(":", "_")))
    image = DOCKER_CLIENT.image.get(image_tag_string)
    with open(tar_path, 'wb') as f:
        for chunk in image.save(chunk_size=None):
            # chunk_size=None streams the image
            f.write(chunk)
    with tarfile.open(tar_path) as tar:
        tar.extractall(temp_path)
    if not os.path.exists(temp_path):
        raise IOError('Unable to untar Docker image')
    # clean up the extracted tarfile
    os.remove(tar_path)
