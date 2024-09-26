# syntax=docker/dockerfile:experimental
# Above line is necessary to activate Docker Buildkit back end

# Build the container with the following command in the QKDServer directory:
#   docker build --tag <username>/qkdserver:<tag> .
# Adding --no-cache option is useful if you wish to rebuild images from scratch eg. to force updates to certain dependencies.
#   docker build --no-cache -t <username>/qkdserver:<tag> .
# Run the container with:
#   docker run -it --rm --device=/dev/serial/by-id/* --device-cgroup-rule='a *:* rwm'  <username>/qkdserver:latest
# or if you regulary change devices use the following command:
#   docker run -it --rm -v /dev:/dev --device-cgroup-rule='a *:* rwm'  mathias/qkdserver:latest
# This mounts the dev folder and keeps it in sync with the host sytem.

# Small footnote for apk del if nested in different RUN context
# https://stackoverflow.com/questions/46221063/what-is-build-deps-for-apk-add-virtual-command#comment86443214_46221063

# python:3.9.17-slim image has some incompatibility issues with docker-compose
FROM python:3.9.16-slim
LABEL Author="Mathias Seidler"

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

# Install necessary packages
# Consider using Docker v23+ to obtain support for BuildKit,
# which will cache build stages
RUN \
    # --mount=type=cache,target=/var/cache/apt \
    apt update \
    && apt install -y \
# For compiling, includes gcc
        build-essential \
# For pfind.c compilation
        libfftw3-dev \
        git \
        vim \
# For pkill
        procps \
    && pip install -U pip setuptools wheel \
    && pip install git+https://github.com/s-fifteen-instruments/pyS15.git@beb98508a05bfc8d1b5382f7a45ffd66d1fc6817 \
# Add fpfind + freqcd routines
    && pip install git+https://github.com/s-fifteen-instruments/fpfind.git@v1.2024.4 \
# Fix missing pyximport dependency in pyS15
    && pip install Cython

# Install qcrypto
RUN \
    mkdir -p ${HOME}/code \
    && cd ${HOME}/code \
    && git clone --depth 1 https://github.com/s-fifteen-instruments/qcrypto.git \
# Compile qcrypto and allow increased rates for high-count side
    && cd ${HOME}/code/qcrypto/remotecrypto \
    && make allow-increased-rates \
    && sed -i "s/return -emsg(63)/emsg(63)/" transferd.c \
    && make CC=${CC} \
    && cd ../errorcorrection \
    && make CC=${CC} \
    && cd ../timestamp7 \
    && make CC=${CC}

# Install the python qcrypto wrapper
RUN \
    cd ${HOME}/code \
    && git clone --branch master --depth 1 https://github.com/s-fifteen-instruments/QKDServer.git \
    && cd ${HOME}/code/QKDServer \
    && pip install -e .\
    && cd ${HOME}/code/QKDServer/Settings_WebClient \
    && pip install -r requirements.txt \
    && ln -s ${HOME}/code/qcrypto bin

RUN \
    pip install ipython gunicorn

ENTRYPOINT ["/root/code/QKDServer/entrypoint.sh"]
