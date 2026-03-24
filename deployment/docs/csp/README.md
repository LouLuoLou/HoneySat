# Honeysat CSP Stack

The information about Honeysat CSP stack can be found in this document. Basic familiarity with docker and docker compose is assumed throughout this doc.

## Run

### Important Note on Environment Variables

Before running the project, ensure the required environment variables are correctly set up. For more information, refer to Configuration section.

### Commands

To start all services, use: (remove `-d` option if you want to run the services in the foreground)
```bash
docker compose --file ./docker-compose-csp.yaml --profile ALL up -d
```

To stop all services, use:
```bash
docker compose --file ./docker-compose-csp.yaml --profile ALL down
#or docker compose --file ./docker-compose-csp.yaml --profile ALL down -v to remove volumes as well
```

For specific services, like `HONEYSAT` or individual services, use:
```bash
docker compose --file ./docker-compose-csp.yaml --profile [PROFILE_NAME] up -d
```
Replace `[PROFILE_NAME]` with `HONEYSAT`, `WEB`, `SUCHAI_GS`, etc., as needed.

For running multiple single services, like `LOGS_MONGODB` and `HONEYSAT_API`, use:
```bash
docker compose --file ./docker-compose-csp.yaml --profile [PROFILE_NAME_1] --profile [PROFILE_NAME_2] up -d
```
Example:
```bash
docker compose --file ./docker-compose-csp.yaml --profile LOGS_MONGODB --profile HONEYSAT_API up -d
```

## Services
These are the services used in Honeysat CSP stack:

1. **Web Interface**: The web interface for HoneySat. This web interface is used to show real-time telemetry.
2. **SUCHAI Ground Station**: The component for ground station operations. This is an actual ground station software implementation used in a CubeSat mission.
3. **SUCHAI Flight Software**: The flight software for the satellite. This is an actual flight software implementation used in a CubeSat mission.
4. **Logs MongoDB**: Centralized logging database for all components.
5. **Honeysat API**: The core API service for HoneySat, which simulates multiple satellite sensors and subsystems.
more info about inner workings of this can be found at `/projects/honeysat-api/README.md`.
6. **Honeypot Desktop**: To gain more insight into an attacker's behavior, you may want to provide the attacker with a desktop environment that includes GUI tools. An example can be found in `/projects/vnc-setup`. Note that this setup requires additional isolation when used with actual attackers.

## Attacker's Point of View
The attacker can open the web interface (login with admin:admin credentials through `http://localhost:80`). This web interface hints to existence of a telnet service.

The telnet interface is provided by SUCHAI Ground Station service and is forwarded to localhost's port 24. Through this interface, the attacker will be able to interact with MCS Functinality. A basic guide about the available commands is printed in the telnet interface by entering `help` command. Any interaction between the attacker and Honeysat is logged to the MongoDB database for later investiation. This webpage also allows access to a Desktop Honeypot.

## Configuration
Each service has a number of configurations that affect its behavior; For example, the coordinates of the ground station affect the contents of web interface, and the behavior of the satellite simulator might be changed by parameters like `MIN_TEMPERATURE` and `MAX_TEMPERATURE`. Such configurations are specific to each service.

On the other hand, there are some configurations that mostly concern the architecture of the system. Such configurations are mostly managed in docker-compose file.

### Web Interface
The behavior of the web interface is configured by some environment variables. The details are accessible in its [docs](/docs/honeysat-webpage/README.md).
Some of these environment variables are written in `configs/csp_webpage.env`. The others are configured in `docker-compose-csp.yaml` itself.
So, in order to change the configuration of the web interface, these two files should be edited.

### Honeysat API (Satellite Simulator)
This service can be configured through the `/projects/honeysat-api/SatellitePersonality.py` file at build time. For details on Honeysat API configuration, please refer to the respective guide [here](/docs/honeysat-api/README.md).

### SUCHAI Ground Station
This service is configured through some environment variables and docker build arguments. Refer to its [docs](/docs/honeysat-suchai-gs/README.md) for details, and edit `docker-compose-csp.yaml` for changing the configuration in our default setup.

### SUCHAI Flight Software
This service is configured through some environment variables and docker build arguments. Refer to its [docs](/docs/honeysat-suchai-fsw/README.md) for details, and edit `docker-compose-csp.yaml` for changing the configuration in our default setup.

### Infrastructure-related Configurations
As mentioned before, some parts of `docker-compose-csp.yaml` file are responsible for the architecture and infrastructure of the system, e.g. TCP ports forwarded from the host machine to the services, docker volumes to persistently store the data in database, etc.

One can easily understand these settings if they are already familiar with docker compose syntax. Therefore, there will not be a detailed explanation about them here.

## Logs
As mentioned before, a MongoDB instance is used to collect the logs from different services.
In order to interact with this database, it is suggested to install [MongoDB Compass](https://www.mongodb.com/try/download/compass) GUI.
It lets the user to easily browse the logs stored at the database.
The credentials and port number required to connect to the database can be found in docker compose file.
Further explanation of this tool is out of scope of this document.


