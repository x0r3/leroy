#!/bin/sh
set -eu

repo_dir="${WORKSPACE}/repo"
known_hosts_file="${WORKSPACE}/.nikicas-hub-known_hosts"
deploy_env_file="${WORKSPACE}/.nikicas-hub.env"
remote_host="${EFFECTIVE_DEPLOY_USER}@${DEPLOY_HOST}"
image_tar_basename="nikicas-hub-${NIKICAS_HUB_IMAGE_TAG}.tar"
remote_image_tar="${DEPLOY_DIR}/.images/${image_tar_basename}"

cleanup() {
  rm -f "${known_hosts_file}" "${known_hosts_file}.tmp" "${deploy_env_file}"
  if [ -n "${NIKICAS_HUB_IMAGE_TAR:-}" ]; then
    rm -f "${NIKICAS_HUB_IMAGE_TAR}"
  fi
}
trap cleanup EXIT INT TERM

cp -- "${KNOWN_HOSTS}" "${known_hosts_file}"
chmod 600 "${known_hosts_file}"

export DEPLOY_ENV_FILE="${deploy_env_file}"
python3 - <<'PY'
import os
import sys

mapping = [
    ("NIKICAS_HUB_IMAGE", "NIKICAS_HUB_IMAGE_REF"),
    ("PUBLIC_ORIGIN", "PUBLIC_ORIGIN"),
    ("ALLOWED_ORIGINS", "ALLOWED_ORIGINS"),
    ("TRAEFIK_HOST_RULE", "TRAEFIK_HOST_RULE"),
    ("ACME_EMAIL", "ACME_EMAIL", False),
    ("ACME_STORAGE_PATH", "ACME_STORAGE_PATH", True),
    ("TRUST_PROXY_HOPS", "TRUST_PROXY_HOPS"),
    ("REQUIRE_HTTPS", None),
    ("DEFAULT_ADMIN_USER", "DEFAULT_ADMIN_USER"),
    ("DEFAULT_ADMIN_LOGIN_SECRET", "DEFAULT_ADMIN_LOGIN_SECRET"),
    ("EVENT_HASH_SALT", "EVENT_HASH_SALT"),
    ("APP_SALT", "APP_SALT"),
]

with open(os.environ["DEPLOY_ENV_FILE"], "w", encoding="utf-8") as handle:
    for item in mapping:
        if len(item) == 2:
            key, env_name = item
            required = True
        else:
            key, env_name, required = item
        value = "true" if env_name is None else os.environ.get(env_name, "")
        if required and not value:
            print(f"ERROR: {key} resolved to an empty value.", file=sys.stderr)
            sys.exit(1)
        if chr(10) in value or chr(13) in value:
            print(f"ERROR: {key} must not contain newlines.", file=sys.stderr)
            sys.exit(1)
        handle.write(f"{key}={value}" + chr(10))
PY
chmod 600 "${deploy_env_file}"

ssh_opts="-i ${SSH_KEY_FILE} -p ${DEPLOY_PORT} -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${known_hosts_file} -o ConnectTimeout=15"

ssh ${ssh_opts} "${remote_host}" "mkdir -p '${DEPLOY_DIR}' '${DEPLOY_DIR}/data' '${DEPLOY_DIR}/react-app/server/public_gallery' '${DEPLOY_DIR}/react-app/server/private_gallery' '${DEPLOY_DIR}/prod' '${DEPLOY_DIR}/.images'"

if [ ! -f "${repo_dir}/prod/docker-compose.yml" ]; then
  echo "ERROR: missing compose file in checked out repo: ${repo_dir}/prod/docker-compose.yml"
  exit 1
fi

rsync -az   -e "ssh ${ssh_opts}"   "${repo_dir}/prod/docker-compose.yml" "${remote_host}:${DEPLOY_DIR}/prod/docker-compose.yml"

rsync -az   -e "ssh ${ssh_opts}"   "${deploy_env_file}" "${remote_host}:${DEPLOY_DIR}/prod/.env"

if [ "${DRY_RUN}" != "true" ]; then
  if [ ! -f "${NIKICAS_HUB_IMAGE_TAR}" ]; then
    echo "ERROR: missing local image archive: ${NIKICAS_HUB_IMAGE_TAR}"
    exit 1
  fi
  rsync -az     -e "ssh ${ssh_opts}"     "${NIKICAS_HUB_IMAGE_TAR}" "${remote_host}:${remote_image_tar}"
fi

ssh ${ssh_opts} "${remote_host}" "sh -s -- '${DEPLOY_DIR}' '${DRY_RUN}' '${ACME_STORAGE_PATH}' '${NIKICAS_HUB_IMAGE_REF}' '${remote_image_tar}'" <<'EOF'
set -eu

deploy_dir="$1"
dry_run="$2"
acme_storage_path="$3"
image_ref="$4"
image_tar="$5"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker command not found on remote host."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  compose_cmd="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd="docker-compose"
else
  echo "ERROR: docker compose (plugin or docker-compose) not found on remote host."
  exit 1
fi

if [ ! -f "${deploy_dir}/prod/docker-compose.yml" ]; then
  echo "ERROR: missing compose file: ${deploy_dir}/prod/docker-compose.yml"
  exit 1
fi

if [ ! -f "${acme_storage_path}" ]; then
  echo "ERROR: Traefik ACME storage file not found on remote host: ${acme_storage_path}"
  exit 1
fi

if [ "${dry_run}" = "true" ]; then
  ${compose_cmd} --project-directory "${deploy_dir}" -f "${deploy_dir}/prod/docker-compose.yml" --env-file "${deploy_dir}/prod/.env" config >/dev/null
  echo "Dry run successful. Compose configuration is valid for ${image_ref}."
  exit 0
fi

if [ ! -f "${image_tar}" ]; then
  echo "ERROR: transferred image archive not found on remote host: ${image_tar}"
  exit 1
fi

docker load -i "${image_tar}"
docker image inspect "${image_ref}" >/dev/null

${compose_cmd} --project-directory "${deploy_dir}" -f "${deploy_dir}/prod/docker-compose.yml" --env-file "${deploy_dir}/prod/.env" config >/dev/null
${compose_cmd} --project-directory "${deploy_dir}" -f "${deploy_dir}/prod/docker-compose.yml" --env-file "${deploy_dir}/prod/.env" up -d --no-build --remove-orphans proxy
${compose_cmd} --project-directory "${deploy_dir}" -f "${deploy_dir}/prod/docker-compose.yml" --env-file "${deploy_dir}/prod/.env" up -d --wait --wait-timeout 180 --no-build --force-recreate --no-deps app

rm -f "${image_tar}"
# Shared Docker images are not globally pruned by Leroy.

echo "Remote deployment finished."
EOF
