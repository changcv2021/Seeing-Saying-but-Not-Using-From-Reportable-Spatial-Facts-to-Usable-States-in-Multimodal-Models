#!/usr/bin/env bash
set -euo pipefail
repair='./SpaceConflict/research/state_binding_phase_a1/format_repair_v2'
result=0
for task in prepare_review present; do
  if bash "$repair/launch.sh" "$task" "$@"; then
    :
  else
    result=$?
    printf 'Format v2 review step %s failed with exit %s.\n' "$task" "$result"
    break
  fi
done
if bash "$repair/launch.sh" review_status "$@"; then
  :
else
  status_result=$?
  if [[ "$result" == 0 ]]; then result=$status_result; fi
fi
exit "$result"
