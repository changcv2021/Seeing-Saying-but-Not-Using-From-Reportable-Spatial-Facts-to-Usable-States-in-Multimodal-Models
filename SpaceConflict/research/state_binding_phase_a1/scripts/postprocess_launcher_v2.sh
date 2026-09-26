#!/usr/bin/env bash
# CPU-only orchestration of existing A1 steps. No core inference.
set -euo pipefail
umask 0007
code='./SpaceConflict/research/state_binding_phase_a1'
result=0
for task in calibrate prepare_review present; do
  if bash "$code/scripts/job_launcher_v2.sh" "$task" "$@"; then
    :
  else
    result=$?
    printf 'A1 postprocess stopped at %s with exit %s; preserving evidence and refreshing status.\n' "$task" "$result"
    break
  fi
done
if bash "$code/scripts/job_launcher_v2.sh" status_report "$@"; then
  :
else
  report_result=$?
  if [[ "$result" == 0 ]]; then result=$report_result; fi
fi
exit "$result"
