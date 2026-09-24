#!/usr/bin/env bash
# Adds a dedicated swap file for this VPS without changing an existing swap.
set -euo pipefail

SWAP_FILE="/swapfile-document-intake"
SWAP_SIZE="${1:-2G}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bu skripti root istifadəçisi ilə başladın."
  exit 1
fi

if swapon --show=NAME --noheadings | grep -Fxq "${SWAP_FILE}"; then
  echo "Əlavə swap artıq aktivdir: ${SWAP_FILE}"
  swapon --show
  exit 0
fi

if [[ -e "${SWAP_FILE}" ]]; then
  echo "${SWAP_FILE} artıq mövcuddur, təhlükəsizlik üçün dəyişdirilmədi."
  exit 1
fi

fallocate -l "${SWAP_SIZE}" "${SWAP_FILE}"
chmod 600 "${SWAP_FILE}"
mkswap "${SWAP_FILE}"
swapon "${SWAP_FILE}"

if ! grep -Fqx "${SWAP_FILE} none swap sw 0 0" /etc/fstab; then
  echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
fi

sysctl -w vm.swappiness=10
if ! grep -Fqx "vm.swappiness=10" /etc/sysctl.conf; then
  echo "vm.swappiness=10" >> /etc/sysctl.conf
fi

echo "Swap əlavə edildi və rebootdan sonra da aktiv qalacaq:"
free -h
