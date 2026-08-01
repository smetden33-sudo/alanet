#!/usr/bin/env bash
set -Euo pipefail

umask 077

token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env | tr -d '\r\n')"
telegram_token="$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' /opt/alanet/deploy/.env | tr -d '\r\n')"
telegram_admin_chat_id="$(sed -n 's/^TELEGRAM_ADMIN_CHAT_ID=//p' /opt/alanet/deploy/.env | tr -d '\r\n')"
auth=(-H "Authorization: Bearer ${token}")

monitor_state_dir="/var/lib/alanet-monitor"
monitor_state_file="${monitor_state_dir}/health.state"
monitor_summary_file="${monitor_state_dir}/health.summary"
node_registry_file="${ALANET_NODE_REGISTRY:-/opt/alanet/infra/node-registry.json}"
load_state_file="${monitor_state_dir}/load.failures"
api_state_file="${monitor_state_dir}/api.failures"
ports_state_file="${monitor_state_dir}/ports.failures"
load_failure_threshold="${ALANET_LOAD_FAILURE_THRESHOLD:-3}"
api_failure_threshold="${ALANET_API_FAILURE_THRESHOLD:-3}"
ports_failure_threshold="${ALANET_PORTS_FAILURE_THRESHOLD:-3}"
mkdir -p "${monitor_state_dir}"

status_rank=0
status_name="ok"
warnings=()
incidents=()

send_alert() {
  local message="$1"
  [[ -n "${telegram_token}" && -n "${telegram_admin_chat_id}" ]] || return 0
  curl --silent --show-error --max-time 15 \
    --data-urlencode "chat_id=${telegram_admin_chat_id}" \
    --data-urlencode "text=${message}" \
    "https://api.telegram.org/bot${telegram_token}/sendMessage" >/dev/null || true
}

raise_status() {
  local rank="$1" name="$2"
  if (( rank > status_rank )); then
    status_rank="${rank}"
    status_name="${name}"
  fi
}

add_warning() {
  warnings+=("$1")
  raise_status 1 "warning"
}

add_degraded() {
  incidents+=("$1")
  raise_status 2 "degraded"
}

add_incident() {
  incidents+=("$1")
  raise_status 3 "incident"
}

failure_count() {
  local state_file="$1" value
  value="$(cat "${state_file}" 2>/dev/null || printf '0')"
  [[ "${value}" =~ ^[0-9]+$ ]] || value=0
  value=$((value + 1))
  printf '%s\n' "${value}" > "${state_file}"
  printf '%s' "${value}"
}

clear_failure() {
  rm -f "$1"
}

check_http() {
  local name="$1" url="$2" expected="$3" status
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${url}" || printf '000')"
  printf '%s=%s\n' "${name}" "${status}"
  [[ "${status}" == "${expected}" ]]
}

check_http_immediate() {
  local name="$1" url="$2" expected="$3" impact="$4"
  if ! check_http "${name}" "${url}" "${expected}"; then
    add_incident "${name}: HTTP check failed. Expected ${expected}. Impact: ${impact}"
  fi
}

check_http_threshold() {
  local name="$1" url="$2" expected="$3" state_file="$4" threshold="$5" impact="$6" status failures
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${url}" || printf '000')"
  printf '%s=%s\n' "${name}" "${status}"
  if [[ "${status}" == "${expected}" ]]; then
    clear_failure "${state_file}"
    return 0
  fi
  failures="$(failure_count "${state_file}")"
  printf '%s_failure=%s/%s\n' "${name}" "${failures}" "${threshold}"
  if (( failures >= threshold )); then
    add_degraded "${name}: HTTP ${status}, expected ${expected} (${failures}/${threshold}). Impact: ${impact}"
  else
    add_warning "${name}: transient HTTP ${status}, expected ${expected} (${failures}/${threshold})."
  fi
}

finish_healthcheck() {
  local previous_state summary message
  previous_state="$(cat "${monitor_state_file}" 2>/dev/null || true)"
  {
    printf 'status=%s\n' "${status_name}"
    for item in "${warnings[@]}"; do
      printf 'warning=%s\n' "${item}"
    done
    for item in "${incidents[@]}"; do
      printf 'problem=%s\n' "${item}"
    done
  } > "${monitor_summary_file}"
  printf '%s\n' "${status_name}" > "${monitor_state_file}"

  if (( status_rank >= 2 )); then
    if [[ "${previous_state}" != "${status_name}" ]]; then
      message="ALANET ${status_name^^}
"
      for item in "${incidents[@]}"; do
        message+="- ${item}
"
      done
      if ((${#warnings[@]} > 0)); then
        message+="Warnings:
"
        for item in "${warnings[@]}"; do
          message+="- ${item}
"
        done
      fi
      send_alert "${message}"
    fi
    exit 1
  fi

  if [[ "${previous_state}" == "degraded" || "${previous_state}" == "incident" ]]; then
    send_alert "ALANET RESOLVED
Health-check is passing again. Services recovered."
  fi
  exit 0
}

trap finish_healthcheck EXIT

check_http_immediate site https://alanet.ru/ 200 "public landing page may be unavailable"
check_http_immediate account https://account.alanet.ru/ 200 "customer cabinet may be unavailable"
check_http_threshold api https://api.alanet.ru/health 200 "${api_state_file}" "${api_failure_threshold}" "payments, Telegram webhook and provisioning may be degraded"
check_http_immediate panel https://panel.alanet.ru/ 200 "Remnawave panel may be unavailable"
check_http_immediate subscription_root https://sub.alanet.ru/ 404 "subscription page routing may expose an unexpected root page"
check_http_immediate sensitive_path https://alanet.ru/.env 404 "sensitive files may be publicly exposed"

tls_failed=0
for domain in alanet.ru account.alanet.ru api.alanet.ru panel.alanet.ru sub.alanet.ru; do
  if echo | openssl s_client -connect "${domain}:443" -servername "${domain}" 2>/dev/null \
    | openssl x509 -checkend 604800 -noout >/dev/null; then
    printf 'tls_%s=valid_7d\n' "${domain}"
  else
    printf 'tls_%s=failed\n' "${domain}"
    tls_failed=1
  fi
done
if (( tls_failed == 0 )); then
  printf 'tls_certificates=valid_7d\n'
else
  add_incident "TLS certificate check failed. Impact: clients may see certificate errors or fail to connect."
fi

disk_percent="$(df -P / | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
memory_percent="$(free | awk '/^Mem:/ {printf "%d", ($3/$2)*100}')"
load_1m="$(awk '{print $1}' /proc/loadavg)"
cpu_count="$(nproc)"
printf 'resources=disk_%s%%_memory_%s%%_load_%s_cpus_%s\n' "${disk_percent}" "${memory_percent}" "${load_1m}" "${cpu_count}"
if (( disk_percent >= 90 )); then
  add_incident "Disk usage is ${disk_percent}%. Impact: database, Docker builds and logs may fail."
fi
if (( memory_percent >= 95 )); then
  add_incident "Memory usage is ${memory_percent}%. Impact: services may restart or become slow."
fi
if ! awk -v load_value="${load_1m}" -v cpus="${cpu_count}" 'BEGIN { exit !(load_value < cpus * 2) }'; then
  load_failures="$(failure_count "${load_state_file}")"
  printf 'load_spike=%s/%s\n' "${load_failures}" "${load_failure_threshold}"
  if (( load_failures >= load_failure_threshold )); then
    add_degraded "Load is ${load_1m} on ${cpu_count} CPU (${load_failures}/${load_failure_threshold}). Impact: responses may be slow."
  else
    add_warning "Transient load spike ${load_1m} on ${cpu_count} CPU (${load_failures}/${load_failure_threshold})."
  fi
else
  clear_failure "${load_state_file}"
fi

if webhook_json="$(curl --fail --silent --show-error "https://api.telegram.org/bot${telegram_token}/getWebhookInfo" 2>/dev/null)"; then
  webhook_url="$(jq -r '.result.url // empty' <<<"${webhook_json}")"
  if [[ "${webhook_url}" == "https://api.alanet.ru/webhooks/telegram" ]]; then
    printf 'telegram_webhook=200\n'
  else
    printf 'telegram_webhook=wrong_url\n'
    add_incident "Telegram webhook points to '${webhook_url:-empty}'. Impact: bot may not receive updates."
  fi
else
  printf 'telegram_webhook=failed\n'
  add_incident "Telegram webhook status check failed. Impact: bot delivery state is unknown."
fi

if nodes_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/nodes 2>/dev/null)"; then
  if [[ -f "${node_registry_file}" ]]; then
    mapfile -t expected_nodes < <(jq -r '.nodes[] | select(.status == "active") | .node_name' "${node_registry_file}")
  else
    expected_nodes=(ALANET-FIN-01 ALANET-DE-1 ALANET-CZ-1 ALANET-SE-1 ALANET-PL-1 ALANET-ES-1 ALANET-LV-1)
  fi
  for node_name in "${expected_nodes[@]}"; do
    connected="$(jq -r --arg name "${node_name}" '(.response | if type == "array" then . else (.nodes // []) end) | map(select(.name == $name))[0].isConnected // false' <<<"${nodes_json}")"
    printf '%s_connected=%s\n' "${node_name,,}" "${connected}"
    if [[ "${connected}" != "true" ]]; then
      add_degraded "Node ${node_name} is not connected in Remnawave. Impact: this location may not provision or serve clients."
    fi
  done
  printf 'nodes_checked=%s\n' "${#expected_nodes[@]}"
else
  printf 'remnawave_nodes_api=failed\n'
  add_incident "Cannot query Remnawave /api/nodes. Impact: node state and provisioning visibility are unknown."
fi

if hosts_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/hosts 2>/dev/null)"; then
  host_count=0
  failed_hosts=()
  while IFS=$'\t' read -r remark address port; do
    [[ -n "${address}" && -n "${port}" ]] || continue
    host_count=$((host_count + 1))
    label="${remark:-${address}:${port}}"
    if timeout 5 bash -c 'cat < /dev/null > /dev/tcp/"$0"/"$1"' "${address}" "${port}"; then
      printf 'host_port_ok=%s_%s_%s\n' "${label}" "${address}" "${port}"
    else
      printf 'host_port_failed=%s_%s_%s\n' "${label}" "${address}" "${port}"
      failed_hosts+=("${label} ${address}:${port}")
    fi
  done < <(jq -r '(.response // [])[] | select((.isDisabled // false) == false) | [(.remark // .name // "host"), .address, (.port | tostring)] | @tsv' <<<"${hosts_json}")
  if (( host_count == 0 )); then
    add_incident "No active Remnawave hosts found. Impact: subscriptions may contain no usable locations."
  elif ((${#failed_hosts[@]} == 0)); then
    clear_failure "${ports_state_file}"
  else
    port_failures="$(failure_count "${ports_state_file}")"
    printf 'host_ports_failure=%s/%s\n' "${port_failures}" "${ports_failure_threshold}"
    if (( port_failures >= ports_failure_threshold )); then
      add_degraded "Host ports unavailable (${port_failures}/${ports_failure_threshold}): ${failed_hosts[*]}. Impact: affected locations may not connect."
    else
      add_warning "Transient host-port failure (${port_failures}/${ports_failure_threshold}): ${failed_hosts[*]}."
    fi
  fi
  printf 'hosts_checked=%s\n' "${host_count}"
else
  printf 'remnawave_hosts_api=failed\n'
  add_incident "Cannot query Remnawave /api/hosts. Impact: host-port monitoring is unavailable."
fi

subscription_url="$(docker exec alanet-billing-db-1 psql -U billing -d billing -Atq -c "select subscription_url from subscriptions order by starts_at desc limit 1" | tr -d '\r' || true)"
if [[ -z "${subscription_url}" ]]; then
  add_incident "No subscription URL found in billing database. Impact: subscription validation cannot run."
else
  if ! check_http subscription "${subscription_url}" 200; then
    add_incident "Latest subscription URL is not reachable. Impact: clients may not update subscriptions."
  elif curl --fail --silent --show-error --user-agent 'v2rayN/7.0' "${subscription_url}" > /tmp/alanet-client-subscription; then
    if grep -q '^vless://' /tmp/alanet-client-subscription; then
      cp /tmp/alanet-client-subscription /tmp/alanet-client-subscription.decoded
    else
      tr -d '\r\n' < /tmp/alanet-client-subscription | base64 -d > /tmp/alanet-client-subscription.decoded 2>/dev/null || true
    fi
    if grep -q '^vless://' /tmp/alanet-client-subscription.decoded 2>/dev/null; then
      printf 'vless_subscription=valid\n'
    else
      add_incident "Latest subscription does not contain VLESS links. Impact: clients may receive invalid configuration."
    fi
  else
    add_incident "Cannot download latest subscription body. Impact: clients may not update subscriptions."
  fi
fi

if ss -ltn | grep -q ':443 '; then
  printf 'https_listener=443\n'
else
  add_incident "Local HTTPS listener 443 is missing. Impact: public HTTPS may be down."
fi
if ss -ltn | grep -q ':8443 '; then
  printf 'fin_xray_listener=8443\n'
else
  add_degraded "Local Finland Xray listener 8443 is missing. Impact: Finland location may be down."
fi

container_failed=0
for container in \
  alanet-web-1 alanet-api-1 alanet-worker-1 alanet-caddy-1 \
  alanet-billing-db-1 alanet-billing-redis-1 \
  remnawave remnawave-db remnawave-redis \
  remnawave-subscription-page remnanode
do
  if [[ "$(docker inspect -f '{{.State.Running}}' "${container}" 2>/dev/null || printf 'false')" == "true" ]]; then
    printf 'container_ok=%s\n' "${container}"
  else
    printf 'container_failed=%s\n' "${container}"
    container_failed=1
  fi
done
if (( container_failed == 0 )); then
  printf 'containers=11/11\n'
else
  add_incident "One or more required containers are not running. Impact: production service may be partially down."
fi

rm -f /tmp/alanet-client-subscription /tmp/alanet-client-subscription.decoded
