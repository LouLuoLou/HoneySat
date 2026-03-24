# RCCN Userspace

This repository contains the Userspace applications for RACCOON OS.

## Quickstart

### Compile and Run

From the root of this repository, run:

    cargo run --bin rccn_usr_comm

and, in a new terminal, run:

    cargo run --bin rccn_usr_example_app

Now you're ready to receive TCs from the ground segment.

### Ground Segment Setup

First download and compile our forked version of [Yamcs](https://yamcs.org).[^1]


    mkdir ~/dev/rccn/yamcs
    cd ~/dev/rccn/yamcs
    git clone https://github.com/jdiez17/yamcs
    cd yamcs

Then follow the instructions in the README to compile and install Yamcs.
In short, run these commands:

    cd yamcs-web/src/main/webapp
    npm install
    npm run build
    cd -

(builds the web UI)
and

    mvn clean install -DskipTests

(compiles and install Yamcs).

Then, clone the Yamcs instance that we use for RACCOON development:

    cd ~/dev/rccn/yamcs
    git clone https://gitlab.com/rccn/yamcs-instance

Start the Yamcs server:

    ./mvnw yamcs:run

### Send a Command

- Navigate to http://localhost:8090 to open the Yamcs Web UI.
- Choose the `rccn_usr` instance.
- Go to **Commanding** >> **Send a command** >> `RACCOON_SVC` >> `GeneratedCommandTest`
- Enter 42 as the `apid` argument. Choose the rest of the arguments to your liking.
- Click **Send**

## Repository Structure

```
.
├── scripts
│   └── ostree-push.sh                            - Creates an OSTree commit from an install directory. WIP.
└── src
    ├── rccn_usr                                  - Rust library providing facilities to implement PUS services.
    │   ├── Cargo.toml
    │   └── src
    │       ├── pus                               - Rust module that provides some standard PUS services
    │       │   ├── service                       - API for defining PUS services. Fairly stable.
    │       │   ├── parameter_management_service  - WIP implementation of PUS service 20
    │       │   └── app.rs                        - Provides PusApp for combining multiple services
    │       ├── time.rs                           - Time helpers
    │       └── types.rs
    ├── rccn_usr_comm                             - Provides COMM services (frames <-> VCs, SDLS). WIP.
    │   ├── etc
    │   │   └── config.yaml                       - Configuration file for rccn_usr_comm
    │   └── src
    │       ├── config.rs                         - Configuration parser
    │       ├── frame_processor.rs                - Frame processing logic
    │       ├── main.rs                           - Well, it's the main.
    │       └── transport.rs                      - Transport abstraction, may be removed in the future
    ├── rccn_usr_example_app                      - Example app implementing a custom service
    │   └── src
    │       ├── example_service
    │       └── main.rs
```

[^1]: This version contains some changes that are in the process of being upstreamed, like the collapsible sidebar.
In the future, we want to use only the upstream Yamcs, or publish our forked packages to Maven Central so users don't have to compile Yamcs themselves.