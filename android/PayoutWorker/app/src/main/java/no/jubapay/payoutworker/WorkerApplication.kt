package no.jubapay.payoutworker

import android.app.Application
import androidx.room.Room
import androidx.work.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import no.jubapay.payoutworker.data.*
import no.jubapay.payoutworker.device.*
import no.jubapay.payoutworker.domain.*
import java.util.concurrent.TimeUnit

class WorkerApplication: Application() {
 val graph by lazy { AppGraph(this) }
 override fun onCreate() { super.onCreate(); graph }
}
class AppGraph(app: Application) {
 val cipher=KeystoreCipher()
 val vault=Vault(app,cipher)
 val pin=OperatorPin(vault)
 val database=Room.databaseBuilder(app,WorkerDatabase::class.java,"payout-worker.db").build()
 val store=RoomAttemptStore(database,cipher)
 val backend=HttpBackend(vault,DeviceKey(),BuildConfig.DEBUG)
 val sms=SmsQueueWorker(app,backend,vault)
 val readiness=AndroidReadiness(app,backend::enrolled)
 val providerPin=LocalProviderPin(vault)
 val engine=WorkerEngine(store,backend,Evc712Provider(RuntimeEvcSession,providerPin),
  Readiness{readiness.checks()+RuntimeEvcSession.setupChecks(app)},backend::config)
 val sessionRunning=MutableStateFlow(false)
 val status=MutableStateFlow("Enroll this device to begin")
 private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
 val recovered=scope.async {engine.recover()}
 fun startAutomaticEvc(context:android.content.Context) {
  if(!backend.enrolled()||!providerPin.configured()||vault.get("evc-auto-enabled")=="false")return
  if(context.checkSelfPermission(android.Manifest.permission.CALL_PHONE)!=android.content.pm.PackageManager.PERMISSION_GRANTED||
   context.checkSelfPermission(android.Manifest.permission.READ_PHONE_STATE)!=android.content.pm.PackageManager.PERMISSION_GRANTED)return
  try {androidx.core.content.ContextCompat.startForegroundService(context,android.content.Intent(context,EvcSessionService::class.java))}
  catch(_:Exception){status.value="Open the app to resume the automatic EVC worker"}
 }
 init {
  val work=PeriodicWorkRequestBuilder<OutboxUploadWorker>(15,TimeUnit.MINUTES)
   .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
   .setBackoffCriteria(BackoffPolicy.EXPONENTIAL,30,TimeUnit.SECONDS).build()
  WorkManager.getInstance(app).enqueueUniquePeriodicWork("outbox-upload",ExistingPeriodicWorkPolicy.KEEP,work)
 }
}
class OutboxUploadWorker(context: android.content.Context,params: WorkerParameters): CoroutineWorker(context,params) {
 override suspend fun doWork(): Result {
  val g=(applicationContext as WorkerApplication).graph
  return try {g.recovered.await();if(g.backend.enrolled()){g.engine.flush();g.sms.flush()};Result.success()}
  catch(_: WorkerFailure.Authentication){g.engine.pause();g.status.value="Credential expired or revoked: operator action required";Result.failure()}
  catch(_: Exception){Result.retry()}
 }
}
