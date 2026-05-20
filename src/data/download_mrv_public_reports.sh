#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RAW_DIR="${ROOT_DIR}/data/raw/mrv"
TODAY="${TODAY:-2026-05-20}"
BASE_URL="https://mrv.emsa.europa.eu"
COOKIE_FILE="${RAW_DIR}/.mrv_cookies.txt"

mkdir -p "${RAW_DIR}"

curl -L -sS -c "${COOKIE_FILE}" "${BASE_URL}/" -o "${RAW_DIR}/portal-index-${TODAY}.html"

curl -L -sS -b "${COOKIE_FILE}" -H "Accept: application/json" \
  "${BASE_URL}/api/public-emission-report/downloadable-files" \
  -o "${RAW_DIR}/downloadable-files-${TODAY}.json"

curl -L -sS -b "${COOKIE_FILE}" -H "Accept: application/json" \
  "${BASE_URL}/api/public-emission-report/reporting-periods" \
  -o "${RAW_DIR}/reporting-periods-${TODAY}.json"

curl -L -sS -b "${COOKIE_FILE}" -H "Accept: application/json" \
  "${BASE_URL}/api/public-emission-report/configuration" \
  -o "${RAW_DIR}/configuration-${TODAY}.json"

jq -r '.results[] | [.reportingPeriod, .version, (.fileName | gsub(" "; "_") | gsub("[^A-Za-z0-9_.-]"; "_"))] | @tsv' \
  "${RAW_DIR}/downloadable-files-${TODAY}.json" |
while IFS=$'\t' read -r year version file_name; do
  out="${RAW_DIR}/${file_name}.xlsx"
  if [[ -s "${out}" ]]; then
    echo "exists ${out}"
    continue
  fi

  echo "downloading ${year} version ${version} -> ${out}"
  curl -L -sS -b "${COOKIE_FILE}" -H "Accept: */*" \
    "${BASE_URL}/api/public-emission-report/reporting-period-document/binary/${year}/${version}" \
    -o "${out}"
done

find "${RAW_DIR}" -maxdepth 1 -type f ! -name "SHA256SUMS" ! -name ".mrv_cookies.txt" -print |
  sort |
  xargs shasum -a 256 > "${RAW_DIR}/SHA256SUMS"
