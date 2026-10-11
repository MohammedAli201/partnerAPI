"""Enrollment and controls for existing Android worker devices. No synthetic provisioning."""
import argparse
import json
from uuid import UUID

import backend_core as c
from phone_worker import device_control, enabled, enrollment_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', default='local-phone-operator')
    commands = parser.add_subparsers(dest='command', required=True)
    code = commands.add_parser('code')
    code.add_argument('--device', type=UUID, required=True)
    commands.add_parser('devices')
    control = commands.add_parser('control')
    control.add_argument('--device', type=UUID, required=True)
    control.add_argument('--action', required=True, choices=['pause', 'resume', 'drain', 'undrain', 'revoke', 'unquarantine'])
    args = parser.parse_args()
    from database import SessionLocal
    with SessionLocal.begin() as db:
        if args.command == 'code':
            result = enrollment_code(db, args.device, args.actor)
        elif args.command == 'control':
            enabled()
            result = device_control(db, args.device, args.action, args.actor)
        else:
            result = [dict(row) for row in c.run(db, '''SELECT d.id,d.worker_id,d.wallet_id,d.provider,d.network,d.quarantined,
                f.paused,f.drain,f.revoked,f.last_seen_at,f.state
                FROM payout_devices d JOIN payment_workers w ON w.id=d.worker_id
                LEFT JOIN phone_worker_credentials f ON f.device_id=d.id ''').mappings()]
    print(json.dumps(result, default=str, indent=2))


if __name__ == '__main__':
    main()
