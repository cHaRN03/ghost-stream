# 🌌 Ghost Stream: Real-Time Live Streaming System

## 📌 Overview

Ghost Stream is a **real-time microservice-based live streaming system** designed for low-latency, stateless, and failure-first architecture. It allows users to start a live video stream that exists only while it is being broadcasted. No recording, replay, or storage is allowed. If the streamer disconnects, the stream immediately dies and disappears from the live list.

---

## 📦 Project Structure

The system is built using a **microservices architecture**, with the following components:

### 🧠 Control Plane
- **Control Service**: Manages stream creation, termination, and metadata. Uses **gRPC** for communication and stores **in-memory metadata** (stream IDs, relay assignments, etc.). It **does not handle media traffic**.

### 🚀 Data Plane
- **Ingest Gateway**: Accepts live video streams via **QUIC** and forwards media chunks to the Relay Service.
- **Relay Service**: Receives media chunks and **fans them out** to connected viewers. It is **stateless**, holds only in-memory viewer connections, and **aggressively drops packets** when overloaded.
- **Viewer Gateway**: Allows users to request the list of active streams and obtain a relay address for joining. Viewers connect directly to the relay via **QUIC** for media delivery.

---

## 🧠 Architecture Requirements

###  Control Plane
- **Control Service**:
  - Responsible for:
    - Creating streams
    - Ending streams
    - Listing currently live streams
    - Assigning relay nodes
  - Uses **gRPC**
  - Stores **in-memory metadata**
  - **Never handles live media traffic**

### 🚀 Data Plane
- **Ingest Gateway**:
  - Accepts live connections using **QUIC**
  - Forwards media chunks to Relay Services
- **Relay Services**:
  - Stateless
  - Hold only in-memory viewer connections
  - Aggressively drop packets when overloaded
  - Allowed to fail; viewers may be disconnected without recovery
- **Viewer Gateway**:
  - Allows users to request the list of active streams
  - Provides relay addresses for joining

---

## 🚨 Failure Behavior

- **Streamer disconnect → Stream ends instantly**
- **Viewer bad network → Only that viewer suffers**
- **Relay crash → Affected viewers disconnect**
- **Control service crash → Existing streams continue temporarily, but new ones cannot start**
- **Traffic spikes → Reject excess viewers instead of slowing the stream**

---

## 📦 Implementation Constraints

- Use **microservices** with **one Docker container per service**
- All services must be **deployable locally first using Docker**
- After local validation, deploy the containers onto a **single low-cost AWS instance** for testing
- Avoid **persistent databases** in version one; use only **in-memory state**
- Do **not implement** chat, reactions, recording, authentication, or adaptive bitrate in the first version

---

## 🎯 Goals

The goal of this project is to learn real-world system design principles, including:

- Real-time streaming pipelines
- **QUIC vs. traditional transport tradeoffs**
- **Control plane vs. hot-path separation**
- **Stateless horizontal scaling**
- **Failure-first architecture thinking**
- **Containerized microservice deployment**
- **Basic AWS hosting for distributed services**

---

## 🚀 Getting Started

### 🐳 Prerequisites
- Docker
- Python 3.10+
- gRPC
- QUIC (e.g., via `quic-go` or similar)

### 📁 Project Structure
```
ghost-stream/
├── control-service/
├── ingest-gateway/
├── relay-service/
├── viewer-gateway/
├── README.md
├── Dockerfile
└── docker-compose.yml
```

### 🐳 Run Locally
```bash
docker-compose up
```