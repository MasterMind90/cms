#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_DIR=$(realpath $DIR/../docker)

cd $DOCKER_COMPOSE_DIR
docker-compose build
docker-compose run main dockerize -wait tcp://postgres:5432 cmsInitDB
