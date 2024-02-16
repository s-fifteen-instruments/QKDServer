default: restart

###############
#  CONSTANTS  #
###############

DEVICE_ROOT=/dev/serial/by-id
IOBOARD_ROOT=/dev/ioboards
CONFIG_FILE=S15qkd/qkd_engine_config.json
DEFAULT_CONFIG_FILE=S15qkd/configs/qkd_engine_config.default.json
USER_CONFIG_FILE=S15qkd/configs/qkd_engine_config.local.json
# Only for Debian-based and RHEL 7+
TZ=$(shell timedatectl | grep "zone" | awk '{print $$3}')

qkdserver_root=$(shell pwd)
serial_devs=$(shell \
	if [ -d "$(DEVICE_ROOT)" ]; then\
		for dev in $(DEVICE_ROOT)/*;\
			do echo -n "--device $$dev:$$dev ";\
		done\
	fi\
)
ioboard_devs=$(shell \
	if [ -d "$(IOBOARD_ROOT)" ]; then\
		for dev in $(IOBOARD_ROOT)/*;\
			do echo -n "--device=$$dev ";\
		done\
	fi\
)
# Timestamp has minute-resolution in order to easily match logs with other nodes
timestamp=$(shell date +%Y%m%d_%H%M00)
datestamp=$(shell date +%Y%m%d)
host=$(shell hostname)


###################
#  CONFIGURATION  #
###################

# Allow readevents priority to be elevated within the container
enable_sys_nice=$(shell jq '.ENVIRONMENT.raise_readevents_priority' $(CONFIG_FILE))
sys_nice_flag=$(shell if [ "$(enable_sys_nice)" = "true" ]; then echo -n "--cap-add=SYS_NICE "; fi)
sudo_flag=$(shell if [ "$(enable_sys_nice)" = "true" ]; then echo -n "sudo "; fi)

# Directory where secrets are kept
secrets_root=$(shell jq '.ENVIRONMENT.secrets_root' $(CONFIG_FILE))

# Docker build string
docker_image_ls=$(shell docker image ls | grep "s-fifteen/qkdserver")

# Check existence of dependencies to properly evaluate this Makefile
verify-dependencies: verify-jq verify-config verify-build
verify-jq:
	@command -v jq >/dev/null 2>&1 || { echo "'jq' is not installed  (hint: install with 'apt/zypper install jq')"; exit 1; }
verify-config:
	@test -f "$(CONFIG_FILE)" || { echo "No configuration file found  (hint: run 'make generate-config')"; exit 1; }
verify-build:
	@if [ "$(docker_image_ls)" = "" ]; then { echo "QKD image has not been built  (hint: run 'make build')"; exit 1; }; fi
generate-config: verify-jq
	@test -f "$(USER_CONFIG_FILE)" || { echo "User configuration file missing: '$(USER_CONFIG_FILE)'  (hint: see README for setup instructions)"; exit 1; }
	@jq -s '.[0]*.[1]' \
		$(DEFAULT_CONFIG_FILE) $(USER_CONFIG_FILE) \
		> S15qkd/qkd_engine_config.json


#############
#  RECIPES  #
#############

all: stop qkd

# Build containers
build-fresh:
	docker build --network host --no-cache -t s-fifteen/qkdserver:qkd .
build:
	docker build --network host -t s-fifteen/qkdserver:qkd .

restart: stop qkd log

log:
	docker logs -f qkd
log-freq:
	docker logs -f qkd | grep -P "(digest_genlog|BBM92|freqcorr|fpfind|freq difference)"
log-qber:
	docker logs -f qkd | grep -P "(minimum_qber|BBM92|target QBER|Avg\(qber\))"
log-keys:
	docker logs -f qkd | grep -P "(ecnotepipe_digest|Undigested)"

# Note that Docker logs will truncate. The following logs are saved:
#   1. /root/code/QKDServer/Settings_WebClient/logs for full QKDServer logs
#   2. /tmp/cryptostuff for qcrypto component logs
savelog save-logs: pull-logs backup-logs
pull-logs:
	mkdir -p logs/$(datestamp)
	docker cp qkd:/root/code/QKDServer/Settings_WebClient/logs logs/$(datestamp)/qkdlogs_$(host)
	docker cp qkd:/tmp/cryptostuff logs/$(datestamp)/cryptostuff_$(host)
# Compress logs before sending ('gzip' as fallback if 'pigz' does not exist)
backup-logs:
	rm -f logs/$(timestamp)_qkdlog_$(host).tar.gz
	tar -I pigz -cf logs/$(timestamp)_qkdlog_$(host).tar.gz -C logs $(datestamp) || \
		{ tar -czf logs/$(timestamp)_qkdlog_$(host).tar.gz -C logs $(datestamp); }
	rm -rf logs/$(datestamp)
	@echo "Logs successfully archived: 'logs/$(timestamp)_qkdlog_$(host).tar.gz'"

# Enter shell in QKDServer container
exec:
	docker exec -w /root/code/QKDServer/Settings_WebClient -it qkd /bin/bash

# Sleep needed here, for some Docker cleanup happening in the background.
stop:
	-docker stop qkd
	-docker rm qkd && sleep 7

# In the event QKDServer terminates abruptly, e.g. power failure, do not remove
# the container nor automatically restart, so that logs can still be retrieved
# via 'make savelog'.
qkd: generate-config verify-dependencies
	$(sudo_flag) docker run \
		--volume $(qkdserver_root)/entrypoint.sh:/root/code/QKDServer/entrypoint.sh \
		--volume $(qkdserver_root)/S15qkd:/root/code/QKDServer/S15qkd \
		--volume $(qkdserver_root)/$(CONFIG_FILE):/root/code/QKDServer/Settings_WebClient/qkd_engine_config.json \
		--volume $(secrets_root):/root/keys/authd \
		--volume epochs:/epoch_files \
		--name qkd -dit \
		$(sys_nice_flag) $(ioboard_devs) $(serial_devs) \
		--device-cgroup-rule='a *:* rwm' -p 4855:4855 -p 8000:8000 -p 55555:55555 s-fifteen/qkdserver:qkd
