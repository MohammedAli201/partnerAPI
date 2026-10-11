# Security

Enrollment uses a single-use code and a device signing key. The app stores backend
credentials and SMS records encrypted with Android Keystore. Operator PIN controls
lock after two minutes; tracking and uploads continue. Provider payment PINs are
not part of SMS execution. Release builds reject plain HTTP.

The real SMS sender requires SEND_SMS permission, a default SMS SIM and explicit
one-time enabling of the automatic worker. The foreground notification exposes
its activity. Emergency stop disables new SMS claims while preserving current
send tracking. UNKNOWN never triggers automatic modem replay.

SMS success proves a successful Android send callback, not a money transfer.
Development test settlement uses separate SMS-test clearing and fee accounts and
reports under simulation/test activity. Production rejects this substitute.
The app's legacy payment adapter only reports existing history and fails closed
on new money-transfer execution.
