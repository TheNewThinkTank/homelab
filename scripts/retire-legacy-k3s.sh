#!/usr/bin/env bash
set -euo pipefail

[[ "$EUID" -eq 0 && "$(uname -s)" == Linux ]] || {
    printf 'Run this only as root on the Linux PN51 host.\n' >&2
    exit 1
}
[[ "$(hostname)" == gus-MINIPC-PN51 || "$(hostname)" == pn51 ]] || {
    printf 'Refusing an unexpected host.\n' >&2
    exit 1
}

backup=/var/backups/homelab/legacy-k3s
[[ ! -L "$backup" && ! -L /var/backups/homelab ]] || exit 1
if [[ -f "$backup/complete" ]]; then
    pushd "$backup" >/dev/null
    sha256sum --check state.tar.sha256 >/dev/null
    popd >/dev/null
    printf 'Legacy archive is already complete and verified.\n'
    exit 0
fi
[[ -d /var/lib/rancher/k3s/server && -x /usr/local/bin/k3s-killall.sh ]] || {
    printf 'No supported legacy K3s installation found; nothing was removed.\n' >&2
    exit 1
}
mkdir -p "$backup"
chmod 0700 "$backup"
[[ ! -e "$backup/state.tar" && ! -e "$backup/state.tar.partial" ]] || {
    printf 'An incomplete prior archive exists; inspect it before retrying.\n' >&2
    exit 1
}

was_enabled=0
systemctl is-enabled --quiet k3s && was_enabled=1
quiesced=0
restore_on_failure() {
    exit_code=$?
    if [[ "$quiesced" -eq 1 ]]; then
        if [[ "$was_enabled" -eq 1 ]]; then
            systemctl enable --now k3s || true
        else
            systemctl start k3s || true
        fi
    fi
    exit "$exit_code"
}
trap restore_on_failure ERR

/usr/local/bin/k3s kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml \
    get all,ingress,pv,pvc,nodes -A -o json > "$backup/resources.json"
python3 - "$backup/resources.json" <<'PY'
import json
import sys
from pathlib import Path

with Path(sys.argv[1]).open() as stream:
    resources = json.load(stream)["items"]
if len([item for item in resources if item["kind"] == "Node"]) != 1:
    raise SystemExit("Refusing an incomplete backup of a multi-node legacy cluster.")
root = Path("/var/lib/rancher/k3s/storage")
if root.resolve() != root:
    raise SystemExit("Legacy storage is symlinked; back it up explicitly before retirement.")
for item in resources:
    if item["kind"] != "PersistentVolume":
        continue
    specification = item["spec"]
    volume_path = specification.get("hostPath", specification.get("local", {})).get("path")
    if not volume_path or not Path(volume_path).resolve().is_relative_to(root):
        raise SystemExit("Legacy PV storage is outside the supported archive; back it up first.")
PY
systemctl stop k3s
quiesced=1
/usr/local/bin/k3s-killall.sh

sources=()
for candidate in \
    etc/rancher/k3s \
    var/lib/rancher/k3s/server \
    var/lib/rancher/k3s/storage \
    etc/systemd/system/k3s.service \
    etc/systemd/system/k3s.service.env; do
    [[ ! -e "/$candidate" ]] || sources+=("$candidate")
done
umask 077
tar --acls --xattrs --numeric-owner -C / -cf "$backup/state.tar.partial" "${sources[@]}"
mv "$backup/state.tar.partial" "$backup/state.tar"
sync -f "$backup/state.tar"
pushd "$backup" >/dev/null
sha256sum state.tar > state.tar.sha256
sha256sum --check state.tar.sha256 >/dev/null
popd >/dev/null
systemctl disable k3s
printf 'Cold legacy archive completed.\n' > "$backup/complete"
trap - ERR
printf 'Cold legacy archive completed; original files were preserved.\n'
