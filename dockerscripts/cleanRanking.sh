#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_DIR=$(realpath $DIR/../docker)

cd $DOCKER_COMPOSE_DIR
docker-compose run main bash -c 'export GLOBIGNORE="*logo.png"; rm -r /var/local/lib/cms/ranking/*'
docker-compose restart rankingserver

