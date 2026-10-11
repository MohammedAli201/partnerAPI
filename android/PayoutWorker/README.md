# PayoutWorker

Native Kotlin/Compose Android worker for the Hubaal backend. The working path is
backend payment admission ? one SMS job ? real Android SMS send ? durable result
upload ? development test settlement. Real money-transfer execution remains disabled.

## Build

For a preconfigured package, set `PAYOUT_BACKEND_URL` to the HTTPS backend before
building. On launch the app checks `/health` without credentials and updates its
stored endpoint while preserving existing enrollment. Install over the existing
app; uninstalling or clearing data removes its device credentials. For a new
device, an optional `PAYOUT_ENROLLMENT_CODE` build variable supplies a single-use
enrollment code. Such packages are device-specific and must not be committed or
distributed as a general APK. Expired or consumed codes require provisioning a
new package; enrollment authentication is never disabled.

Install Android SDK 37 and JDK 17, then run:

```powershell
.\gradlew.bat :domain:test :app:assembleDebug :data:assembleDebugAndroidTest
```

The debug APK is `app/build/outputs/apk/debug/app-debug.apk`. Keep `local.properties`,
SDK paths, keystores, generated APKs and build directories out of Git.

## Connect and run

Use the Hubaal backend documented in `../../docs/PAYOUTWORKER.rst` when this project
is checked out under `android/PayoutWorker`. Apply backend migrations, start the
local phone host and issue a single-use enrollment code for an existing device.
For an ADB-connected phone, `adb reverse tcp:8000 tcp:8000` allows backend URL
`http://127.0.0.1:8000`. Otherwise use the reachable PC address.

Install the APK, enroll once, unlock operator controls, grant SMS permission and
choose a default SMS SIM. Enable **Automatic SMS worker** once. It remains waiting
when the queue empties and processes one new backend job at a time. Keep the phone
and backend online. Reopen the app after Android force-stop.

SMS sent and delivery results are separate. A missing sent result holds the queue
and is never automatically resent. Development accounting records successful
SMS tests as SENT and recognizes test fees; it does not transfer money to a wallet.

See [architecture](docs/ARCHITECTURE.md), [security](docs/SECURITY.md) and
[validation](docs/TESTING.md).
