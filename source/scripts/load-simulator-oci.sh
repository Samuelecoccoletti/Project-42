#!/usr/bin/env bash
# Course .tar is OCI layout, not a "docker save" tarball.
# "docker load" fails; import with skopeo (including via container).

set -euo pipefail

TAR_PATH="${SIMULATOR_OCI_TAR:-$HOME/Desktop/progetto mecella/seismic-signal-simulator-oci.tar}"

if [[ ! -f "$TAR_PATH" ]]; then
  echo "File not found: $TAR_PATH"
  echo "Set SIMULATOR_OCI_TAR=/path/to/seismic-signal-simulator-oci.tar"
  exit 1
fi

echo "Import into Docker from: $TAR_PATH"

docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$TAR_PATH:/image.tar:ro" \
  quay.io/skopeo/stable:latest \
  copy oci-archive:/image.tar \
  docker-daemon:docker.io/library/seismic-signal-simulator:multiarch_v1

echo "OK. Image: seismic-signal-simulator:multiarch_v1"
