# Validation

Run `./gradlew :domain:test :app:assembleDebug :data:assembleDebugAndroidTest`.
Domain tests check instruction validation, one active slot and recovery. Android
instrumentation sources check persistent Room boundaries, encryption, outbox
replay, concurrent assignment and operator PIN throttling. Building their APK
does not execute instrumentation on a physical phone.

The Hubaal backend test suite covers automatic payment-to-SMS admission, request
replay, worker authentication, concurrent claims, lease expiry, UNKNOWN handling,
late receipts and exactly-once partner debit/test fee recognition.

For a physical test, enable the enrolled worker and submit an authorized payment
through Insomnia. Inspect `GET /payouts/{id}` for the linked SMS status, and the
Earnings page with Activity set to Simulation / test. No mock backend is required.
