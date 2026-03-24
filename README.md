# HoneySat: A Network-based Satellite Honeypot Framework  
NDSS 2026 Artifact Evaluation – README

This README accompanies the artifact for the paper:

> **HoneySat: A Network-based Satellite Honeypot Framework** (NDSS 2026)

The artifact provides a Dockerized version of HoneySat and evaluation scripts to reproduce the main experimental results and support the artifact evaluation process.

---

## 1. Artifact Contents and Goals

### 1.1. What this artifact provides

The artifact includes:

- A **Dockerized HoneySat deployment** that can bootstrap honeypots for:
  - **CSP-based** satellite missions  
  - **CCSDS/YAMCS-based** satellite missions
- **Evaluation utilities** (Python scripts) that:
  - Demonstrate believable telemetry and telecommand handling  
  - Show realistic communication windows and interaction capabilities  
  - Expose logging capabilities  
  - Showcase configurability and extensibility of HoneySat

### 1.2. Paper claims supported by this artifact

The experiments in this artifact are designed to support the following claims.

- **(C1)** HoneySat can be used to deceive adversaries and log activities.
  - **E1.1**: HoneySat’s simulator provides believable telemetry (TM)  
  - **E1.2**: HoneySat enforces realistic communication windows  
  - **E1.3**: HoneySat supports interactive capabilities (process TC, provide TM)  
  - **E1.4**: HoneySat logs interaction details

- **(C2)** HoneySat is extensible and supports two different protocol ecosystems.
  - **E2**: HoneySat is configurable and can be customized with relatively low effort

---

## 2. Getting the Artifact

The artifact is distributed as a compressed archive (for example `ndss-artifact-eval.tar.gz`) via Zenodo:

- DOI: **https://doi.org/10.5281/zenodo.17548980**

After downloading:

```bash
tar xzpvf ndss-artifact-eval.tar.gz
cd ndss-artifact-eval
````

All paths in this README are relative to the extracted repository root.

---

## 3. System Requirements

### 3.1. Hardware

* Approximately **25 GB of free disk space**
* At least **4 CPU cores**
* At least **8 GB RAM**

### 3.2. Software

A recent Linux distribution is required. The artifact has been **verified on Ubuntu 24.04.2 LTS**. Other modern Linux systems may work but are not guaranteed.

Required software:

* **Docker** (with Docker Compose and related components)

  * We recommend following the official instructions: [https://docs.docker.com/engine/install/](https://docs.docker.com/engine/install/)
* **Python 3.12**

  * Newer versions may also work
* **Python virtual environment** support (`venv`)
* **Bash**
* **Telnet client** (for example the `telnet` package)
* **Modern web browser** (for example Firefox or Chrome)

### 3.3. Network and privileges

* Ability to bind local ports (for example `80` for the web interface, `24` for the CSP telnet interface)
* Ability to run Docker (usually membership in the `docker` group or use of `sudo`)

---

## 4. Repository Layout

From the repository root:

* `deployment/`
  Dockerized HoneySat services and deployment configuration. This directory contains the Docker Compose setup and detailed deployment documentation in `deployment/README.md`.

* `evaluation/`
  Python utilities and experiment scripts for evaluating HoneySat’s capabilities.
  The Python dependencies for this directory are listed in:

  * `evaluation/requirements.txt`

---

## 5. Environment Setup

Follow these steps from the **repository root**.

### 5.1. Create and activate a Python virtual environment

```bash
python3 -m venv .
source bin/activate
```

This creates a virtual environment in the current directory and activates it.

### 5.2. Install Python dependencies

```bash
python3 -m pip install -r evaluation/requirements.txt
```

This installs the Python packages needed by the evaluation scripts.

### 5.3. Configure Docker user (optional but recommended)

To avoid prefixing every Docker command with `sudo`, add your user to the `docker` group:

```bash
sudo usermod -aG docker $USER
sudo reboot now
```

After the reboot, verify Docker works without `sudo`:

```bash
docker ps
```

If this command runs without errors and without asking for `sudo`, Docker is correctly configured.

### 5.4. Starting HoneySat services

All remaining setup is handled through Docker containers. You can either:

* Use the **convenience scripts** under `evaluation/` (recommended for AE)
  or
* Follow `deployment/README.md` to bring up services using Docker Compose manually

The next section presents a quick start route for evaluating pass simulations.

---

## 6. Quick Start for Pass Simulations

One key feature of HoneySat is the modeling of **realistic communication windows**. The satellite is only reachable while passing over a ground station. For many experiments it is useful to start from a configuration where a pass occurs almost immediately after startup.

We provide **two helper scripts** that:

* Compute a suitable ground-station location along the satellite’s predicted ground track
* Ensure a pass occurs shortly after startup
* Build and start the necessary Docker Compose services
* Shut down the services cleanly when you press `CTRL+C`

### 6.1. CSP-based honeypot

From the repository root:

```bash
./evaluation/experiment-1/run-experiment-csp.sh
```

This script:

* Builds and starts a **CSP-based** HoneySat instance
* Positions the ground station so that communication becomes possible shortly after startup
* Enables you to observe how an attacker would perceive an imminent pass without waiting for a long time

### 6.2. CCSDS/YAMCS-based honeypot

From the repository root:

```bash
./evaluation/experiment-1/run-experiment-ccsds.sh
```

This script:

* Builds and starts a **CCSDS/YAMCS-based** HoneySat instance
* Uses the same predicted ground track logic to schedule a pass shortly after startup

After running either script, proceed with the experiments in Section 7, or consult `deployment/README.md` for additional configuration details.

---

## 7. Experiment Guide

This section provides a step by step guide to reproduce the experiments used in the paper and in the artifact appendix. For convenience, we also list approximate **human time** per experiment.

All experiments assume:

* You have followed Section 5 (environment setup)
* Docker daemon is running
* You execute commands from the **repository root** with the virtual environment activated

### 7.1. Experiment 1 (E1.1) – Believable TM/TC

* **Goal**. Demonstrate that HoneySat produces believable telemetry ( TM ) in response to telecommands ( TC ) for a CCSDS/YAMCS setup.
* **Estimated human time**. ~10 minutes

#### 7.1.1. Preparation

Ensure dependencies are installed as described in Sections 3 and 5.

#### 7.1.2. Execution

Run:

```bash
./evaluation/experiment-1/run-experiment-ccsds.sh
```

The script will:

* Build and start the relevant containers
* Issue a set of telecommands
* Print the resulting telemetry values to `stdout`

Optionally, once the system is up you can also inspect telemetry via the **YAMCS web interface** (exposed by the deployment). Details of the web interface, including ports, are described in `deployment/README.md`.

#### 7.1.3. Expected results

You should see believable telemetry values for the selected battery configuration, for example:

* Voltage. approximately **8000 mV** (normal test case)
* Temperature. approximately **30 °C**
* Current draw. approximately **74 mA**

These values should be stable and realistic for a nominal satellite condition.

**Supported claim**. C1 (believable telemetry and telecommand behavior).

---

### 7.2. Experiment 1.2 (E1.2) – Believable passes

* **Goal**. Show that HoneySat enforces realistic communication windows. The satellite should be reachable only during predicted passes over a ground station.
* **Estimated human time**. ~20 minutes

#### 7.2.1. Preparation

Start the CSP-based scenario:

```bash
./evaluation/experiment-1/run-experiment-csp.sh
```

This script:

* Starts the CSP-based honeypot
* Positions the ground station such that a pass begins approximately **2–3 minutes** after startup (adjustable in the script)
* Starts all required services (including the web interface and CSP telnet service)

#### 7.2.2. Execution

1. **Monitor predicted passes via the web interface**

   Open a web browser and navigate to:

   * [http://localhost:80](http://localhost:80)

   Log in with:

   * **Username**. `admin`
   * **Password**. `admin`

   Then:

   * Click on the **ground station icon**
   * Inspect the list of **predicted passes**
   * Wait until the next pass shows as **ongoing**

2. **Connect to the CSP telnet interface**

   In a separate terminal:

   ```bash
   telnet localhost 24
   ```

   Inside the telnet session:

   ```text
   activate
   ```

3. **Probe satellite reachability during the pass**

   While watching the predicted pass timeline, probe reachability every few seconds by entering:

   ```text
   1: com_ping 10
   ```

#### 7.2.3. Expected results

* The satellite **responds to `com_ping` only during the predicted pass**
* Before the pass starts and after it ends, the satellite remains **unreachable**, so you will see no valid responses
* Responses during the pass will indicate the expected addressing:

  * **Source address** = 1
  * **Destination address** = 10

This behavior demonstrates that HoneySat implements **realistic communication windows** consistent with orbital predictions.

**Supported claim**. C1 (realistic communication windows).

---

### 7.3. Experiment 1.3 (E1.3) – Simulated interaction

* **Goal**. Demonstrate HoneySat’s interactive capabilities once the satellite is reachable, including the execution of commands via the simulated on board computer (OBC).
* **Estimated human time**. ~15 minutes

#### 7.3.1. Preparation

Repeat the setup from **Experiment 1.2**:

* Start the CSP-based experiment using:

  ```bash
  ./evaluation/experiment-1/run-experiment-csp.sh
  ```

* Connect via telnet and wait until the satellite becomes reachable, as in E1.2

Additionally, familiarize yourself with the commands documented in the `evaluation/experiment-1.3/` folder.

#### 7.3.2. Execution

Once the satellite is reachable (see E1.2 for how to detect this), use the telnet interface to issue commands. For example, to execute arbitrary shell commands on the OBC:

```text
1: obc_system [shell command]
```

Replace `[shell command]` with any valid shell command, found in the evaluation/experiment-1.3/` folder.

#### 7.3.3. Expected results

* Commands issued via `obc_system` are executed on the simulated OBC
* Output is returned through the telnet session as expected
* Interaction is possible only while the satellite is reachable during a pass

This experiment demonstrates HoneySat’s ability to simulate realistic **telecommand based interaction** with a satellite platform.

**Supported claim**. C1 (interaction capabilities).

---

### 7.4. Experiment 1.4 (E1.4) – Logging capabilities

* **Goal**. Verify that HoneySat logs interaction details and relevant parameters in a database.
* **Estimated human time**. ~5 minutes (after a CSP instance is already running)

#### 7.4.1. Preparation

* Start a CSP based HoneySat instance as in **Experiment 1.3**
* Optionally interact with the honeypot (for example by issuing pings and OBC commands) to generate log data

#### 7.4.2. Execution

From the repository root, with the virtual environment activated:

```bash
python3 ./evaluation/experiment-1/python_dump_mongodb/dump_mongodb.py
```

Alternatively, you can connect directly to the MongoDB instance using any MongoDB client, based on the connection parameters used in the deployment.

#### 7.4.3. Expected results

* The script prints the contents of the MongoDB database to `stdout`
* Entries show:

  * Telecommands and telemetry
  * Parameters related to the interactions
  * Timestamps and other contextual details

This demonstrates that HoneySat **logs interactions** for later analysis.

**Supported claim**. C1 (logging and observability).

---

### 7.5. Experiment 2 (E2) – Customization and extensibility

* **Goal**. Demonstrate that HoneySat is configurable and can be adapted to different satellites, locations, and protocol stacks with relatively low effort.
* **Estimated human time**. Scenario dependent, typically ~10–20 minutes

#### 7.5.1. Preparation

Navigate to the Experiment 2 directory:

```bash
cd evaluation/experiment-2
```

Make sure your virtual environment is still active.

#### 7.5.2. Execution

1. **Create a baseline customization**

   Use the `honeysat.py` script to generate a configuration:

   ```bash
   python3 ./honeysat.py [csp|ccsds] "{satellite name}" "{location}"
   ```

   Example:

   ```bash
   python3 ./honeysat.py csp "BEESAT" "Berlin"
   ```

   This command creates configuration files for the chosen protocol stack and scenario.

2. **Start services with the generated configuration**

   You can then start HoneySat using:

   ```bash
   python3 ./honeysat.py start [csp|ccsds] "{satellite name}" "{location}"
   ```

   Example:

   ```bash
   python3 ./honeysat.py start csp "BEESAT" "Berlin"
   ```

   The script will bring up the required Docker services for the specified configuration.

3. **Stop services**

   When finished, stop the configured instance:

   ```bash
   python3 ./honeysat.py stop [csp|ccsds]
   ```

   Example:

   ```bash
   python3 ./honeysat.py stop csp
   ```

#### 7.5.3. Expected results

* HoneySat can be configured for different:

  * Satellite identifiers
  * Ground-station locations
  * Protocol ecosystems (CSP or CCSDS/YAMCS)
* The configuration process requires **relatively little manual effort**, demonstrating HoneySat’s extensibility and modularity.

**Supported claim**. C2 (configurability and support for multiple protocol ecosystems).


