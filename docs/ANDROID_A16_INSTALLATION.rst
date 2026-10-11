Galaxy A16 standalone installation investigation
===============================================

Scope and evidence
------------------

The affected device is Samsung Galaxy A16 SM-A165F/DSB. No A16 is connected to
this workstation. The user reports installing the earlier package on the A16,
but the app now reports connection unavailable. That is distinct from a package
installer failure; its exact cause still requires device evidence.

The earlier APK is signed with a valid APK v2 signature and the local Android
debug certificate. Its merged manifest is debuggable, permits cleartext traffic,
and includes Compose preview/test activities. It has package
``no.jubapay.payoutworker``, minSdk 24 and targetSdk 37. There is no identified
evidence that targetSdk 37 caused installation failure. No target/min SDK change
was made. Installer policy, a conflicting installed signer, incomplete file
transfer and device-specific errors remain possibilities, not established causes.

Changes
-------

* Added ``directInstall`` APK build type: non-debuggable, no debug dependencies,
  release library variants, no shrinking/optimization. Avoiding shrinking keeps
  the existing dynamically accessed worker and persistence code intact.
* Kept the previous local testing signer for upgrade compatibility. This is
  explicitly a signed testing distribution, not a production signing identity.
  Changing the signer would prevent an ordinary update over the old signed app.
* Increased versionCode to 2 and versionName to 1.1 to identify the update.
* Explicitly disabled ABI splits; the output is a single standalone APK. Native
  packaging remains unchanged. All supplied ABIs are retained.
* The distribution inherits the main manifest's HTTPS-only policy and disabled
  backups. The debug manifest override and debug Compose activities are absent.
  All original permissions, worker components, SMS services, USSD/accessibility
  service, PIN storage and API code remain present.
* Built with the newly supplied ``PAYOUT_BACKEND_URL``. This is build-time
  provisioning, not an API payload change. Existing enrollment is retained when
  installing an update. No shared enrollment credential is embedded.
* Added ``development_support/validate_android_apk.py`` to repeat signature,
  previous-signer comparison, 16 KB/native and 4-byte ZIP alignment, ZIP integrity,
  package/SDK/ABI and merged-manifest checks without installing the app.

Build and validate
------------------

Set ``ANDROID_HOME`` and ``PAYOUT_BACKEND_URL`` for the intended backend. Run::

    gradlew.bat clean :domain:test :app:assembleDirectInstall --no-configuration-cache

The APK is ``android/PayoutWorker/app/build/outputs/apk/directInstall/app-directInstall.apk``.
Use the validator with this APK, the previous APK, Android build-tools, the
directInstall merged manifest and a JSON report destination. The validator
executes ``apksigner verify --verbose --print-certs`` and
``zipalign -c -P 16 -v 4``. The generated report captures command output and SHA-256.

Validation of the delivered artifact
------------------------------------

The clean build and lint-vital tasks completed successfully. All 24 domain tests
passed. The standalone APK is 8,904,382 bytes and contains arm64-v8a,
armeabi-v7a, x86 and x86_64 libraries. Its APK v2 signature verifies; the signing
certificate matches the previous APK (SHA-256
``e581ca3fc11140428299b33ee3ad2e04496394428cd2da1f756a48a9ccc18eb5``).
ZIP integrity and ``zipalign -c -P 16 -v 4`` passed. The validator confirmed
unchanged permissions, package and SDK levels, absent debug/testOnly/split flags,
and retained SMS/accessibility components.

Artifact SHA-256::

    b55f213e7f7a56c4d8c1f1003d566c41edcaecaf62c57b6a0d2b65e46df3c2ad

The backend health endpoint returned healthy/database connected. The APK was
downloaded through the new HTTPS tunnel and its hash matched the local artifact::

    https://7483-2a05-9cc2-23-1e1f-7dee-6b49-906a-1747.ngrok-free.app/static/PayoutWorker-A16-v1.1.apk

This URL needs the backend and ngrok tunnel to remain running. The build embeds
that backend address and an empty enrollment-code field. A newly installed,
unenrolled A16 still requires its own device enrollment; credentials from the A53
are not included in this APK. Detailed validation output is saved in the local
Downloads file ``PayoutWorker-A16-validation.json``. No real-device installation
was performed for this artifact.

Real-device checks still required
--------------------------------

Download the complete APK on the A16 and install it as an update through its
package installer. Keep app data and enrollment; do not uninstall as a default
troubleshooting step. Record exact errors if installation fails, Android/One UI
version, and whether a differently signed package is already installed.
Check unknown-source permission for the app opening the APK, and whether Samsung
Auto Blocker or device management is preventing installation. These are user
device settings and cannot be changed by APK packaging.

After installation, confirm version 1.1, backend health reachability from the A16,
retained enrollment, encrypted settings and permission prompts. Verify actual
SMS execution/status uploads and USSD diagnostics on the device. Automatic real
payment dispatch/PIN submission remains pending; this packaging change does not
enable it. Passing static validation does not prove successful A16 installation
or runtime operation.

Primary references
------------------

Android signing/update identity:
https://developer.android.com/studio/publish/app-signing

Samsung Auto Blocker installation policy:
https://www.samsung.com/ph/support/mobile-devices/protect-your-galaxy-device-with-the-new-auto-blocker-feature/
