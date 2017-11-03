FROM ubuntu:16.04

# Deps
RUN apt-get update
RUN apt-get install -y build-essential fpc \
    postgresql postgresql-client gettext python2.7 \
    iso-codes shared-mime-info stl-manual cgroup-lite \
    python-pip libpq-dev libcups2-dev libffi-dev \
    sudo dos2unix wget

# Install other compilers here
RUN apt-get install -y fpc php7.0-cli haskell-platform

# Install Java.
RUN \
  echo oracle-java8-installer shared/accepted-oracle-license-v1-1 select true | debconf-set-selections && \
  apt-get install -y software-properties-common && \
  add-apt-repository -y ppa:webupd8team/java && \
  apt-get update && \
  apt-get install -y oracle-java8-installer && \
  rm -rf /var/lib/apt/lists/* && \
  rm -rf /var/cache/oracle-jdk8-installer

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
