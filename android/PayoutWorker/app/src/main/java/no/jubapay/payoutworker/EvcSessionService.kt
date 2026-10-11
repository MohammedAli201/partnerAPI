package no.jubapay.payoutworker

import android.app.*
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*
import no.jubapay.payoutworker.device.RuntimeEvcSession

/** One foreground execution loop. Process death quarantines attempts; it never resends them. */
class EvcSessionService:Service() {
 private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
 private var task:Job?=null
 private val g get()=(application as WorkerApplication).graph
 override fun onBind(intent:Intent?)=null
 override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
  if(!g.backend.enrolled()||!g.providerPin.configured()||g.vault.get("evc-auto-enabled")=="false"){stopSelf();return START_NOT_STICKY}
  if(task?.isActive==true)return START_STICKY
  val nm=getSystemService(NotificationManager::class.java)
  if(Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(NotificationChannel("evc-worker","EVC payment worker",NotificationManager.IMPORTANCE_LOW))
  val open=PendingIntent.getActivity(this,0,Intent(this,MainActivity::class.java),PendingIntent.FLAG_IMMUTABLE)
  startForeground(19,NotificationCompat.Builder(this,"evc-worker").setSmallIcon(android.R.drawable.stat_notify_sync)
   .setContentTitle("Automatic EVC payment worker").setContentText("Waiting for backend payouts; one USSD session at a time")
   .setOngoing(true).setContentIntent(open).build())
  task=scope.launch {
   g.sessionRunning.value=true
   try {
    g.recovered.await();g.sms.stop()
    var configured=false
    while(isActive&&g.vault.get("evc-auto-enabled")!="false") {
     try {
      if(!configured) {
       val subscription=RuntimeEvcSession.subscription(this@EvcSessionService)
       g.providerPin.bindToSubscription(subscription)
       g.backend.configureEvc(subscription);g.engine.start();configured=true
      }
      g.engine.cycle()
      g.status.value="EVC worker: ${g.engine.state.value}. Backend payouts execute automatically when READY."
     }catch(e:CancellationException){throw e}
     catch(e:Exception){g.status.value="EVC worker blocked: ${e.message?.takeIf{it.matches(Regex("[A-Z_0-9]+"))}?:"check enrollment, Hormuud SIM and phone permissions"}"}
     delay(5_000)
    }
   }finally{g.sessionRunning.value=false;stopForeground(STOP_FOREGROUND_REMOVE);stopSelf()}
  }
  return START_STICKY
 }
 override fun onDestroy(){scope.cancel();super.onDestroy()}
}
