#!/usr/bin/env bash
# AMI build recipe (UNTESTED draft). Run once on a clean Ubuntu 26.04 build instance, as the
# default `ubuntu` user with sudo. Produces the state we want every head/worker to boot with.
#
# Inputs (rsync them to the build instance first; nothing secret is needed):
#   RUNNER_SRC   directory with the runner source incl. tools/ (copied to ~harshav/benchmark-evals)
#   PUBKEYS      file with the public keys allowed to ssh in as harshav (ray-smoke's + ours)
# Optional: CYBERGYM_COMMIT (default d0ae0f0, the upstream commit our patches target)
# Afterwards run ami_scrub.sh, stop the instance, then create the image from the stopped instance.
set -euo pipefail
RUNNER_SRC="${RUNNER_SRC:?path to the runner source}"
PUBKEYS="${PUBKEYS:?file with public keys}"
CYBERGYM_COMMIT="${CYBERGYM_COMMIT:-d0ae0f0}"
EXPECT_RAY="2.59.0"
# Ray refuses to join nodes whose Python PATCH version differs (3.12.15 on the head vs 3.12.16 from the first
# AMI broke the first scale-up test). Pin it to what the head runs: `~/benchmark-evals/.venv/bin/python -V` there.
EXPECT_PYTHON="${EXPECT_PYTHON:-3.12.15}"
# base images the runner pulls by digest (DEFAULT_IMAGE in prepare.py is the second one). With Docker's
# containerd image store the image ID equals the manifest digest, so `docker images --digests` on the
# first VM showed pullable digests; the earlier "invalid reference format" came from shell quoting.
# AMI v2 was built from the previous version of this list (base-builder:latest, plus both digests that
# were present on the build instance); the exact digests in v2 are to be confirmed with
# `docker image inspect <ref>` on the first instance launched from it.
BASE_IMAGES=(
  "gcr.io/oss-fuzz-base/base-builder@sha256:8eda74a11e800aead5a041ee479a65b33dab3150d6e89e5694e2b6eb27be98fc"
  "gcr.io/oss-fuzz-base/base-builder@sha256:fba1033c6a64433642ab97b6ea987ddaa9938e06596c6cace1c786130fc1461b"
)

echo "== 1. user harshav (same name and home as the existing VMs: jobs carry absolute paths)"
id harshav >/dev/null 2>&1 || sudo useradd -m -s /bin/bash harshav
echo 'harshav ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-harshav >/dev/null
sudo chmod 440 /etc/sudoers.d/90-harshav
sudo install -d -m 700 -o harshav -g harshav /home/harshav/.ssh
sudo install -m 600 -o harshav -g harshav "$PUBKEYS" /home/harshav/.ssh/authorized_keys

echo "== 2. packages, docker, sysctl"
sudo apt-get update -y
sudo apt-get install -y docker.io git curl rsync python3
sudo systemctl enable --now docker
sudo usermod -aG docker harshav
printf 'vm.mmap_rnd_bits=28\n' | sudo tee /etc/sysctl.d/99-cybergym.conf >/dev/null
sudo sysctl -w vm.mmap_rnd_bits=28 >/dev/null

echo "== 3. runner source + upstream checkout pinned to ${CYBERGYM_COMMIT}"
sudo rsync -a --exclude .venv --exclude __pycache__ --exclude '*.egg-info' --exclude config/.env --exclude config/.bedrock_key \
  "${RUNNER_SRC%/}/" /home/harshav/benchmark-evals/
sudo chown -R harshav:harshav /home/harshav/benchmark-evals
sudo -iu harshav bash -euo pipefail <<INNER
[ -d ~/cybergym-e2e/.git ] || git clone https://github.com/sunblaze-ucb/cybergym-e2e.git ~/cybergym-e2e
git -C ~/cybergym-e2e checkout -q ${CYBERGYM_COMMIT}
# bootstrap_ec2.sh asks uv for "3.12", which now resolves to a newer patch than the head: run a pinned copy.
# The copy must live next to the original (it finds the repo root from its own location) and is removed after.
sed -e "s/uv python install 3.12/uv python install ${EXPECT_PYTHON}/" -e "s/--python 3.12 /--python ${EXPECT_PYTHON} /g" "\$HOME/benchmark-evals/scripts/bootstrap_ec2.sh" > "\$HOME/benchmark-evals/scripts/.bootstrap_pinned.sh"
grep -q "${EXPECT_PYTHON}" "\$HOME/benchmark-evals/scripts/.bootstrap_pinned.sh" || { echo "pinning the python version failed" >&2; exit 1; }
(cd ~/benchmark-evals && bash scripts/.bootstrap_pinned.sh); rm -f "\$HOME/benchmark-evals/scripts/.bootstrap_pinned.sh"   # uv, pinned Python, envs, patches, CLI
~/benchmark-evals/.venv/bin/python - <<PY
import platform, ray
assert ray.__version__ == "${EXPECT_RAY}", ray.__version__
assert platform.python_version() == "${EXPECT_PYTHON}", platform.python_version()
print("ray", ray.__version__, "python", platform.python_version())
PY
INNER

echo "== 4. base images"
for i in "${BASE_IMAGES[@]}"; do sudo -iu harshav docker pull "$i"; done

echo "== 5. network isolation: squid proxy + internal network, restart on every boot"
sudo -iu harshav bash -euo pipefail <<'INNER'
docker pull ubuntu/squid:latest
cd ~/cybergym-e2e/scripts
~/cybergym-e2e/.venv/bin/python -m firewall start --which run --domain bedrock-runtime.us-east-1.amazonaws.com
# 'always', not 'unless-stopped': a container stopped by hand (e.g. before imaging) would stay stopped after boot
docker update --restart always cybergym-proxy
docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}'   # expect 172.18.0.1
INNER

echo "== done. next: ami_scrub.sh, stop the instance, create the image."
