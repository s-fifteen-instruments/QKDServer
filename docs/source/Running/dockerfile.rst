==========
Dockerfile
==========

Here, we dive into the specifics of the dockerfile. Intimate knowledge of its contents is not required to run QKDServer, but may prove useful in troubleshooting.

.. code-block:: docker

  FROM python:3.9-alpine
  
QKDServer's container builds upon the python-alpine image.

.. code-block:: docker

  LABEL Author="Mathias Seidler"
  ARG CC=gcc
  ENV HOME=/root
  
Setting some variables: gcc compiler and /root as home directory. Next we install the necessary packages with the RUN command.
 
.. code-block:: docker
 
  RUN \
      # --mount=type=ssh \
      apk update --no-cache \
      && apk add --no-cache --virtual qkdserver-base \
          build-base \
          gcc \
          clang \
          llvm-dev \
          wget \
          git \
          subversion\
          openssh \
      && apk add --virtual qkdserver-run \
          fftw-dev \
          make \
          vim \
          bash \
          grep \
          coreutils \
          linux-headers \
          libstdc++ \
      && pip install --upgrade pip setuptools wheel \
      && pip install git+https://github.com/s-fifteen-instruments/pyS15.git
    
RUN runs the commands in the linux shell. apk is the alpine package manager, like zypper for openSUSE, apt-get on Ubuntu and so on.

**--no-cache** option to not cache the index. This saves space on the container.

**--virtual** Creates a virtual package of all the packages that follow. Eg. ``build-base``, ``gcc``, ``clang``... are all packaged into ``qkdserver-base``. Later, 
we delete ``qkdserver-base``, which deletes all of these at once since we only need them for the initial compilation stage. For now, the next step is
to install qcrypto, the code that allows intercommunication between S15's devices.

.. code-block:: docker
 
  RUN \
    # --mount=type=ssh \
    mkdir -p ${HOME}/code \
    && cd ${HOME}/code \
    && git clone https://github.com/s-fifteen-instruments/qcrypto.git qcrypto \
    && cd ${HOME}/code/qcrypto/remotecrypto \
    && make CC=${CC} \
    && cd ../errorcorrection \
    && make CC=${CC} \
    && cd ../remotecrypto \
    && unlink errcd \
    && ln -s ../ec2/ecd2 errcd \
    && cd .. \
    && svn checkout https://qolah.org/repos/readevents4 \
    && cd readevents4 \
    && make CC=${CC} \
    && cd ../remotecrypto \
    && unlink readevents \
    && ln -s ../readevents4/readevents4a ./readevents


We pull from two repositories, one is qcrypto on S15's github, the other is a subversion repo that belongs to CQT's quantum optics group (ie. Christian Kurtsiefer).
'readevents4a' is pulled from subversion to interface with the newer timestamp cards.
 
Of note, we call ``make`` thrice. This compiles the code for ``qcrypto``, ``errorcorrection`` and ``readevents4a``.
 
Finally, with 'ln -s...', we create symbolic links in remotecrypto folder to programs in other subfolders. Remotecrypto will serve as the central operating folder. You
may think of symbolic links as shortcuts to the actual files. Unlink deletes old links that were there by default, and 'ln -s' replaces these with the updated ones.
 
.. code-block:: docker

  RUN \
    # --mount=type=ssh \
    cd ${HOME}/code \ 
    && git clone -b readevents4 https://github.com/s-fifteen-instruments/QKDServer.git QKDserver \
    && cd ${HOME}/code/QKDserver \
    && pip install -e .\
    && cd ${HOME}/code/QKDserver/Settings_WebClient \
    && pip install -r requirements.txt \
    && ln -s ${HOME}/code/qcrypto bin
    
We pull and install the QKDServer github repo. QKDServer is the python qcrypto wrapper.
 
.. code-block:: docker
 
  RUN \
    # --mount=type=ssh \
    pip install ipython gunicorn
    
Gunicorn for server functions.

.. code-block:: docker

  RUN \
    # --mount=type=ssh \
    apk del --no-cache qkdserver-base
    
Delete packages which were only needed to compile the applications. This reduces the docker container size.
 
.. code-block:: docker

  WORKDIR ${HOME}/code/QKDserver/Settings_WebClient
  CMD [ "gunicorn", "--threads=1", "-b 0.0.0.0:8000", "index:server"]
  
Finally, we set an entrypoint into the container.
