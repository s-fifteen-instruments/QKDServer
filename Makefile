restart:
	-docker stop qkd
	sleep 5
	make default
	docker logs -f qkd
exec:
	docker exec -it qkd /bin/sh

default:
	docker run --volume /home/s-fifteen/code/QKDServer/S15qkd:/root/code/QKDserver/S15qkd --volume /home/s-fifteen/code/QKDServer/entrypoint.sh:/root/entrypoint.sh --name qkd --rm -dit --entrypoint="/root/entrypoint.sh" --device=/dev/ioboards/usbtmst0 --device=/dev/serial/by-id/* --device-cgroup-rule='a *:* rwm' -p 8080:8000  s-fifteen/qkdserver
