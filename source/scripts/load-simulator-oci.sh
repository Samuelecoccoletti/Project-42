#!/usr/bin/env bash
# Il file .tar del corso è in formato OCI layout, non "docker save".
# "docker load" fallisce; serve importare con skopeo (anche via container).

set -euo pipefail

TAR_PATH="${SIMULATOR_OCI_TAR:-$HOME/Desktop/progetto mecella/seismic-signal-simulator-oci.tar}"

if [[ ! -f "$TAR_PATH" ]]; then
  echo "File non trovato: $TAR_PATH"
  echo "Imposta SIMULATOR_OCI_TAR=/percorso/al/seismic-signal-simulator-oci.tar"
  exit 1
fi

echo "Import in Docker da: $TAR_PATH"

docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$TAR_PATH:/image.tar:ro" \
  quay.io/skopeo/stable:latest \
  copy oci-archive:/image.tar \
  docker-daemon:docker.io/library/seismic-signal-simulator:multiarch_v1

echo "OK. Immagine: seismic-signal-simulator:multiarch_v1"
