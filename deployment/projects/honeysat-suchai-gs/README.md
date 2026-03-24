# honeysat-suchai-gs

## Overview
This repository includes an updated Dockerfile for setting up an environment on Ubuntu 20.04 for building and running the SUCHAI 2 software. The Dockerfile now uses a multi-stage build process for better efficiency and modularity.

## Dockerfile Details
The Dockerfile now consists of multiple stages:

- **Base Stage (`common-suchai-image`)**:
  - Sets Ubuntu 20.04 as the base image.
  - Configures a non-interactive shell to streamline the build process.
  - Installs necessary packages such as cmake, gcc, make, ninja-build, python3, python2, libzmq3-dev, python3-zmq, pkg-config, git, sqlite3, and libsqlite3-dev.
  - Validates that installed packages meet the specified version requirements.
  - Clones the `framework-sim` branch of the SUCHAI 2 software repository from GitLab.
  - Runs the `init.sh` script from the cloned repository for initial setup.

- **Groundstation Stage (`groundstation`)**:
  - Inherits from the `common-suchai-image`.
  - Executes the `build_groundstation.sh` script to build the groundstation components.
  - Sets the working directory to the groundstation directory within the SUCHAI 2 software.
  - Specifies the command to run the groundstation application.

## Prerequisites
Ensure Docker is installed on your system. Visit [Docker's official website](https://www.docker.com/get-started) for installation instructions.

## Building the Docker Image
To build the Docker image `honeysat-suchai-gs`, execute:

```bash
docker build -t honeysat-suchai-gs .
```

This command builds the image using the multi-stage process defined in the Dockerfile.

## Running the Docker Container
To run the Docker container:

```bash
docker run -it honeysat-suchai-gs
```

This command starts a new container, launching you directly into the groundstation application with an interactive shell.