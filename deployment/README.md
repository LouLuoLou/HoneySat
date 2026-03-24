# Honeysat

## Requirements
In order to run the project, docker engine and docker compose must be installed on the system. The installation steps can be found [here](https://docs.docker.com/engine/install/).

## Run
The detailed instructions to run and use each stack can be found in the following location:
* [CSP Stack](./docs/csp/README.md)
* [CCSDS Stack](./docs/ccsds/README.md) (Yamcs integration)

## Subprojects
This repository consists of multiple subprojects, each used in at least one of the aforementioned deployment stacks. For an example of their usage and their role in a typical setup, refer to CSP and CCSDS docs.

- Honeysat API: [Source](/projects/honeysat-api/) / [Docs](/docs/honeysat-api/README.md)
- Honeysat SUCHAI Flight Software: [Source](/projects/honeysat-suchai-fsw/) / [Docs](/docs/honeysat-suchai-fsw/)
- Honeysat SUCHAI Ground Station: [Source](/projects/honeysat-suchai-gs/) / [Docs](/docs/honeysat-suchai-gs/)
- Honeysat Web Interface: [Source](/projects/honeysat-webpage-v2/) / [Docs](/docs/honeysat-webpage/)
- Yamcs Instance: [Source](/projects/yamcs/)
- Raccoon Wrapper: [Source](/projects/raccoon-wrapper/)
