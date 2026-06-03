#!/usr/bin/env bash
# Generate a new service skeleton under a project's services root, matching the
# standard file set: route registration, controller, service layer, data access,
# error handling, logging, a contract README stub, and a runnable smoke test.
# This is a portable Node/Express-style default template. When the project uses a
# different stack or convention, generate by hand from the cataloged conventions
# instead and raise spgr-escalate so a matching template can be added.
#
# Usage: scaffold-service.sh <service-name> <services-root>
# Example: scaffold-service.sh billing ./src/services
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: scaffold-service.sh <service-name> <services-root>" >&2
  exit 2
fi

name="$1"
root="$2"

case "$name" in
  *[!a-z0-9-]*|"" )
    echo "error: service name must be lowercase-kebab (a-z, 0-9, -): $name" >&2
    exit 2 ;;
esac

dir="$root/$name"
if [ -e "$dir" ]; then
  echo "error: service directory already exists: $dir" >&2
  echo "a new service must not overwrite an existing one; escalate if the name collides" >&2
  exit 2
fi

mkdir -p "$dir"

cat > "$dir/routes.js" <<EOF
// $name routes. Registered explicitly into the project router.
const express = require('express');
const controller = require('./controller');
const router = express.Router();

router.get('/health', controller.health);

module.exports = router;
EOF

cat > "$dir/controller.js" <<EOF
// $name controller. Request and response boundary only. No business logic here.
const service = require('./service');
const logger = require('./logger');

async function health(req, res, next) {
  try {
    const status = await service.health();
    res.status(200).json(status);
  } catch (err) {
    logger.error('$name health check failed', { err: err.message });
    next(err);
  }
}

module.exports = { health };
EOF

cat > "$dir/service.js" <<EOF
// $name service layer. Business logic lives here.
async function health() {
  return { service: '$name', status: 'ok' };
}

module.exports = { health };
EOF

cat > "$dir/repository.js" <<EOF
// $name data access layer. Remove this file if the service owns no data.
module.exports = {};
EOF

cat > "$dir/errors.js" <<EOF
// $name error handling. Follows the project error convention.
function errorHandler(err, req, res, next) {
  const status = err.status || 500;
  res.status(status).json({ error: err.message || 'internal error' });
}

module.exports = { errorHandler };
EOF

cat > "$dir/logger.js" <<EOF
// $name structured logging. Replace with the project's shared logger.
function log(level, msg, fields) {
  process.stdout.write(JSON.stringify({ level, msg, service: '$name', ...fields }) + '\n');
}

module.exports = {
  info: (msg, fields) => log('info', msg, fields || {}),
  error: (msg, fields) => log('error', msg, fields || {}),
};
EOF

cat > "$dir/README.md" <<EOF
# $name service

## Purpose

Describe what the $name service does.

## Contract

- Inputs: list the inputs this service accepts.
- Outputs: list the outputs this service produces.
- Failure modes: list how this service fails and how callers should handle it.
EOF

cat > "$dir/smoke.test.js" <<EOF
// $name smoke test. Starts the service and confirms the health check responds.
const service = require('./service');

test('$name health check returns ok', async () => {
  const status = await service.health();
  expect(status.status).toBe('ok');
});
EOF

echo "scaffolded service: $dir"
