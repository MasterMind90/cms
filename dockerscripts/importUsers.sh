#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_DIR=$(realpath $DIR/../docker)
USERS_JSON_FILE=$(realpath $1)

cd $DOCKER_COMPOSE_DIR
docker-compose up -d rankingserver
docker-compose run main dockerize -wait tcp://postgres:5432
docker-compose run -v $USERS_JSON_FILE:/tmp/users.json main cmsJsonUserImporter -c 1 /tmp/users.json

