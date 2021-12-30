====================
The Docker Container
====================

QKDServer is dockerized with the image 'python:3.9-alpine'. It runs python 3.9 on an Alpine Linux kernel.

Building
--------

To build the image, run the following code inside the QKDServer directory:

.. code-block:: docker

  docker build --tag <username>/qkdserver:<tag> .
  
The period at the end tells docker to build the image from the Dockerfile in the current directory (QKDServer). The --tag option and the stuff the follows
attaches a name to the docker image for easier identification later.

Warning: Building the image takes approximately 26 minutes. This is due to some known issues with python wheels and 
alpine-linux https://pythonspeed.com/articles/alpine-docker-python/ . The main time sink comes from building numpy 
from source. There may be a future update to move QKDServer to other python images, maybe Ubuntu or Debian.

Running
-------

To run the image, enter ``make default`` in the terminal. This runs the docker command with a bunch of options:

.. code-block:: docker
 
  docker run --volume /home/alice/code/QKDServer/S15qkd:/root/code/QKDserver/S15qkd --volume /home/alice/code/QKDServer/entrypoint.sh:/root/entrypoint.sh --name qkd --rm -dit --entrypoint="/root/entrypoint.sh" --device=/dev/ttyACM0 --device-cgroup-rule='a *:* rwm' -p 8080:8000 -p 4853:4853 alice/qkdserver

Some of the options are broken down below in brief. For the specifics, please refer to official docker documentation (insert link).

'-dit': 
  '-it' for interactive mode, '-d' to run the container in detached/background mode.

'--rm': 
  remove container when it is stopped.

'-p <published port>:<container port>': 
  publish ports for external programs to interact with.

--device:
  adds the device to the container filesystem.

--volume:
  create docker volumes. Data is usually lost when a container is removed. Volumes allow data to persist outside of containers. This may be useful for perserving certain QKDServer settings.

Makefile
--------

In the ``QKDServer`` directory, a ``Makefile`` has been included that runs several Docker commands. They are generally useful during testing. Calling ``make <command>`` in the terminal runs the respective command.

default:
  Runs the docker containers with the appropriate parameters
  
restart:
  Stops the container, waits for a bit, then restarts the container as per ``default``
  
exec:
  Grants access to a bourne shell terminal *within* the docker container. Allows you to manipulate the contents within the container directly. Only recommended if you know what you are doing.
  
watchdog:
  Livestreams the watchdog log file. The watchdog program keeps logs of various QKDServe processes. Might be useful in troubleshooting.
  


