serial_devs = $(shell for dev in /dev/serial/by-id/* ;\
	    do echo -n "--device $$dev:$$dev " ;\
	    done)

timestamp=$(shell date +%Y%m%d)
host=$(shell hostname)

all: stop default

build_fresh:
	docker build --network host --no-cache -t s-fifteen/qkdserver:qkd .
build:
	docker build --network host -t s-fifteen/qkdserver:qkd .

restart: stop default log

log:
	docker logs -f qkd

savelog:
	mkdir -p logs
	docker logs qkd > logs/$(timestamp)_qkdlog_$(host) 2>&1
exec:
	docker exec -w /root/code/QKDServer/Settings_WebClient -it qkd /bin/bash

stop:
	-docker stop qkd
	sleep 7

default:
	test -f "S15qkd/qkd_engine_config.json" || { echo "No configuration file found - run 'make qkda' or 'make qkdb' first."; exit 1; }
	docker run \
		--volume /root/code/QKDServer/S15qkd:/root/code/QKDServer/S15qkd \
		--volume /root/code/QKDServer/S15qkd/qkd_engine_config.json:/root/code/QKDServer/Settings_WebClient/qkd_engine_config.json \
		--volume /root/code/QKDServer/Settings_WebClient/apps/QKD_status.py:/root/code/QKDServer/Settings_WebClient/apps/QKD_status.py \
		--volume /root/code/QKDServer/Settings_WebClient/apps/QKD_settings.py:/root/code/QKDServer/Settings_WebClient/apps/QKD_settings.py \
		--volume /root/code/QKDServer/Settings_WebClient/app.py:/root/code/QKDServer/Settings_WebClient/app.py \
		--volume /root/code/QKDServer/Settings_WebClient/index.py:/root/code/QKDServer/Settings_WebClient/index.py \
		--volume /root/code/QKDServer/entrypoint.sh:/root/entrypoint.sh \
		--volume /root/keys/authd:/root/keys/authd \
		--name qkd --rm -dit \
		--network host \
		--entrypoint="/root/entrypoint.sh" \
		--device=/dev/ioboards/usbtmst0 $(serial_devs) \
		--device-cgroup-rule='a *:* rwm' -p 4855:4855 -p 8000:8000 -p 55555:55555 s-fifteen/qkdserver:qkd

# For local testing and deployment, the appropriate changes can be propagated into
# the Docker container by mapping the corresponding volumes, e.g.
#
#   docker run ... \
#       --volume /root/code/QKDServer/S15qkd:/root/code/QKDServer/S15qkd \
#	    --volume /root/code/QKDServer/entrypoint.sh:/root/entrypoint.sh \
#       ...
#
# These lines are uncommented by default, assuming a testing environment and user 's-fifteen'.
# For production, uncomment those corresponding lines out.
#
# NB: If editing QKDServer, the entire Python package needs to be reinstalled as well,
#     which is achieved by injecting the installation code in the entrypoint.sh script.

no-device:
	docker run \
		--volume /root/code/QKDServer/S15qkd:/root/code/QKDServer/S15qkd \
		--volume /root/code/QKDServer/Settings_WebClient/certs:/root/code/QKDServer/Settings_WebClient/certs \
		--volume /root/code/QKDServer/Settings_WebClient/apps/QKD_settings.py:/root/code/QKDServer/Settings_WebClient/apps/QKD_settings.py \
		--volume /root/code/QKDServer/Settings_WebClient/apps/QKD_status.py:/root/code/QKDServer/Settings_WebClient/apps/QKD_status.py \
		--volume /root/code/QKDServer/entrypoint.sh:/root/entrypoint.sh \
		--name qkd_nodev --rm -dit \
		--entrypoint="/root/entrypoint.sh" \
		-p 8080:8000 -p 55566:55555 s-fifteen/qkdserver:qkd

# Apply example QKD-A settings
qkda:
	cp S15qkd/qkd_engine_config.qkda.json S15qkd/qkd_engine_config.json

# Apply example QKD-B settings
qkdb:
	cp S15qkd/qkd_engine_config.qkdb.json S15qkd/qkd_engine_config.json


generate-config:
	jq -s '.[0]*.[1]' \
		S15qkd/configs/qkd_engine_config.default.json \
		S15qkd/configs/qkd_engine_config.local.json \
		> S15qkd/qkd_engine_config.json
