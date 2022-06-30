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
	docker run --volume /home/s-fifteen/code/QKDServer/S15qkd:/root/code/QKDserver/S15qkd \
		   --volume /home/s-fifteen/code/QKDServer/entrypoint.sh:/root/entrypoint.sh \
		   --name qkd --rm -dit \
		   --entrypoint="/root/entrypoint.sh" \
		   --device=/dev/ioboards/usbtmst0 $(serial_devs) \
		   --device-cgroup-rule='a *:* rwm' -p 8080:8000 -p 55555:55555 s-fifteen/qkdserver:qkd

no-device:
	docker run \
		--volume /home/s-fifteen/code/QKDServer/S15qkd:/root/code/QKDserver/S15qkd \
		--volume /home/s-fifteen/code/QKDServer/Settings_WebClient/certs:/root/code/QKDserver/Settings_WebClient/certs \
		--volume /home/s-fifteen/code/QKDServer/Settings_WebClient/apps/QKD_settings.py:/root/code/QKDserver/Settings_WebClient/apps/QKD_settings.py \
		--volume /home/s-fifteen/code/QKDServer/Settings_WebClient/apps/QKD_status.py:/root/code/QKDserver/Settings_WebClient/apps/QKD_status.py \
		--volume /home/s-fifteen/code/QKDServer/entrypoint.sh:/root/entrypoint.sh \
		--name qkd_nodev --rm -dit \
		--entrypoint="/root/entrypoint.sh" \
		-p 8080:8000 -p 55566:55555 s-fifteen/qkdserver:qkd
