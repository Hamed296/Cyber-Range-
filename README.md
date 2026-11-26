# Cyber Range Platform

A web-based cybersecurity training platform for managing practical labs and running hands-on scenarios. It provides separate student and administrator dashboards and supports Docker and VMware lab environments when the host machine is configured for them.

> **Note:** The current interface and in-app text are in Arabic. This project is intended for local development and training inside a trusted lab network. Review the [Security](#security) section before deploying it or making it accessible over the internet.

## Contents

- [Overview](#overview)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Requirements](#requirements)
- [Local Installation and Startup](#local-installation-and-startup)
- [Demo Accounts](#demo-accounts)
- [Running Docker Labs](#running-docker-labs)
- [Running VMware Labs](#running-vmware-labs)
- [Adding a Scenario](#adding-a-scenario)
- [Environment Configuration](#environment-configuration)
- [Project Structure](#project-structure)
- [API](#api)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [License](#license)

## Overview

Cyber Range Platform is a FastAPI web application for managing hands-on training sessions. Students can browse courses and scenarios, start a lab session, follow its steps and scoring, and then end the session. Administrators can manage users, courses, scenarios, lab steps, and monitor runtime resources.

On startup, the application creates the database tables, adds the demo accounts if they do not already exist, and synchronizes scenarios defined by `scenario.json` files into the database.

## Features

### Student features

- Log in and log out.
- View courses and general scenarios from the student dashboard.
- Review scenario details, lab steps, and possible points.
- Start and end training sessions.
- Submit answers to lab steps and track progress and scores.
- Open the training environment started by Docker or VMware when configured.

### Administrator features

- View active sessions, session history, and runtime resources.
- Create, search, edit, and delete student accounts; view student statistics.
- Create courses and assign scenarios to them.
- Create, edit, synchronize, and delete scenarios.
- Create lab steps and set their order, points, answer type, and hints.
- Monitor server resources, virtual machines, containers, and temporary runtime clones.
- End sessions, stop virtual machines, and remove temporary runtime clones through the admin interface.

### Lab environment types

- **Docker:** Runs the scenario's `docker-compose.yml` file.
- **VMware:** Creates temporary clones from virtual machine templates defined by the scenario. Requires local VMware configuration.

## Technology Stack

- Python, FastAPI, and Uvicorn.
- SQLAlchemy with SQLite by default.
- Pydantic Settings for configuration through environment variables and a `.env` file.
- HTML, CSS, and JavaScript for the web interface.
- Docker Compose for some scenarios.
- VMware Workstation and `vmrun` for virtual machine scenarios.

## Requirements

### To run the application and basic web interface

- Windows 10/11, Linux, or macOS.
- Python 3.10 or later.
- An internet connection for the initial package installation.

### To run Docker scenarios

- Docker Desktop on Windows/macOS or Docker Engine on Linux.
- Docker Compose V2, with Docker running before starting a scenario.

### To run VMware scenarios

- A compatible VMware Workstation installation.
- The `vmrun` utility and its correct path.
- The virtual machine templates referenced by the scenario files. The VM files themselves are not included in this repository.
- VMware custom networks (VMnets) configured in advance, with an available VMnet pool.

The platform interface can run without Docker or VMware, but starting scenarios that use either runtime requires the corresponding runtime engine and configuration.

## Local Installation and Startup

Open a terminal in the project directory and create a Python virtual environment.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install psutil
```

If PowerShell prevents activation because of its execution policy, allow activation for the current terminal session only, then activate the environment again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install psutil
```

> `routers/admin.py` imports the `psutil` package, but it is currently missing from `requirements.txt`. Install it with the command above.

Start the development server:

```bash
uvicorn main:app --reload
```

Open these URLs in your browser:

- Application: <http://127.0.0.1:8000/>
- Interactive API documentation: <http://127.0.0.1:8000/docs>
- Alternative API documentation: <http://127.0.0.1:8000/redoc>

Stop the server with `Ctrl+C`. The `--reload` option is intended for local development only.

### Where is application data stored?

The default database URL is `sqlite:///./database.db`, which stores the database file named `database.db` in the server's current working directory. If the file does not exist, the application creates a new database automatically at startup. Existing database files from the developer's machine are not required for a fresh installation. Do not upload databases containing real user data or accounts.

## Demo Accounts

On a new database, the application automatically creates these demo accounts:

| Role | Username | Default password |
|---|---|---|
| Administrator | `admin` | `admin` |
| Student | `student` | `student` |

These credentials are for local demonstration only. Change them immediately, and do not use them in a shared or public environment. The current application stores passwords as plain text. Do not use real accounts or sensitive information until password storage has been changed to a secure hashing mechanism.

## Running Docker Labs

1. Install Docker and make sure the Docker service is running.
2. Check that Compose V2 is available:

   ```bash
   docker compose version
   ```

3. Log in as a student and start a Docker scenario from the student interface.
4. The application runs `docker compose up -d --build` for the scenario, then provides a link to the training environment.
5. When the session ends, the application stops the Compose services and removes the volumes defined by the scenario (`down -v`).

A Docker example is included in `scenarios/docker/ssh_bruteforce/`. It uses an SSH training container and an attacker terminal container. Run this scenario only in an isolated local lab.

## Running VMware Labs

VMware labs require machine-specific setup; installing the Python packages alone is not sufficient:

1. Install VMware Workstation and confirm that `vmrun` works.
2. Create the required virtual machine templates in advance. Large VM template files are not stored in this repository.
3. Review the `scenarios/vm/*/scenario.json` files and update each `template_vmx` value to the `.vmx` file path on your machine.
4. Set `VMRUN_PATH`, `VM_CLONES_DIR`, and `VMWARE_VMNET_POOL` in `.env` as described below.
5. Create the custom VMnet networks named in the configuration. Make sure the network adapters in your VM templates are suitable for an isolated lab.
6. Start the application and launch a VM scenario from a student account.

The existing scenarios contain template paths specific to the developer's computer, such as `E:/virtual_os/templates/...`. Update these paths before running the scenarios on another machine. Do not publish VM templates or their passwords unless you have permission to share them, and replace any demo credentials.

## Adding a Scenario

The application automatically searches the `scenarios` directory for files named `scenario.json`. Each scenario must include at least:

```json
{
  "scenario_key": "my_lab",
  "name": "My Lab",
  "description": "A short description of the lab",
  "type": "docker"
}
```

The `type` value must be either `docker` or `vm`.

- For a Docker scenario, create a directory such as `scenarios/docker/my_lab/` and place `scenario.json` and `docker-compose.yml` inside it.
- For a VMware scenario, create a directory such as `scenarios/vm/my_lab/`, add VMware configuration to `scenario.json`, and specify template paths, access settings, and the machine the student will use to enter the lab.
- After adding the files, restart the application (scenarios are synchronized at startup), or run synchronization from the administrator interface.
- Assign the scenario to a course and add lab steps through the administrator interface if needed.

Make sure each `scenario_key` is unique and document and configure any local dependencies or additional files required by the scenario on the host machine.

## Environment Configuration

You can override the defaults by creating a `.env` file in the project directory. Do not commit your real `.env` file to GitHub; add secrets and machine-specific paths to `.gitignore`.

Example configuration (update the paths for your machine):

```dotenv
APP_NAME=Cyber Range
DATABASE_URL=sqlite:///./database.db
PUBLIC_BASE_URL=http://localhost:8000
SCENARIOS_DIR=scenarios
PORTS_START=20000
PORTS_END=40000
DOCKER_BIN=docker
DOCKER_COMPOSE_ARGS=compose
VMRUN_PATH=C:/Program Files (x86)/VMware/VMware Workstation/vmrun.exe
VM_CLONES_DIR=C:/cyberrange/runtime_clones
VMWARE_VMNET_POOL=VMnet10,VMnet11,VMnet12,VMnet13,VMnet14
```

| Variable | Purpose |
|---|---|
| `APP_NAME` | Application name. |
| `DATABASE_URL` | Database URL; SQLite is the default. |
| `SCENARIOS_DIR` | Directory containing scenario files; defaults to the project's `scenarios` directory. |
| `PUBLIC_BASE_URL` | Host URL used to build links to runtime environments. |
| `PORTS_START`, `PORTS_END` | Range of random ports used for runtime services. Make sure these ports are available and not blocked. |
| `DOCKER_BIN` | Name or path of the Docker command. |
| `DOCKER_COMPOSE_ARGS` | Compose arguments; defaults to `compose`. |
| `VMRUN_PATH` | Path to VMware's `vmrun` utility. |
| `VM_CLONES_DIR` | Directory for temporary VMware clones. |
| `VMWARE_VMNET_POOL` | Comma-separated names of available custom VMnet networks. |

The default SQLite path is relative to the server's working directory. Use a fixed path if you start the application from a different directory.

## Project Structure

```text
CyberRange_platform/
├── main.py                     # FastAPI application and startup initialization
├── requirements.txt            # Core Python packages
├── core/                       # Settings, database connection, and permissions
├── models/                     # SQLAlchemy models
├── schemas/                    # API data schemas
├── routers/                    # Authentication, student, and admin routes
├── services/                   # User, scenario, and session logic
│   └── runtime/                # Docker and VMware runtime handlers
├── scenarios/                  # Scenario definitions and Compose files
├── static/                     # HTML, CSS, JavaScript, and image assets
├── utils/                      # Helper utilities
└── migrate_add_courses_and_steps.py # Migration for an older database, if needed
```

## API

All API routes are automatically documented at `/docs`. Main route groups:

- `/api/auth`: login and logout.
- `/api/student`: student dashboard, courses, scenario steps, progress, and session start/end.
- `/api/admin`: users, courses, scenarios, steps, sessions, and platform resources.

Most student and administrator operations require authentication and the appropriate role.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'psutil'`:** Activate the virtual environment and install `psutil` with `pip install psutil`.
- **`uvicorn` command not found:** Make sure the virtual environment is active, then reinstall packages from `requirements.txt`.
- **Port 8000 is already in use:** Start the application on another port, for example `uvicorn main:app --reload --port 8001`, and open the new URL.
- **Docker scenario does not start:** Confirm that Docker Desktop/Engine is running, Compose V2 is available, and the required ports are not already in use.
- **VMware scenario does not start:** Check `VMRUN_PATH`, the `.vmx` paths in the scenario definition, the temporary clone directory, and the VMnet networks.
- **Scenarios are missing:** Confirm the JSON is valid and includes `scenario_key`, `name`, and a valid `type`, then restart the application or run synchronization.
- **Changes to an older database are not visible:** The older database may need the appropriate schema migration. Back up the database before running any migration.

## Security

This is an educational platform under development. Before running it outside the developer's machine:

- Change the demo accounts and remove all default credentials.
- Do not expose the application directly to the internet; use an isolated lab network and firewall.
- Do not commit `.env` files, databases, passwords, session tokens, or VM files to the repository.
- Review credentials in scenario files, VMware settings, and Compose files; replace them with lab-only demo values or local configuration that is not tracked by Git.
- Update authentication to hash passwords securely, and configure session protection and HTTPS before deployment.
- Review the licenses for container images and virtual machines used by the labs.
- Use the scenarios only on systems you own or have explicit authorization to test.

## License

No license file is currently included in the project. Add a `LICENSE` file and choose a license before allowing others to reuse or distribute the project.
