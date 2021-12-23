QKDServer is dockerized with the image 'python:3.9-alpine'.

To build the image:

.. code-block:: docker

  docker build --tag <username>/qkdserver:<tag> .\

Warning: Building the image takes approximately 26 minutes. This is due to some known issues with python wheels and 
alpine-linux https://pythonspeed.com/articles/alpine-docker-python/ . The main time sink comes from building numpy 
from source. There may be a future update to move QKDServer to other python images, maybe Ubuntu or Debian.

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
