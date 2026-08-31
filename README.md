# Media Screener

A containerized REST API for content moderation, detecting potentially unsafe content in images, videos, and documents.

## Features

- **Image detection** — JPG, PNG, WebP, GIF, BMP
- **Video scanning** — MP4, WebM, AVI, MOV, MKV (configurable frame sampling)
- **Document scanning** — PDF (page renders), DOCX & PPTX (embedded images)
- **Two endpoints:**
  - `POST /infer` — Full detection with bounding boxes
  - `POST /classify` — Safe/unsafe classification with early exit option

## Prerequisites

- Podman (or Docker)
- `curl`, `sha256sum`, and internet access to GitHub's release asset API when provisioning the model

---

## Run Standalone on a Single Host

The scripts below run the screener on one machine, bound to loopback. This is a development and single-host convenience; it is not a deployment system, and it assumes something else mediates access to the port.

### 1. Create a dedicated service user (recommended)

For security, run the API under a dedicated unprivileged user:

```bash
# Create user without login shell
sudo useradd -r -s /usr/sbin/nologin -m -d /opt/media-screener media-screener

# Or use an existing API service user if you have one
```

### 2. Clone and configure

```bash
# Switch to service user
sudo -u media-screener -s /bin/bash
cd /opt/media-screener

# Clone repository
git clone https://github.com/cmiic/media-screener-api.git .

# Configure deployment
cp deploy/.env.example deploy/.env
nano deploy/.env  # Adjust settings as needed
```

### 3. Provision, build, and run

```bash
# Make scripts executable
chmod +x deploy/*.sh scripts/*.sh

# Download and verify the model outside the container image
./scripts/provision-model.sh models/640m.onnx

# Build container
./deploy/build.sh

# Start container (will auto-restart on reboot)
./deploy/run.sh
```

### 4. Verify

```bash
# Check container status
podman ps

# View logs
./deploy/logs.sh

# Test API
curl http://localhost:8080/docs
```

---

## Standalone Scripts

| Script | Purpose |
| ------- | ------- |
| `scripts/provision-model.sh` | Download and verify the external model |
| `deploy/build.sh` | Build container image |
| `deploy/run.sh` | Start container with hardening |
| `deploy/stop.sh` | Stop and remove container |
| `deploy/logs.sh` | View container logs (follow mode) |

### Configuration

All settings are in `deploy/.env`:

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `IMAGE_NAME` | media-screener | Container image name |
| `CONTAINER_NAME` | media-screener | Container instance name |
| `HOST_PORT` | 8080 | Port on host |
| `HOST_IP` | 127.0.0.1 | Host IP to bind; keep loopback unless access is mediated |
| `MEMORY_LIMIT` | 2g | Container memory limit |
| `CPU_LIMIT` | 2 | Container CPU limit |
| `MODEL_FILE` | `models/640m.onnx` | Host path to the provisioned model |
| `MAX_UPLOAD_SIZE` | 209715200 | Maximum buffered upload bytes |
| `MAX_PDF_PAGES` | 100 | Maximum PDF pages |
| `MAX_PDF_RENDERED_PIXELS` | 100000000 | Maximum cumulative PDF render pixels |
| `MAX_VIDEO_DURATION_SECONDS` | 600 | Maximum video duration |
| `MAX_VIDEO_SAMPLED_FRAMES` | 120 | Maximum sampled video frames |
| `MAX_DOCUMENT_IMAGES` | 100 | Maximum DOCX/PPTX images |
| `MAX_CONCURRENT_SCANS` | 1 | Maximum active parser/inference workers |
| `SCAN_QUEUE_TIMEOUT_SECONDS` | 5 | Maximum wait for a worker slot |
| `UPLOAD_TIMEOUT_SECONDS` | 10 | Maximum upload read duration |
| `PROCESSING_TIMEOUT_SECONDS` | 40 | Maximum parser/inference response wait |

---

## API Usage

```bash
# Classify image
curl -F file=@image.jpg http://localhost:8080/classify

# Classify with custom threshold
curl -F file=@image.jpg "http://localhost:8080/classify?threshold=0.5"

# Classify video (sample every 5 seconds, full scan)
curl -F file=@video.mp4 "http://localhost:8080/classify?sample_interval=5&early_exit=false"

# Full detection on PDF
curl -F file=@document.pdf http://localhost:8080/infer
```

### Interactive Documentation

Swagger UI: `http://<host>:<port>/docs`

---

## Endpoints

### POST /classify

Classify file as safe or unsafe.

**Query Parameters:**

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `threshold` | 0.35 | Minimum confidence for unsafe |
| `sample_interval` | 5.0 | Seconds between video frames (0.1 to 60) |
| `early_exit` | true | Stop on first unsafe detection |

**Response (image):**

```json
{
  "format": "image",
  "unsafe": true,
  "confidence": 0.82,
  "detected_classes": ["FEMALE_BREAST_EXPOSED"]
}
```

**Response (video):**

```json
{
  "format": "video",
  "unsafe": true,
  "confidence": 0.82,
  "detected_classes": ["FEMALE_BREAST_EXPOSED"],
  "frames_checked": 3,
  "total_frames": 30,
  "first_unsafe_at": 4.0
}
```

**Response (PDF):**

```json
{
  "format": "pdf",
  "unsafe": false,
  "confidence": 0.0,
  "detected_classes": [],
  "pages_checked": 5,
  "total_pages": 5,
  "first_unsafe_at": null
}
```

### POST /infer

Full detection with bounding boxes.

**Response:**

```json
{
  "format": "image",
  "prediction": [
    {"class": "FACE_FEMALE", "score": 0.85, "box": [x, y, w, h]}
  ]
}
```

---

## Supported File Types

| Type | Extensions | Processing |
| ---- | ---------- | ---------- |
| Image | jpg, jpeg, png, webp, gif, bmp | Full scan |
| Video | mp4, webm, avi, mov, mkv | Frame sampling |
| PDF | pdf | Page rendering (150 DPI) |
| Word | docx | Embedded images |
| PowerPoint | pptx | Embedded images |

---

## Testing

```bash
# Place test files in .testfiles/
./test.sh

# Custom settings
API_URL=http://localhost:8080 THRESHOLD=0.5 ./test.sh
```

---

## Management

### Update deployment

```bash
sudo -u media-screener -s /bin/bash
cd /opt/media-screener

git pull
./deploy/build.sh
./deploy/stop.sh
./deploy/run.sh
```

### View status

```bash
podman ps                    # Running containers
podman logs media-screener   # Container logs
podman stats media-screener  # Resource usage
```

---

## Security

### Container hardening

The `deploy/run.sh` script applies:

- Read-only root filesystem
- Dropped all Linux capabilities
- No new privileges
- Memory and CPU limits
- Auto-restart on failure/reboot

### Network considerations

- This scanner is a private internal service and must not be exposed directly to untrusted networks.
- The standalone scripts bind the host port to loopback (`127.0.0.1`) by default. The container listens on all container interfaces so published-port routing continues to work.
- The service has no built-in authentication. Keep same-host and Compose traffic on a private network.
- Before any cross-host deployment, require TLS plus service authentication at a reverse proxy or gateway; prefer mutually authenticated TLS for service-to-service traffic and apply rate limits there.
- Upload, parser, concurrency, and timeout limits are defense-in-depth controls and should remain below the calling client's and any proxy's limits.
- The default queue, upload, and processing deadlines total 55 seconds. Whatever calls this service must allow at least that long, or it will give up while classification is still running and the worker slot stays held until the underlying work stops.

---

## Development

Open in VS Code with DevContainers extension for pre-configured development environment.

### Dependencies

```bash
# Install locked dependencies locally
uv sync --locked

# Provision the model outside the application image
./scripts/provision-model.sh models/640m.onnx

# Run API locally
MODEL_PATH="$PWD/models/640m.onnx" uv run uvicorn app:app --reload --host 127.0.0.1 --port 8080
```

### API Documentation

Documentation is auto-generated from the running API and published to GitHub Pages on every push to `main`.

View at: <https://cmiic.github.io/media-screener-api/>

---

## License

Copyright (C) 2026 Christoph Stadlbauer. This project is licensed under the [GNU Affero General Public License, version 3 or later](LICENSE).

NudeNet's `v3` source tree contains the AGPL-3.0 license, although its `setup.py` and PyPI metadata identify it as MIT. This service conservatively treats NudeNet 3.4.2 as AGPL-licensed and licenses the combined application under AGPL-3.0-or-later. The running API exposes its Corresponding Source location at `GET /source` and in the OpenAPI documentation. For deployed releases, that repository must be public and retain the exact source tag corresponding to the running image.

PDF page rendering uses the Apache-2.0/BSD-3-Clause licensed `pypdfium2` wrapper and BSD-style licensed PDFium. Binary distributions must retain the license notices shipped with these dependencies.

Every application image collects the exact installed Python dependency licenses and a versioned notice manifest under `/app/THIRD_PARTY_LICENSES`; package-native copies also remain under `/app/.venv/lib/python3.14/site-packages/`.

### Model

This API uses the `640m.onnx` model (YOLOv8m, 640x640 resolution) for better accuracy. The default `320n` model is faster but less accurate.

- Source: [NudeNet v3.4 `640m.onnx` release asset](https://github.com/notAI-tech/NudeNet/releases/download/v3.4-weights/640m.onnx)
- Artifact: `640m.onnx`
- Size: `103538690` bytes
- SHA-256: `04fe3d77980780c1f8297dc6d7f942fd5b3abe6942a188f742a85241e4f634eb`
- Provisioning: `scripts/provision-model.sh` downloads GitHub release asset API ID `176832019` anonymously as `application/octet-stream` and rejects bytes that do not match the pinned checksum
- Runtime: The provisioned host file is mounted read-only at `/models/640m.onnx`; startup fails if it is absent or has the wrong checksum
- Distribution: The model is not stored in Git and is not included in the application container image; operators obtain it directly from NudeNet. The build also removes the `320n.onnx` model bundled in the NudeNet package and ONNX Runtime's sample models.
- License basis: The release asset is published in NudeNet's AGPL-licensed repository without separate model terms; this service follows that repository license
