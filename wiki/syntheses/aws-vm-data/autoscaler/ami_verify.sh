#!/usr/bin/env bash
# Run on an instance launched from the new AMI, as harshav (UNTESTED draft). Exits 1 on any failure.
fail=0; ok(){ echo "ok   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
[[ "$(id -un)" == harshav ]] && ok "user harshav" || bad "not harshav"
docker ps >/dev/null 2>&1 && ok "docker without sudo" || bad "docker access"
[[ "$(sudo sysctl -n vm.mmap_rnd_bits)" == 28 ]] && ok "mmap_rnd_bits 28" || bad "mmap_rnd_bits"
[[ "$(docker inspect -f '{{.State.Running}}' cybergym-proxy 2>/dev/null)" == true && "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' cybergym-proxy 2>/dev/null)" == always ]] && ok "squid proxy running, restart=always" || bad "proxy not running or restart policy not always"
gw=$(docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null)
[[ "$gw" == 172.18.0.1 ]] && ok "gateway $gw" || bad "gateway '$gw'"
v=$(~/benchmark-evals/.venv/bin/python -c 'import ray;print(ray.__version__)' 2>/dev/null)
[[ "$v" == 2.59.0 ]] && ok "ray $v" || bad "ray '$v'"
[[ "$(docker images -q 'gcr.io/oss-fuzz-base/base-builder' | wc -l)" -ge 1 ]] && ok "base-builder image" || bad "base image"
~/benchmark-evals/.venv/bin/cybergym-eval --help >/dev/null 2>&1 && ok "cybergym-eval CLI" || bad "CLI"
for f in ~/benchmark-evals/config/.env ~/benchmark-evals/config/.bedrock_key ~/.ray/auth_token; do [[ -e "$f" ]] && bad "secret present: $f" || ok "absent $f"; done
curl -s -m 3 -o /dev/null -w '%{http_code}' -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' http://169.254.169.254/latest/api/token | grep -q 200 && ok "IMDSv2 reachable" || bad "IMDS"
exit $fail
