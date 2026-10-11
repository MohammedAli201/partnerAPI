package no.jubapay.payoutworker

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import no.jubapay.payoutworker.domain.*

class WorkerViewModel(app: Application): AndroidViewModel(app) {
 val g=(app as WorkerApplication).graph
 val jobs=g.store.changes.stateIn(viewModelScope,SharingStarted.WhileSubscribed(5_000),emptyList())
 val readiness=MutableStateFlow<List<ReadinessCheck>>(emptyList())
 val pending=MutableStateFlow(0)
 val message=MutableStateFlow("")
 val enrolled=MutableStateFlow(g.backend.enrolled())
 val pinConfigured=MutableStateFlow(g.pin.configured())
 private val providerPin=no.jubapay.payoutworker.data.LocalProviderPin(g.vault)
 val providerPinConfigured=MutableStateFlow(providerPin.configured())
 val unlocked=MutableStateFlow(false)
 val busy=MutableStateFlow(false)
 private var lastInteraction=0L
 init {viewModelScope.launch(Dispatchers.IO) {
  if(BuildConfig.PROVISIONED_BACKEND.isNotBlank()) {
   try {
    g.backend.configureProvisionedBackend(BuildConfig.PROVISIONED_BACKEND,BuildConfig.PROVISIONED_ENROLLMENT)
    enrolled.value=g.backend.enrolled()
    g.startAutomaticEvc(app)
    message.value=if(enrolled.value)"HTTPS backend connected; existing enrollment retained"else"Device enrollment needs provisioning"
   } catch(_:Exception) {message.value="Automatic HTTPS connection unavailable. Reopen the app when the backend is online."}
  }
  while(isActive) {
   try {readiness.value=g.readiness.checks()+no.jubapay.payoutworker.device.RuntimeEvcSession.setupChecks(getApplication());pending.value=g.store.pending().size} catch(_:Exception){message.value="Local storage or protected settings unavailable"}
   if(unlocked.value && android.os.SystemClock.elapsedRealtime()-lastInteraction>120_000)unlocked.value=false
   delay(3_000)
  }
 }}
 fun touch(){lastInteraction=android.os.SystemClock.elapsedRealtime()}
 fun lock(){unlocked.value=false}
 private fun action(block:suspend()->Unit) {if(busy.value)return;busy.value=true;viewModelScope.launch(Dispatchers.IO) {
  try{block()}catch(_:Exception){message.value="Operation failed safely. Check network, code/PIN and readiness; no automatic payment retry."}finally{busy.value=false}
 }}
 fun setupPin(pin:String,confirm:String)=action {g.pin.setup(pin,confirm);pinConfigured.value=true;unlocked.value=true;touch()}
 fun unlock(pin:String)=action {unlocked.value=g.pin.verify(pin);if(unlocked.value){touch();message.value="Controls unlocked"}else message.value="PIN not accepted or temporarily rate-limited"}
 fun saveProviderPin(pin:String,confirmation:String)=action {
  check(unlocked.value)
  if(pin.length !in 4..12 || pin.any{it !in '0'..'9'} || pin!=confirmation) {
   message.value="EVC PINs must match and contain 4–12 digits";return@action
  }
  providerPin.set(pin.toCharArray(),confirmation.toCharArray())
  g.vault.put("evc-auto-enabled","true");g.startAutomaticEvc(getApplication())
  providerPinConfigured.value=true;touch();message.value="EVC payment PIN saved securely on this phone"
 }
 fun enroll(url:String,code:String)=action {check(unlocked.value);g.backend.enroll(url,code);enrolled.value=true;message.value="Enrolled; waiting for EVC readiness";g.startAutomaticEvc(getApplication());touch()}

 fun resumeEvc(){if(unlocked.value){g.vault.put("evc-auto-enabled","true");g.startAutomaticEvc(getApplication());touch()}}
 fun pause(){if(unlocked.value){g.engine.pause();touch();message.value="Paused: no new submissions; existing confirmation tracking continues"}}
 fun drain(){if(unlocked.value){g.engine.drain();touch();message.value="Draining: no new work; tracking and uploads continue"}}
 fun emergency(){g.vault.put("evc-auto-enabled","false");g.sms.stop();g.engine.emergencyStop();message.value="Stop requested: no new payments or SMS; current result tracking continues"}
 fun reconcile()=action {check(unlocked.value);g.engine.reconcile();message.value="Reconciliation requested; only backend-audited evidence can resolve uncertainty";touch()}
}
