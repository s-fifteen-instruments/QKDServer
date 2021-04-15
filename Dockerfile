# syntax=docker/dockerfile:experimental
# Above line is necessary to activate Docker Buildkit back end

# Build the container with:
#   docker build --tag <username>/qkdserver
# Then run with:
#   docker run -it --rm 
#          -v /dev:/dev1 \
#          --device-cgroup-rule 'a *:* rwm'
#          <username>/qkdserver:latest



FROM python:3.9-alpine
LABEL Author="Mathias Seidler"
LABEL MAINTAINER="Cyrus Proctor cyrusproctor@gmail.com"

ARG CC=gcc
ENV HOME=/root

# Ensure basic packages are installed for building and running qsim
# Add in a new group and user
# Inject Github's public key into root's known host list
# Pull in ssh-agent from host to clone private repositories
# Assumes an unlocked SSH key paired with Github is available for use
# Clone private repositories
# Minor sed fixes for testing
# Build qcrypto and qsim

# Install necessary system apps
RUN --mount=type=ssh \
    apk update --no-cache \
    && apk add --no-cache --virtual qkdserver-base \
        build-base \
        gcc \
        clang \
        llvm-dev \
        wget \
        git \
        openssh \
    && apk add --virtual qkdserver-run \
        fftw-dev \
        make \
        vim \
        bash \
        grep \
        coreutils \
        linux-headers \
    && pip install --upgrade pip setuptools wheel \
    && pip install git+https://github.com/s-fifteen-instruments/pyS15.git

# Install qcrypto
RUN --mount=type=ssh \
    mkdir -p ${HOME}/code \
    && cd ${HOME}/code \
    && git clone https://github.com/s-fifteen-instruments/qcrypto.git qcrypto \
    && cd ${HOME}/code/qcrypto/remotecrypto \
    && make CC=${CC} \
    && cd ../errorcorrection \
    && make CC=${CC} 
    
# Install the python qcrypto wrapper
RUN --mount=type=ssh \
    cd ${HOME}/code \ 
    && git clone https://github.com/s-fifteen-instruments/QKDServer.git QKDserver \
    && cd ${HOME}/code/QKDserver \
    && pip install -e .\
    && cd ${HOME}/code/QKDserver/Settings_WebClient \
    && pip install -r requirements.txt 

# Delete apps which were only needed to compile the applications. This reduces the docker container size.
RUN --mount=type=ssh apk del --no-cache qkdserver-base

# Set an entry point into the image
WORKDIR ${HOME}/code
ENTRYPOINT ["/bin/bash"] 
