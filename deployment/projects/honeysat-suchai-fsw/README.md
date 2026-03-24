# honeysat-suchai-fsw

## Overview
This repository includes a Dockerfile for setting up an Ubuntu 20.04 environment tailored to build and run the SUCHAI 2 flight software. The Dockerfile uses a multi-stage build process, optimizing the build and isolating the flight software build process.

## Dockerfile Details
The Dockerfile comprises multiple stages:

- **Base Stage (`common-suchai-image`)**:
  - Starts with Ubuntu 20.04 as the base image.
  - Sets up a non-interactive shell for seamless building.
  - Installs required packages, including cmake, gcc, make, ninja-build, python3, python2, libzmq3-dev, python3-zmq, pkg-config, git, sqlite3, and libsqlite3-dev.
  - Verifies that installed packages meet the minimum version requirements.
  - Clones the `framework-sim` branch of the SUCHAI 2 software repository.

- **Flight Software Stage (`flight-software`)**:
  - Inherits from the `common-suchai-image`.
  - Executes the `build_plantsat_sim.sh` script to build the flight software.
  - Sets the working directory to the plantsat directory within the SUCHAI 2 software.
  - Configures the command to execute the plantsat application.

## Prerequisites
You must have Docker installed on your system. For instructions, visit [Docker's official website](https://www.docker.com/get-started).

## Building the Docker Image
To build the Docker image named `honeysat-suchai-fsw`, run the following command in the directory containing the Dockerfile:

```bash
docker build -t honeysat-suchai-fsw .
```

This will build the image using the specified multi-stage process.

## Running the Docker Container
To run the Docker container, use:

```bash
docker run -it honeysat-suchai-fsw
```

This command initiates a new container, giving you access to the plantsat application with an interactive shell.