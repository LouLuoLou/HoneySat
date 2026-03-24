# Start from Ubuntu 20.04
FROM ubuntu:22.04 as common-suchai-image

# Set a non-interactive shell to avoid prompts during build
ARG DEBIAN_FRONTEND=noninteractive

# Update and install the necessary packages
RUN apt-get update && \
    apt-get install -y \
    cmake \
    gcc \
    make \
    ninja-build \
    python3 \
    python2 \
    libzmq3-dev \
    python3-zmq \
    pkg-config \
    git \
    sqlite3 \
    libsqlite3-dev \
    libmongoc-dev

# Clone the required repository
RUN git clone -b framework-sim https://gitlab.com/spel-uchile/suchai-2-software.git

# Set the working directory to the cloned repository
WORKDIR /suchai-2-software

# Run the initialization and build scripts
RUN sh init.sh

FROM common-suchai-image as flight-software

# Retrieve external environment variables
# IDENT_NAME: The name of the satellite from obc_ident command
ARG OBC_IDENT_NAME
ENV OBC_IDENT_NAME=${OBC_IDENT_NAME:-"NanoMindA3200"}

# CONSOLE_PROMPT: The prompt of the console. Originally "SUCHAI" to get "SUCHAI> "
ARG CONSOLE_PROMPT
ENV CONSOLE_PROMPT=${CONSOLE_PROMPT:-"NANOMIND"}

# BANNER_CONSOLE_NAME: The name of the console banner. Originally "SUCHAI" to get "WELCOME TO THE SUCHAI CONSOLE - PRESS ANY KEY TO START"
ARG BANNER_CONSOLE_NAME
ENV BANNER_CONSOLE_NAME=${BANNER_CONSOLE_NAME:-"NANOMIND"}

# RUN sed -i 's/localhost/honeysat-api/' apps/plantsat/src/drivers/drivers-sim/interface.c
RUN sed -i 's/-DSCH_TRX_PORT_APP=16/-DSCH_TRX_PORT_APP=16 -DSCH_COMM_ZMQ_IN=\\"tcp:\/\/honeysat-api:8001\\" -DSCH_COMM_ZMQ_OUT=\\"tcp:\/\/honeysat-api:8002\\"/' build_plantsat_sim.sh
RUN sed -i 's/localhost/logs_mongodb/' build_plantsat_sim.sh
RUN sed -i 's/suchai-log/honeysat_log/' build_plantsat_sim.sh

RUN /bin/bash -c "sed -i 's/Name: %s/Name: $OBC_IDENT_NAME/' suchai-flight-software/src/system/cmdOBC.c"
RUN sed -i 's/SCH_NAME,//' suchai-flight-software/src/system/cmdOBC.c

RUN /bin/bash -c "sed -i 's/SUCHAI> /$CONSOLE_PROMPT> /' suchai-flight-software/src/system/taskConsole.c"

RUN sed -i 's/"\\n_/\/*"\\n_/' suchai-flight-software/src/system/taskConsole.c
RUN sed -i 's/_\\n\\n";/_\\n\\n";*\//' suchai-flight-software/src/system/taskConsole.c
RUN sed -i 's/\/\/"\\n\\n======/"\\n\\n======/' suchai-flight-software/src/system/taskConsole.c

RUN sed -i 's/WELCOME TO THE SUCHAI CONSOLE - PRESS ANY KEY TO START/WELCOME TO THE BEATAXO CONSOLE/' suchai-flight-software/src/system/taskConsole.c
RUN /bin/bash -c "sed -i 's/BEATAXO/$BANNER_CONSOLE_NAME/' suchai-flight-software/src/system/taskConsole.c"



RUN sh build_plantsat_sim.sh

# Change to the plantsat directory and execute the app
WORKDIR /suchai-2-software/build-suchai-sim/apps/plantsat
CMD ["./suchai-app"]