#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_DIR=$(realpath $DIR/../docker)
CONTEST_DIR=$(realpath $1)

cd $DOCKER_COMPOSE_DIR
docker-compose run main dockerize -wait tcp://postgres:5432 
docker-compose run -v $CONTEST_DIR:/contest/ main cmsImportContest -i -u -U /contest/

