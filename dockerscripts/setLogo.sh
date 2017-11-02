#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_DIR=$(realpath $DIR/../docker)
LOGO_FILE=$(realpath $1)
LOGO_FILENAME=$(basename $LOGO_FILE)
LOGO_EXTENSION="${LOGO_FILENAME##*.}"

cd $DOCKER_COMPOSE_DIR
docker-compose run -v $LOGO_FILE:/tmp/$LOGO_FILENAME main cp /tmp/$LOGO_FILENAME /var/local/lib/cms/ranking/logo.$LOGO_EXTENSION
docker-compose restart rankingserver

