FROM node:18.20-bullseye AS build

RUN apt-get update && apt-get install -y \
    openjdk-17-jdk \
    maven

COPY yamcs /yamcs
WORKDIR /yamcs

RUN cd yamcs-web/src/main/webapp && \
    npm install && \
    npm run build

RUN mvn clean install -DskipTests

COPY yamcs-instance /yamcs-instance
WORKDIR /yamcs-instance
RUN mvn clean compile package

FROM ubuntu:24.04

RUN apt update && apt install -y openjdk-17-jdk

WORKDIR /app

COPY --from=build /yamcs-instance/target/honeysat-1.0.0-bundle.tar.gz ./
RUN tar -xvf honeysat-1.0.0-bundle.tar.gz

WORKDIR /app/honeysat-1.0.0

ENTRYPOINT ["./bin/yamcsd", "--data-dir", "/data/"]
