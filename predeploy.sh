#!/bin/sh
# Run before deploying any model or pipeline change. There is no CI in this repo;
# this script IS the gate. It must exit 0 before `ollama create` / a pipeline edit ships.
set -e
cd "$(dirname "$0")"
PY=./capital-call-env/bin/python

echo "== import check =="
$PY -c "import verification.severity, verification.verdict, verification.rules, \
verification.report, verification.pipeline, verification.demo_pipeline, verification.evaluate, \
approvals.model, approvals.store, approvals.service, approvals.notify, \
cash_planning.core, cash_planning.narrative, \
forecasting.core, forecasting.narrative, \
k1_routing.core, k1_routing.store, k1_routing.service, agents.app, demo; \
print('  all modules import OK')"

echo "== regression tests (verdict multi-label/severity/order-independence + approvals state machine) =="
$PY -m pytest tests/ -q

echo
echo "predeploy OK"
