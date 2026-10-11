package no.jubapay.payoutworker.device

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.os.StatFs
import android.telephony.SubscriptionManager
import android.view.accessibility.AccessibilityManager
import no.jubapay.payoutworker.domain.*

class AndroidReadiness(private val context: Context,private val enrolled: ()->Boolean): Readiness {
 override suspend fun checks(): List<ReadinessCheck> {
  val network=context.getSystemService(ConnectivityManager::class.java)
  val connected=network.getNetworkCapabilities(network.activeNetwork)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)==true
  val battery=context.registerReceiver(null,IntentFilter(Intent.ACTION_BATTERY_CHANGED))
  val level=battery?.getIntExtra(BatteryManager.EXTRA_LEVEL,-1)?:-1
  val scale=battery?.getIntExtra(BatteryManager.EXTRA_SCALE,100)?:100
  val pct=if(level>=0&&scale>0)level*100/scale else -1
  val charging=(battery?.getIntExtra(BatteryManager.EXTRA_PLUGGED,0)?:0)!=0
  val thermal=if(Build.VERSION.SDK_INT>=29)context.getSystemService(PowerManager::class.java).currentThermalStatus else 0
  val free=StatFs(context.filesDir.absolutePath).availableBytes
  val notifications=Build.VERSION.SDK_INT<33||context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED
  return listOf(ReadinessCheck("Network",connected,if(connected)"Network available; backend checked separately" else "No network"),
   ReadinessCheck("Enrollment",enrolled(),if(enrolled())"Device credential available; server validates expiry/revocation" else "Enroll this phone"),
   ReadinessCheck("Storage",free>50L*1024*1024,"${free/1024/1024} MiB free; 50 MiB minimum"),
   ReadinessCheck("Battery",charging||pct>=20,"$pct% • ${if(charging)"charging"else"not charging"}"),
   ReadinessCheck("Thermal",thermal<3,"Thermal status $thermal"),ReadinessCheck("Notifications",notifications,"Session notification permission"),
   ReadinessCheck("Provider compatibility",true,"Real SIM diagnostic: grant Phone permission when running a test"))
 }
 fun simDiagnostics(): String {
  if(context.checkSelfPermission(Manifest.permission.READ_PHONE_STATE)!=PackageManager.PERMISSION_GRANTED)return "Real USSD uses the Android default call SIM; SIM details permission not requested"
  return try {context.getSystemService(SubscriptionManager::class.java).activeSubscriptionInfoList.orEmpty().joinToString {"slot ${it.simSlotIndex}: subscription ${it.subscriptionId}"}.ifBlank{"No active SIM"}}
  catch(_: SecurityException){"SIM details unavailable"}
 }
 fun accessibilityEnabled()=context.getSystemService(AccessibilityManager::class.java).isEnabled
}

/** Integration boundaries only. No USSD codes, payment PINs or remote scripts accepted. */
interface UssdGateway { suspend fun sendVerifiedSingleRequest(subscriptionId: Int, approvedFlowId: String): Evidence }
interface AccessibilityGateway { suspend fun executeVerifiedStep(packageName: String, expectedScreenId: String, semanticActionId: String): Evidence }
class DisabledUssdGateway: UssdGateway {
 override suspend fun sendVerifiedSingleRequest(subscriptionId: Int,approvedFlowId: String): Evidence = throw WorkerFailure.Protocol("USSD_NOT_INTEGRATED")
}
class DisabledAccessibilityGateway: AccessibilityGateway {
 override suspend fun executeVerifiedStep(packageName: String,expectedScreenId: String,semanticActionId: String): Evidence = throw WorkerFailure.Protocol("ACCESSIBILITY_NOT_INTEGRATED")
}
