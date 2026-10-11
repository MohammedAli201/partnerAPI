package no.jubapay.payoutworker

import android.content.Intent
import android.content.ActivityNotFoundException
import android.net.Uri
import androidx.compose.ui.platform.LocalContext
import android.Manifest
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.*
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import no.jubapay.payoutworker.domain.*
import no.jubapay.payoutworker.ui.theme.PayoutWorkerTheme

class MainActivity: ComponentActivity() {
 private val notificationPermission=registerForActivityResult(ActivityResultContracts.RequestPermission()){}
 override fun onCreate(savedInstanceState:Bundle?) {
  super.onCreate(savedInstanceState)
  window.addFlags(WindowManager.LayoutParams.FLAG_SECURE or WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
  setContent {PayoutWorkerTheme {WorkerScreen(requestNotifications={if(Build.VERSION.SDK_INT>=33)notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)})}}
 }
 override fun onResume() {
  super.onResume()
  (application as WorkerApplication).graph.startAutomaticEvc(this)
  val sms=(application as WorkerApplication).graph.sms
  if(sms.enabled() && checkSelfPermission(Manifest.permission.SEND_SMS)==android.content.pm.PackageManager.PERMISSION_GRANTED)
   androidx.core.content.ContextCompat.startForegroundService(this,Intent(this,SmsSessionService::class.java))
 }
}
@Composable fun WorkerScreen(requestNotifications:()->Unit,vm:WorkerViewModel=viewModel()) {
 val enrolled by vm.enrolled.collectAsState();val configured by vm.pinConfigured.collectAsState();val unlocked by vm.unlocked.collectAsState()
 val jobs by vm.jobs.collectAsState();val checks by vm.readiness.collectAsState();val pending by vm.pending.collectAsState()
 val message by vm.message.collectAsState();val status by vm.g.status.collectAsState();val state by vm.g.engine.state.collectAsState()
 val busy by vm.busy.collectAsState();val running by vm.g.sessionRunning.collectAsState()
 var pin by remember{mutableStateOf("")};var confirm by remember{mutableStateOf("")}
 var url by remember{mutableStateOf(BuildConfig.PROVISIONED_BACKEND.ifBlank{if(BuildConfig.DEBUG)"http://10.0.2.2:8000"else"https://"})};var code by remember{mutableStateOf("")}
 var details by remember{mutableStateOf(false)}
 Scaffold {padding->Column(Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
  Text("Payout Worker",style=MaterialTheme.typography.headlineMedium)
  Surface(color=MaterialTheme.colorScheme.tertiaryContainer,shape=MaterialTheme.shapes.medium) {
   Text("AUTOMATIC EVC PAYOUT WORKER",Modifier.fillMaxWidth().padding(14.dp),style=MaterialTheme.typography.titleMedium)
  }
  Text("$state • ${if(running)"Session active"else"Session stopped"}",style=MaterialTheme.typography.titleLarge)
  Text(status)
  if(message.isNotBlank())Text(message,color=MaterialTheme.colorScheme.primary)
  if(!configured || !unlocked) {
   Text(if(!configured)"Set your operator PIN"else"Operator controls locked",style=MaterialTheme.typography.titleMedium)
   Text("6–12 digits. This is separate from provider PINs. Controls lock after 2 minutes; payment tracking continues.")
   OutlinedTextField(pin,{pin=it.take(12)},label={Text("Operator PIN")},visualTransformation=PasswordVisualTransformation(),keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.NumberPassword),modifier=Modifier.fillMaxWidth())
   if(!configured)OutlinedTextField(confirm,{confirm=it.take(12)},label={Text("Confirm PIN")},visualTransformation=PasswordVisualTransformation(),keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.NumberPassword),modifier=Modifier.fillMaxWidth())
   Button(onClick={if(configured)vm.unlock(pin)else vm.setupPin(pin,confirm);pin="";confirm=""},enabled=!busy){Text(if(configured)"Unlock controls"else"Save PIN")}
  } else {
   ProviderPinCard(vm)
   if(enrolled) {EvcWorkerCard(vm);SmsQueueCard(vm);ManualUssdTestCard(vm)}
   if(!enrolled) {
    Text("Enroll this phone",style=MaterialTheme.typography.titleMedium)
    OutlinedTextField(url,{url=it;vm.touch()},label={Text("Backend URL")},modifier=Modifier.fillMaxWidth())
    OutlinedTextField(code,{code=it;vm.touch()},label={Text("Single-use enrollment code")},visualTransformation=PasswordVisualTransformation(),modifier=Modifier.fillMaxWidth())
    Button(onClick={vm.enroll(url,code);code=""},enabled=!busy){Text("Enroll")}
    Text("Use the provisioned HTTPS backend and a single-use enrollment code.")
   } else {
    val config=vm.g.backend.config()
    Text("Device: ${config.deviceId}\nUSSD runs on your Android default call SIM.")
    Text("Ready phones claim backend payouts automatically, one at a time. Keep the worker phone unlocked.")
    OutlinedButton(onClick={vm.reconcile()},enabled=!busy){Text("Request reconciliation")}
   }
   TextButton(onClick={vm.lock()}){Text("Lock controls")}
  }
  OutlinedButton(onClick={vm.emergency()}){Text("Emergency stop new submissions")}
  HorizontalDivider()
  Text("Readiness",style=MaterialTheme.typography.titleLarge)
  checks.forEach {Text("${if(it.ready)"READY"else"BLOCKED"} • ${it.name}\n${it.detail}")}
  TextButton(onClick=requestNotifications){Text("Allow session notifications")}
  Text("Pending uploads: $pending • Local history limited to 1,000 attempts")
  val unresolved=jobs.any{it.phase.uncertain}
  if(unresolved)Text("QUARANTINED: unresolved attempt. Do not retry payment. Backend reconciliation required.",color=MaterialTheme.colorScheme.error)
  val current=jobs.firstOrNull{!it.phase.confirmed}
  if(current!=null)Text("Current: ${current.phase}\n${current.assignment.maskedRecipient} • elapsed since update: ${(System.currentTimeMillis()-current.updatedAt)/1000}s")
  Text("Jobs: Confirmed: ${jobs.count{it.phase==Phase.CONFIRMED_SUCCESS}} • Not paid: ${jobs.count{it.phase==Phase.CONFIRMED_NOT_PAID}} • Unknown: ${jobs.count{it.phase.uncertain}}")
  Text("Recent jobs",style=MaterialTheme.typography.titleLarge)
  jobs.take(20).forEach {a->Card(Modifier.fillMaxWidth()){Column(Modifier.padding(12.dp)) {
   Text(a.assignment.maskedRecipient+" • "+a.phase.name)
   Text("${a.assignment.amountMinor} minor units ${a.assignment.currency} • ${if(a.resultAcknowledged)"Result acknowledged"else"Reporting pending"}")
   Text("Attempt ${a.assignment.attemptId.take(12)}")
  }}}
  TextButton(onClick={details=!details}){Text("Settings and redacted diagnostics")}
  if(details)Text("Version ${BuildConfig.VERSION_NAME} • automatic EVC worker\n${vm.g.readiness.simDiagnostics()}\nCarrier recipient, name and amount must match before PIN submission.\nUnknown outcomes require reconciliation; payments are never automatically resubmitted.\nScreenshots and backup are disabled.\nBackend: ${if(enrolled)vm.g.backend.baseUrl()else"not enrolled"}")
 }}
}
@Composable private fun ProviderPinCard(vm:WorkerViewModel) {
 val saved by vm.providerPinConfigured.collectAsState()
 val busy by vm.busy.collectAsState()
 var pin by remember {mutableStateOf("")}
 var confirmation by remember {mutableStateOf("")}
 Card(Modifier.fillMaxWidth()) {Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
  Text("EVC payment PIN",style=MaterialTheme.typography.titleMedium)
  Text(if(saved)"A payment PIN is saved on this phone. Enter both fields to replace it."else"Enter this SIM's EVC payment PIN and confirm it.")
  Text("Stored encrypted on this phone. Separate from your operator PIN. Update it if you change SIM. Automatic execution starts when enrollment and phone readiness checks pass.")
  OutlinedTextField(pin,{pin=it.filter(Char::isDigit).take(12);vm.touch()},label={Text("EVC payment PIN")},visualTransformation=PasswordVisualTransformation(),keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.NumberPassword),modifier=Modifier.fillMaxWidth())
  OutlinedTextField(confirmation,{confirmation=it.filter(Char::isDigit).take(12);vm.touch()},label={Text("Confirm EVC payment PIN")},visualTransformation=PasswordVisualTransformation(),keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.NumberPassword),modifier=Modifier.fillMaxWidth())
  Button(onClick={vm.saveProviderPin(pin,confirmation);pin="";confirmation=""},enabled=!busy&&pin.isNotBlank()&&confirmation.isNotBlank()){Text(if(saved)"Update EVC PIN"else"Save EVC PIN")}
 }}
}

@Composable private fun EvcWorkerCard(vm:WorkerViewModel) {
 val context=LocalContext.current
 val launcher=androidx.activity.compose.rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
  vm.resumeEvc()
 }
 Card(Modifier.fillMaxWidth()) {Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
  Text("Automatic EVC payouts",style=MaterialTheme.typography.titleMedium)
  Text("Save the EVC payment PIN, enable EVC accessibility, allow phone and SIM permissions, and keep the phone unlocked. The worker then waits for backend jobs.")
  Button(onClick={
   val permissions=mutableListOf(Manifest.permission.CALL_PHONE,Manifest.permission.READ_PHONE_STATE)
   if(Build.VERSION.SDK_INT>=33)permissions.add(Manifest.permission.POST_NOTIFICATIONS)
   launcher.launch(permissions.toTypedArray())
  }){Text("Allow permissions and resume worker")}
  OutlinedButton(onClick={context.startActivity(Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS))}){Text("EVC accessibility settings")}
 }}
}
