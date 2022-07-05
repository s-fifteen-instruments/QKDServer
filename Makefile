serial_devs = $(shell for dev in /dev/serial/by-id/* ;\
	    do echo -n "--device $$dev:$$dev " ;\
	    done)

all: stop default

build_fresh:
	docker build --no-cache -t s-fifteen/qkdserver:qkd .
build:
	docker build -t s-fifteen/qkdserver:qkd .

restart: stop default log

log:
	docker logs -f qkd
exec:
	docker exec -it qkd /bin/sh

stop:
	-docker stop qkd
	sleep 7

default:
	docker run \
		--volume /home/s-fifteen/code/QKDServer/S15qkd:/root/code/QKDserver/S15qkd \
		--volume /home/s-fifteen/code/QKDServer/Settings_WebClient/qkd_engine_config.json:/root/code/QKDserver/Settings_WebClient/qkd_engine_config.json \
		--volume /home/s-fifteen/code/QKDServer/entrypoint.sh:/root/entrypoint.sh \
		--name qkd --rm -dit \
		--entrypoint="/root/entrypoint.sh" \
		--device=/dev/ioboards/usbtmst0 $(serial_devs) \
		--device-cgroup-rule='a *:* rwm' -p 8000:8000 -p 55555:55555 s-fifteen/qkdserver:qkd

# For local testing and deployment, the appropriate changes can be propagated into
# the Docker container by mapping the corresponding volumes, e.g.
#
#   docker run ... \
#       --volume /home/s-fifteen/code/QKDServer/S15qkd:/root/code/QKDserver/S15qkd \
#	    --volume /home/s-fifteen/code/QKDServer/entrypoint.sh:/root/entrypoint.sh \
#       ...
#
# These lines are uncommented by default, assuming a testing environment and user 's-fifteen'.
# For production, uncomment those corresponding lines out.
#
# NB: If editing QKDServer, the entire Python package needs to be reinstalled as well,
#     which is achieved by injecting the installation code in the entrypoint.sh script.
