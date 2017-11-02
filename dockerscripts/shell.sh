#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_DIR=$(realpath $DIR/../docker)
USERS_JSON_FILE=$(realpath $1)

cd $DOCKER_COMPOSE_DIR
docker-compose run main bash

