FROM ubuntu:16.04

# Deps
RUN apt-get update
RUN apt-get install -y build-essential openjdk-8-jre openjdk-8-jdk fpc \
    postgresql postgresql-client gettext python2.7 \
    iso-codes shared-mime-info stl-manual cgroup-lite \
    python-pip libpq-dev libcups2-dev libffi-dev \
    sudo dos2unix wget

# Dockerize
ENV DOCKERIZE_VERSION=v0.5.0
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz

# Python deps
ADD requirements.txt /app/
RUN pip install -r /app/requirements.txt

ADD . /app/
ADD docker/cms.conf /etc/
ADD docker/cms.ranking.conf /etc/

WORKDIR /app/

RUN useradd -ms /bin/bash cmsuser
ENV SUDO_USER=cmsuser

RUN ./prerequisites.py build --as-root
RUN ./prerequisites.py install -y --no-conf

RUN python setup.py install

CMD dockerize -wait tcp://postgres:5432 /app/docker/start.sh
