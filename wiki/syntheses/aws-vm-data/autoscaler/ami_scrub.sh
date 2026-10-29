#!/usr/bin/env bash
# Remove secrets and per-instance state before imaging (UNTESTED draft). Run on the build instance
# as `ubuntu`, then STOP the instance (do not reboot it) and create the image from the stopped instance.
set -euo pipefail
# secrets and tokens that must never be in an image
sudo rm -f /home/harshav/benchmark-evals/config/.env /home/harshav/benchmark-evals/config/.bedrock_key
sudo rm -rf /home/harshav/.ray /home/harshav/secrets /home/harshav/.aws /home/harshav/.config /home/harshav/.codex /home/harshav/.cache/huggingface
sudo rm -rf /root/.aws /root/.ray /home/ubuntu/.aws /home/ubuntu/.ray
# run state
sudo rm -rf /home/harshav/cybergym-work /tmp/ray* /tmp/*.log
sudo rm -f /home/harshav/.bash_history /home/ubuntu/.bash_history /root/.bash_history
sudo rm -f /home/harshav/.ssh/known_hosts
# docker: do NOT stop containers by hand (the shutdown does it cleanly and the proxy restarts on boot); drop client credentials only
sudo rm -f /home/harshav/.docker/config.json
# per-instance identity regenerated on first boot
sudo cloud-init clean --logs --seed
sudo truncate -s 0 /etc/machine-id
sudo rm -f /etc/ssh/ssh_host_*
sudo journalctl --rotate >/dev/null 2>&1 || true; sudo journalctl --vacuum-time=1s >/dev/null 2>&1 || true
# the build instance's own login key must not survive either: the image gets keys from PUBKEYS only
sudo rm -f /home/ubuntu/.ssh/authorized_keys
echo "scrubbed. stop the instance now (aws ec2 stop-instances), then create the image."
echo "--- leftover secret-looking files (should print nothing):"
sudo find /home /root -xdev \( -name '.env' -o -name '*.pem' -o -name '*_key' -o -name 'auth_token' -o -name 'credentials' \) 2>/dev/null | grep -v '/\.cache/' || true
