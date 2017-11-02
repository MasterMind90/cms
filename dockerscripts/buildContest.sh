#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONTEST_DIR=$(realpath $DIR/../contest)

docker run --rm -v $CONTEST_DIR:/contest/ asdacap/polygon-build
