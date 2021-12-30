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

To run the image:

.. code-block:: docker
 
  docker run -it --rm --device=/dev/serial/by-id/* --device-cgroup-rule='a *:* rwm' -p 8080:8000 -p 4853:4853 <username>/qkdserver:latest
  
'-it': Interactive mode

'--rm': remove container after closing

'-p <host port>:<container port>': publish ports for external progs to interact

--device adds the device to the container, but the syntax that is shown here is wrong. The idea is to search through the host's filesystem for all
attached devices and copy that over to the container's filesystem. Will update once the proper syntax is found. Currently the way around this is
to replace the asterisk with the explicit serial device id. The id can be found by using 'ls' or similar commands and listing out all devices in
'/dev/serial/by-id/', assuming the host system is linux based. The command for Windows systems is not known to us yet.

Alternatively, add device via ``tty`` with the filepath '/dev/ttyACM0'.

Makefile
--------

In the ``QKDServer`` directory, a ``Makefile`` has been included that runs several Docker commands. They are generally useful during testing. Calling ``make <command>`` in the terminal runs the respective command.

default:
  Runs the docker containers with the appropriate parameters
  
restart:
  Stops the container, waits for a bit, then restarts the container as per ``default``
  
exec:
  Grants access to a bourne shell terminal *within* the docker container. Allows you to manipulate the contents within the container directly. Only recommended if you know what you are     doing.
  
watchdog:
  Livestreams the watchdog log file. The watchdog program keeps logs of various QKDServe processes. Might be useful in troubleshooting.
  


