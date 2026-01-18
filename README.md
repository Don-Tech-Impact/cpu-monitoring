# Finance Monitoring System

Infrastructure monitoring application built with Docker Compose, Flask, MySQL, and Nginx.

## Architecture

```
Client → Nginx (Reverse Proxy) → Flask App (3 replicas) → MySQL Database
```

- **Nginx**: Reverse proxy, load balancing, SSL termination
- **Flask**: REST API for server monitoring
- **MySQL**: Database for server metrics
- **Docker Compose**: Orchestration and networking

## Prerequisites

- Docker & Docker Compose
- Git

## Quick Start

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/finance-monitoring-system.git
cd finance-monitoring-system

# Create .env file (copy from .env.example)
cp .env.example .env

# Start services
make up

# View logs
make logs

# Test database connection
make test-connection
```

## Available Commands

```bash
make up                 # Start all services
make down               # Stop and remove containers
make logs               # View real-time logs
make shell              # SSH into web container
make verify             # Verify database initialization
make test-connection    # Test MySQL connection
```

## API Endpoints

- `GET /` - Health check
- `GET /health` - Service health status
- `GET /servers` - List all servers
- `POST /servers` - Add new server
- `PUT /servers/<id>` - Update server
- `DELETE /servers/<id>` - Delete server

## Environment Variables

See `.env.example` for all configuration options.

**Important**: Never commit `.env` file with sensitive credentials!

## Project Structure

```
.
├── app/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── db/
│   └── init.sql
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

## Deployment

For production, update:
- `.env` with secure credentials
- `docker-compose.yml` with production settings
- Nginx SSL certificates in `nginx/conf.d/`

## Troubleshooting

**Database connection error:**
```bash
make test-connection
docker-compose logs db
```

**Container won't start:**
```bash
docker-compose logs [service-name]
```

**Network issues:**
```bash
docker network inspect interview_finance_network
```

## Author

Abdulai Tamba Lebbie