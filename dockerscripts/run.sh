#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_DIR=$(realpath $DIR/../docker)

cd $DOCKER_COMPOSE_DIR
docker-compose up -d

