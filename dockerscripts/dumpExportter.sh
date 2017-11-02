#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_DIR=$(realpath $DIR/../docker)
CDIR=$PWD

cd $DOCKER_COMPOSE_DIR
docker-compose run main dockerize -wait tcp://postgres:5432
docker-compose run -v $CDIR:/tmp/workdir -w /tmp/workdir main cmsDumpExporter $1

