package no.jubapay.payoutworker

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.telephony.SubscriptionManager
import android.telephony.TelephonyManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import java.util.UUID
import org.json.JSONObject
import kotlin.coroutines.resume

/** Operator-triggered, single USSD request. Never participates in payout settlement. */
data class UssdDiagnostic(val id:String,val command:String,val status:String,val response:String?,val expires:Long)

private fun diagnostic(j:JSONObject)=UssdDiagnostic(j.getString("test_id"),j.getString("command"),
 j.getString("status"),if(j.isNull("response"))null else j.optString("response"),j.getLong("expires_at"))

private fun UssdDiagnostic.json()=JSONObject().put("test_id",id).put("command",command)
 .put("status",status).put("response",response?:JSONObject.NULL).put("expires_at",expires)

private suspend fun prepareDiagnostic(vm:WorkerViewModel,recipient:String):UssdDiagnostic {
 val existing=vm.g.vault.get("ussd-request")?.let{JSONObject(it)}
 val request=existing?:JSONObject().put("id",UUID.randomUUID().toString()).put("recipient",recipient)
 check(request.getString("recipient")==recipient) {"Finish or clear the previous test first."}
 vm.g.vault.put("ussd-request",request.toString())
 val remote=diagnostic(vm.g.backend.standaloneUssdInstruction(request.getString("id"),recipient))
 if(remote.status!="REQUESTED")return remote
 // A previous request has no proven result. Upload cached evidence or UNKNOWN;
 // never send it again after a crash, timeout or lost response.
 val saved=vm.g.vault.get("manual-ussd-test")?.let{diagnostic(JSONObject(it))}
 val result=if(saved!=null && saved.id==remote.id && saved.status in setOf("RESPONDED","FAILED","UNKNOWN"))saved
  else remote.copy(status="UNKNOWN",response="Request was already issued; no automatic retry.")
 vm.g.vault.put("manual-ussd-test",result.json().toString())
 vm.g.backend.manualUssdResult(result.id,result.status,result.response)
 return result
}

private suspend fun modemRequest(context:Context,command:String):Pair<String,String> {
 if(Build.VERSION.SDK_INT<26)return "FAILED" to "Android 8 or later is required."
 if(context.checkSelfPermission(Manifest.permission.CALL_PHONE)!=PackageManager.PERMISSION_GRANTED)
  return "FAILED" to "Phone permission is required."
 val subscription=SubscriptionManager.getDefaultVoiceSubscriptionId()
 if(!SubscriptionManager.isValidSubscriptionId(subscription))return "FAILED" to "Select a default call SIM in Android settings."
 val manager=context.getSystemService(TelephonyManager::class.java).createForSubscriptionId(subscription)
 return try {
  withTimeout(30_000) {
   suspendCancellableCoroutine { continuation ->
    manager.sendUssdRequest(command,object:TelephonyManager.UssdResponseCallback() {
     override fun onReceiveUssdResponse(t:TelephonyManager,request:String,response:CharSequence) {
      if(continuation.isActive)continuation.resume("RESPONDED" to response.toString().take(2000))
     }
     override fun onReceiveUssdResponseFailed(t:TelephonyManager,request:String,failureCode:Int) {
      if(continuation.isActive)continuation.resume("FAILED" to "Carrier/Android failure code: $failureCode")
     }
    },Handler(Looper.getMainLooper()))
   }
  }
 } catch(_:TimeoutCancellationException) { "UNKNOWN" to "No carrier response within 30 seconds; request will not be retried." }
 catch(_:SecurityException) { "FAILED" to "Android denied access to the selected SIM." }
 catch(_:UnsupportedOperationException) { "FAILED" to "USSD is not supported by this phone/SIM." }
}

private suspend fun executeDiagnostic(context:Context,vm:WorkerViewModel,test:UssdDiagnostic):UssdDiagnostic {
 check(test.status=="CREATED" && System.currentTimeMillis()<test.expires) {"Expired or previously issued test."}
 check(context.checkSelfPermission(Manifest.permission.CALL_PHONE)==PackageManager.PERMISSION_GRANTED) {"Phone permission required."}
 val requested=test.copy(status="REQUESTED",response=null)
 // Persist before both the backend boundary and modem call. A restart cannot replay it.
 vm.g.vault.put("manual-ussd-test",requested.json().toString())
 vm.g.backend.manualUssdResult(test.id,"REQUESTED",null)
 vm.g.engine.pause()
 val result=try {
  val (status,response)=modemRequest(context,test.command)
  test.copy(status=status,response=response)
 } catch(_:Exception) {test.copy(status="UNKNOWN",response="USSD tracking interrupted; request will not be retried.")}
 withContext(NonCancellable) {
  vm.g.vault.put("manual-ussd-test",result.json().toString())
  vm.g.backend.manualUssdResult(result.id,result.status,result.response)
 }
 return result
}

@Composable fun ManualUssdTestCard(vm:WorkerViewModel) {
 val context=LocalContext.current
 val scope=rememberCoroutineScope()
 var recipient by remember {mutableStateOf(vm.g.vault.get("ussd-request")?.let{JSONObject(it).getString("recipient")}?:"615738865")}
 var test by remember {mutableStateOf<UssdDiagnostic?>(null)}
 var busy by remember {mutableStateOf(false)}
 var confirm by remember {mutableStateOf(false)}
 var message by remember {mutableStateOf("")}
 val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
  message=if(granted)"Phone permission granted. Review the test and press Run." else "Phone permission is required for a USSD test."
 }
 Card(Modifier.fillMaxWidth()) {Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
  Text("Real SIM USSD test",style=MaterialTheme.typography.titleMedium)
  Text("Hubaal sends the instruction. Your phone runs it on the default call SIM and reports the actual carrier response.")
  OutlinedTextField(recipient,{recipient=it.filter(Char::isDigit).take(9)},enabled=!busy&&vm.g.vault.get("ussd-request")==null,label={Text("Somali mobile number (9 digits)")})
  Button(enabled=recipient.length==9&&!busy,onClick={scope.launch {
   busy=true;vm.touch()
   try {test=prepareDiagnostic(vm,recipient);message="Test loaded from Hubaal."}
   catch(_:Exception){message="Could not load/save the test. Check the backend connection; no USSD retry."}
   finally {busy=false}
  }}) {Text("Load USSD test from backend")}
  test?.let {t ->
   Text(t.command)
   Text("USSD status: ${t.status}")
   t.response?.let {Text(it)}
   if(t.status in setOf("RESPONDED","FAILED","UNKNOWN")) TextButton(enabled=!busy,onClick={vm.g.vault.remove("ussd-request");test=null;message="Ready for a new operator-requested test."}) {Text("New test")}
   if(t.status=="CREATED")Button(enabled=!busy,onClick={
    vm.touch()
    if(Build.VERSION.SDK_INT<26)message="Android 8 or later is required."
    else if(context.checkSelfPermission(Manifest.permission.CALL_PHONE)!=PackageManager.PERMISSION_GRANTED)
     permission.launch(Manifest.permission.CALL_PHONE)
    else confirm=true
   }) {Text("Run USSD test on default SIM")}
  }
  if(message.isNotBlank())Text(message)
 }}
 if(confirm)AlertDialog(onDismissRequest={confirm=false},title={Text("Send this USSD request?")},
  text={Text("${test?.command}\nUses your default call SIM. Review any carrier prompts yourself. This diagnostic does not establish payment success.")},
  dismissButton={TextButton(onClick={confirm=false}){Text("Cancel")}},
  confirmButton={TextButton(onClick={
   confirm=false
   scope.launch {
    busy=true;vm.touch()
    try {test=executeDiagnostic(context,vm,test!!);message="Carrier result saved in Hubaal."}
    catch(_:Exception){message="Result pending or test expired. Press Load to recover reporting; no automatic USSD retry."}
    finally {busy=false}
   }
  }){Text("Send USSD")}})
}
