#!/bin/sh

# Wait until Vault is running in docker container
start=$(date +%s)
while [ "$(curl -sL -w '%{http_code}' http://vault:8200/v1/sys/health  -o /dev/null)" != "200" ] && [ "$(($(date +%s)-$start))" -lt 5 ]
do
        sleep 1
done

./configure-vault.sh > out/setup_vault.log 2>&1
../scripts/start.sh