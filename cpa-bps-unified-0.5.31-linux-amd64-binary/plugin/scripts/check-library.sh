#!/bin/sh
# Load the plugin in a NEW temporary container using the installed CPA image.
# No production volumes, credentials, ports or network are provided.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
container=${1:-cpamp-cli-proxy-api-1}
case "$container" in *[!a-zA-Z0-9_.-]*|'') echo 'Invalid container name' >&2; exit 2;; esac
test -s dist/cpa-bps.so
test -s dist/native-smoke
(cd dist && sha256sum -c SHA256SUMS)
# BuildKit's local exporter may leave the output directory accessible only to
# root. The isolated check runs as UID 65534 and needs traversal/read/execute.
# Change only generated public build artifacts, never the parent or credentials.
chmod 0755 dist dist/native-smoke
chmod 0644 dist/cpa-bps.so
image_id=$(docker inspect --format '{{.Image}}' "$container")
platform=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image_id")
if test "$platform" != linux/amd64; then
    echo "Expected linux/amd64; installed CPA image is $platform" >&2
    exit 1
fi
docker run --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user 65534:65534 \
    --memory 256m --pids-limit 64 \
    --mount "type=bind,src=$(pwd)/dist,dst=/plugin-check,readonly" \
    --entrypoint /plugin-check/native-smoke \
    "$image_id" /plugin-check/cpa-bps.so
printf '\nLibrary loads in the installed image. Actual CPA registration and BPS OAuth still need acceptance.\n'
