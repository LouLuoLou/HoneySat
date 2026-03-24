FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

## Install Java
RUN apt update && apt install -y openjdk-21-jdk openjdk-21-jre

## Install NVM
RUN apt update && apt install -y git curl

RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash

ENV NODE_VERSION=20
ENV NVM_DIR=/root/.nvm
RUN . "$NVM_DIR/nvm.sh" && nvm install ${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm use v${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm alias default v${NODE_VERSION}
ENV PATH="/root/.nvm/versions/node/v${NODE_VERSION}/bin/:${PATH}"

## Install maven
RUN apt install -y maven

ENV JAVA_HOME /usr/lib/jvm/java-1.21.0-openjdk-amd64/

## Install YAMCS Fork
RUN mkdir yamcs_install && git clone https://github.com/jdiez17/yamcs.git yamcs_install && cd yamcs_install && git checkout raccoon-dev

RUN . "$NVM_DIR/nvm.sh" && cd yamcs_install && mvn clean install -DskipTests && cd yamcs-web/src/main/webapp && npm install && npm run build && cd - && mvn clean install -DskipTests

## Initialize Workdir
RUN mkdir /yamcs
# ADD . /yamcs/

WORKDIR /yamcs
